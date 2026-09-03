"""x402 payment gate for the paid tier (proposal §7 / §9.1).

Applies to ``GET /v1/agents/{id}/score``, ``GET /v1/provenalt/{id}``, and
``GET /v1/eligibility``. Per request on a gated route:

1. A valid partner ``X-API-Key`` bypasses payment (metered as ``api_key``).
2. If x402 is not configured (no receiving wallet), the call is allowed (metered ``unpaid_open``).
3. Otherwise, without an ``X-PAYMENT`` header a spec-correct **402** is returned (built offline
   from the official x402 SDK schemas); with one, the payment is verified + settled via the
   facilitator (production) and metered with the payer + tx hash.

See ``docs/x402.md`` for the researched protocol and sources.
"""

from __future__ import annotations

import base64
import re
from collections.abc import Awaitable, Callable
from dataclasses import dataclass
from typing import Any

from fastapi import Request, Response
from fastapi.responses import JSONResponse
from provenalt_shared.db import repository as repo
from provenalt_shared.settings import Settings

from provenalt_api import deps

CallNext = Callable[[Request], Awaitable[Response]]

# (method, path regex, endpoint label)
_GATED: list[tuple[str, re.Pattern[str], str]] = [
    ("GET", re.compile(r"^/v1/agents/[^/]+/score$"), "score"),
    ("GET", re.compile(r"^/v1/provenalt/[^/]+$"), "provenalt"),
    ("GET", re.compile(r"^/v1/eligibility$"), "eligibility"),
]


def gated_endpoint(method: str, path: str) -> str | None:
    for m, rx, label in _GATED:
        if method == m and rx.match(path):
            return label
    return None


@dataclass(frozen=True)
class X402Config:
    enabled: bool
    pay_to: str | None
    network: str
    price: str
    facilitator_url: str


def config_from_settings(s: Settings) -> X402Config:
    return X402Config(
        enabled=s.x402_enabled and bool(s.x402_pay_to),
        pay_to=s.x402_pay_to,
        network=s.x402_network,
        price=s.x402_price,
        facilitator_url=s.x402_facilitator_url,
    )


def _price_asset(cfg: X402Config) -> Any:
    from x402.mechanisms.evm.exact import ExactEvmServerScheme

    return ExactEvmServerScheme().parse_price(cfg.price, cfg.network)


def payment_required_body(cfg: X402Config, error: str) -> dict[str, Any]:
    """Build the spec-correct 402 body from the official x402 schemas (offline)."""
    from x402.schemas import PaymentRequired, PaymentRequirements

    asset = _price_asset(cfg)
    requirement = PaymentRequirements(
        scheme="exact",
        network=cfg.network,
        asset=asset.asset,
        amount=asset.amount,
        pay_to=cfg.pay_to,
        max_timeout_seconds=60,
        extra=asset.extra,
    )
    payment_required = PaymentRequired(
        x402_version=1, error=error, accepts=[requirement], extensions={}
    )
    body: dict[str, Any] = payment_required.model_dump(
        by_alias=True, exclude_none=True, mode="json"
    )
    return body


def _factory(request: Request) -> Any:
    factory = getattr(request.app.state, "db_factory", None)
    return factory if factory is not None else deps.session_factory()


def _meter(
    request: Request,
    endpoint: str,
    payer: str,
    kind: str,
    *,
    amount: int = 0,
    asset: str | None = None,
    tx_hash: str | None = None,
) -> None:
    with _factory(request)() as session:
        repo.record_usage_event(
            session,
            endpoint=endpoint,
            method=request.method,
            payer=payer,
            payment_kind=kind,
            amount_atomic=amount,
            asset=asset,
            tx_hash=tx_hash,
        )
        session.commit()


async def x402_gate(request: Request, call_next: CallNext) -> Response:
    label = gated_endpoint(request.method, request.url.path)
    if label is None:
        return await call_next(request)

    cfg: X402Config = request.app.state.x402_config

    # 1) Partner API-key bypass.
    api_key = request.headers.get("x-api-key")
    if api_key:
        with _factory(request)() as session:
            key_label = repo.api_key_label(session, api_key)
        if key_label is not None:
            response = await call_next(request)
            if response.status_code < 400:
                _meter(request, label, payer=f"key:{key_label or 'partner'}", kind="api_key")
            return response

    # 2) x402 not configured — allow (dev/test), but still record usage.
    if not cfg.enabled:
        response = await call_next(request)
        if response.status_code < 400:
            _meter(request, label, payer="open", kind="unpaid_open")
        return response

    # 3) x402 enforcement.
    payment = request.headers.get("x-payment")
    if not payment:
        return JSONResponse(
            payment_required_body(cfg, "X-PAYMENT header is required"), status_code=402
        )
    return await _enforce_paid(request, call_next, cfg, label)


async def _enforce_paid(
    request: Request, call_next: CallNext, cfg: X402Config, label: str
) -> Response:
    """Production path: verify → fulfill → settle via the facilitator. Not exercised offline."""
    try:
        from x402.schemas import PaymentPayload

        server = _resource_server(request, cfg)
        requirements = _requirements(request, cfg)
        raw = base64.b64decode(request.headers["x-payment"])
        payload = PaymentPayload.model_validate_json(raw)

        verify = await server.verify_payment(payload, requirements)
        if not getattr(verify, "is_valid", False):
            return JSONResponse(
                payment_required_body(cfg, "payment verification failed"), status_code=402
            )

        response = await call_next(request)
        settle = await server.settle_payment(payload, requirements)

        asset = _price_asset(cfg)
        _meter(
            request,
            label,
            payer=str(getattr(payload, "payer", "unknown")),
            kind="paid",
            amount=int(asset.amount),
            asset=asset.asset,
            tx_hash=getattr(settle, "transaction", None),
        )
        tx = getattr(settle, "transaction", None)
        if tx:
            response.headers["X-PAYMENT-RESPONSE"] = base64.b64encode(
                settle.model_dump_json().encode()
            ).decode()
        return response
    except Exception:  # noqa: BLE001 — fail safe: never leak internals, ask for payment again
        return JSONResponse(
            payment_required_body(cfg, "payment could not be processed"), status_code=402
        )


def _resource_server(request: Request, cfg: X402Config) -> Any:
    server = getattr(request.app.state, "x402_server", None)
    if server is None:
        from x402.http import FacilitatorConfig, HTTPFacilitatorClient
        from x402.mechanisms.evm.exact import ExactEvmServerScheme
        from x402.server import x402ResourceServer

        facilitator = HTTPFacilitatorClient(FacilitatorConfig(url=cfg.facilitator_url))
        server = x402ResourceServer(facilitator)
        server.register(cfg.network, ExactEvmServerScheme())
        server.initialize()
        request.app.state.x402_server = server
    return server


def _requirements(request: Request, cfg: X402Config) -> Any:
    from x402.http import PaymentOption
    from x402.http.types import RouteConfig

    server = _resource_server(request, cfg)
    config = RouteConfig(
        accepts=[
            PaymentOption(scheme="exact", pay_to=cfg.pay_to, price=cfg.price, network=cfg.network)
        ],
        mime_type="application/json",
    )
    return server.build_payment_requirements(config)[0]

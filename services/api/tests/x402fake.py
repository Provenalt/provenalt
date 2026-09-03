"""A fake x402 facilitator/resource-server for offline paid-path tests (not a test module).

The real verify/settle path talks to a live facilitator and is exercised only in
production. Here we stub the resource server's ``verify_payment`` / ``settle_payment`` so the
gate's paid branch can be exercised offline: valid payment → 200 + metered ``paid`` event,
invalid payment → 402, settlement failure → 402 (result withheld).

The ``X-PAYMENT`` header still carries a real, SDK-valid ``PaymentPayload`` (built from the
official schemas) so the gate's ``PaymentPayload.model_validate_json`` step runs for real.
"""

from __future__ import annotations

import base64
import json
from dataclasses import dataclass
from typing import Any

USDC_BASE = "0x833589fCD6eDb6E08f4c7C32D4f71b54bdA02913"


def payment_header(*, pay_to: str, network: str = "eip155:8453", amount: str = "10000") -> str:
    """Build a spec-valid base64 ``X-PAYMENT`` payload from the official x402 schemas."""
    from x402.schemas import PaymentPayload, PaymentRequirements

    requirements = PaymentRequirements(
        scheme="exact",
        network=network,
        asset=USDC_BASE,
        amount=amount,
        pay_to=pay_to,
        max_timeout_seconds=60,
        extra={"name": "USD Coin", "version": "2"},
    )
    payload = PaymentPayload(payload={"stub": "offline-test"}, accepted=requirements)
    raw = payload.model_dump_json(by_alias=True).encode()
    return base64.b64encode(raw).decode()


@dataclass
class _FakeVerify:
    is_valid: bool


@dataclass
class _FakeSettle:
    success: bool
    transaction: str | None = None
    payer: str | None = None

    def model_dump_json(self) -> str:
        return json.dumps(
            {"success": self.success, "transaction": self.transaction, "payer": self.payer}
        )


class FakeFacilitatorServer:
    """Stands in for ``x402ResourceServer`` (set as ``app.state.x402_server``)."""

    def __init__(
        self,
        *,
        valid: bool = True,
        settle_success: bool = True,
        tx_hash: str = "0xdeadbeef",
        payer: str = "0x00000000000000000000000000000000000000Fe",
        settle_raises: bool = False,
    ) -> None:
        self._valid = valid
        self._settle_success = settle_success
        self._tx = tx_hash
        self._payer = payer
        self._settle_raises = settle_raises

    def build_payment_requirements(self, config: Any, extensions: Any = None) -> list[Any]:
        # verify/settle stubs ignore the requirements; a placeholder is enough offline.
        return [None]

    async def verify_payment(self, payload: Any, requirements: Any, *a: Any, **k: Any) -> Any:
        return _FakeVerify(is_valid=self._valid)

    async def settle_payment(self, payload: Any, requirements: Any, *a: Any, **k: Any) -> Any:
        if self._settle_raises:
            raise RuntimeError("facilitator unreachable")
        if not self._settle_success:
            return _FakeSettle(success=False)
        return _FakeSettle(success=True, transaction=self._tx, payer=self._payer)

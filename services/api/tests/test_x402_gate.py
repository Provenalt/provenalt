"""x402 gate tests: 402 when unpaid, API-key bypass, metering, free routes (§9.1)."""

from __future__ import annotations

import seed
from fastapi.testclient import TestClient
from provenalt_shared.db import repository as repo
from sqlalchemy.orm import Session

from provenalt_api.x402_gate import X402Config, gated_endpoint

OWNER = "0x1111111111111111111111111111111111111111"
PAY_TO = "0x000000000000000000000000000000000000dEaD"


def _enable_x402(client: TestClient) -> None:
    client.app.state.x402_config = X402Config(
        enabled=True,
        pay_to=PAY_TO,
        network="eip155:8453",
        price="$0.01",
        facilitator_url="https://x402.org/facilitator",
    )


def test_gated_endpoint_matcher() -> None:
    assert gated_endpoint("GET", "/v1/agents/7/score") == "score"
    assert gated_endpoint("GET", "/v1/provenalt/7") == "provenalt"
    assert gated_endpoint("GET", "/v1/eligibility") == "eligibility"
    assert gated_endpoint("GET", "/v1/agents/7") is None  # free detail endpoint
    assert gated_endpoint("GET", "/v1/agents") is None
    assert gated_endpoint("GET", "/v1/stats") is None


def test_returns_402_when_enabled_and_unpaid(session: Session, client: TestClient) -> None:
    seed.add_agent(session, 1, OWNER)
    seed.add_score(session, 1, score=72)
    session.commit()
    _enable_x402(client)

    r = client.get("/v1/agents/1/score")
    assert r.status_code == 402
    body = r.json()
    assert body["x402Version"] == 1
    accept = body["accepts"][0]
    assert accept["scheme"] == "exact"
    assert accept["network"] == "eip155:8453"
    assert accept["amount"] == "10000"  # $0.01 USDC (6 decimals)
    assert accept["payTo"] == PAY_TO
    # canonical USDC on Base mainnet
    assert accept["asset"].lower() == "0x833589fcd6edb6e08f4c7c32d4f71b54bda02913"


def test_valid_api_key_bypasses_and_is_metered(session: Session, client: TestClient) -> None:
    seed.add_agent(session, 1, OWNER)
    seed.add_score(session, 1, score=72)
    repo.create_api_key(session, "partner-secret", label="acme")
    session.commit()
    _enable_x402(client)

    r = client.get("/v1/agents/1/score", headers={"X-API-Key": "partner-secret"})
    assert r.status_code == 200
    assert r.json()["score"] == 72

    events = session.query(repo.UsageEvent).all()
    assert len(events) == 1
    assert events[0].endpoint == "score"
    assert events[0].payment_kind == "api_key"
    assert events[0].payer == "key:acme"


def test_invalid_api_key_still_requires_payment(session: Session, client: TestClient) -> None:
    seed.add_agent(session, 1, OWNER)
    seed.add_score(session, 1, score=72)
    session.commit()
    _enable_x402(client)
    assert client.get("/v1/agents/1/score", headers={"X-API-Key": "nope"}).status_code == 402


def test_free_routes_unaffected_when_x402_enabled(session: Session, client: TestClient) -> None:
    seed.add_agent(session, 1, OWNER)
    session.commit()
    _enable_x402(client)
    assert client.get("/v1/stats").status_code == 200
    assert client.get("/v1/agents").status_code == 200
    assert client.get("/v1/agents/1").status_code == 200


def test_metering_records_unpaid_open_when_disabled(session: Session, client: TestClient) -> None:
    seed.add_agent(session, 1, OWNER)
    seed.add_score(session, 1, score=72)
    session.commit()
    # x402 disabled by default → allowed, metered as unpaid_open.
    assert client.get("/v1/agents/1/score").status_code == 200
    summary = {(r.endpoint, r.payment_kind): r for r in repo.usage_summary(session)}
    assert ("score", "unpaid_open") in summary
    assert summary[("score", "unpaid_open")].calls == 1

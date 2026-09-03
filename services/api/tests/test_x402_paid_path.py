"""Offline paid-path tests using a fake facilitator (verify/settle stubs).

The live facilitator round-trip only runs in production; here we stub the resource server so
the gate's paid branch is fully exercised offline:

* valid payment  → 200 + a usage event with ``payment_kind='paid'`` and a ``tx_hash``
* invalid payment → 402, nothing metered
* settlement failure (returns non-success, or raises) → 402, result withheld, nothing metered
* a failed handler (e.g. 404) is not settled/charged
"""

from __future__ import annotations

import seed
from fastapi.testclient import TestClient
from provenalt_shared.db import repository as repo
from sqlalchemy.orm import Session
from x402fake import FakeFacilitatorServer, payment_header

from provenalt_api.x402_gate import X402Config

OWNER = "0x1111111111111111111111111111111111111111"
PAY_TO = "0x000000000000000000000000000000000000dEaD"


def _enable_x402(client: TestClient) -> None:
    client.app.state.x402_config = X402Config(
        enabled=True,
        pay_to=PAY_TO,
        network="eip155:8453",
        price="$0.01",
        facilitator_url="https://facilitator.internal/x402",
    )


def _seed_scored_agent(session: Session, agent_id: int = 1, score: int = 72) -> None:
    seed.add_agent(session, agent_id, OWNER)
    seed.add_score(session, agent_id, score=score, confidence="high")
    session.commit()


def test_valid_payment_returns_200_and_meters_paid(session: Session, client: TestClient) -> None:
    _seed_scored_agent(session)
    _enable_x402(client)
    client.app.state.x402_server = FakeFacilitatorServer(
        valid=True, settle_success=True, tx_hash="0xfeedface", payer="0xPAYER"
    )

    r = client.get("/v1/agents/1/score", headers={"X-PAYMENT": payment_header(pay_to=PAY_TO)})
    assert r.status_code == 200
    assert r.json()["score"] == 72
    assert "X-PAYMENT-RESPONSE" in r.headers  # settlement info echoed back

    events = session.query(repo.UsageEvent).all()
    assert len(events) == 1
    assert events[0].endpoint == "score"
    assert events[0].payment_kind == "paid"
    assert events[0].tx_hash == "0xfeedface"
    assert events[0].amount_atomic == 10000  # $0.01 USDC (6 decimals)
    assert events[0].payer == "0xPAYER"


def test_invalid_payment_returns_402_and_meters_nothing(
    session: Session, client: TestClient
) -> None:
    _seed_scored_agent(session)
    _enable_x402(client)
    client.app.state.x402_server = FakeFacilitatorServer(valid=False)

    r = client.get("/v1/agents/1/score", headers={"X-PAYMENT": payment_header(pay_to=PAY_TO)})
    assert r.status_code == 402
    assert session.query(repo.UsageEvent).count() == 0


def test_settlement_failure_withholds_result(session: Session, client: TestClient) -> None:
    """Chosen behavior: settle happens after the handler but before the response is served;
    if settlement does not succeed, the paid result is withheld (402) and nothing is metered."""
    _seed_scored_agent(session)
    _enable_x402(client)
    client.app.state.x402_server = FakeFacilitatorServer(valid=True, settle_success=False)

    r = client.get("/v1/agents/1/score", headers={"X-PAYMENT": payment_header(pay_to=PAY_TO)})
    assert r.status_code == 402
    assert session.query(repo.UsageEvent).count() == 0


def test_settlement_exception_withholds_result(session: Session, client: TestClient) -> None:
    _seed_scored_agent(session)
    _enable_x402(client)
    client.app.state.x402_server = FakeFacilitatorServer(valid=True, settle_raises=True)

    r = client.get("/v1/agents/1/score", headers={"X-PAYMENT": payment_header(pay_to=PAY_TO)})
    assert r.status_code == 402
    assert session.query(repo.UsageEvent).count() == 0


def test_failed_handler_is_not_settled_or_charged(session: Session, client: TestClient) -> None:
    """A verified payment for a request the handler rejects (404) is not settled/charged."""
    _enable_x402(client)
    client.app.state.x402_server = FakeFacilitatorServer(valid=True, settle_success=True)

    r = client.get("/v1/agents/999/score", headers={"X-PAYMENT": payment_header(pay_to=PAY_TO)})
    assert r.status_code == 404
    assert session.query(repo.UsageEvent).count() == 0

"""Endpoint tests for /v1/eligibility (proposal §7.2) with a fake chain + seeded registry."""

from __future__ import annotations

from b20fake import FakeB20Chain
from fastapi.testclient import TestClient
from provenalt_shared.db import repository as repo
from sqlalchemy.orm import Session

from provenalt_api.deps import get_chain

WAD = 10**18
AAPL = "0xb200000000000000000000c2e324d24d7eecd1fb"
WALLET = "0x00000000000000000000000000000000000000aa"


def _seed_registry(session: Session) -> None:
    repo.upsert_b20_token(session, AAPL, "AAPLc", 8)
    session.commit()


def _use_fake_chain(client: TestClient, chain: FakeB20Chain) -> None:
    client.app.dependency_overrides[get_chain] = lambda: chain


def test_eligibility_by_address(session: Session, client: TestClient) -> None:
    _seed_registry(session)
    _use_fake_chain(
        client,
        FakeB20Chain(
            receiver_policy=5,
            sender_policy=5,
            authorized={5: True},
            balance=1_000,
            scaled=3_000,
            multiplier=3 * WAD,
        ),
    )

    r = client.get("/v1/eligibility", params={"wallet": WALLET, "token": AAPL})
    assert r.status_code == 200
    body = r.json()
    assert body["symbol"] == "AAPLc"
    assert body["decimals"] == 8
    assert body["token_address"] == AAPL
    assert body["wallet"] == WALLET
    assert body["can_hold"] is True
    assert body["can_send"] is True
    assert body["eligible"] is True
    assert body["raw_balance"] == "1000"
    assert body["adjusted_balance"] == "3000"
    assert body["multiplier"] == str(3 * WAD)


def test_eligibility_by_symbol_blocked_sender(session: Session, client: TestClient) -> None:
    _seed_registry(session)
    _use_fake_chain(
        client,
        FakeB20Chain(
            receiver_policy=5,
            sender_policy=7,
            authorized={5: True, 7: False},
            balance=0,
            scaled=0,
            multiplier=WAD,
        ),
    )

    body = client.get("/v1/eligibility", params={"wallet": WALLET, "token": "AAPLc"}).json()
    assert body["can_hold"] is True
    assert body["can_send"] is False
    assert body["eligible"] is False


def test_eligibility_unknown_token_404(session: Session, client: TestClient) -> None:
    _seed_registry(session)
    _use_fake_chain(
        client,
        FakeB20Chain(
            receiver_policy=0, sender_policy=0, authorized={}, balance=0, scaled=0, multiplier=WAD
        ),
    )
    r = client.get(
        "/v1/eligibility",
        params={"wallet": WALLET, "token": "0x00000000000000000000000000000000deadbeef"},
    )
    assert r.status_code == 404


def test_eligibility_invalid_wallet_422(session: Session, client: TestClient) -> None:
    _seed_registry(session)
    r = client.get("/v1/eligibility", params={"wallet": "not-an-address", "token": "AAPLc"})
    assert r.status_code == 422


def test_eligibility_listed_in_openapi(client: TestClient) -> None:
    paths = client.get("/openapi.json").json()["paths"]
    assert "/v1/eligibility" in paths

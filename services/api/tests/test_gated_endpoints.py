"""Data tests for the gated score/verdict endpoints (x402 disabled by default → reachable)."""

from __future__ import annotations

import seed
from fastapi.testclient import TestClient
from sqlalchemy.orm import Session

OWNER = "0x1111111111111111111111111111111111111111"


def test_score_endpoint_returns_breakdown(session: Session, client: TestClient) -> None:
    seed.add_agent(session, 1, OWNER)
    seed.add_score(session, 1, score=72, confidence="high")
    session.commit()

    body = client.get("/v1/agents/1/score").json()
    assert body["score"] == 72
    assert body["confidence"] == "high"
    assert body["sufficient"] is True
    assert body["weights_version"] == "1"
    assert isinstance(body["breakdown"], list) and body["breakdown"]  # per-component breakdown


def test_score_endpoint_insufficient_when_unscored(session: Session, client: TestClient) -> None:
    seed.add_agent(session, 1, OWNER)
    session.commit()
    body = client.get("/v1/agents/1/score").json()
    assert body["score"] is None
    assert body["confidence"] == "insufficient_data"
    assert body["breakdown"] == []


def test_score_endpoint_404(client: TestClient) -> None:
    assert client.get("/v1/agents/999/score").status_code == 404


def test_verdict_endpoint_bands(session: Session, client: TestClient) -> None:
    seed.add_agent(session, 1, OWNER)
    seed.add_score(session, 1, score=80, confidence="high")
    seed.add_agent(session, 2, OWNER)
    seed.add_score(session, 2, score=50, confidence="medium")
    seed.add_agent(session, 3, OWNER)
    seed.add_score(session, 3, score=20, confidence="low")
    seed.add_agent(session, 4, OWNER)  # unscored
    session.commit()

    assert client.get("/v1/provenalt/1").json()["verdict"] == "pass"
    assert client.get("/v1/provenalt/2").json()["verdict"] == "warn"
    assert client.get("/v1/provenalt/3").json()["verdict"] == "fail"
    assert client.get("/v1/provenalt/4").json()["verdict"] == "insufficient"


def test_verdict_endpoint_404(client: TestClient) -> None:
    assert client.get("/v1/provenalt/999").status_code == 404

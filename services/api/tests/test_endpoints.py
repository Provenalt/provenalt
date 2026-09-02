"""Endpoint tests for the public API (free tier) using an in-memory DB."""

from __future__ import annotations

import seed
from fastapi.testclient import TestClient
from sqlalchemy.orm import Session

OWNER_A = "0x1111111111111111111111111111111111111111"
OWNER_B = "0x2222222222222222222222222222222222222222"
CLIENT = "0x3333333333333333333333333333333333333333"
RESPONDER = "0x4444444444444444444444444444444444444444"


def test_healthz(client: TestClient) -> None:
    r = client.get("/healthz")
    assert r.status_code == 200
    assert r.json() == {"status": "ok"}


def test_openapi_and_docs_published(client: TestClient) -> None:
    schema = client.get("/openapi.json")
    assert schema.status_code == 200
    paths = schema.json()["paths"]
    assert "/v1/agents" in paths
    assert "/v1/agents/{agent_id}" in paths
    assert "/v1/agents/{agent_id}/feedback" in paths
    assert "/v1/stats" in paths
    assert client.get("/docs").status_code == 200


def test_list_agents_pagination_and_owner_filter(session: Session, client: TestClient) -> None:
    seed.add_agent(session, 1, OWNER_A)
    seed.add_agent(session, 2, OWNER_A)
    seed.add_agent(session, 3, OWNER_B)
    seed.add_score(session, 1, score=72, confidence="high")
    session.commit()

    r = client.get("/v1/agents", params={"limit": 2, "offset": 0})
    body = r.json()
    assert r.status_code == 200
    assert body["total"] == 3
    assert [i["agent_id"] for i in body["items"]] == [1, 2]
    assert body["items"][0]["score"] == 72
    assert body["items"][0]["confidence"] == "high"
    assert body["items"][1]["score"] is None  # no score yet

    # second page
    page2 = client.get("/v1/agents", params={"limit": 2, "offset": 2}).json()
    assert [i["agent_id"] for i in page2["items"]] == [3]

    # owner filter (case-insensitive)
    filtered = client.get("/v1/agents", params={"owner": OWNER_B.upper()}).json()
    assert filtered["total"] == 1
    assert filtered["items"][0]["agent_id"] == 3


def test_agent_detail(session: Session, client: TestClient) -> None:
    seed.add_agent(session, 1, OWNER_A, uri="ipfs://card1", block=100)
    seed.add_transfer(session, 1, OWNER_A, OWNER_B, block=200)
    seed.add_card(session, 1)
    seed.add_score(session, 1, score=64)
    seed.add_metadata(session, 1, "agentWallet", bytes.fromhex(OWNER_B[2:]), block=200)
    session.commit()

    r = client.get("/v1/agents/1")
    body = r.json()
    assert r.status_code == 200
    assert body["agent_id"] == 1
    assert body["owner"] == OWNER_B  # current owner after transfer
    assert body["card"]["fetch_status"] == "ok"
    assert body["card"]["registration_match"] is True
    assert body["score"]["score"] == 64
    assert body["metadata"][0]["metadata_key"] == "agentWallet"
    assert body["metadata"][0]["value_hex"] == OWNER_B
    # owner history: mint (0x0 -> A) then transfer (A -> B)
    assert [h["to_address"] for h in body["owner_history"]] == [OWNER_A, OWNER_B]


def test_agent_detail_404(client: TestClient) -> None:
    assert client.get("/v1/agents/999").status_code == 404


def test_feedback_timeline_flags(session: Session, client: TestClient) -> None:
    seed.add_agent(session, 1, OWNER_A)
    seed.add_feedback(session, 1, CLIENT, index=0, block=100, value=5)
    seed.add_feedback(session, 1, CLIENT, index=1, block=110, value=-2)
    seed.add_revocation(session, 1, CLIENT, index=0, block=120)
    seed.add_response(session, 1, CLIENT, index=1, responder=RESPONDER, block=130)
    session.commit()

    body = client.get("/v1/agents/1/feedback").json()
    assert body["total"] == 2
    by_index = {f["feedback_index"]: f for f in body["items"]}
    assert by_index[0]["revoked"] is True
    assert by_index[0]["responded"] is False
    assert by_index[1]["responded"] is True
    assert by_index[1]["value"] == "-2"  # signed value preserved as string
    assert by_index[0]["tag1"] == "quality"


def test_feedback_timeline_404_for_unknown_agent(client: TestClient) -> None:
    assert client.get("/v1/agents/999/feedback").status_code == 404


def test_stats(session: Session, client: TestClient) -> None:
    # agents registered across a range of blocks so the growth series has multiple points.
    for i in range(1, 6):
        seed.add_agent(session, i, OWNER_A if i % 2 else OWNER_B, block=i * 1000)
    seed.add_card(session, 1)
    seed.add_score(session, 1, score=50)
    seed.add_feedback(session, 1, CLIENT, index=0, block=100)
    seed.add_cursor(session, "identity", anchor=10, last=999)
    session.commit()

    body = client.get("/v1/stats").json()
    assert body["total_agents"] == 5
    assert body["max_agent_id"] == 5
    assert body["total_feedback"] == 1
    assert body["total_scored"] == 1
    assert body["total_cards"] == 1
    assert body["registries"] == [
        {"registry": "identity", "anchor_block": 10, "last_indexed_block": 999}
    ]
    # growth is a cumulative, non-decreasing series ending at the total agent count.
    growth = body["growth"]
    assert growth, "expected a non-empty growth series"
    cumulatives = [p["cumulative_agents"] for p in growth]
    assert cumulatives == sorted(cumulatives)
    assert cumulatives[-1] == 5

"""Unit tests for the agent-card repository primitives (proposal §4)."""

from __future__ import annotations

import pytest
from sqlalchemy.orm import Session

from provenalt_shared.db import AgentCard, Base, make_engine, make_session_factory
from provenalt_shared.db import repository as repo

OWNER_A = "0x1111111111111111111111111111111111111111"
WALLET = "0x00000000000000000000000000000000000000aa"


@pytest.fixture
def session() -> Session:
    engine = make_engine("sqlite://")
    Base.metadata.create_all(engine)
    with make_session_factory(engine)() as s:
        yield s


def _agent(s: Session, agent_id: int, uri: str) -> None:
    repo.upsert_agent(
        s,
        agent_id=agent_id,
        owner=OWNER_A,
        agent_uri=uri,
        registered_block=1,
        registered_tx_hash=f"0x{agent_id:064x}",
        registered_log_index=0,
    )


def _set_wallet_metadata(
    s: Session, agent_id: int, value: bytes, block: int, log_index: int
) -> None:
    repo.insert_metadata(
        s,
        agent_id=agent_id,
        metadata_key="agentWallet",
        indexed_key_hash="0x" + "00" * 32,
        metadata_value=value,
        block_number=block,
        tx_hash=f"0xw{agent_id}{block}",
        log_index=log_index,
    )


# ── agentWallet ──────────────────────────────────────────────────────────────


def test_get_agent_wallet_from_20_byte_value(session: Session) -> None:
    _agent(session, 1, "ipfs://a")
    _set_wallet_metadata(session, 1, bytes.fromhex(WALLET[2:]), block=10, log_index=0)
    session.commit()
    assert repo.get_agent_wallet(session, 1) == WALLET


def test_get_agent_wallet_from_32_byte_padded_value(session: Session) -> None:
    _agent(session, 1, "ipfs://a")
    padded = bytes(12) + bytes.fromhex(WALLET[2:])
    _set_wallet_metadata(session, 1, padded, block=10, log_index=0)
    session.commit()
    assert repo.get_agent_wallet(session, 1) == WALLET


def test_get_agent_wallet_returns_latest(session: Session) -> None:
    _agent(session, 1, "ipfs://a")
    _set_wallet_metadata(session, 1, bytes.fromhex(OWNER_A[2:]), block=10, log_index=0)
    _set_wallet_metadata(session, 1, bytes.fromhex(WALLET[2:]), block=20, log_index=0)
    session.commit()
    assert repo.get_agent_wallet(session, 1) == WALLET


def test_get_agent_wallet_none_when_unset(session: Session) -> None:
    _agent(session, 1, "ipfs://a")
    session.commit()
    assert repo.get_agent_wallet(session, 1) is None


# ── card upsert / drift ──────────────────────────────────────────────────────


def test_upsert_agent_card_inserts_then_replaces(session: Session) -> None:
    _agent(session, 1, "ipfs://a")
    repo.upsert_agent_card(
        session,
        agent_id=1,
        token_uri="ipfs://a",
        fetch_status="ok",
        content_hash="h1",
        schema_valid=True,
    )
    session.commit()
    assert repo.get_agent_card(session, 1).content_hash == "h1"

    repo.upsert_agent_card(
        session,
        agent_id=1,
        token_uri="ipfs://a",
        fetch_status="ok",
        content_hash="h2",
        schema_valid=False,
        schema_errors=["boom"],
    )
    session.commit()
    card = repo.get_agent_card(session, 1)
    assert session.query(AgentCard).count() == 1  # replaced, not duplicated
    assert card.content_hash == "h2"
    assert card.schema_valid is False
    assert card.schema_errors == ["boom"]


def test_record_card_drift(session: Session) -> None:
    repo.record_card_drift(
        session, agent_id=1, token_uri="ipfs://a", old_content_hash="h1", new_content_hash="h2"
    )
    session.commit()
    drift = session.query(repo.CardDrift).one()
    assert drift.old_content_hash == "h1"
    assert drift.new_content_hash == "h2"


# ── refresh queue ────────────────────────────────────────────────────────────


def test_enqueue_is_idempotent_per_agent(session: Session) -> None:
    assert repo.enqueue_card_refresh(session, 1, "new_agent") is True
    assert repo.enqueue_card_refresh(session, 1, "uri_updated") is False  # already queued
    session.commit()
    pending = repo.list_pending_card_refresh(session)
    assert len(pending) == 1
    assert pending[0].reason == "new_agent"


def test_delete_card_refresh(session: Session) -> None:
    repo.enqueue_card_refresh(session, 1, "new_agent")
    session.commit()
    repo.delete_card_refresh(session, 1)
    session.commit()
    assert repo.list_pending_card_refresh(session) == []


def test_agents_needing_card_refresh_new_and_uri_updated(session: Session) -> None:
    _agent(session, 1, "ipfs://v2")  # will have a card with old uri → uri_updated
    _agent(session, 2, "ipfs://b")  # never fetched → new_agent
    repo.upsert_agent_card(session, agent_id=1, token_uri="ipfs://v1", fetch_status="ok")
    session.commit()

    needing = dict(repo.agents_needing_card_refresh(session))
    assert needing == {1: "uri_updated", 2: "new_agent"}


def test_enqueue_all_agents_for_refresh(session: Session) -> None:
    for i in (1, 2, 3):
        _agent(session, i, "ipfs://x")
    session.commit()
    assert repo.enqueue_all_agents_for_refresh(session, "periodic") == 3
    session.commit()
    assert repo.enqueue_all_agents_for_refresh(session, "periodic") == 0  # already queued

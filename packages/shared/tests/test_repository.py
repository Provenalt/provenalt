"""Unit tests for the DB repository primitives (against in-memory SQLite)."""

from __future__ import annotations

import pytest
from sqlalchemy.orm import Session

from provenalt_shared.db import Agent, Base, make_engine, make_session_factory
from provenalt_shared.db import repository as repo
from provenalt_shared.db.models import ZERO_ADDRESS

OWNER_A = "0x1111111111111111111111111111111111111111"
OWNER_B = "0x2222222222222222222222222222222222222222"


@pytest.fixture
def session() -> Session:
    engine = make_engine("sqlite://")
    Base.metadata.create_all(engine)
    factory = make_session_factory(engine)
    with factory() as s:
        yield s


def _register(s: Session, agent_id: int, owner: str, block: int, uri: str = "ipfs://a") -> None:
    tx = f"0x{agent_id:064x}"
    repo.upsert_agent(
        s,
        agent_id=agent_id,
        owner=owner,
        agent_uri=uri,
        registered_block=block,
        registered_tx_hash=tx,
        registered_log_index=0,
    )
    repo.append_owner_history(
        s,
        agent_id=agent_id,
        from_address=ZERO_ADDRESS,
        to_address=owner,
        block_number=block,
        tx_hash=tx,
        log_index=0,
    )


# ── idempotency ──────────────────────────────────────────────────────────────


def test_upsert_raw_log_is_idempotent_on_tx_and_log_index(session: Session) -> None:
    kwargs = dict(
        address="0xabc",
        block_number=10,
        block_hash="0xhash",
        tx_hash="0xtx",
        log_index=0,
        topic0="0xtopic",
        topics=["0xtopic"],
        data="0x",
    )
    assert repo.upsert_raw_log(session, **kwargs) is True  # inserted
    assert repo.upsert_raw_log(session, **kwargs) is False  # duplicate, no-op
    session.commit()
    assert session.query(repo.RawLog).count() == 1


def test_upsert_agent_is_idempotent(session: Session) -> None:
    _register(session, 1, OWNER_A, block=10)
    _register(session, 1, OWNER_A, block=10)  # replay
    session.commit()
    assert session.query(Agent).count() == 1


def test_append_owner_history_idempotent_and_recompute_owner(session: Session) -> None:
    _register(session, 1, OWNER_A, block=10)
    # Transfer A -> B at block 20
    repo.append_owner_history(
        session,
        agent_id=1,
        from_address=OWNER_A,
        to_address=OWNER_B,
        block_number=20,
        tx_hash="0xtransfer",
        log_index=1,
    )
    repo.set_agent_owner(session, 1, OWNER_B)
    session.commit()

    # duplicate transfer log is a no-op
    inserted = repo.append_owner_history(
        session,
        agent_id=1,
        from_address=OWNER_A,
        to_address=OWNER_B,
        block_number=20,
        tx_hash="0xtransfer",
        log_index=1,
    )
    assert inserted is False
    session.commit()
    assert session.query(repo.AgentOwnerHistory).filter_by(agent_id=1).count() == 2

    # recompute derives the latest owner from history
    repo.recompute_owner_from_history(session, 1)
    session.commit()
    assert session.get(Agent, 1).owner == OWNER_B


# ── cursor ───────────────────────────────────────────────────────────────────


def test_cursor_upsert_and_advance(session: Session) -> None:
    assert repo.get_cursor(session, "identity") is None
    repo.upsert_cursor(session, "identity", anchor_block=100, last_indexed_block=100)
    session.commit()

    cur = repo.get_cursor(session, "identity")
    assert cur is not None
    assert cur.anchor_block == 100
    assert cur.last_indexed_block == 100

    repo.set_last_indexed_block(session, "identity", 250)
    session.commit()
    cur = repo.get_cursor(session, "identity")
    assert cur.last_indexed_block == 250
    assert cur.anchor_block == 100  # anchor unchanged


# ── continuity (2.5) ─────────────────────────────────────────────────────────


def test_agent_id_continuity_detects_gaps(session: Session) -> None:
    _register(session, 1, OWNER_A, block=10)
    _register(session, 2, OWNER_A, block=11)
    _register(session, 4, OWNER_A, block=13)  # missing 3
    session.commit()

    assert repo.max_agent_id(session) == 4
    assert repo.missing_agent_ids(session) == [3]


def test_agent_id_continuity_clean_when_sequential(session: Session) -> None:
    for i in range(1, 6):
        _register(session, i, OWNER_A, block=10 + i)
    session.commit()
    assert repo.missing_agent_ids(session) == []


# ── reorg rewind (2.4) ───────────────────────────────────────────────────────


def test_delete_rows_above_and_raw_logs_above_remove_tail_only(session: Session) -> None:
    _register(session, 1, OWNER_A, block=100)
    _register(session, 2, OWNER_B, block=150)  # registered in the reorged tail
    repo.upsert_raw_log(
        session,
        address="0xabc",
        block_number=150,
        block_hash="0xh150",
        tx_hash="0xtx150",
        log_index=0,
        topic0="0xt",
        topics=["0xt"],
        data="0x",
    )
    session.commit()

    repo.delete_rows_above(session, Agent, 140, block_column="registered_block")
    repo.delete_raw_logs_above(session, 140, ["0xabc"])
    session.commit()

    assert session.get(Agent, 1) is not None  # survived
    assert session.get(Agent, 2) is None  # registered above fork → removed
    assert session.query(repo.RawLog).filter(repo.RawLog.block_number > 140).count() == 0


def test_delete_raw_logs_above_is_scoped_by_address(session: Session) -> None:
    # Two registries share raw_logs; a rewind for one must not delete the other's rows.
    for addr in ("0xidentity", "0xreputation"):
        repo.upsert_raw_log(
            session,
            address=addr,
            block_number=200,
            block_hash="0xh",
            tx_hash=f"0xtx{addr}",
            log_index=0,
            topic0="0xt",
            topics=["0xt"],
            data="0x",
        )
    session.commit()

    repo.delete_raw_logs_above(session, 150, ["0xidentity"])
    session.commit()

    remaining = {r.address for r in session.query(repo.RawLog).all()}
    assert remaining == {"0xreputation"}

"""Reputation head-follow + reorg tests, incl. cross-registry isolation of shared raw_logs."""

from __future__ import annotations

import pytest
from fakechain import FakeChain
from logbuilders import new_feedback_log, registered_log, transfer_log
from provenalt_shared.db import Agent, Base, Feedback, make_engine, make_session_factory
from provenalt_shared.db import repository as repo
from sqlalchemy.orm import Session

from provenalt_indexer import events, reputation
from provenalt_indexer.backfill import backfill
from provenalt_indexer.follow import follow_once
from provenalt_indexer.projection import ingest_logs
from provenalt_indexer.reputation_projection import ingest_reputation_logs, rewind_reputation

ZERO = "0x" + "00" * 20
OWNER_A = "0x1111111111111111111111111111111111111111"
CLIENT = "0x2222222222222222222222222222222222222222"
REP = "reputation"
IDN = "identity"
N = 64


@pytest.fixture
def session() -> Session:
    engine = make_engine("sqlite://")
    Base.metadata.create_all(engine)
    with make_session_factory(engine)() as s:
        yield s


def _follow_reputation(session: Session, chain: FakeChain) -> None:
    follow_once(
        session,
        chain,
        address=reputation.REPUTATION_REGISTRY_ADDRESS,
        event_topic0s=reputation.REPUTATION_EVENT_TOPIC0S,
        registry=REP,
        finality_depth=N,
        ingest=ingest_reputation_logs,
        rewind_fn=rewind_reputation,
        segment_size=1000,
    )


def _backfill_reputation(session: Session, chain: FakeChain, from_block: int) -> None:
    backfill(
        session,
        chain,
        address=reputation.REPUTATION_REGISTRY_ADDRESS,
        event_topic0s=reputation.REPUTATION_EVENT_TOPIC0S,
        registry=REP,
        from_block=from_block,
        to_block=chain.head,
        segment_size=1000,
        ingest=ingest_reputation_logs,
    )


def test_reputation_reorg_removes_orphaned_feedback(session: Session) -> None:
    original = [
        new_feedback_log(1, CLIENT, value=50, feedback_index=0, block=100, tx="0xf0"),
        new_feedback_log(1, CLIENT, value=60, feedback_index=1, block=105, tx="0xf1"),
    ]
    repo.upsert_cursor(session, REP, anchor_block=100, last_indexed_block=99)
    session.commit()
    _backfill_reputation(session, FakeChain(original, head=105), from_block=100)
    assert session.query(Feedback).count() == 2

    # Reorg at block 105: the second feedback never happened on the new canonical chain.
    reorged = FakeChain(
        logs=[new_feedback_log(1, CLIENT, value=50, feedback_index=0, block=100, tx="0xf0")],
        head=105,
        block_hashes={105: "0x" + "ee" * 32},
    )
    _follow_reputation(session, reorged)

    assert session.query(Feedback).count() == 1  # orphaned feedback rewound
    assert session.query(Feedback).one().feedback_index == 0
    assert repo.get_cursor(session, REP).last_indexed_block == 105


def test_reputation_reorg_does_not_touch_identity_rows(session: Session) -> None:
    """Both registries share raw_logs; a reputation rewind must leave identity data intact."""
    # Seed identity: agent 1 registered at block 100 (identity address logs).
    identity_logs = [
        registered_log(1, OWNER_A, "ipfs://a", block=100, tx="0xr1"),
        transfer_log(ZERO, OWNER_A, 1, block=100, tx="0xr1", log_index=1),
    ]
    repo.upsert_cursor(session, IDN, anchor_block=100, last_indexed_block=99)
    session.commit()
    backfill(
        session,
        FakeChain(identity_logs, head=100),
        address=events.IDENTITY_REGISTRY_ADDRESS,
        event_topic0s=events.IDENTITY_EVENT_TOPIC0S,
        registry=IDN,
        from_block=100,
        to_block=100,
        segment_size=1000,
        ingest=ingest_logs,
    )

    # Seed reputation feedback at block 105 (reputation address logs).
    repo.upsert_cursor(session, REP, anchor_block=100, last_indexed_block=99)
    session.commit()
    _backfill_reputation(
        session,
        FakeChain([new_feedback_log(1, CLIENT, 50, 0, block=105, tx="0xf0")], head=105),
        from_block=100,
    )

    identity_raw_before = (
        session.query(repo.RawLog)
        .filter(repo.RawLog.address == events.IDENTITY_REGISTRY_ADDRESS.lower())
        .count()
    )

    # Reputation reorg at 105 rewinds reputation only.
    reorged = FakeChain(logs=[], head=105, block_hashes={105: "0x" + "ee" * 32})
    _follow_reputation(session, reorged)

    assert session.query(Feedback).count() == 0  # reputation tail removed
    assert session.get(Agent, 1) is not None  # identity agent intact
    identity_raw_after = (
        session.query(repo.RawLog)
        .filter(repo.RawLog.address == events.IDENTITY_REGISTRY_ADDRESS.lower())
        .count()
    )
    assert identity_raw_after == identity_raw_before  # identity raw_logs untouched
    assert repo.get_cursor(session, IDN).last_indexed_block == 100  # identity cursor intact


def test_reputation_follow_no_reorg_when_hashes_match(session: Session) -> None:
    logs = [new_feedback_log(1, CLIENT, 50, 0, block=100, tx="0xf0")]
    chain = FakeChain(list(logs), head=100)
    repo.upsert_cursor(session, REP, anchor_block=100, last_indexed_block=99)
    session.commit()
    _follow_reputation(session, chain)

    raw_before = session.query(repo.RawLog).count()
    _follow_reputation(session, chain)
    assert session.query(repo.RawLog).count() == raw_before
    assert repo.get_cursor(session, REP).last_indexed_block == 100

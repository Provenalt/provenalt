"""Unit tests for the head-follow loop with reorg detection (proposal §2.4)."""

from __future__ import annotations

import pytest
from fakechain import FakeChain
from logbuilders import registered_log, transfer_log
from provenalt_shared.db import Agent, Base, make_engine, make_session_factory
from provenalt_shared.db import repository as repo
from sqlalchemy.orm import Session

from provenalt_indexer import events
from provenalt_indexer.backfill import backfill
from provenalt_indexer.follow import follow_once
from provenalt_indexer.projection import ingest_logs, rewind_identity

ZERO = "0x" + "00" * 20
OWNER_A = "0x1111111111111111111111111111111111111111"
OWNER_B = "0x2222222222222222222222222222222222222222"
REGISTRY = "identity"
N = 64


@pytest.fixture
def session() -> Session:
    engine = make_engine("sqlite://")
    Base.metadata.create_all(engine)
    with make_session_factory(engine)() as s:
        yield s


def _follow(session: Session, chain: FakeChain) -> None:
    follow_once(
        session,
        chain,
        address=events.IDENTITY_REGISTRY_ADDRESS,
        event_topic0s=events.IDENTITY_EVENT_TOPIC0S,
        registry=REGISTRY,
        finality_depth=N,
        segment_size=1000,
        ingest=ingest_logs,
        rewind_fn=rewind_identity,
    )


def test_follow_indexes_new_blocks(session: Session) -> None:
    logs = [
        registered_log(1, OWNER_A, "ipfs://a", block=100, tx="0xr1"),
        transfer_log(ZERO, OWNER_A, 1, block=100, tx="0xr1", log_index=1),
    ]
    chain = FakeChain(list(logs), head=100)
    repo.upsert_cursor(session, REGISTRY, anchor_block=100, last_indexed_block=99)
    session.commit()

    _follow(session, chain)  # catches up to 100
    assert session.get(Agent, 1) is not None

    # A new block 101 appears with a second agent.
    chain.logs.append(registered_log(2, OWNER_B, "ipfs://b", block=101, tx="0xr2"))
    chain.head = 101
    _follow(session, chain)

    assert repo.all_agent_ids(session) == [1, 2]
    assert repo.get_cursor(session, REGISTRY).last_indexed_block == 101


def test_follow_detects_reorg_and_reverts_owner(session: Session) -> None:
    # --- Original chain: agent 1 registered at 100, then sold A→B at block 105. ---
    original_logs = [
        registered_log(1, OWNER_A, "ipfs://a", block=100, tx="0xr1"),
        transfer_log(ZERO, OWNER_A, 1, block=100, tx="0xr1", log_index=1),
        transfer_log(OWNER_A, OWNER_B, 1, block=105, tx="0xsold"),
    ]
    repo.upsert_cursor(session, REGISTRY, anchor_block=100, last_indexed_block=99)
    session.commit()
    backfill(
        session,
        FakeChain(original_logs, head=105),
        address=events.IDENTITY_REGISTRY_ADDRESS,
        event_topic0s=events.IDENTITY_EVENT_TOPIC0S,
        registry=REGISTRY,
        from_block=100,
        to_block=105,
        segment_size=1000,
    )
    assert session.get(Agent, 1).owner == OWNER_B  # sold

    # --- Reorg: blocks 105 replaced; the sale never happened on the new canonical chain. ---
    reorged_chain = FakeChain(
        logs=[
            registered_log(1, OWNER_A, "ipfs://a", block=100, tx="0xr1"),
            transfer_log(ZERO, OWNER_A, 1, block=100, tx="0xr1", log_index=1),
            # no transfer at 105 anymore
        ],
        head=105,
        block_hashes={105: "0x" + "ee" * 32},  # different hash → fork at 105
    )

    _follow(session, reorged_chain)

    # The sale was rewound; owner reverts to A; the stale transfer log is gone.
    assert session.get(Agent, 1).owner == OWNER_A
    assert (
        session.query(repo.AgentOwnerHistory).filter_by(agent_id=1, to_address=OWNER_B).count() == 0
    )
    assert session.query(repo.RawLog).filter(repo.RawLog.block_number >= 105).count() == 0
    assert repo.get_cursor(session, REGISTRY).last_indexed_block == 105


def test_follow_no_reorg_when_hashes_match(session: Session) -> None:
    logs = [registered_log(1, OWNER_A, "ipfs://a", block=100, tx="0xr1")]
    chain = FakeChain(list(logs), head=100)
    repo.upsert_cursor(session, REGISTRY, anchor_block=100, last_indexed_block=99)
    session.commit()
    _follow(session, chain)

    raw_before = session.query(repo.RawLog).count()
    _follow(session, chain)  # same hashes → no rewind, no duplication
    assert session.query(repo.RawLog).count() == raw_before
    assert repo.get_cursor(session, REGISTRY).last_indexed_block == 100

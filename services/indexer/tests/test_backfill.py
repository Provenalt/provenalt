"""Unit tests for the identity backfill worker (2.3): decode → upsert, resumable, idempotent."""

from __future__ import annotations

import pytest
from fakechain import FakeChain
from logbuilders import metadata_log, registered_log, transfer_log, uri_updated_log
from provenalt_shared.db import Agent, Base, make_engine, make_session_factory
from provenalt_shared.db import repository as repo
from sqlalchemy.orm import Session

from provenalt_indexer import events
from provenalt_indexer.backfill import backfill

OWNER_A = "0x1111111111111111111111111111111111111111"
OWNER_B = "0x2222222222222222222222222222222222222222"
REGISTRY = "identity"


@pytest.fixture
def session() -> Session:
    engine = make_engine("sqlite://")
    Base.metadata.create_all(engine)
    with make_session_factory(engine)() as s:
        yield s


def _scenario_logs() -> list[dict]:
    return [
        registered_log(1, OWNER_A, "ipfs://a1", block=100, tx="0xa1"),
        transfer_log("0x" + "00" * 20, OWNER_A, 1, block=100, tx="0xa1", log_index=1),
        registered_log(2, OWNER_B, "ipfs://a2", block=101, tx="0xa2"),
        transfer_log(OWNER_A, OWNER_B, 1, block=102, tx="0xt1"),  # agent 1 sold A→B
        metadata_log(1, "agentWallet", b"\x01\x02", block=103, tx="0xm1"),
        uri_updated_log(1, "ipfs://a1-v2", OWNER_B, block=104, tx="0xu1"),
    ]


def _run_backfill(session: Session, chain: FakeChain, from_block: int) -> None:
    backfill(
        session,
        chain,
        address=events.IDENTITY_REGISTRY_ADDRESS,
        event_topic0s=events.IDENTITY_EVENT_TOPIC0S,
        registry=REGISTRY,
        from_block=from_block,
        to_block=chain.head,
        segment_size=2,
    )


def test_backfill_decodes_and_persists_all_event_types(session: Session) -> None:
    chain = FakeChain(_scenario_logs(), head=104)
    repo.upsert_cursor(session, REGISTRY, anchor_block=100, last_indexed_block=99)
    session.commit()

    _run_backfill(session, chain, from_block=100)

    assert repo.all_agent_ids(session) == [1, 2]
    agent1 = session.get(Agent, 1)
    assert agent1.owner == OWNER_B  # latest owner after transfer
    assert agent1.agent_uri == "ipfs://a1-v2"  # latest uri after URIUpdated
    assert session.get(Agent, 2).owner == OWNER_B

    # metadata recorded
    assert session.query(repo.AgentMetadata).filter_by(agent_id=1).count() == 1
    # owner history: mint(0→A) + transfer(A→B) for agent 1
    hist = (
        session.query(repo.AgentOwnerHistory)
        .filter_by(agent_id=1)
        .order_by(repo.AgentOwnerHistory.block_number)
        .all()
    )
    assert [(h.from_address, h.to_address) for h in hist] == [
        ("0x" + "00" * 20, OWNER_A),
        (OWNER_A, OWNER_B),
    ]
    # cursor advanced to head
    assert repo.get_cursor(session, REGISTRY).last_indexed_block == 104


def test_backfill_is_idempotent_on_replay(session: Session) -> None:
    chain = FakeChain(_scenario_logs(), head=104)
    repo.upsert_cursor(session, REGISTRY, anchor_block=100, last_indexed_block=99)
    session.commit()

    _run_backfill(session, chain, from_block=100)
    counts_first = (
        session.query(repo.RawLog).count(),
        session.query(Agent).count(),
        session.query(repo.AgentOwnerHistory).count(),
        session.query(repo.AgentMetadata).count(),
    )

    # Replay the entire range again — upserts must not duplicate anything.
    _run_backfill(session, chain, from_block=100)
    counts_second = (
        session.query(repo.RawLog).count(),
        session.query(Agent).count(),
        session.query(repo.AgentOwnerHistory).count(),
        session.query(repo.AgentMetadata).count(),
    )
    assert counts_first == counts_second


def test_backfill_resumes_from_cursor(session: Session) -> None:
    chain = FakeChain(_scenario_logs(), head=104)
    # Pretend blocks up to 101 were already indexed in a previous run.
    repo.upsert_cursor(session, REGISTRY, anchor_block=100, last_indexed_block=101)
    session.commit()

    _run_backfill(session, chain, from_block=102)

    # Only the tail (102–104) was processed this run; agents 1 and 2 were registered
    # earlier, so they are absent here — proving we resumed rather than restarted.
    assert repo.get_cursor(session, REGISTRY).last_indexed_block == 104
    assert session.query(repo.RawLog).filter(repo.RawLog.block_number <= 101).count() == 0

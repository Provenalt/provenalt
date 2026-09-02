"""Unit tests for worker orchestration (bootstrap + catch-up wiring)."""

from __future__ import annotations

import pytest
from fakechain import FakeChain
from logbuilders import registered_log
from provenalt_shared.db import Base, make_engine, make_session_factory
from provenalt_shared.db import repository as repo
from sqlalchemy.orm import Session

from provenalt_indexer import events, worker

OWNER_A = "0x1111111111111111111111111111111111111111"


@pytest.fixture
def session() -> Session:
    engine = make_engine("sqlite://")
    Base.metadata.create_all(engine)
    with make_session_factory(engine)() as s:
        yield s


def test_bootstrap_discovers_anchor_and_seeds_cursor(session: Session) -> None:
    chain = FakeChain(logs=[], head=5000, deployed_at=1234)

    anchor = worker.bootstrap_cursor(
        session, chain, registry=worker.REGISTRY_NAME, address="0xregistry"
    )

    assert anchor == 1234
    cur = repo.get_cursor(session, worker.REGISTRY_NAME)
    assert cur.anchor_block == 1234
    assert cur.last_indexed_block == 1233  # anchor - 1 (nothing indexed yet)


def test_bootstrap_is_noop_when_cursor_exists(session: Session) -> None:
    repo.upsert_cursor(session, worker.REGISTRY_NAME, anchor_block=999, last_indexed_block=999)
    session.commit()
    chain = FakeChain(logs=[], head=5000, deployed_at=1234)

    anchor = worker.bootstrap_cursor(
        session, chain, registry=worker.REGISTRY_NAME, address="0xregistry"
    )
    assert anchor == 999  # existing anchor kept; no re-discovery


def test_catch_up_backfills_from_anchor_to_head(session: Session) -> None:
    logs = [registered_log(1, OWNER_A, "ipfs://a", block=1234, tx="0xr1")]
    chain = FakeChain(logs=logs, head=1234, deployed_at=1234)

    worker.bootstrap_cursor(
        session, chain, registry=worker.REGISTRY_NAME, address=events.IDENTITY_REGISTRY_ADDRESS
    )
    worker.catch_up(
        session,
        chain,
        registry=worker.REGISTRY_NAME,
        address=events.IDENTITY_REGISTRY_ADDRESS,
        event_topic0s=events.IDENTITY_EVENT_TOPIC0S,
        segment_size=1000,
    )

    assert repo.all_agent_ids(session) == [1]
    assert repo.get_cursor(session, worker.REGISTRY_NAME).last_indexed_block == 1234

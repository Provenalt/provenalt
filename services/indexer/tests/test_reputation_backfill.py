"""Unit tests for reputation backfill (proposal §3.3), reusing the Group 2 worker."""

from __future__ import annotations

from decimal import Decimal

import pytest
from fakechain import FakeChain
from logbuilders import feedback_revoked_log, new_feedback_log, response_appended_log
from provenalt_shared.db import Base, Feedback, make_engine, make_session_factory
from provenalt_shared.db import repository as repo
from sqlalchemy.orm import Session

from provenalt_indexer import reputation
from provenalt_indexer.backfill import backfill
from provenalt_indexer.reputation_projection import ingest_reputation_logs

CLIENT = "0x1111111111111111111111111111111111111111"
RESPONDER = "0x3333333333333333333333333333333333333333"
REGISTRY = "reputation"


@pytest.fixture
def session() -> Session:
    engine = make_engine("sqlite://")
    Base.metadata.create_all(engine)
    with make_session_factory(engine)() as s:
        yield s


def _scenario() -> list[dict]:
    return [
        new_feedback_log(
            1,
            CLIENT,
            value=80,
            feedback_index=0,
            block=100,
            tx="0xf0",
            value_decimals=1,
            tag1="quality",
        ),
        new_feedback_log(1, CLIENT, value=-5, feedback_index=1, block=101, tx="0xf1"),
        feedback_revoked_log(1, CLIENT, feedback_index=0, block=102, tx="0xrev"),
        response_appended_log(1, CLIENT, 1, RESPONDER, "ipfs://resp", block=103, tx="0xresp"),
    ]


def _run(session: Session, chain: FakeChain, from_block: int) -> None:
    backfill(
        session,
        chain,
        address=reputation.REPUTATION_REGISTRY_ADDRESS,
        event_topic0s=reputation.REPUTATION_EVENT_TOPIC0S,
        registry=REGISTRY,
        from_block=from_block,
        to_block=chain.head,
        segment_size=2,
        ingest=ingest_reputation_logs,
    )


def test_backfill_persists_all_reputation_event_types(session: Session) -> None:
    chain = FakeChain(_scenario(), head=103)
    repo.upsert_cursor(session, REGISTRY, anchor_block=100, last_indexed_block=99)
    session.commit()

    _run(session, chain, from_block=100)

    feedbacks = session.query(Feedback).order_by(Feedback.feedback_index).all()
    assert [f.feedback_index for f in feedbacks] == [0, 1]
    assert feedbacks[0].value == Decimal("80")
    assert feedbacks[0].value_scaled.quantize(Decimal("0.1")) == Decimal("8.0")  # 80 / 10^1
    assert feedbacks[1].value == Decimal("-5")  # signed int128
    assert feedbacks[0].client_address == CLIENT

    assert session.query(repo.FeedbackRevocation).count() == 1
    resp = session.query(repo.FeedbackResponse).one()
    assert resp.responder == RESPONDER
    assert resp.response_uri == "ipfs://resp"

    assert repo.get_cursor(session, REGISTRY).last_indexed_block == 103


def test_backfill_is_idempotent_on_replay(session: Session) -> None:
    chain = FakeChain(_scenario(), head=103)
    repo.upsert_cursor(session, REGISTRY, anchor_block=100, last_indexed_block=99)
    session.commit()

    _run(session, chain, from_block=100)
    counts = (
        session.query(Feedback).count(),
        session.query(repo.FeedbackRevocation).count(),
        session.query(repo.FeedbackResponse).count(),
        session.query(repo.RawLog).count(),
    )
    _run(session, chain, from_block=100)
    assert counts == (
        session.query(Feedback).count(),
        session.query(repo.FeedbackRevocation).count(),
        session.query(repo.FeedbackResponse).count(),
        session.query(repo.RawLog).count(),
    )

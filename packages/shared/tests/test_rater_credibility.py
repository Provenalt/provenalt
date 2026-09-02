"""Unit tests for rater-credibility computation (proposal §3.4)."""

from __future__ import annotations

from decimal import Decimal

import pytest
from sqlalchemy import text
from sqlalchemy.orm import Session

from provenalt_shared.db import Base, make_engine, make_session_factory
from provenalt_shared.db import repository as repo

OWNER_A = "0x1111111111111111111111111111111111111111"
OWNER_B = "0x2222222222222222222222222222222222222222"
CLIENT_C = "0x3333333333333333333333333333333333333333"
ZERO = "0x0000000000000000000000000000000000000000"


@pytest.fixture
def session() -> Session:
    engine = make_engine("sqlite://")
    Base.metadata.create_all(engine)
    with make_session_factory(engine)() as s:
        yield s


def _agent(s: Session, agent_id: int, owner: str, registered_block: int = 1) -> None:
    repo.upsert_agent(
        s,
        agent_id=agent_id,
        owner=owner,
        agent_uri="ipfs://x",
        registered_block=registered_block,
        registered_tx_hash=f"0x{agent_id:064x}",
        registered_log_index=0,
    )
    # Real indexing seeds a mint owner-history entry; block-height self-feedback needs it.
    repo.append_owner_history(
        s,
        agent_id=agent_id,
        from_address=ZERO,
        to_address=owner,
        block_number=registered_block,
        tx_hash=f"0xmint{agent_id}",
        log_index=0,
    )


def _transfer(s: Session, agent_id: int, frm: str, to: str, block: int) -> None:
    repo.append_owner_history(
        s,
        agent_id=agent_id,
        from_address=frm,
        to_address=to,
        block_number=block,
        tx_hash=f"0xt{agent_id}{block}",
        log_index=0,
    )
    repo.set_agent_owner(s, agent_id, to)


def _feedback(s: Session, agent_id: int, client: str, index: int, block: int) -> None:
    repo.insert_feedback(
        s,
        agent_id=agent_id,
        client_address=client,
        feedback_index=index,
        value=100,
        value_decimals=0,
        value_scaled=Decimal(100),
        indexed_tag1_hash="0x" + "00" * 32,
        tag1="",
        tag2="",
        endpoint="",
        feedback_uri="",
        feedback_hash="0x" + "00" * 32,
        block_number=block,
        tx_hash=f"0x{agent_id}{client[-4:]}{index}",
        log_index=index,
    )


def _seed(s: Session) -> None:
    _agent(s, 1, OWNER_A)
    _agent(s, 2, OWNER_B)
    # CLIENT_C rates agent 1 twice and agent 2 once (never self).
    _feedback(s, 1, CLIENT_C, index=0, block=100)
    _feedback(s, 1, CLIENT_C, index=1, block=110)
    _feedback(s, 2, CLIENT_C, index=0, block=120)
    # OWNER_A rates agent 1, which it owns → self-feedback.
    _feedback(s, 1, OWNER_A, index=0, block=105)
    s.commit()


def test_rater_credibility_metrics(session: Session) -> None:
    _seed(session)
    rows = {r.client_address: r for r in repo.rater_credibility_rows(session)}

    c = rows[CLIENT_C]
    assert c.first_seen_block == 100
    assert c.feedback_count == 3
    assert c.distinct_agents_rated == 2
    assert c.self_feedback_count == 0

    a = rows[OWNER_A]
    assert a.first_seen_block == 105
    assert a.feedback_count == 1
    assert a.distinct_agents_rated == 1
    assert a.self_feedback_count == 1  # rated an agent it owns


def test_self_feedback_uses_owner_at_block_not_current_owner(session: Session) -> None:
    """Regression: a rater who owned the agent when rating counts as self even after selling;
    the same rater's later feedback (after transfer) does not. Current-owner logic would miss
    the pre-transfer self-rating."""
    _agent(session, 1, OWNER_A, registered_block=1)
    _transfer(session, 1, OWNER_A, OWNER_B, block=200)
    # OWNER_A rated while owning it (block 100 → self) and again after selling (block 300 → not).
    _feedback(session, 1, OWNER_A, index=0, block=100)
    _feedback(session, 1, OWNER_A, index=1, block=300)
    # OWNER_B rates while owning it (block 300 → self).
    _feedback(session, 1, OWNER_B, index=0, block=300)
    session.commit()

    rows = {r.client_address: r for r in repo.rater_credibility_rows(session)}
    # Current owner is OWNER_B; the current-owner definition would give OWNER_A 0.
    assert rows[OWNER_A].self_feedback_count == 1
    assert rows[OWNER_B].self_feedback_count == 1


def test_value_scaled_is_stored_as_numeric(session: Session) -> None:
    _agent(session, 1, OWNER_A)
    repo.insert_feedback(
        session,
        agent_id=1,
        client_address=CLIENT_C,
        feedback_index=0,
        value=-12345,
        value_decimals=2,
        value_scaled=Decimal("-123.45"),
        indexed_tag1_hash="0x" + "00" * 32,
        tag1="q",
        tag2="",
        endpoint="",
        feedback_uri="",
        feedback_hash="0x" + "00" * 32,
        block_number=10,
        tx_hash="0xfeedback",
        log_index=0,
    )
    session.commit()
    fb = session.query(repo.Feedback).one()
    assert fb.value == Decimal("-12345")  # raw signed int128
    # NUMERIC is exact on Postgres (production); SQLite stores it as float, so compare at
    # the declared scale rather than bit-exact.
    assert fb.value_scaled.quantize(Decimal("0.01")) == Decimal("-123.45")


def test_view_sql_matches_the_core_select(session: Session) -> None:
    """The hand-written RATER_CREDIBILITY_SQL (used by the migration) must equal the
    Core select used by rater_credibility_rows."""
    _seed(session)
    session.execute(
        text(f"CREATE VIEW {repo.RATER_CREDIBILITY_VIEW} AS {repo.RATER_CREDIBILITY_SQL}")
    )

    view_rows = {
        r.client_address: (
            int(r.first_seen_block),
            int(r.feedback_count),
            int(r.distinct_agents_rated),
            int(r.self_feedback_count or 0),
        )
        for r in session.execute(text(f"SELECT * FROM {repo.RATER_CREDIBILITY_VIEW}"))
    }
    select_rows = {
        r.client_address: (
            r.first_seen_block,
            r.feedback_count,
            r.distinct_agents_rated,
            r.self_feedback_count,
        )
        for r in repo.rater_credibility_rows(session)
    }
    assert view_rows == select_rows

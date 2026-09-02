"""DB-backed scoring tests: gather (block-height self-feedback, circular), golden bands,
and the scoring pipeline (proposal §5.1–§5.5)."""

from __future__ import annotations

from decimal import Decimal

import pytest
from sqlalchemy.orm import Session

from provenalt_shared.db import Base, make_engine, make_session_factory
from provenalt_shared.db import repository as repo
from provenalt_shared.scoring import pipeline as scoring_pipeline
from provenalt_shared.scoring import score_agent
from provenalt_shared.scoring.inputs import gather_inputs
from provenalt_shared.scoring.ownership import ZERO_ADDRESS

DAY = 43_200
OWNER = "0x1111111111111111111111111111111111111111"
BUYER = "0x2222222222222222222222222222222222222222"


@pytest.fixture
def session() -> Session:
    engine = make_engine("sqlite://")
    Base.metadata.create_all(engine)
    with make_session_factory(engine)() as s:
        yield s


def _agent(
    s: Session, agent_id: int, owner: str, registered_block: int, uri: str = "ipfs://x"
) -> None:
    repo.upsert_agent(
        s,
        agent_id=agent_id,
        owner=owner,
        agent_uri=uri,
        registered_block=registered_block,
        registered_tx_hash=f"0x{agent_id:064x}",
        registered_log_index=0,
    )
    repo.append_owner_history(
        s,
        agent_id=agent_id,
        from_address=ZERO_ADDRESS,
        to_address=owner,
        block_number=registered_block,
        tx_hash=f"0xm{agent_id}",
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


def _card(
    s: Session,
    agent_id: int,
    *,
    fetch_status: str = "ok",
    schema_valid: bool = True,
    registration_match: bool = True,
    wallet_status: str = "match",
) -> None:
    repo.upsert_agent_card(
        s,
        agent_id=agent_id,
        token_uri="ipfs://x",
        fetch_status=fetch_status,
        schema_valid=schema_valid,
        registration_match=registration_match,
        wallet_status=wallet_status,
        content_hash="h",
    )


def _wallet(s: Session, agent_id: int, wallet: str, block: int) -> None:
    repo.insert_metadata(
        s,
        agent_id=agent_id,
        metadata_key="agentWallet",
        indexed_key_hash="0x" + "00" * 32,
        metadata_value=bytes.fromhex(wallet[2:]),
        block_number=block,
        tx_hash=f"0xw{agent_id}{block}",
        log_index=0,
    )


def _fb(s: Session, agent_id: int, client: str, index: int, block: int, value: str = "1") -> None:
    repo.insert_feedback(
        s,
        agent_id=agent_id,
        client_address=client,
        feedback_index=index,
        value=int(value),
        value_decimals=0,
        value_scaled=Decimal(value),
        indexed_tag1_hash="0x" + "00" * 32,
        tag1="",
        tag2="",
        endpoint="",
        feedback_uri="",
        feedback_hash="0x" + "00" * 32,
        block_number=block,
        tx_hash=f"0xf{agent_id}-{client[-4:]}-{index}-{block}",
        log_index=index,
    )


# ── self-feedback at block height (design note b) ─────────────────────────────


def test_self_feedback_judged_by_owner_at_feedback_block(session: Session) -> None:
    _agent(session, 1, OWNER, registered_block=0)
    _transfer(session, 1, OWNER, BUYER, block=500)
    # OWNER rated while owning it (block 400 → self) and after selling (600 → not self).
    _fb(session, 1, OWNER, index=0, block=400)
    _fb(session, 1, OWNER, index=1, block=600)
    session.commit()

    inputs = gather_inputs(session, 1, as_of_block=1000)
    by_index = {f.feedback_index: f for f in inputs.feedback}
    assert by_index[0].is_self is True  # OWNER owned it at block 400
    assert by_index[1].is_self is False  # BUYER owned it at block 600, not the rater


# ── circular feedback ─────────────────────────────────────────────────────────


def test_circular_feedback_detected_via_owner_reciprocity(session: Session) -> None:
    # Agent 1 owned by OWNER; agent 2 owned by BUYER.
    _agent(session, 1, OWNER, registered_block=0)
    _agent(session, 2, BUYER, registered_block=0)
    # OWNER rates agent 2 (owned by BUYER); BUYER rates agent 1 (owned by OWNER) → circular.
    _fb(session, 2, OWNER, index=0, block=100)
    _fb(session, 1, BUYER, index=0, block=110)
    session.commit()

    inputs = gather_inputs(session, 1, as_of_block=1000)
    assert inputs.feedback[0].client_address == BUYER
    assert inputs.feedback[0].is_circular is True


# ── golden fixtures (5.5) ─────────────────────────────────────────────────────


def _seed_credible_raters(
    s: Session, agent_id: int, count: int, at_block: int, fresh: bool, base: int
) -> None:
    # `base` gives each fixture a distinct rater-address range so rater history never leaks.
    for i in range(count):
        rater = f"0x{(base + i):040x}"
        if not fresh:
            # Prior feedback on another agent long ago → rater has history (credible).
            _fb(s, 700 + base + i, rater, index=0, block=at_block - 90 * DAY)
        _fb(s, agent_id, rater, index=1, block=at_block, value="1")


AS_OF = 100 * DAY


def test_golden_score_bands(session: Session) -> None:
    # established: old, valid card, aged wallet, credible positive feedback.
    _agent(session, 1, OWNER, registered_block=0)
    _card(session, 1)
    _wallet(session, 1, OWNER, block=0)
    _seed_credible_raters(session, 1, count=6, at_block=AS_OF, fresh=False, base=0x100000)

    # sybil-boosted: same but feedback from a burst of fresh raters.
    _agent(session, 2, OWNER, registered_block=0)
    _card(session, 2)
    _wallet(session, 2, OWNER, block=0)
    _seed_credible_raters(session, 2, count=6, at_block=AS_OF, fresh=True, base=0x200000)

    # transferred-ownership: established, but sold recently.
    _agent(session, 3, OWNER, registered_block=0)
    _card(session, 3)
    _wallet(session, 3, OWNER, block=0)
    _seed_credible_raters(session, 3, count=6, at_block=AS_OF, fresh=False, base=0x300000)
    _transfer(session, 3, OWNER, BUYER, block=AS_OF - 5 * DAY)

    # fresh: brand new, nothing indexed.
    _agent(session, 4, OWNER, registered_block=AS_OF - DAY)

    session.commit()

    established = score_agent(session, 1, AS_OF)
    sybil = score_agent(session, 2, AS_OF)
    transferred = score_agent(session, 3, AS_OF)
    fresh = score_agent(session, 4, AS_OF)

    assert established.score is not None and established.score >= 55
    assert established.confidence in ("medium", "high")

    # Sybil boosting does not pay off: reputation is discounted and the burst is flagged.
    assert established.score > sybil.score
    sybil_rep = next(c for c in sybil.components if c.name == "reputation")
    assert sybil_rep.detail["fresh_burst_flag"] is True

    # Recent transfer discounts longevity → lower than the untransferred twin.
    assert established.score > transferred.score
    transferred_long = next(c for c in transferred.components if c.name == "longevity")
    assert transferred_long.detail["recently_transferred"] is True

    # A bare fresh agent yields "insufficient data", not a confident number.
    assert fresh.confidence == "insufficient_data"
    assert fresh.sufficient is False


# ── pipeline (5.3) ────────────────────────────────────────────────────────────


def test_pipeline_persists_scores_and_drains_queue(session: Session) -> None:
    _agent(session, 1, OWNER, registered_block=0)
    _card(session, 1)
    _seed_credible_raters(session, 1, count=4, at_block=AS_OF, fresh=False, base=0x400000)
    session.commit()

    processed = scoring_pipeline.run_once(session, as_of_block=AS_OF)
    assert processed >= 1
    stored = repo.get_agent_score(session, 1)
    assert stored is not None
    assert stored.weights_version == "1"
    assert stored.breakdown  # component breakdown persisted
    assert repo.list_pending_score_refresh(session) == []


def test_agents_needing_score_refresh_new_then_activity(session: Session) -> None:
    _agent(session, 1, OWNER, registered_block=0)
    session.commit()
    # No score yet → new_agent.
    assert repo.agents_needing_score_refresh(session) == [(1, "new_agent")]

    scoring_pipeline.persist_score(session, 1, as_of_block=100)
    session.commit()
    assert repo.agents_needing_score_refresh(session) == []  # up to date

    # New feedback after the scored block → activity.
    _fb(session, 1, BUYER, index=0, block=500)
    session.commit()
    assert repo.agents_needing_score_refresh(session) == [(1, "activity")]


def test_score_agent_returns_none_for_unknown_agent(session: Session) -> None:
    assert score_agent(session, 999, AS_OF) is None
    assert gather_inputs(session, 999, AS_OF) is None

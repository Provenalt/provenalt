"""Pure unit tests for scoring: ownership helpers, components, and the engine (no DB)."""

from __future__ import annotations

from decimal import Decimal

from provenalt_shared.scoring import compute_score
from provenalt_shared.scoring.components import (
    score_card_integrity,
    score_longevity,
    score_reputation,
    score_wallet_behavior,
)
from provenalt_shared.scoring.ownership import (
    ZERO_ADDRESS,
    last_transfer_block,
    owner_at_block,
)
from provenalt_shared.scoring.types import AgentScoringInputs, FeedbackInput, OwnerChange
from provenalt_shared.scoring.weights import default_weights

W = default_weights()
DAY = 43_200
OWNER = "0x1111111111111111111111111111111111111111"
BUYER = "0x2222222222222222222222222222222222222222"
RATER = "0x3333333333333333333333333333333333333333"


# ── ownership (design note b) ─────────────────────────────────────────────────


def _history() -> list[OwnerChange]:
    return [
        OwnerChange(ZERO_ADDRESS, OWNER, block_number=100, log_index=0),  # mint
        OwnerChange(OWNER, BUYER, block_number=500, log_index=0),  # transfer
    ]


def test_owner_at_block_returns_owner_at_that_height() -> None:
    hist = _history()
    assert owner_at_block(hist, 100) == OWNER  # right after mint
    assert owner_at_block(hist, 499) == OWNER  # before transfer
    assert owner_at_block(hist, 500) == BUYER  # at transfer
    assert owner_at_block(hist, 9999) == BUYER  # after
    assert owner_at_block(hist, 50) is None  # before mint


def test_last_transfer_block_excludes_mint() -> None:
    assert last_transfer_block(_history()) == 500
    mint_only = [OwnerChange(ZERO_ADDRESS, OWNER, 100, 0)]
    assert last_transfer_block(mint_only) is None


# ── longevity ─────────────────────────────────────────────────────────────────


def test_longevity_grows_with_age() -> None:
    young = AgentScoringInputs(agent_id=1, as_of_block=100 + DAY, registered_block=100)
    old = AgentScoringInputs(agent_id=1, as_of_block=100 + 400 * DAY, registered_block=100)
    assert score_longevity(old, W).value > score_longevity(young, W).value


def test_longevity_discounted_by_recent_transfer() -> None:
    base = AgentScoringInputs(agent_id=1, as_of_block=100 + 200 * DAY, registered_block=100)
    transferred = AgentScoringInputs(
        agent_id=1,
        as_of_block=100 + 200 * DAY,
        registered_block=100,
        last_transfer_block=100 + 200 * DAY - 5 * DAY,  # 5 days ago → within window
    )
    assert score_longevity(transferred, W).value < score_longevity(base, W).value


# ── card integrity (design note a) ────────────────────────────────────────────


def _card_inputs(**kw: object) -> AgentScoringInputs:
    defaults = dict(
        agent_id=1,
        as_of_block=1000,
        registered_block=0,
        has_card=True,
        card_fetch_ok=True,
        schema_valid=True,
        registration_match=True,
        wallet_status="match",
    )
    defaults.update(kw)
    return AgentScoringInputs(**defaults)  # type: ignore[arg-type]


def test_registration_match_weighs_far_more_than_wallet() -> None:
    # A wallet mismatch costs little; a registration mismatch costs a lot.
    wallet_bad = score_card_integrity(_card_inputs(wallet_status="mismatch"), W).value
    reg_bad = score_card_integrity(_card_inputs(registration_match=False), W).value
    full = score_card_integrity(_card_inputs(), W).value
    assert (full - wallet_bad) < (full - reg_bad)
    assert (full - wallet_bad) < 0.1  # wallet mismatch is a light ding


def test_card_not_declared_wallet_is_neutral() -> None:
    declared = score_card_integrity(_card_inputs(wallet_status="match"), W).value
    not_declared = score_card_integrity(_card_inputs(wallet_status="not_declared"), W).value
    assert not_declared < declared  # neutral 0.5, below a positive match
    assert not_declared > score_card_integrity(_card_inputs(wallet_status="mismatch"), W).value


def test_card_unavailable_when_never_fetched() -> None:
    result = score_card_integrity(_card_inputs(has_card=False), W)
    assert result.available is False


def test_drift_penalises_card_integrity() -> None:
    clean = score_card_integrity(_card_inputs(drift_count=0), W).value
    drifted = score_card_integrity(_card_inputs(drift_count=3), W).value
    assert drifted < clean


# ── reputation & sybil ────────────────────────────────────────────────────────


def _fb(client: str, block: int, value: str = "1", **kw: object) -> FeedbackInput:
    return FeedbackInput(
        client_address=client, feedback_index=0, value=Decimal(value), block_number=block, **kw
    )  # type: ignore[arg-type]


def test_reputation_excludes_self_feedback() -> None:
    inputs = AgentScoringInputs(
        agent_id=1,
        as_of_block=10 * DAY,
        registered_block=0,
        feedback=[_fb(OWNER, 5 * DAY, is_self=True, rater_first_seen_block=0)],
    )
    result = score_reputation(inputs, W)
    assert result.available is False  # only self-feedback → no credible feedback
    assert result.detail["self_excluded"] == 1


def test_reputation_per_rater_cap_limits_influence() -> None:
    block = 100 * DAY
    many_from_one = AgentScoringInputs(
        agent_id=1,
        as_of_block=block,
        registered_block=0,
        feedback=[
            _fb(RATER, block - 50 * DAY, rater_first_seen_block=0, rater_total_count=20)
            for _ in range(20)
        ],
    )
    result = score_reputation(many_from_one, W)
    assert result.detail["credible_feedback"] == W.per_rater_cap  # capped


def test_reputation_fresh_rater_burst_is_flagged_and_discounted() -> None:
    block = 100 * DAY
    # 6 distinct raters, all first seen right at the feedback block, each with 1 total → fresh.
    fresh = AgentScoringInputs(
        agent_id=1,
        as_of_block=block,
        registered_block=0,
        feedback=[
            _fb(f"0x{i:040x}", block, rater_first_seen_block=block, rater_total_count=1)
            for i in range(6)
        ],
    )
    established = AgentScoringInputs(
        agent_id=1,
        as_of_block=block,
        registered_block=0,
        feedback=[
            _fb(f"0x{i:040x}", block, rater_first_seen_block=0, rater_total_count=50)
            for i in range(6)
        ],
    )
    fresh_result = score_reputation(fresh, W)
    assert fresh_result.detail["fresh_burst_flag"] is True
    assert fresh_result.value < score_reputation(established, W).value


def test_circular_feedback_is_discounted() -> None:
    block = 100 * DAY
    normal = AgentScoringInputs(
        agent_id=1,
        as_of_block=block,
        registered_block=0,
        feedback=[_fb(RATER, block, rater_first_seen_block=0, rater_total_count=50)],
    )
    circular = AgentScoringInputs(
        agent_id=1,
        as_of_block=block,
        registered_block=0,
        feedback=[
            _fb(RATER, block, rater_first_seen_block=0, rater_total_count=50, is_circular=True)
        ],
    )
    assert score_reputation(circular, W).value < score_reputation(normal, W).value
    assert score_reputation(circular, W).detail["circular_flag"] is True


# ── wallet behavior ───────────────────────────────────────────────────────────


def test_wallet_behavior_unavailable_when_not_set() -> None:
    inputs = AgentScoringInputs(
        agent_id=1, as_of_block=1000, registered_block=0, agent_wallet_set=False
    )
    assert score_wallet_behavior(inputs, W).available is False


# ── engine ────────────────────────────────────────────────────────────────────


def test_compute_score_insufficient_data_for_bare_agent() -> None:
    bare = AgentScoringInputs(agent_id=1, as_of_block=1000, registered_block=900)
    result = compute_score(bare, W)
    assert result.confidence == "insufficient_data"
    assert result.sufficient is False


def test_compute_score_renormalises_over_available_components() -> None:
    # Only longevity available (no card, no feedback, no wallet) → score reflects longevity alone.
    inputs = AgentScoringInputs(agent_id=1, as_of_block=100 + 400 * DAY, registered_block=100)
    result = compute_score(inputs, W)
    longevity = next(c for c in result.components if c.name == "longevity")
    assert result.score == round(longevity.value * 100)
    assert result.weights_version == "1"


def test_compute_score_is_bounded_0_100() -> None:
    block = 500 * DAY
    inputs = AgentScoringInputs(
        agent_id=1,
        as_of_block=block,
        registered_block=0,
        has_card=True,
        card_fetch_ok=True,
        schema_valid=True,
        registration_match=True,
        wallet_status="match",
        agent_wallet_set=True,
        agent_wallet_set_block=0,
        feedback=[
            _fb(f"0x{i:040x}", block - 100 * DAY, rater_first_seen_block=0, rater_total_count=50)
            for i in range(12)
        ],
    )
    result = compute_score(inputs, W)
    assert result.score is not None
    assert 0 <= result.score <= 100
    assert result.confidence == "high"

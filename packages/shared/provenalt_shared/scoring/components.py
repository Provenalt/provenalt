"""Pure component scoring functions over ``AgentScoringInputs`` (proposal §6).

Each returns a :class:`ComponentScore` with a normalised value in ``[0, 1]``, its top-level
weight, an ``available`` flag (unavailable components are excluded and their weight
re-normalised by the engine), and a detail dict for the published breakdown.
"""

from __future__ import annotations

from collections import defaultdict

from provenalt_shared.scoring.types import (
    AgentScoringInputs,
    ComponentScore,
    FeedbackInput,
)
from provenalt_shared.scoring.weights import ScoringWeights


def _clamp(value: float, low: float, high: float) -> float:
    return max(low, min(high, value))


def score_longevity(inputs: AgentScoringInputs, w: ScoringWeights) -> ComponentScore:
    age = max(0, inputs.as_of_block - inputs.registered_block)
    base = age / (age + w.longevity_half_life_blocks) if age > 0 else 0.0

    recently_transferred = (
        inputs.last_transfer_block is not None
        and (inputs.as_of_block - inputs.last_transfer_block) <= w.recent_transfer_window_blocks
    )
    discount = w.recent_transfer_discount if recently_transferred else 1.0
    value = base * discount
    return ComponentScore(
        "longevity",
        value,
        w.longevity,
        available=True,
        detail={
            "age_blocks": age,
            "recently_transferred": recently_transferred,
            "last_transfer_block": inputs.last_transfer_block,
        },
    )


def score_card_integrity(inputs: AgentScoringInputs, w: ScoringWeights) -> ComponentScore:
    if not inputs.has_card:
        return ComponentScore(
            "card_integrity",
            0.0,
            w.card_integrity,
            available=False,
            detail={"reason": "no card fetched yet"},
        )

    cw = w.card
    fetch_ok = 1.0 if inputs.card_fetch_ok else 0.0
    schema = 1.0 if inputs.schema_valid else 0.0
    reg = 1.0 if inputs.registration_match else 0.0
    # Heuristic wallet check: only a clear mismatch dings; unknown states are neutral.
    wallet = {
        "match": 1.0,
        "not_declared": 0.5,
        "wallet_not_set": 0.5,
        "mismatch": 0.0,
    }.get(inputs.wallet_status or "", 0.5)

    total_w = cw.fetch + cw.schema + cw.registration_match + cw.wallet
    raw = (
        cw.fetch * fetch_ok + cw.schema * schema + cw.registration_match * reg + cw.wallet * wallet
    ) / total_w
    drift_penalty = min(cw.max_drift_penalty, inputs.drift_count * cw.drift_penalty_per_event)
    value = max(0.0, raw - drift_penalty)
    return ComponentScore(
        "card_integrity",
        value,
        w.card_integrity,
        available=True,
        detail={
            "fetch_ok": bool(inputs.card_fetch_ok),
            "schema_valid": inputs.schema_valid,
            "registration_match": inputs.registration_match,
            "wallet_status": inputs.wallet_status,
            "drift_penalty": drift_penalty,
        },
    )


def _rater_credibility(f: FeedbackInput, w: ScoringWeights) -> float:
    history = max(0, f.block_number - f.rater_first_seen_block)
    return _clamp(history / w.rater_full_credibility_blocks, w.rater_min_credibility, 1.0)


def _is_fresh(f: FeedbackInput, w: ScoringWeights) -> bool:
    history = f.block_number - f.rater_first_seen_block
    return (
        history <= w.fresh_rater_history_blocks and f.rater_total_count <= w.fresh_rater_max_total
    )


def score_reputation(inputs: AgentScoringInputs, w: ScoringWeights) -> ComponentScore:
    # Exclude revoked and self-feedback (self judged at the feedback's block height).
    valid = [f for f in inputs.feedback if not f.revoked and not f.is_self]
    if not valid:
        return ComponentScore(
            "reputation",
            0.0,
            w.reputation,
            available=False,
            detail={
                "reason": "no credible feedback",
                "self_excluded": sum(1 for f in inputs.feedback if f.is_self),
            },
        )

    by_rater: dict[str, list[FeedbackInput]] = defaultdict(list)
    for f in valid:
        by_rater[f.client_address.lower()].append(f)

    weighted_pos = 0.0
    weighted_neg = 0.0
    fresh_count = 0
    circular_count = 0
    counted = 0
    for entries in by_rater.values():
        capped = sorted(entries, key=lambda f: f.block_number)[: w.per_rater_cap]
        for f in capped:
            counted += 1
            cred = _rater_credibility(f, w)
            if _is_fresh(f, w):
                fresh_count += 1
            if f.is_circular:
                circular_count += 1
                cred *= w.circular_discount
            polarity = _clamp(float(f.value), -1.0, 1.0)
            if polarity >= 0:
                weighted_pos += cred * polarity
            else:
                weighted_neg += cred * (-polarity)

    net = weighted_pos - weighted_neg
    value = net / (net + w.reputation_saturation) if net > 0 else 0.0

    fresh_burst = (
        fresh_count >= w.fresh_burst_min_count
        and counted > 0
        and fresh_count / counted >= w.fresh_burst_share
    )
    if fresh_burst:
        value *= w.fresh_burst_discount

    return ComponentScore(
        "reputation",
        value,
        w.reputation,
        available=True,
        detail={
            "credible_feedback": counted,
            "fresh_raters": fresh_count,
            "fresh_burst_flag": fresh_burst,
            "circular_flag": circular_count > 0,
            "self_excluded": sum(1 for f in inputs.feedback if f.is_self),
            "weighted_positive": round(weighted_pos, 4),
            "weighted_negative": round(weighted_neg, 4),
        },
    )


def score_revocations_responses(inputs: AgentScoringInputs, w: ScoringWeights) -> ComponentScore:
    total = len(inputs.feedback)
    if total == 0:
        return ComponentScore(
            "revocations_responses",
            0.0,
            w.revocations_responses,
            available=False,
            detail={"reason": "no feedback"},
        )
    revoked = sum(1 for f in inputs.feedback if f.revoked)
    responded = sum(1 for f in inputs.feedback if f.responded)
    value = _clamp(0.5 + 0.5 * (responded / total) - 0.5 * (revoked / total), 0.0, 1.0)
    return ComponentScore(
        "revocations_responses",
        value,
        w.revocations_responses,
        available=True,
        detail={"total": total, "revoked": revoked, "responded": responded},
    )


def score_wallet_behavior(inputs: AgentScoringInputs, w: ScoringWeights) -> ComponentScore:
    if not inputs.agent_wallet_set or inputs.agent_wallet_set_block is None:
        return ComponentScore(
            "wallet_behavior",
            0.0,
            w.wallet_behavior,
            available=False,
            detail={
                "reason": "agentWallet not set; tx diversity / flagged contracts not indexed in v1"
            },
        )
    age = max(0, inputs.as_of_block - inputs.agent_wallet_set_block)
    value = 0.5 + 0.5 * (age / (age + w.wallet_full_age_blocks))
    return ComponentScore(
        "wallet_behavior",
        value,
        w.wallet_behavior,
        available=True,
        detail={"agent_wallet_age_blocks": age, "note": "v1: presence + age only"},
    )


def score_validation(inputs: AgentScoringInputs, w: ScoringWeights) -> ComponentScore:
    return ComponentScore(
        "validation",
        0.0,
        w.validation,
        available=False,
        detail={"reason": "Validation Registry not deployed (reserved)"},
    )


ALL_COMPONENTS = (
    score_longevity,
    score_card_integrity,
    score_reputation,
    score_revocations_responses,
    score_wallet_behavior,
    score_validation,
)

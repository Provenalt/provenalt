"""Configurable, versioned scoring weights (proposal §6; published in METHODOLOGY.md).

Block-based durations assume Base's ~2s block time (~43,200 blocks/day). Bump
``WEIGHTS_VERSION`` whenever any weight or parameter changes so persisted scores remain
traceable to the methodology that produced them.
"""

from __future__ import annotations

from dataclasses import dataclass, field

WEIGHTS_VERSION = "1"

_BLOCKS_PER_DAY = 43_200


@dataclass(frozen=True)
class CardIntegrityWeights:
    """Sub-weights within the card-integrity component.

    ``registration_match`` is weighted heavily and ``wallet`` lightly: the registrations[]
    binding is authoritative, while the agentWallet-vs-card check is heuristic and can
    produce false mismatches (operator design note).
    """

    fetch: float = 0.25
    schema: float = 0.25
    registration_match: float = 0.45
    wallet: float = 0.05
    drift_penalty_per_event: float = 0.1
    max_drift_penalty: float = 0.5


@dataclass(frozen=True)
class ScoringWeights:
    # Top-level component weights (validation reserved at 0 until the registry ships).
    longevity: float = 0.20
    card_integrity: float = 0.20
    reputation: float = 0.35
    revocations_responses: float = 0.10
    wallet_behavior: float = 0.15
    validation: float = 0.0

    card: CardIntegrityWeights = field(default_factory=CardIntegrityWeights)

    # Longevity
    longevity_half_life_blocks: int = 90 * _BLOCKS_PER_DAY
    recent_transfer_window_blocks: int = 30 * _BLOCKS_PER_DAY
    recent_transfer_discount: float = 0.5

    # Reputation / sybil
    per_rater_cap: int = 3
    rater_full_credibility_blocks: int = 30 * _BLOCKS_PER_DAY
    rater_min_credibility: float = 0.1
    fresh_rater_history_blocks: int = 1 * _BLOCKS_PER_DAY
    fresh_rater_max_total: int = 2
    fresh_burst_min_count: int = 3
    fresh_burst_share: float = 0.5
    fresh_burst_discount: float = 0.3
    circular_discount: float = 0.2
    reputation_saturation: float = 5.0

    # Wallet behavior (v1 uses agentWallet presence + age only)
    wallet_full_age_blocks: int = 30 * _BLOCKS_PER_DAY

    # Confidence thresholds (credible feedback count)
    confidence_low_max: int = 3
    confidence_medium_max: int = 10


def default_weights() -> ScoringWeights:
    return ScoringWeights()

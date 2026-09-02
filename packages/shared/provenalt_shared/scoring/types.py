"""Pure dataclasses for scoring inputs and outputs (no DB, no I/O)."""

from __future__ import annotations

from dataclasses import dataclass, field
from decimal import Decimal


@dataclass(frozen=True)
class OwnerChange:
    """One ownership-history entry (Registered mint or Transfer)."""

    from_address: str
    to_address: str
    block_number: int
    log_index: int


@dataclass(frozen=True)
class FeedbackInput:
    """One feedback entry on the agent being scored, enriched with rater history + flags."""

    client_address: str
    feedback_index: int
    value: Decimal
    block_number: int
    revoked: bool = False
    responded: bool = False
    # Rater's own history across all agents (for credibility / sybil heuristics).
    rater_first_seen_block: int = 0
    rater_total_count: int = 1
    # Flags resolved during gather (block-height correct).
    is_self: bool = False
    is_circular: bool = False


@dataclass(frozen=True)
class AgentScoringInputs:
    """Everything a pure score computation needs for one agent."""

    agent_id: int
    as_of_block: int
    registered_block: int
    last_transfer_block: int | None = None
    has_card: bool = False
    card_fetch_ok: bool = False
    schema_valid: bool | None = None
    registration_match: bool | None = None
    wallet_status: str | None = None
    drift_count: int = 0
    agent_wallet_set: bool = False
    agent_wallet_set_block: int | None = None
    feedback: list[FeedbackInput] = field(default_factory=list)


@dataclass(frozen=True)
class ComponentScore:
    name: str
    value: float  # normalised 0..1
    weight: float
    available: bool
    detail: dict[str, object] = field(default_factory=dict)


@dataclass(frozen=True)
class ScoreResult:
    agent_id: int
    score: int | None  # 0..100, or None if no component is available
    confidence: str  # insufficient_data | low | medium | high
    sufficient: bool
    components: list[ComponentScore]
    weights_version: str
    as_of_block: int

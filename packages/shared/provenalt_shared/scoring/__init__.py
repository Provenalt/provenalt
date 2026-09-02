"""Provenalt Score v1 — transparent, heuristic agent scoring (proposal §6).

Layers:
    * ``weights``    — configurable, versioned component weights (published in METHODOLOGY.md).
    * ``types``      — pure input/output dataclasses.
    * ``ownership``  — pure ownership-at-block helpers (transfer recency, self-feedback).
    * ``components`` — pure component scoring functions over the input dataclasses.
    * ``engine``     — pure ``compute_score`` + DB-backed ``score_agent``.
    * ``inputs``     — gather ``AgentScoringInputs`` from DB state.
    * ``pipeline``   — persist scores + refresh queue (event-driven + nightly sweep).
"""

from provenalt_shared.scoring.engine import compute_score, score_agent
from provenalt_shared.scoring.types import (
    AgentScoringInputs,
    ComponentScore,
    FeedbackInput,
    OwnerChange,
    ScoreResult,
)
from provenalt_shared.scoring.weights import WEIGHTS_VERSION, ScoringWeights, default_weights

__all__ = [
    "compute_score",
    "score_agent",
    "AgentScoringInputs",
    "ComponentScore",
    "FeedbackInput",
    "OwnerChange",
    "ScoreResult",
    "ScoringWeights",
    "WEIGHTS_VERSION",
    "default_weights",
]

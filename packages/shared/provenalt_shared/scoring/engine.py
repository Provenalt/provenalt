"""Score computation: pure ``compute_score`` and DB-backed ``score_agent`` (proposal §6)."""

from __future__ import annotations

from typing import TYPE_CHECKING

from provenalt_shared.scoring.components import ALL_COMPONENTS
from provenalt_shared.scoring.types import AgentScoringInputs, ScoreResult
from provenalt_shared.scoring.weights import WEIGHTS_VERSION, ScoringWeights, default_weights

if TYPE_CHECKING:
    from sqlalchemy.orm import Session


def _confidence(inputs: AgentScoringInputs, w: ScoringWeights) -> str:
    credible = sum(1 for f in inputs.feedback if not f.revoked and not f.is_self)
    has_ok_card = inputs.has_card and inputs.card_fetch_ok
    if credible == 0 and not has_ok_card:
        return "insufficient_data"
    if credible < w.confidence_low_max:
        return "low"
    if credible < w.confidence_medium_max:
        return "medium"
    return "high"


def compute_score(inputs: AgentScoringInputs, weights: ScoringWeights | None = None) -> ScoreResult:
    """Pure: compute the 0–100 score, confidence, and per-component breakdown."""
    w = weights or default_weights()
    components = [fn(inputs, w) for fn in ALL_COMPONENTS]

    contributing = [c for c in components if c.available and c.weight > 0]
    total_weight = sum(c.weight for c in contributing)
    if total_weight <= 0:
        score: int | None = None
    else:
        weighted = sum(c.weight * c.value for c in contributing) / total_weight
        score = round(weighted * 100)

    confidence = _confidence(inputs, w)
    return ScoreResult(
        agent_id=inputs.agent_id,
        score=score,
        confidence=confidence,
        sufficient=confidence != "insufficient_data",
        components=components,
        weights_version=WEIGHTS_VERSION,
        as_of_block=inputs.as_of_block,
    )


def score_agent(
    session: Session,
    agent_id: int,
    as_of_block: int,
    weights: ScoringWeights | None = None,
) -> ScoreResult | None:
    """Gather inputs from DB and compute the score. Returns ``None`` if the agent is unknown."""
    from provenalt_shared.scoring.inputs import gather_inputs

    inputs = gather_inputs(session, agent_id, as_of_block)
    if inputs is None:
        return None
    return compute_score(inputs, weights)

"""Gated score endpoints (x402 tier, proposal §7): full breakdown + compact verdict."""

from __future__ import annotations

from fastapi import APIRouter, HTTPException, status

from provenalt_api import queries
from provenalt_api.deps import SessionDep
from provenalt_api.schemas import ProvenaltVerdict, ScoreDetail

router = APIRouter(prefix="/v1", tags=["score"])


def verdict_for(score: int | None, confidence: str) -> str:
    if score is None or confidence == "insufficient_data":
        return "insufficient"
    if score >= 70:
        return "pass"
    if score >= 45:
        return "warn"
    return "fail"


@router.get(
    "/agents/{agent_id}/score",
    response_model=ScoreDetail,
    summary="Provenalt Score with per-component breakdown (x402-gated)",
)
def get_score(agent_id: int, session: SessionDep) -> ScoreDetail:
    if queries.get_agent(session, agent_id) is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="agent not found")
    score = queries.get_score(session, agent_id)
    if score is None:
        return ScoreDetail(
            agent_id=agent_id,
            score=None,
            confidence="insufficient_data",
            sufficient=False,
            weights_version="1",
            as_of_block=0,
            breakdown=[],
        )
    return ScoreDetail(
        agent_id=agent_id,
        score=score.score,
        confidence=score.confidence,
        sufficient=score.sufficient,
        weights_version=score.weights_version,
        as_of_block=score.as_of_block,
        breakdown=list(score.breakdown),
    )


@router.get(
    "/provenalt/{agent_id}",
    response_model=ProvenaltVerdict,
    summary="Compact pass/warn/fail verdict (x402-gated)",
)
def get_verdict(agent_id: int, session: SessionDep) -> ProvenaltVerdict:
    if queries.get_agent(session, agent_id) is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="agent not found")
    score = queries.get_score(session, agent_id)
    if score is None:
        return ProvenaltVerdict(
            agent_id=agent_id, verdict="insufficient", score=None, confidence="insufficient_data"
        )
    return ProvenaltVerdict(
        agent_id=agent_id,
        verdict=verdict_for(score.score, score.confidence),
        score=score.score,
        confidence=score.confidence,
    )

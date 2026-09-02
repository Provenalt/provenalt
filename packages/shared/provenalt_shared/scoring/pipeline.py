"""Score persistence + recompute triggers (proposal §5.3).

The refresh queue is fed event-driven (agents that are new or have had on-chain activity —
feedback / ownership change — since their last score) and by a periodic full sweep. Processing
computes the score for the frontier block and persists it with its breakdown.
"""

from __future__ import annotations

from dataclasses import asdict
from typing import TYPE_CHECKING

from provenalt_shared.db import repository as repo
from provenalt_shared.scoring.engine import score_agent
from provenalt_shared.scoring.weights import ScoringWeights

if TYPE_CHECKING:
    from sqlalchemy.orm import Session


def persist_score(
    session: Session, agent_id: int, as_of_block: int, weights: ScoringWeights | None = None
) -> bool:
    """Compute and persist one agent's score. Returns False if the agent is unknown."""
    result = score_agent(session, agent_id, as_of_block, weights)
    if result is None:
        return False
    repo.upsert_agent_score(
        session,
        agent_id=agent_id,
        score=result.score,
        confidence=result.confidence,
        sufficient=result.sufficient,
        breakdown=[asdict(c) for c in result.components],
        weights_version=result.weights_version,
        as_of_block=as_of_block,
    )
    return True


def enqueue_pending(session: Session) -> int:
    """Enqueue agents that need rescoring (new or with activity since last score)."""
    count = 0
    for agent_id, reason in repo.agents_needing_score_refresh(session):
        if repo.enqueue_score_refresh(session, agent_id, reason):
            count += 1
    return count


def process_queue(
    session: Session,
    as_of_block: int,
    weights: ScoringWeights | None = None,
    limit: int = 100,
) -> int:
    pending = repo.list_pending_score_refresh(session, limit=limit)
    for entry in pending:
        persist_score(session, entry.agent_id, as_of_block, weights)
        repo.delete_score_refresh(session, entry.agent_id)
    session.commit()
    return len(pending)


def run_once(
    session: Session,
    as_of_block: int | None = None,
    weights: ScoringWeights | None = None,
    limit: int = 100,
) -> int:
    """One pass: enqueue stale agents, then rescore the queue. Returns count processed."""
    block = as_of_block if as_of_block is not None else repo.max_indexed_block(session)
    enqueue_pending(session)
    session.commit()
    return process_queue(session, block, weights, limit=limit)

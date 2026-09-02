"""Read queries for the public API — pure DB reads over the shared models."""

from __future__ import annotations

from typing import TYPE_CHECKING

from provenalt_shared.db import (
    Agent,
    AgentCard,
    AgentMetadata,
    AgentOwnerHistory,
    AgentScore,
    Feedback,
    FeedbackResponse,
    FeedbackRevocation,
    IndexerCursor,
)
from sqlalchemy import Integer, cast, func, select

if TYPE_CHECKING:
    from sqlalchemy.orm import Session


def list_agents(
    session: Session, *, limit: int, offset: int, owner: str | None = None
) -> tuple[list[tuple[Agent, int | None, str | None]], int]:
    """Return a page of (agent, score, confidence) plus the total count.

    Optionally filtered by ``owner`` (case-insensitive). Ordered by agent_id.
    """
    where = []
    if owner is not None:
        where.append(Agent.owner == owner.lower())

    total = session.execute(select(func.count()).select_from(Agent).where(*where)).scalar_one()

    rows = session.execute(
        select(Agent, AgentScore.score, AgentScore.confidence)
        .outerjoin(AgentScore, AgentScore.agent_id == Agent.agent_id)
        .where(*where)
        .order_by(Agent.agent_id)
        .limit(limit)
        .offset(offset)
    ).all()
    return [(agent, score, confidence) for agent, score, confidence in rows], int(total)


def get_agent(session: Session, agent_id: int) -> Agent | None:
    return session.get(Agent, agent_id)


def get_card(session: Session, agent_id: int) -> AgentCard | None:
    return session.get(AgentCard, agent_id)


def get_score(session: Session, agent_id: int) -> AgentScore | None:
    return session.get(AgentScore, agent_id)


def agent_metadata(session: Session, agent_id: int) -> list[AgentMetadata]:
    return list(
        session.execute(
            select(AgentMetadata)
            .where(AgentMetadata.agent_id == agent_id)
            .order_by(AgentMetadata.block_number, AgentMetadata.log_index)
        ).scalars()
    )


def owner_history(session: Session, agent_id: int) -> list[AgentOwnerHistory]:
    return list(
        session.execute(
            select(AgentOwnerHistory)
            .where(AgentOwnerHistory.agent_id == agent_id)
            .order_by(AgentOwnerHistory.block_number, AgentOwnerHistory.log_index)
        ).scalars()
    )


def list_feedback(
    session: Session, agent_id: int, *, limit: int, offset: int
) -> tuple[list[Feedback], int, set[tuple[str, int]], set[tuple[str, int]]]:
    """A page of feedback for an agent plus total, and the revoked/responded key sets."""
    total = session.execute(
        select(func.count()).select_from(Feedback).where(Feedback.agent_id == agent_id)
    ).scalar_one()
    rows = list(
        session.execute(
            select(Feedback)
            .where(Feedback.agent_id == agent_id)
            .order_by(Feedback.block_number, Feedback.log_index)
            .limit(limit)
            .offset(offset)
        ).scalars()
    )
    revoked = {
        (r.client_address, r.feedback_index)
        for r in session.execute(
            select(FeedbackRevocation).where(FeedbackRevocation.agent_id == agent_id)
        ).scalars()
    }
    responded = {
        (r.client_address, r.feedback_index)
        for r in session.execute(
            select(FeedbackResponse).where(FeedbackResponse.agent_id == agent_id)
        ).scalars()
    }
    return rows, int(total), revoked, responded


def growth_series(session: Session, buckets: int = 24) -> list[tuple[int, int]]:
    """Cumulative registered-agent count bucketed by registration block (registry growth, §7).

    Returns ``[(block, cumulative_agents), ...]`` — a compact series derived from
    ``agents.registered_block`` (no timestamps needed).
    """
    lo, hi, total = session.execute(
        select(
            func.min(Agent.registered_block),
            func.max(Agent.registered_block),
            func.count(),
        ).select_from(Agent)
    ).one()
    if not total or lo is None or hi is None:
        return []
    if hi == lo:
        return [(int(hi), int(total))]

    width = max(1, (int(hi) - int(lo)) // buckets)
    bucket = cast((Agent.registered_block - lo) / width, Integer)
    rows = session.execute(
        select(bucket.label("b"), func.count()).group_by(bucket).order_by(bucket)
    ).all()

    out: list[tuple[int, int]] = []
    cumulative = 0
    for b, count in rows:
        cumulative += int(count)
        block_end = min(int(lo) + (int(b) + 1) * width, int(hi))
        out.append((block_end, cumulative))
    return out


def stats(session: Session) -> dict[str, object]:
    total_agents = session.execute(select(func.count()).select_from(Agent)).scalar_one()
    max_agent_id = session.execute(select(func.max(Agent.agent_id))).scalar_one_or_none()
    total_feedback = session.execute(select(func.count()).select_from(Feedback)).scalar_one()
    total_scored = session.execute(select(func.count()).select_from(AgentScore)).scalar_one()
    total_cards = session.execute(select(func.count()).select_from(AgentCard)).scalar_one()
    cursors = list(
        session.execute(select(IndexerCursor).order_by(IndexerCursor.registry_name)).scalars()
    )
    return {
        "total_agents": int(total_agents),
        "max_agent_id": int(max_agent_id) if max_agent_id is not None else None,
        "total_feedback": int(total_feedback),
        "total_scored": int(total_scored),
        "total_cards": int(total_cards),
        "cursors": cursors,
        "growth": growth_series(session),
    }

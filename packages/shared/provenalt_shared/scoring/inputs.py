"""Gather ``AgentScoringInputs`` from DB state (proposal §5.1).

This is the only DB-aware part of scoring; the component functions and the engine are pure.
Self-feedback and circular-feedback flags are resolved here (block-height correct) so the
pure layer stays simple.
"""

from __future__ import annotations

from typing import TYPE_CHECKING

from sqlalchemy import func, select

from provenalt_shared.db.models import (
    Agent,
    AgentCard,
    AgentMetadata,
    AgentOwnerHistory,
    CardDrift,
    Feedback,
    FeedbackResponse,
    FeedbackRevocation,
)
from provenalt_shared.scoring.ownership import last_transfer_block, owner_at_block
from provenalt_shared.scoring.types import AgentScoringInputs, FeedbackInput, OwnerChange

if TYPE_CHECKING:
    from sqlalchemy.orm import Session


def _owner_history(session: Session, agent_id: int) -> list[OwnerChange]:
    rows = session.execute(
        select(AgentOwnerHistory)
        .where(AgentOwnerHistory.agent_id == agent_id)
        .order_by(AgentOwnerHistory.block_number, AgentOwnerHistory.log_index)
    ).scalars()
    return [OwnerChange(r.from_address, r.to_address, r.block_number, r.log_index) for r in rows]


def _rater_stats(session: Session, clients: set[str]) -> dict[str, tuple[int, int]]:
    """Per-rater (first_seen_block, total_feedback_count) across ALL agents."""
    if not clients:
        return {}
    rows = session.execute(
        select(
            Feedback.client_address,
            func.min(Feedback.block_number),
            func.count(),
        )
        .where(Feedback.client_address.in_(clients))
        .group_by(Feedback.client_address)
    ).all()
    return {addr: (int(first_seen), int(total)) for addr, first_seen, total in rows}


def _circular_partners(session: Session, owner: str) -> set[str]:
    """Owners of the agents that this agent's owner has itself left feedback on."""
    rated = select(Feedback.agent_id).where(Feedback.client_address == owner).distinct()
    partners = session.execute(
        select(Agent.owner).where(Agent.agent_id.in_(rated), Agent.owner != owner).distinct()
    ).scalars()
    return {p.lower() for p in partners}


def _agent_wallet_set_block(session: Session, agent_id: int) -> int | None:
    block = session.execute(
        select(func.max(AgentMetadata.block_number)).where(
            AgentMetadata.agent_id == agent_id,
            AgentMetadata.metadata_key == "agentWallet",
        )
    ).scalar_one_or_none()
    return int(block) if block is not None else None


def gather_inputs(session: Session, agent_id: int, as_of_block: int) -> AgentScoringInputs | None:
    agent = session.get(Agent, agent_id)
    if agent is None:
        return None

    history = _owner_history(session, agent_id)
    owner = agent.owner.lower()

    card = session.get(AgentCard, agent_id)
    drift_count = session.execute(
        select(func.count()).select_from(CardDrift).where(CardDrift.agent_id == agent_id)
    ).scalar_one()

    wallet_block = _agent_wallet_set_block(session, agent_id)

    feedback_rows = list(
        session.execute(select(Feedback).where(Feedback.agent_id == agent_id)).scalars()
    )
    revoked = {
        (r.client_address.lower(), r.feedback_index)
        for r in session.execute(
            select(FeedbackRevocation).where(FeedbackRevocation.agent_id == agent_id)
        ).scalars()
    }
    responded = {
        (r.client_address.lower(), r.feedback_index)
        for r in session.execute(
            select(FeedbackResponse).where(FeedbackResponse.agent_id == agent_id)
        ).scalars()
    }

    clients = {r.client_address.lower() for r in feedback_rows}
    stats = _rater_stats(session, clients)
    partners = _circular_partners(session, owner)

    feedback: list[FeedbackInput] = []
    for r in feedback_rows:
        client = r.client_address.lower()
        first_seen, total = stats.get(client, (r.block_number, 1))
        feedback.append(
            FeedbackInput(
                client_address=client,
                feedback_index=r.feedback_index,
                value=r.value_scaled,
                block_number=r.block_number,
                revoked=(client, r.feedback_index) in revoked,
                responded=(client, r.feedback_index) in responded,
                rater_first_seen_block=first_seen,
                rater_total_count=total,
                is_self=owner_at_block(history, r.block_number) == client,
                is_circular=client in partners,
            )
        )

    return AgentScoringInputs(
        agent_id=agent_id,
        as_of_block=as_of_block,
        registered_block=agent.registered_block,
        last_transfer_block=last_transfer_block(history),
        has_card=card is not None,
        card_fetch_ok=card is not None and card.fetch_status == "ok",
        schema_valid=card.schema_valid if card is not None else None,
        registration_match=card.registration_match if card is not None else None,
        wallet_status=card.wallet_status if card is not None else None,
        drift_count=int(drift_count),
        agent_wallet_set=wallet_block is not None,
        agent_wallet_set_block=wallet_block,
        feedback=feedback,
    )

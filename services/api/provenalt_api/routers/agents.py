"""Agent endpoints (free tier): list/search, detail, and feedback timeline (proposal §7)."""

from __future__ import annotations

from typing import Annotated

from fastapi import APIRouter, HTTPException, Query, status
from provenalt_shared.settings import get_settings

from provenalt_api import queries
from provenalt_api.deps import SessionDep
from provenalt_api.schemas import (
    AgentDetail,
    AgentListItem,
    AgentPage,
    CardSummary,
    FeedbackEntry,
    FeedbackPage,
    MetadataEntry,
    OwnerHistoryEntry,
    ScoreSummary,
)

router = APIRouter(prefix="/v1", tags=["agents"])


def _clamp_limit(limit: int) -> int:
    return min(limit, get_settings().api_max_page_size)


@router.get("/agents", response_model=AgentPage, summary="Search / list agents (paginated)")
def list_agents(
    session: SessionDep,
    limit: Annotated[int, Query(ge=1, le=1000)] = 50,
    offset: Annotated[int, Query(ge=0)] = 0,
    owner: Annotated[
        str | None, Query(description="Filter by owner address (case-insensitive)")
    ] = None,
) -> AgentPage:
    limit = _clamp_limit(limit)
    rows, total = queries.list_agents(session, limit=limit, offset=offset, owner=owner)
    items = [
        AgentListItem(
            agent_id=agent.agent_id,
            owner=agent.owner,
            agent_uri=agent.agent_uri,
            registered_block=agent.registered_block,
            score=score,
            confidence=confidence,
        )
        for agent, score, confidence in rows
    ]
    return AgentPage(items=items, total=total, limit=limit, offset=offset)


@router.get(
    "/agents/{agent_id}",
    response_model=AgentDetail,
    summary="Agent identity + card + metadata + owner history",
)
def get_agent(agent_id: int, session: SessionDep) -> AgentDetail:
    agent = queries.get_agent(session, agent_id)
    if agent is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="agent not found")

    card = queries.get_card(session, agent_id)
    score = queries.get_score(session, agent_id)
    return AgentDetail(
        agent_id=agent.agent_id,
        owner=agent.owner,
        agent_uri=agent.agent_uri,
        registered_block=agent.registered_block,
        registered_tx_hash=agent.registered_tx_hash,
        card=(
            CardSummary(
                token_uri=card.token_uri,
                fetch_status=card.fetch_status,
                http_status=card.http_status,
                content_hash=card.content_hash,
                schema_valid=card.schema_valid,
                registration_match=card.registration_match,
                wallet_status=card.wallet_status,
            )
            if card is not None
            else None
        ),
        score=(
            ScoreSummary(
                score=score.score,
                confidence=score.confidence,
                sufficient=score.sufficient,
                weights_version=score.weights_version,
                as_of_block=score.as_of_block,
            )
            if score is not None
            else None
        ),
        metadata=[
            MetadataEntry(
                metadata_key=m.metadata_key,
                value_hex="0x" + bytes(m.metadata_value).hex(),
                block_number=m.block_number,
            )
            for m in queries.agent_metadata(session, agent_id)
        ],
        owner_history=[
            OwnerHistoryEntry(
                from_address=h.from_address,
                to_address=h.to_address,
                block_number=h.block_number,
                tx_hash=h.tx_hash,
                log_index=h.log_index,
            )
            for h in queries.owner_history(session, agent_id)
        ],
    )


@router.get(
    "/agents/{agent_id}/feedback",
    response_model=FeedbackPage,
    summary="Feedback timeline for an agent",
)
def get_feedback(
    agent_id: int,
    session: SessionDep,
    limit: Annotated[int, Query(ge=1, le=1000)] = 50,
    offset: Annotated[int, Query(ge=0)] = 0,
) -> FeedbackPage:
    if queries.get_agent(session, agent_id) is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="agent not found")

    limit = _clamp_limit(limit)
    rows, total, revoked, responded = queries.list_feedback(
        session, agent_id, limit=limit, offset=offset
    )
    items = [
        FeedbackEntry(
            client_address=f.client_address,
            feedback_index=f.feedback_index,
            value=str(f.value),
            value_scaled=str(f.value_scaled),
            value_decimals=f.value_decimals,
            tag1=f.tag1,
            tag2=f.tag2,
            block_number=f.block_number,
            revoked=(f.client_address, f.feedback_index) in revoked,
            responded=(f.client_address, f.feedback_index) in responded,
            feedback_uri=f.feedback_uri,
            feedback_hash=f.feedback_hash,
        )
        for f in rows
    ]
    return FeedbackPage(items=items, total=total, limit=limit, offset=offset)

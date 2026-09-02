"""Registry stats endpoint (free tier): totals and per-registry indexer position (proposal §7)."""

from __future__ import annotations

from typing import cast

from fastapi import APIRouter
from provenalt_shared.db import IndexerCursor

from provenalt_api import queries
from provenalt_api.deps import SessionDep
from provenalt_api.schemas import RegistryStatus, Stats

router = APIRouter(prefix="/v1", tags=["stats"])


@router.get("/stats", response_model=Stats, summary="Registry totals and indexer position")
def get_stats(session: SessionDep) -> Stats:
    data = queries.stats(session)
    cursors = cast(list[IndexerCursor], data["cursors"])
    return Stats(
        total_agents=cast(int, data["total_agents"]),
        max_agent_id=cast("int | None", data["max_agent_id"]),
        total_feedback=cast(int, data["total_feedback"]),
        total_scored=cast(int, data["total_scored"]),
        total_cards=cast(int, data["total_cards"]),
        registries=[
            RegistryStatus(
                registry=c.registry_name,
                anchor_block=c.anchor_block,
                last_indexed_block=c.last_indexed_block,
            )
            for c in cursors
        ],
    )

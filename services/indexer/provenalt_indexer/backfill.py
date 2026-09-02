"""Backfill worker: index a registry's events from the anchor to the head (proposal §2.3).

Processes the range in fixed block segments, committing the cursor after each so the worker
is resumable across restarts. Within a segment the chain client's adaptive chunking handles
provider block-range caps and rate limits. All writes are idempotent upserts.

The projection is injected via ``ingest`` so identity and reputation reuse this worker
(defaults to the identity projection for backward compatibility).
"""

from __future__ import annotations

from collections.abc import Callable
from typing import Any, Protocol

from provenalt_shared.db import repository as repo
from sqlalchemy.orm import Session

from provenalt_indexer.projection import ingest_logs

DEFAULT_SEGMENT_SIZE = 50_000

# A projection: consume a batch of raw eth_getLogs entries into DB state.
IngestFn = Callable[[Session, list[dict[str, Any]]], None]


class SupportsGetLogs(Protocol):
    def get_logs(
        self, address: str, topics: list[Any], from_block: int, to_block: int
    ) -> list[dict[str, Any]]: ...


def backfill(
    session: Session,
    client: SupportsGetLogs,
    *,
    address: str,
    event_topic0s: list[str],
    registry: str,
    from_block: int,
    to_block: int,
    segment_size: int = DEFAULT_SEGMENT_SIZE,
    ingest: IngestFn = ingest_logs,
) -> None:
    """Index ``[from_block, to_block]`` in segments, advancing the cursor after each commit.

    ``event_topic0s`` becomes an OR filter on topic0 (``topics=[[t0, t1, ...]]``).
    """
    start = from_block
    while start <= to_block:
        end = min(start + segment_size - 1, to_block)
        logs = client.get_logs(address, [event_topic0s], start, end)
        ingest(session, logs)
        repo.set_last_indexed_block(session, registry, end)
        session.commit()
        start = end + 1

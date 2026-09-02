"""Indexer worker entrypoint: bootstrap anchors, backfill, then head-follow both registries.

Wires shared settings, logging, chain client, and database together with the identity and
reputation backfill/follow logic. The orchestration helpers (``bootstrap_cursor``,
``catch_up``) are unit-tested with fakes; ``main`` is the long-running Railway process that
drives every registry in ``registries.REGISTRIES``.
"""

from __future__ import annotations

import time
from typing import Any, Protocol

from provenalt_shared.chain import ChainClient, HttpxTransport
from provenalt_shared.db import make_engine, make_session_factory
from provenalt_shared.db import repository as repo
from provenalt_shared.logging import configure_logging, get_logger
from provenalt_shared.settings import get_settings
from sqlalchemy.orm import Session

from provenalt_indexer.backfill import IngestFn, backfill
from provenalt_indexer.deploy_block import find_deployment_block
from provenalt_indexer.follow import follow_once
from provenalt_indexer.projection import ingest_logs
from provenalt_indexer.registries import REGISTRIES

# Kept for backwards compatibility with earlier tests/wiring.
REGISTRY_NAME = "identity"
DEFAULT_POLL_SECONDS = 5.0

log = get_logger("indexer.worker")


class SupportsChain(Protocol):
    def get_logs(
        self, address: str, topics: list[Any], from_block: int, to_block: int
    ) -> list[dict[str, Any]]: ...
    def get_block_number(self) -> int: ...
    def get_block_by_number(
        self, block: int, include_transactions: bool = False
    ) -> dict[str, Any] | None: ...
    def get_code(self, address: str, block: int | str = "latest") -> str: ...


def bootstrap_cursor(
    session: Session, client: SupportsChain, *, registry: str, address: str
) -> int:
    """Ensure a cursor exists, discovering the deployment block as the anchor if needed."""
    cursor = repo.get_cursor(session, registry)
    if cursor is not None:
        return cursor.anchor_block

    anchor = find_deployment_block(client, address)
    repo.upsert_cursor(session, registry, anchor_block=anchor, last_indexed_block=anchor - 1)
    session.commit()
    log.info("anchor_discovered", registry=registry, anchor_block=anchor)
    return anchor


def catch_up(
    session: Session,
    client: SupportsChain,
    *,
    registry: str,
    address: str,
    event_topic0s: list[str],
    segment_size: int,
    ingest: IngestFn = ingest_logs,
) -> None:
    """Backfill from the cursor's last-indexed block up to the current head."""
    cursor = repo.get_cursor(session, registry)
    if cursor is None:
        raise ValueError(f"no cursor for registry {registry!r}; bootstrap first")

    head = client.get_block_number()
    if head > cursor.last_indexed_block:
        backfill(
            session,
            client,
            address=address,
            event_topic0s=event_topic0s,
            registry=registry,
            from_block=cursor.last_indexed_block + 1,
            to_block=head,
            segment_size=segment_size,
            ingest=ingest,
        )
        log.info("backfill_complete", registry=registry, head=head)


def main() -> None:  # pragma: no cover - long-running process wiring
    settings = get_settings()
    configure_logging(level=settings.log_level, fmt=settings.log_format)

    if not settings.database_url:
        raise RuntimeError("DATABASE_URL is required to run the indexer")

    engine = make_engine(settings.database_url)
    session_factory = make_session_factory(engine)
    client = ChainClient(
        rpc_urls=settings.rpc_urls,
        transport=HttpxTransport(),
        initial_chunk=settings.getlogs_initial_chunk,
        min_chunk=settings.getlogs_min_chunk,
        max_chunk=settings.getlogs_max_chunk,
    )

    with session_factory() as session:
        for cfg in REGISTRIES:
            bootstrap_cursor(session, client, registry=cfg.name, address=cfg.address)
            catch_up(
                session,
                client,
                registry=cfg.name,
                address=cfg.address,
                event_topic0s=cfg.event_topic0s,
                segment_size=settings.getlogs_max_chunk,
                ingest=cfg.ingest,
            )

        log.info("entering_head_follow", finality_depth=settings.finality_depth)
        while True:
            for cfg in REGISTRIES:
                head = follow_once(
                    session,
                    client,
                    address=cfg.address,
                    event_topic0s=cfg.event_topic0s,
                    registry=cfg.name,
                    finality_depth=settings.finality_depth,
                    ingest=cfg.ingest,
                    rewind_fn=cfg.rewind_fn,
                )
                log.info("head_follow_tick", registry=cfg.name, head=head)
            time.sleep(DEFAULT_POLL_SECONDS)


if __name__ == "__main__":  # pragma: no cover
    main()

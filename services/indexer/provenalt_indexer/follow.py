"""Registry-agnostic head-follow loop with reorg detection (proposal §2.4, reused by §3.3).

Each ``follow_once`` step:

1. Checks the unfinalized window (last ``finality_depth`` blocks) for a reorg by comparing
   each indexed block's stored ``block_hash`` (scoped to this registry's contract) against
   the current chain hash.
2. On a mismatch, rewinds to the fork block via the injected ``rewind_fn`` (which deletes the
   reorged tail and re-derives any registry-specific state).
3. Re-indexes forward with the injected ``ingest`` function.

The registry-specific pieces — how to project logs (``ingest``) and how to unwind a reorg
(``rewind_fn``) — are injected, so identity and reputation share this framework.
"""

from __future__ import annotations

from collections.abc import Callable
from typing import Any, Protocol

from provenalt_shared.db import repository as repo
from sqlalchemy.orm import Session

from provenalt_indexer.backfill import IngestFn, backfill

RewindFn = Callable[[Session, int], None]


class SupportsFollow(Protocol):
    def get_logs(
        self, address: str, topics: list[Any], from_block: int, to_block: int
    ) -> list[dict[str, Any]]: ...
    def get_block_number(self) -> int: ...
    def get_block_by_number(
        self, block: int, include_transactions: bool = False
    ) -> dict[str, Any] | None: ...


def detect_reorg(
    session: Session,
    client: SupportsFollow,
    last_indexed_block: int,
    finality_depth: int,
    anchor: int,
    address: str,
) -> int | None:
    """Return the fork block to rewind to, or ``None`` if the window is consistent.

    Scans this registry's indexed blocks in ``[max(anchor, last-N), last]`` ascending; the
    first stored hash that no longer matches the chain marks the fork (rewind target = block − 1).
    """
    window_start = max(anchor, last_indexed_block - finality_depth)
    for block_number, stored_hash in repo.block_hashes_in_range(
        session, window_start, last_indexed_block, addresses=[address]
    ):
        chain_block = client.get_block_by_number(block_number)
        chain_hash = chain_block["hash"] if chain_block else None
        if chain_hash is None or chain_hash.lower() != stored_hash.lower():
            return block_number - 1
    return None


def rewind(session: Session, fork_block: int, registry: str, rewind_fn: RewindFn) -> None:
    """Unwind a reorg: run the registry-specific rewind, reset the cursor, and commit."""
    rewind_fn(session, fork_block)
    repo.set_last_indexed_block(session, registry, fork_block)
    session.commit()


def follow_once(
    session: Session,
    client: SupportsFollow,
    *,
    address: str,
    event_topic0s: list[str],
    registry: str,
    finality_depth: int,
    ingest: IngestFn,
    rewind_fn: RewindFn,
    segment_size: int = 2000,
) -> int:
    """Run one follow step: detect+handle reorg, then index forward to head. Returns head."""
    cursor = repo.get_cursor(session, registry)
    if cursor is None:
        raise ValueError(f"no cursor for registry {registry!r}; backfill must run first")

    last_indexed = cursor.last_indexed_block
    anchor = cursor.anchor_block

    fork = detect_reorg(session, client, last_indexed, finality_depth, anchor, address)
    if fork is not None and fork < last_indexed:
        rewind(session, fork, registry, rewind_fn)
        last_indexed = fork

    head = client.get_block_number()
    if head > last_indexed:
        backfill(
            session,
            client,
            address=address,
            event_topic0s=event_topic0s,
            registry=registry,
            from_block=last_indexed + 1,
            to_block=head,
            segment_size=segment_size,
            ingest=ingest,
        )
    return head

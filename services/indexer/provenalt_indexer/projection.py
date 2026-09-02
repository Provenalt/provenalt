"""Project decoded identity logs into DB state.

Every raw log is stored append-only in ``raw_logs`` (the source of truth), then dispatched
to the derived tables. All writes go through the idempotent repository primitives, so
replaying logs (backfill restarts, reorg re-index) never duplicates rows. Logs are applied
in ascending ``(block_number, log_index)`` order so "latest wins" for owner/URI holds.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from provenalt_shared.db import Agent, AgentMetadata, AgentOwnerHistory
from provenalt_shared.db import repository as repo
from sqlalchemy.orm import Session

from provenalt_indexer.events import (
    IDENTITY_REGISTRY_ADDRESS,
    TOPIC0,
    MetadataSetEvent,
    RegisteredEvent,
    TransferEvent,
    URIUpdatedEvent,
    decode_identity_log,
)


@dataclass(frozen=True)
class RawLogFields:
    address: str
    block_number: int
    block_hash: str
    tx_hash: str
    log_index: int
    topics: list[str]
    data: str
    removed: bool


def _to_int(value: Any) -> int:
    return int(value, 16) if isinstance(value, str) else int(value)


def parse_raw_log(log: dict[str, Any]) -> RawLogFields:
    """Normalise a raw eth_getLogs entry (hex fields) into typed fields."""
    return RawLogFields(
        address=log["address"],
        block_number=_to_int(log["blockNumber"]),
        block_hash=log["blockHash"],
        tx_hash=log["transactionHash"],
        log_index=_to_int(log["logIndex"]),
        topics=list(log["topics"]),
        data=log.get("data", "0x"),
        removed=bool(log.get("removed", False)),
    )


def apply_log(session: Session, fields: RawLogFields) -> None:
    """Store one raw log and project its decoded effect onto the derived tables."""
    repo.upsert_raw_log(
        session,
        address=fields.address,
        block_number=fields.block_number,
        block_hash=fields.block_hash,
        tx_hash=fields.tx_hash,
        log_index=fields.log_index,
        topic0=fields.topics[0],
        topics=fields.topics,
        data=fields.data,
        log_removed=fields.removed,
    )

    decoded = decode_identity_log(fields.topics, fields.data)
    if decoded is None:
        return

    if isinstance(decoded, RegisteredEvent):
        repo.upsert_agent(
            session,
            agent_id=decoded.agent_id,
            owner=decoded.owner,
            agent_uri=decoded.agent_uri,
            registered_block=fields.block_number,
            registered_tx_hash=fields.tx_hash,
            registered_log_index=fields.log_index,
        )
    elif isinstance(decoded, TransferEvent):
        repo.append_owner_history(
            session,
            agent_id=decoded.token_id,
            from_address=decoded.from_address,
            to_address=decoded.to_address,
            block_number=fields.block_number,
            tx_hash=fields.tx_hash,
            log_index=fields.log_index,
        )
        # The mint Transfer (from 0x0) may precede Registered in the same tx; only update
        # the owner column once the agent row exists.
        if repo.agent_exists(session, decoded.token_id):
            repo.set_agent_owner(session, decoded.token_id, decoded.to_address)
    elif isinstance(decoded, URIUpdatedEvent):
        if repo.agent_exists(session, decoded.agent_id):
            repo.set_agent_uri(session, decoded.agent_id, decoded.new_uri)
    elif isinstance(decoded, MetadataSetEvent):
        repo.insert_metadata(
            session,
            agent_id=decoded.agent_id,
            metadata_key=decoded.metadata_key,
            indexed_key_hash=decoded.indexed_key_hash,
            metadata_value=decoded.metadata_value,
            block_number=fields.block_number,
            tx_hash=fields.tx_hash,
            log_index=fields.log_index,
        )


def ingest_logs(session: Session, logs: list[dict[str, Any]]) -> None:
    """Parse, order, and apply a batch of raw logs."""
    fields = [parse_raw_log(log) for log in logs]
    fields.sort(key=lambda f: (f.block_number, f.log_index))
    for entry in fields:
        apply_log(session, entry)


# ── reorg rewind (identity-specific; injected into the generic follow framework) ──


def _affected_agent_ids(session: Session, fork_block: int) -> set[int]:
    """Agent ids whose derived state may be stale after removing blocks above the fork."""
    affected: set[int] = set()
    for log in repo.raw_logs_above(session, fork_block):
        decoded = decode_identity_log(log.topics, log.data)
        if isinstance(decoded, TransferEvent):
            affected.add(decoded.token_id)
        elif isinstance(decoded, RegisteredEvent | URIUpdatedEvent):
            affected.add(decoded.agent_id)
    return affected


def _recompute_uri(session: Session, agent_id: int) -> None:
    """Re-derive an agent's latest URI from surviving Registered/URIUpdated logs."""
    latest_uri: str | None = None
    for log in repo.raw_logs_by_topic0s(session, [TOPIC0["Registered"], TOPIC0["URIUpdated"]]):
        decoded = decode_identity_log(log.topics, log.data)
        if isinstance(decoded, RegisteredEvent) and decoded.agent_id == agent_id:
            latest_uri = decoded.agent_uri
        elif isinstance(decoded, URIUpdatedEvent) and decoded.agent_id == agent_id:
            latest_uri = decoded.new_uri
    if latest_uri is not None:
        repo.set_agent_uri(session, agent_id, latest_uri)


def rewind_identity(session: Session, fork_block: int) -> None:
    """Delete the identity tail above ``fork_block`` and re-derive affected agents' state.

    Order matters: capture affected agents while their logs still exist, delete the tail
    (derived tables + identity's own raw_logs), then re-derive owner/URI from survivors.
    """
    affected = _affected_agent_ids(session, fork_block)
    repo.delete_rows_above(session, Agent, fork_block, block_column="registered_block")
    repo.delete_rows_above(session, AgentMetadata, fork_block)
    repo.delete_rows_above(session, AgentOwnerHistory, fork_block)
    repo.delete_raw_logs_above(session, fork_block, [IDENTITY_REGISTRY_ADDRESS])
    for agent_id in affected:
        if repo.agent_exists(session, agent_id):
            repo.recompute_owner_from_history(session, agent_id)
            _recompute_uri(session, agent_id)

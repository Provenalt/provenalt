"""Project decoded reputation logs into DB state (proposal §3.3).

Reputation events are append-only logs (no materialised "latest" state), so ingestion is a
straight idempotent insert and reorg rewind is a plain tail delete — no re-derivation needed.
Reuses ``parse_raw_log`` from the identity projection and the generic backfill/follow worker.
"""

from __future__ import annotations

from decimal import Decimal
from typing import Any

from provenalt_shared.db import Feedback, FeedbackResponse, FeedbackRevocation
from provenalt_shared.db import repository as repo
from sqlalchemy.orm import Session

from provenalt_indexer.projection import parse_raw_log
from provenalt_indexer.reputation import (
    REPUTATION_REGISTRY_ADDRESS,
    FeedbackRevokedEvent,
    NewFeedbackEvent,
    ResponseAppendedEvent,
    decode_reputation_log,
)


def _scaled(value: int, decimals: int) -> Decimal:
    return Decimal(value) / (Decimal(10) ** decimals)


def apply_reputation_log(session: Session, log: dict[str, Any]) -> None:
    """Store one raw reputation log and project its decoded effect."""
    fields = parse_raw_log(log)
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

    decoded = decode_reputation_log(fields.topics, fields.data)
    if decoded is None:
        return

    if isinstance(decoded, NewFeedbackEvent):
        repo.insert_feedback(
            session,
            agent_id=decoded.agent_id,
            client_address=decoded.client_address,
            feedback_index=decoded.feedback_index,
            value=decoded.value,
            value_decimals=decoded.value_decimals,
            value_scaled=_scaled(decoded.value, decoded.value_decimals),
            indexed_tag1_hash=decoded.indexed_tag1_hash,
            tag1=decoded.tag1,
            tag2=decoded.tag2,
            endpoint=decoded.endpoint,
            feedback_uri=decoded.feedback_uri,
            feedback_hash=decoded.feedback_hash,
            block_number=fields.block_number,
            tx_hash=fields.tx_hash,
            log_index=fields.log_index,
        )
    elif isinstance(decoded, FeedbackRevokedEvent):
        repo.insert_feedback_revocation(
            session,
            agent_id=decoded.agent_id,
            client_address=decoded.client_address,
            feedback_index=decoded.feedback_index,
            block_number=fields.block_number,
            tx_hash=fields.tx_hash,
            log_index=fields.log_index,
        )
    elif isinstance(decoded, ResponseAppendedEvent):
        repo.insert_feedback_response(
            session,
            agent_id=decoded.agent_id,
            client_address=decoded.client_address,
            feedback_index=decoded.feedback_index,
            responder=decoded.responder,
            response_uri=decoded.response_uri,
            response_hash=decoded.response_hash,
            block_number=fields.block_number,
            tx_hash=fields.tx_hash,
            log_index=fields.log_index,
        )


def ingest_reputation_logs(session: Session, logs: list[dict[str, Any]]) -> None:
    """Parse, order, and apply a batch of raw reputation logs."""
    ordered = sorted(logs, key=lambda log: (int(log["blockNumber"], 16), int(log["logIndex"], 16)))
    for log in ordered:
        apply_reputation_log(session, log)


def rewind_reputation(session: Session, fork_block: int) -> None:
    """Delete the reputation tail above ``fork_block`` (append-only → no re-derivation)."""
    repo.delete_rows_above(session, Feedback, fork_block)
    repo.delete_rows_above(session, FeedbackRevocation, fork_block)
    repo.delete_rows_above(session, FeedbackResponse, fork_block)
    repo.delete_raw_logs_above(session, fork_block, [REPUTATION_REGISTRY_ADDRESS])

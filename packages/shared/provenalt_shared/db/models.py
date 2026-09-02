"""ORM models for the identity index (§2.1) and the reputation index (§3.2).

Identity tables:
    * ``raw_logs``            — append-only event store; the source of truth for BOTH
                                registries. Natural key ``(tx_hash, log_index)`` is unique;
                                ``block_hash`` per row supports reorg detection (§4).
    * ``agents``              — one row per ERC-8004 agent (ERC-721 tokenId). ``owner`` and
                                ``agent_uri`` are the latest materialised values.
    * ``agent_metadata``      — every ``MetadataSet`` event (a log, not a latest-value).
    * ``agent_owner_history`` — every ownership change (``Registered`` seeds it from the
                                zero address; each ``Transfer`` appends a row).
    * ``indexer_cursor``      — per-registry backfill anchor + last-indexed block, so the
                                worker is resumable across restarts.

Reputation tables (append-only event logs, keyed logically by
``(agent_id, client_address, feedback_index)``):
    * ``feedback``             — every ``NewFeedback`` event; ``value`` is the raw signed
                                 int128 and ``value_scaled`` is ``value / 10**value_decimals``.
    * ``feedback_revocations`` — every ``FeedbackRevoked`` event.
    * ``feedback_responses``   — every ``ResponseAppended`` event.
"""

from __future__ import annotations

from datetime import UTC, datetime
from decimal import Decimal

from sqlalchemy import (
    BigInteger,
    Boolean,
    DateTime,
    Index,
    Integer,
    LargeBinary,
    Numeric,
    String,
    UniqueConstraint,
)
from sqlalchemy.orm import Mapped, mapped_column
from sqlalchemy.types import JSON

from provenalt_shared.db.base import Base

ZERO_ADDRESS = "0x0000000000000000000000000000000000000000"


def _utcnow() -> datetime:
    return datetime.now(UTC)


class RawLog(Base):
    __tablename__ = "raw_logs"
    __table_args__ = (
        UniqueConstraint("tx_hash", "log_index", name="uq_raw_logs_tx_log"),
        Index("ix_raw_logs_block_number", "block_number"),
        Index("ix_raw_logs_address_topic0", "address", "topic0"),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    address: Mapped[str] = mapped_column(String(42), nullable=False)
    block_number: Mapped[int] = mapped_column(BigInteger, nullable=False)
    block_hash: Mapped[str] = mapped_column(String(66), nullable=False)
    tx_hash: Mapped[str] = mapped_column(String(66), nullable=False)
    log_index: Mapped[int] = mapped_column(Integer, nullable=False)
    topic0: Mapped[str] = mapped_column(String(66), nullable=False)
    topics: Mapped[list[str]] = mapped_column(JSON, nullable=False, default=list)
    data: Mapped[str] = mapped_column(String, nullable=False, default="0x")
    log_removed: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=_utcnow)


class Agent(Base):
    __tablename__ = "agents"

    agent_id: Mapped[int] = mapped_column(BigInteger, primary_key=True, autoincrement=False)
    owner: Mapped[str] = mapped_column(String(42), nullable=False)
    agent_uri: Mapped[str] = mapped_column(String, nullable=False, default="")
    registered_block: Mapped[int] = mapped_column(BigInteger, nullable=False)
    registered_tx_hash: Mapped[str] = mapped_column(String(66), nullable=False)
    registered_log_index: Mapped[int] = mapped_column(Integer, nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=_utcnow)
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=_utcnow, onupdate=_utcnow
    )


class AgentMetadata(Base):
    __tablename__ = "agent_metadata"
    __table_args__ = (
        UniqueConstraint("tx_hash", "log_index", name="uq_agent_metadata_tx_log"),
        Index("ix_agent_metadata_agent_id", "agent_id"),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    agent_id: Mapped[int] = mapped_column(BigInteger, nullable=False)
    metadata_key: Mapped[str] = mapped_column(String, nullable=False)
    indexed_key_hash: Mapped[str] = mapped_column(String(66), nullable=False)
    metadata_value: Mapped[bytes] = mapped_column(LargeBinary, nullable=False)
    block_number: Mapped[int] = mapped_column(BigInteger, nullable=False)
    tx_hash: Mapped[str] = mapped_column(String(66), nullable=False)
    log_index: Mapped[int] = mapped_column(Integer, nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=_utcnow)


class AgentOwnerHistory(Base):
    __tablename__ = "agent_owner_history"
    __table_args__ = (
        UniqueConstraint("tx_hash", "log_index", name="uq_agent_owner_history_tx_log"),
        Index("ix_agent_owner_history_agent_id", "agent_id"),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    agent_id: Mapped[int] = mapped_column(BigInteger, nullable=False)
    from_address: Mapped[str] = mapped_column(String(42), nullable=False)
    to_address: Mapped[str] = mapped_column(String(42), nullable=False)
    block_number: Mapped[int] = mapped_column(BigInteger, nullable=False)
    tx_hash: Mapped[str] = mapped_column(String(66), nullable=False)
    log_index: Mapped[int] = mapped_column(Integer, nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=_utcnow)


class Feedback(Base):
    __tablename__ = "feedback"
    __table_args__ = (
        UniqueConstraint("tx_hash", "log_index", name="uq_feedback_tx_log"),
        Index("ix_feedback_agent_id", "agent_id"),
        Index("ix_feedback_client_address", "client_address"),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    agent_id: Mapped[int] = mapped_column(BigInteger, nullable=False)
    client_address: Mapped[str] = mapped_column(String(42), nullable=False)
    feedback_index: Mapped[int] = mapped_column(BigInteger, nullable=False)
    # Raw signed int128 value and its decimal scale, plus the decoded scaled value.
    value: Mapped[Decimal] = mapped_column(Numeric(40, 0), nullable=False)
    value_decimals: Mapped[int] = mapped_column(Integer, nullable=False)
    value_scaled: Mapped[Decimal] = mapped_column(Numeric(60, 18), nullable=False)
    indexed_tag1_hash: Mapped[str] = mapped_column(String(66), nullable=False)
    tag1: Mapped[str] = mapped_column(String, nullable=False, default="")
    tag2: Mapped[str] = mapped_column(String, nullable=False, default="")
    endpoint: Mapped[str] = mapped_column(String, nullable=False, default="")
    feedback_uri: Mapped[str] = mapped_column(String, nullable=False, default="")
    feedback_hash: Mapped[str] = mapped_column(String(66), nullable=False)
    block_number: Mapped[int] = mapped_column(BigInteger, nullable=False)
    tx_hash: Mapped[str] = mapped_column(String(66), nullable=False)
    log_index: Mapped[int] = mapped_column(Integer, nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=_utcnow)


class FeedbackRevocation(Base):
    __tablename__ = "feedback_revocations"
    __table_args__ = (
        UniqueConstraint("tx_hash", "log_index", name="uq_feedback_revocations_tx_log"),
        Index("ix_feedback_revocations_feedback", "agent_id", "client_address", "feedback_index"),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    agent_id: Mapped[int] = mapped_column(BigInteger, nullable=False)
    client_address: Mapped[str] = mapped_column(String(42), nullable=False)
    feedback_index: Mapped[int] = mapped_column(BigInteger, nullable=False)
    block_number: Mapped[int] = mapped_column(BigInteger, nullable=False)
    tx_hash: Mapped[str] = mapped_column(String(66), nullable=False)
    log_index: Mapped[int] = mapped_column(Integer, nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=_utcnow)


class FeedbackResponse(Base):
    __tablename__ = "feedback_responses"
    __table_args__ = (
        UniqueConstraint("tx_hash", "log_index", name="uq_feedback_responses_tx_log"),
        Index("ix_feedback_responses_feedback", "agent_id", "client_address", "feedback_index"),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    agent_id: Mapped[int] = mapped_column(BigInteger, nullable=False)
    client_address: Mapped[str] = mapped_column(String(42), nullable=False)
    feedback_index: Mapped[int] = mapped_column(BigInteger, nullable=False)
    responder: Mapped[str] = mapped_column(String(42), nullable=False)
    response_uri: Mapped[str] = mapped_column(String, nullable=False, default="")
    response_hash: Mapped[str] = mapped_column(String(66), nullable=False)
    block_number: Mapped[int] = mapped_column(BigInteger, nullable=False)
    tx_hash: Mapped[str] = mapped_column(String(66), nullable=False)
    log_index: Mapped[int] = mapped_column(Integer, nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=_utcnow)


class AgentCard(Base):
    """Latest agent-card state per agent (proposal §4): fetch result, content hash,
    schema validity, and agentWallet/registration consistency."""

    __tablename__ = "agent_cards"

    agent_id: Mapped[int] = mapped_column(BigInteger, primary_key=True, autoincrement=False)
    token_uri: Mapped[str] = mapped_column(String, nullable=False)
    # ok | fetch_error | unsupported_scheme | empty
    fetch_status: Mapped[str] = mapped_column(String(32), nullable=False)
    http_status: Mapped[int | None] = mapped_column(Integer, nullable=True)
    source: Mapped[str | None] = mapped_column(String, nullable=True)
    content: Mapped[str | None] = mapped_column(String, nullable=True)
    content_hash: Mapped[str | None] = mapped_column(String(64), nullable=True)
    schema_valid: Mapped[bool | None] = mapped_column(Boolean, nullable=True)
    schema_errors: Mapped[list[str] | None] = mapped_column(JSON, nullable=True)
    registration_match: Mapped[bool | None] = mapped_column(Boolean, nullable=True)
    # match | mismatch | not_declared | wallet_not_set
    wallet_status: Mapped[str | None] = mapped_column(String(32), nullable=True)
    fetched_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=_utcnow)
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=_utcnow, onupdate=_utcnow
    )


class CardDrift(Base):
    """Append-only log: content hash changed while the tokenURI stayed the same (§4.3)."""

    __tablename__ = "card_drift"
    __table_args__ = (Index("ix_card_drift_agent_id", "agent_id"),)

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    agent_id: Mapped[int] = mapped_column(BigInteger, nullable=False)
    token_uri: Mapped[str] = mapped_column(String, nullable=False)
    old_content_hash: Mapped[str | None] = mapped_column(String(64), nullable=True)
    new_content_hash: Mapped[str | None] = mapped_column(String(64), nullable=True)
    detected_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=_utcnow)


class CardRefreshQueue(Base):
    """Pending card (re)fetch work (§4.3). One pending entry per agent (PK = agent_id)."""

    __tablename__ = "card_refresh_queue"

    agent_id: Mapped[int] = mapped_column(BigInteger, primary_key=True, autoincrement=False)
    # new_agent | uri_updated | periodic
    reason: Mapped[str] = mapped_column(String(32), nullable=False)
    attempts: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    enqueued_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=_utcnow)


class AgentScore(Base):
    """Latest persisted Provenalt Score per agent (proposal §5.3, §6)."""

    __tablename__ = "agent_scores"

    agent_id: Mapped[int] = mapped_column(BigInteger, primary_key=True, autoincrement=False)
    score: Mapped[int | None] = mapped_column(Integer, nullable=True)
    confidence: Mapped[str] = mapped_column(String(32), nullable=False)
    sufficient: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
    breakdown: Mapped[list[dict[str, object]]] = mapped_column(JSON, nullable=False, default=list)
    weights_version: Mapped[str] = mapped_column(String(16), nullable=False)
    as_of_block: Mapped[int] = mapped_column(BigInteger, nullable=False)
    computed_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=_utcnow, onupdate=_utcnow
    )


class ScoreRefreshQueue(Base):
    """Pending rescore work (§5.3). One pending entry per agent (PK = agent_id)."""

    __tablename__ = "score_refresh_queue"

    agent_id: Mapped[int] = mapped_column(BigInteger, primary_key=True, autoincrement=False)
    # new_agent | activity | periodic
    reason: Mapped[str] = mapped_column(String(32), nullable=False)
    enqueued_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=_utcnow)


class ApiKey(Base):
    """Partner API key for bypassing the free-tier rate limit (proposal §6.2).

    Only the SHA-256 hash of the key is stored — the plaintext key is shown once at
    creation and never persisted (repo ``CLAUDE.md``: no secrets in the DB either).
    """

    __tablename__ = "api_keys"
    __table_args__ = (UniqueConstraint("key_hash", name="uq_api_keys_key_hash"),)

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    key_hash: Mapped[str] = mapped_column(String(64), nullable=False)
    label: Mapped[str] = mapped_column(String, nullable=False, default="")
    active: Mapped[bool] = mapped_column(Boolean, nullable=False, default=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=_utcnow)


class IndexerCursor(Base):
    __tablename__ = "indexer_cursor"

    # Attribute is ``registry_name`` (``registry`` clashes with DeclarativeBase.registry);
    # the DB column keeps the name ``registry``.
    registry_name: Mapped[str] = mapped_column("registry", String(64), primary_key=True)
    anchor_block: Mapped[int] = mapped_column(BigInteger, nullable=False)
    last_indexed_block: Mapped[int] = mapped_column(BigInteger, nullable=False)
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=_utcnow, onupdate=_utcnow
    )

"""Repository primitives for the identity and reputation indexes.

All writes are idempotent (upsert on the ``(tx_hash, log_index)`` natural key or the agent
primary key), so replaying the same logs — during backfill restarts or after a reorg
re-index — never creates duplicates. Higher-level event dispatch and reorg re-derivation
live in the indexer service; this module stays decoupled from event decoding.

Both registries share ``raw_logs``, so reorg deletions are scoped by contract address.
"""

from __future__ import annotations

import hashlib
from dataclasses import dataclass
from datetime import UTC, datetime
from decimal import Decimal
from typing import Any, cast

from sqlalchemy import CursorResult, Select, case, delete, func, select
from sqlalchemy.dialects.postgresql import insert as pg_insert
from sqlalchemy.dialects.sqlite import insert as sqlite_insert
from sqlalchemy.orm import Session

from provenalt_shared.db.models import (
    Agent,
    AgentCard,
    AgentMetadata,
    AgentOwnerHistory,
    AgentScore,
    ApiKey,
    B20Token,
    CardDrift,
    CardRefreshQueue,
    Feedback,
    FeedbackResponse,
    FeedbackRevocation,
    IndexerCursor,
    RawLog,
    ScoreRefreshQueue,
    UsageEvent,
)

__all__ = [
    "Agent",
    "AgentCard",
    "AgentMetadata",
    "AgentOwnerHistory",
    "CardDrift",
    "CardRefreshQueue",
    "Feedback",
    "FeedbackResponse",
    "FeedbackRevocation",
    "IndexerCursor",
    "RawLog",
    "upsert_raw_log",
    "upsert_agent",
    "set_agent_owner",
    "set_agent_uri",
    "agent_exists",
    "append_owner_history",
    "insert_metadata",
    "insert_feedback",
    "insert_feedback_revocation",
    "insert_feedback_response",
    "recompute_owner_from_history",
    "get_cursor",
    "upsert_cursor",
    "set_last_indexed_block",
    "raw_logs_above",
    "raw_logs_by_topic0s",
    "block_hashes_in_range",
    "delete_rows_above",
    "delete_raw_logs_above",
    "max_agent_id",
    "all_agent_ids",
    "missing_agent_ids",
    "RaterCredibility",
    "rater_credibility_select",
    "rater_credibility_rows",
    "refresh_rater_credibility",
    "RATER_CREDIBILITY_VIEW",
    "RATER_CREDIBILITY_SQL",
    "get_agent_wallet",
    "upsert_agent_card",
    "get_agent_card",
    "record_card_drift",
    "enqueue_card_refresh",
    "list_pending_card_refresh",
    "delete_card_refresh",
    "agents_needing_card_refresh",
    "enqueue_all_agents_for_refresh",
    "max_indexed_block",
    "upsert_agent_score",
    "get_agent_score",
    "enqueue_score_refresh",
    "list_pending_score_refresh",
    "delete_score_refresh",
    "agents_needing_score_refresh",
    "enqueue_all_agents_for_scoring",
    "api_key_hash",
    "create_api_key",
    "is_valid_api_key",
    "api_key_label",
    "upsert_b20_token",
    "get_b20_token",
    "list_b20_tokens",
    "record_usage_event",
    "usage_summary",
    "UsageSummaryRow",
]


def _insert(session: Session, model: type) -> Any:
    """Return a dialect-appropriate INSERT construct supporting ON CONFLICT."""
    dialect = session.get_bind().dialect.name
    if dialect == "postgresql":
        return pg_insert(model)
    if dialect == "sqlite":
        return sqlite_insert(model)
    raise RuntimeError(f"unsupported dialect for upsert: {dialect}")


def _insert_ignore(
    session: Session, model: type, values: dict[str, Any], conflict_cols: list[str]
) -> bool:
    """Insert-or-ignore on a conflict target. Returns True iff a row was inserted."""
    stmt = (
        _insert(session, model)
        .values(**values)
        .on_conflict_do_nothing(index_elements=conflict_cols)
    )
    result = cast(CursorResult[Any], session.execute(stmt))
    return bool(result.rowcount)


# ── raw_logs ─────────────────────────────────────────────────────────────────


def upsert_raw_log(
    session: Session,
    *,
    address: str,
    block_number: int,
    block_hash: str,
    tx_hash: str,
    log_index: int,
    topic0: str,
    topics: list[str],
    data: str,
    log_removed: bool = False,
) -> bool:
    return _insert_ignore(
        session,
        RawLog,
        {
            "address": address.lower(),
            "block_number": block_number,
            "block_hash": block_hash.lower(),
            "tx_hash": tx_hash.lower(),
            "log_index": log_index,
            "topic0": topic0.lower(),
            "topics": [t.lower() for t in topics],
            "data": data,
            "log_removed": log_removed,
        },
        ["tx_hash", "log_index"],
    )


def raw_logs_above(session: Session, block_number: int) -> list[RawLog]:
    return list(session.execute(select(RawLog).where(RawLog.block_number > block_number)).scalars())


def block_hashes_in_range(
    session: Session, low: int, high: int, addresses: list[str] | None = None
) -> list[tuple[int, str]]:
    """Distinct ``(block_number, block_hash)`` for indexed blocks in ``[low, high]``.

    Used for reorg detection: a stored hash that no longer matches the chain marks a fork.
    ``addresses`` scopes the scan to one registry's contract(s) — required because both
    registries share ``raw_logs``.
    """
    stmt = select(RawLog.block_number, RawLog.block_hash).where(
        RawLog.block_number >= low, RawLog.block_number <= high
    )
    if addresses is not None:
        stmt = stmt.where(RawLog.address.in_([a.lower() for a in addresses]))
    rows = session.execute(stmt.distinct().order_by(RawLog.block_number)).all()
    return [(int(bn), bh) for bn, bh in rows]


def raw_logs_by_topic0s(session: Session, topic0s: list[str]) -> list[RawLog]:
    """All logs matching any of ``topic0s``, ordered by (block_number, log_index)."""
    lowered = [t.lower() for t in topic0s]
    return list(
        session.execute(
            select(RawLog)
            .where(RawLog.topic0.in_(lowered))
            .order_by(RawLog.block_number, RawLog.log_index)
        ).scalars()
    )


# ── agents ───────────────────────────────────────────────────────────────────


def upsert_agent(
    session: Session,
    *,
    agent_id: int,
    owner: str,
    agent_uri: str,
    registered_block: int,
    registered_tx_hash: str,
    registered_log_index: int,
) -> bool:
    """Insert a newly registered agent. Registration is one-time → insert-or-ignore."""
    return _insert_ignore(
        session,
        Agent,
        {
            "agent_id": agent_id,
            "owner": owner.lower(),
            "agent_uri": agent_uri,
            "registered_block": registered_block,
            "registered_tx_hash": registered_tx_hash.lower(),
            "registered_log_index": registered_log_index,
        },
        ["agent_id"],
    )


def agent_exists(session: Session, agent_id: int) -> bool:
    return session.get(Agent, agent_id) is not None


def set_agent_owner(session: Session, agent_id: int, owner: str) -> None:
    agent = session.get(Agent, agent_id)
    if agent is not None:
        agent.owner = owner.lower()


def set_agent_uri(session: Session, agent_id: int, agent_uri: str) -> None:
    agent = session.get(Agent, agent_id)
    if agent is not None:
        agent.agent_uri = agent_uri


def append_owner_history(
    session: Session,
    *,
    agent_id: int,
    from_address: str,
    to_address: str,
    block_number: int,
    tx_hash: str,
    log_index: int,
) -> bool:
    return _insert_ignore(
        session,
        AgentOwnerHistory,
        {
            "agent_id": agent_id,
            "from_address": from_address.lower(),
            "to_address": to_address.lower(),
            "block_number": block_number,
            "tx_hash": tx_hash.lower(),
            "log_index": log_index,
        },
        ["tx_hash", "log_index"],
    )


def recompute_owner_from_history(session: Session, agent_id: int) -> None:
    """Set ``agents.owner`` to the ``to_address`` of the latest surviving history row."""
    latest = session.execute(
        select(AgentOwnerHistory)
        .where(AgentOwnerHistory.agent_id == agent_id)
        .order_by(AgentOwnerHistory.block_number.desc(), AgentOwnerHistory.log_index.desc())
        .limit(1)
    ).scalar_one_or_none()
    if latest is not None:
        set_agent_owner(session, agent_id, latest.to_address)


# ── metadata ─────────────────────────────────────────────────────────────────


def insert_metadata(
    session: Session,
    *,
    agent_id: int,
    metadata_key: str,
    indexed_key_hash: str,
    metadata_value: bytes,
    block_number: int,
    tx_hash: str,
    log_index: int,
) -> bool:
    return _insert_ignore(
        session,
        AgentMetadata,
        {
            "agent_id": agent_id,
            "metadata_key": metadata_key,
            "indexed_key_hash": indexed_key_hash.lower(),
            "metadata_value": metadata_value,
            "block_number": block_number,
            "tx_hash": tx_hash.lower(),
            "log_index": log_index,
        },
        ["tx_hash", "log_index"],
    )


# ── cursor ───────────────────────────────────────────────────────────────────


def get_cursor(session: Session, registry: str) -> IndexerCursor | None:
    return session.get(IndexerCursor, registry)


def upsert_cursor(
    session: Session, registry: str, anchor_block: int, last_indexed_block: int
) -> None:
    cursor = session.get(IndexerCursor, registry)
    if cursor is None:
        session.add(
            IndexerCursor(
                registry_name=registry,
                anchor_block=anchor_block,
                last_indexed_block=last_indexed_block,
            )
        )
    else:
        cursor.anchor_block = anchor_block
        cursor.last_indexed_block = last_indexed_block


def set_last_indexed_block(session: Session, registry: str, block_number: int) -> None:
    cursor = session.get(IndexerCursor, registry)
    if cursor is None:
        raise ValueError(f"no cursor for registry {registry!r}; call upsert_cursor first")
    cursor.last_indexed_block = block_number


# ── reorg rewind ─────────────────────────────────────────────────────────────


def delete_rows_above(
    session: Session,
    model: type,
    block_number: int,
    *,
    block_column: str = "block_number",
) -> None:
    """Delete rows of ``model`` whose block column is above ``block_number`` (reorg rewind)."""
    column = getattr(model, block_column)
    session.execute(delete(model).where(column > block_number))


def delete_raw_logs_above(session: Session, block_number: int, addresses: list[str]) -> None:
    """Delete ``raw_logs`` above ``block_number`` for the given contract address(es) only.

    Scoped by address so one registry's reorg rewind never deletes the other's logs from
    the shared ``raw_logs`` table.
    """
    lowered = [a.lower() for a in addresses]
    session.execute(
        delete(RawLog).where(RawLog.block_number > block_number, RawLog.address.in_(lowered))
    )


# ── continuity (verification harness 2.5) ────────────────────────────────────


def max_agent_id(session: Session) -> int | None:
    return session.execute(select(func.max(Agent.agent_id))).scalar_one_or_none()


def all_agent_ids(session: Session) -> list[int]:
    return list(session.execute(select(Agent.agent_id).order_by(Agent.agent_id)).scalars())


def missing_agent_ids(session: Session) -> list[int]:
    """Return the agentIds absent from the contiguous range ``1..max`` (should be empty)."""
    top = max_agent_id(session)
    if top is None:
        return []
    present = set(all_agent_ids(session))
    return [i for i in range(1, top + 1) if i not in present]


# ── reputation writes (proposal §3.2) ────────────────────────────────────────


def insert_feedback(
    session: Session,
    *,
    agent_id: int,
    client_address: str,
    feedback_index: int,
    value: int,
    value_decimals: int,
    value_scaled: Decimal,
    indexed_tag1_hash: str,
    tag1: str,
    tag2: str,
    endpoint: str,
    feedback_uri: str,
    feedback_hash: str,
    block_number: int,
    tx_hash: str,
    log_index: int,
) -> bool:
    return _insert_ignore(
        session,
        Feedback,
        {
            "agent_id": agent_id,
            "client_address": client_address.lower(),
            "feedback_index": feedback_index,
            "value": Decimal(value),
            "value_decimals": value_decimals,
            "value_scaled": value_scaled,
            "indexed_tag1_hash": indexed_tag1_hash.lower(),
            "tag1": tag1,
            "tag2": tag2,
            "endpoint": endpoint,
            "feedback_uri": feedback_uri,
            "feedback_hash": feedback_hash.lower(),
            "block_number": block_number,
            "tx_hash": tx_hash.lower(),
            "log_index": log_index,
        },
        ["tx_hash", "log_index"],
    )


def insert_feedback_revocation(
    session: Session,
    *,
    agent_id: int,
    client_address: str,
    feedback_index: int,
    block_number: int,
    tx_hash: str,
    log_index: int,
) -> bool:
    return _insert_ignore(
        session,
        FeedbackRevocation,
        {
            "agent_id": agent_id,
            "client_address": client_address.lower(),
            "feedback_index": feedback_index,
            "block_number": block_number,
            "tx_hash": tx_hash.lower(),
            "log_index": log_index,
        },
        ["tx_hash", "log_index"],
    )


def insert_feedback_response(
    session: Session,
    *,
    agent_id: int,
    client_address: str,
    feedback_index: int,
    responder: str,
    response_uri: str,
    response_hash: str,
    block_number: int,
    tx_hash: str,
    log_index: int,
) -> bool:
    return _insert_ignore(
        session,
        FeedbackResponse,
        {
            "agent_id": agent_id,
            "client_address": client_address.lower(),
            "feedback_index": feedback_index,
            "responder": responder.lower(),
            "response_uri": response_uri,
            "response_hash": response_hash.lower(),
            "block_number": block_number,
            "tx_hash": tx_hash.lower(),
            "log_index": log_index,
        },
        ["tx_hash", "log_index"],
    )


# ── rater credibility (proposal §3.4) ────────────────────────────────────────

RATER_CREDIBILITY_VIEW = "rater_credibility"

# Portable SQL kept in sync with ``rater_credibility_select`` via a cross-check test.
# Self-feedback = the rater was the owner of the rated agent AT THE FEEDBACK'S BLOCK HEIGHT
# (from agent_owner_history), not the current owner — consistent with the scoring engine.
RATER_CREDIBILITY_SQL = """
SELECT
    f.client_address AS client_address,
    MIN(f.block_number) AS first_seen_block,
    COUNT(*) AS feedback_count,
    COUNT(DISTINCT f.agent_id) AS distinct_agents_rated,
    SUM(
        CASE WHEN f.client_address = (
            SELECT h.to_address
            FROM agent_owner_history h
            WHERE h.agent_id = f.agent_id AND h.block_number <= f.block_number
            ORDER BY h.block_number DESC, h.log_index DESC
            LIMIT 1
        ) THEN 1 ELSE 0 END
    ) AS self_feedback_count
FROM feedback f
GROUP BY f.client_address
""".strip()


@dataclass(frozen=True)
class RaterCredibility:
    client_address: str
    first_seen_block: int
    feedback_count: int
    distinct_agents_rated: int
    self_feedback_count: int


def rater_credibility_select() -> Select[Any]:
    """The materialized-view query as a SQLAlchemy Select (single source of truth).

    Self-feedback is judged by the owner of the rated agent *at the feedback's block height*
    (a correlated lookup into ``agent_owner_history``), matching the scoring engine.
    """
    owner_at_block = (
        select(AgentOwnerHistory.to_address)
        .where(
            AgentOwnerHistory.agent_id == Feedback.agent_id,
            AgentOwnerHistory.block_number <= Feedback.block_number,
        )
        .order_by(
            AgentOwnerHistory.block_number.desc(),
            AgentOwnerHistory.log_index.desc(),
        )
        .limit(1)
        .correlate(Feedback)
        .scalar_subquery()
    )
    self_feedback = func.sum(case((Feedback.client_address == owner_at_block, 1), else_=0))
    return (
        select(
            Feedback.client_address.label("client_address"),
            func.min(Feedback.block_number).label("first_seen_block"),
            func.count().label("feedback_count"),
            func.count(func.distinct(Feedback.agent_id)).label("distinct_agents_rated"),
            self_feedback.label("self_feedback_count"),
        )
        .select_from(Feedback)
        .group_by(Feedback.client_address)
    )


def rater_credibility_rows(session: Session) -> list[RaterCredibility]:
    """Compute rater credibility directly from ``feedback`` (portable; used in tests)."""
    rows = session.execute(rater_credibility_select()).all()
    return [
        RaterCredibility(
            client_address=r.client_address,
            first_seen_block=int(r.first_seen_block),
            feedback_count=int(r.feedback_count),
            distinct_agents_rated=int(r.distinct_agents_rated),
            self_feedback_count=int(r.self_feedback_count or 0),
        )
        for r in rows
    ]


def refresh_rater_credibility(session: Session) -> None:
    """Refresh the Postgres materialized view. No-op on SQLite (plain view is live)."""
    from sqlalchemy import text

    if session.get_bind().dialect.name == "postgresql":
        session.execute(text(f"REFRESH MATERIALIZED VIEW {RATER_CREDIBILITY_VIEW}"))


# ── agent card pipeline (proposal §4) ────────────────────────────────────────


def get_agent_wallet(session: Session, agent_id: int) -> str | None:
    """Return the agent's latest on-chain ``agentWallet`` (from indexed MetadataSet), or None.

    The reserved ``agentWallet`` metadata value is a 20-byte address (stored as bytes); a
    32-byte left-padded encoding is also tolerated.
    """
    row = session.execute(
        select(AgentMetadata.metadata_value)
        .where(
            AgentMetadata.agent_id == agent_id,
            AgentMetadata.metadata_key == "agentWallet",
        )
        .order_by(AgentMetadata.block_number.desc(), AgentMetadata.log_index.desc())
        .limit(1)
    ).scalar_one_or_none()
    if row is None:
        return None
    value = bytes(row)
    if len(value) >= 20:
        return "0x" + value[-20:].hex()
    return None


def upsert_agent_card(
    session: Session,
    *,
    agent_id: int,
    token_uri: str,
    fetch_status: str,
    http_status: int | None = None,
    source: str | None = None,
    content: str | None = None,
    content_hash: str | None = None,
    schema_valid: bool | None = None,
    schema_errors: list[str] | None = None,
    registration_match: bool | None = None,
    wallet_status: str | None = None,
) -> None:
    """Insert or replace the latest card state for an agent (one row per agent)."""
    card = session.get(AgentCard, agent_id)
    if card is None:
        card = AgentCard(agent_id=agent_id, token_uri=token_uri, fetch_status=fetch_status)
        session.add(card)
    card.token_uri = token_uri
    card.fetch_status = fetch_status
    card.http_status = http_status
    card.source = source
    card.content = content
    card.content_hash = content_hash
    card.schema_valid = schema_valid
    card.schema_errors = schema_errors
    card.registration_match = registration_match
    card.wallet_status = wallet_status
    card.fetched_at = datetime.now(UTC)


def get_agent_card(session: Session, agent_id: int) -> AgentCard | None:
    return session.get(AgentCard, agent_id)


def record_card_drift(
    session: Session,
    *,
    agent_id: int,
    token_uri: str,
    old_content_hash: str | None,
    new_content_hash: str | None,
) -> None:
    session.add(
        CardDrift(
            agent_id=agent_id,
            token_uri=token_uri,
            old_content_hash=old_content_hash,
            new_content_hash=new_content_hash,
        )
    )


def enqueue_card_refresh(session: Session, agent_id: int, reason: str) -> bool:
    """Enqueue an agent for (re)fetch. One pending entry per agent (insert-or-ignore)."""
    return _insert_ignore(
        session,
        CardRefreshQueue,
        {"agent_id": agent_id, "reason": reason, "attempts": 0},
        ["agent_id"],
    )


def list_pending_card_refresh(session: Session, limit: int = 100) -> list[CardRefreshQueue]:
    return list(
        session.execute(
            select(CardRefreshQueue).order_by(CardRefreshQueue.enqueued_at).limit(limit)
        ).scalars()
    )


def delete_card_refresh(session: Session, agent_id: int) -> None:
    entry = session.get(CardRefreshQueue, agent_id)
    if entry is not None:
        session.delete(entry)


def agents_needing_card_refresh(session: Session) -> list[tuple[int, str]]:
    """Agents that should be (re)fetched: never fetched (``new_agent``) or whose current
    ``agent_uri`` differs from the last-fetched ``token_uri`` (``uri_updated``)."""
    result: list[tuple[int, str]] = []
    rows = session.execute(
        select(Agent.agent_id, Agent.agent_uri, AgentCard.token_uri).outerjoin(
            AgentCard, AgentCard.agent_id == Agent.agent_id
        )
    ).all()
    for agent_id, agent_uri, card_uri in rows:
        if card_uri is None:
            result.append((agent_id, "new_agent"))
        elif agent_uri != card_uri:
            result.append((agent_id, "uri_updated"))
    return result


def enqueue_all_agents_for_refresh(session: Session, reason: str = "periodic") -> int:
    """Enqueue every known agent (periodic sweep). Returns the number newly enqueued."""
    enqueued = 0
    for agent_id in all_agent_ids(session):
        if enqueue_card_refresh(session, agent_id, reason):
            enqueued += 1
    return enqueued


# ── scoring persistence (proposal §5.3) ──────────────────────────────────────


def max_indexed_block(session: Session) -> int:
    """The highest indexed block (frontier), used as the scoring ``as_of_block`` default."""
    return int(session.execute(select(func.max(RawLog.block_number))).scalar_one_or_none() or 0)


def upsert_agent_score(
    session: Session,
    *,
    agent_id: int,
    score: int | None,
    confidence: str,
    sufficient: bool,
    breakdown: list[dict[str, Any]],
    weights_version: str,
    as_of_block: int,
) -> None:
    row = session.get(AgentScore, agent_id)
    if row is None:
        row = AgentScore(
            agent_id=agent_id,
            confidence=confidence,
            weights_version=weights_version,
            as_of_block=as_of_block,
        )
        session.add(row)
    row.score = score
    row.confidence = confidence
    row.sufficient = sufficient
    row.breakdown = breakdown
    row.weights_version = weights_version
    row.as_of_block = as_of_block


def get_agent_score(session: Session, agent_id: int) -> AgentScore | None:
    return session.get(AgentScore, agent_id)


def enqueue_score_refresh(session: Session, agent_id: int, reason: str) -> bool:
    return _insert_ignore(
        session, ScoreRefreshQueue, {"agent_id": agent_id, "reason": reason}, ["agent_id"]
    )


def list_pending_score_refresh(session: Session, limit: int = 100) -> list[ScoreRefreshQueue]:
    return list(
        session.execute(
            select(ScoreRefreshQueue).order_by(ScoreRefreshQueue.enqueued_at).limit(limit)
        ).scalars()
    )


def delete_score_refresh(session: Session, agent_id: int) -> None:
    entry = session.get(ScoreRefreshQueue, agent_id)
    if entry is not None:
        session.delete(entry)


def agents_needing_score_refresh(session: Session) -> list[tuple[int, str]]:
    """Agents that should be rescored: never scored (``new_agent``) or with on-chain activity
    (feedback / ownership change) after the block their score was last computed for."""
    result: list[tuple[int, str]] = []

    latest_feedback = (
        select(Feedback.agent_id, func.max(Feedback.block_number).label("blk"))
        .group_by(Feedback.agent_id)
        .subquery()
    )
    latest_owner = (
        select(
            AgentOwnerHistory.agent_id,
            func.max(AgentOwnerHistory.block_number).label("blk"),
        )
        .group_by(AgentOwnerHistory.agent_id)
        .subquery()
    )

    rows = session.execute(
        select(
            Agent.agent_id,
            AgentScore.as_of_block,
            latest_feedback.c.blk,
            latest_owner.c.blk,
        )
        .outerjoin(AgentScore, AgentScore.agent_id == Agent.agent_id)
        .outerjoin(latest_feedback, latest_feedback.c.agent_id == Agent.agent_id)
        .outerjoin(latest_owner, latest_owner.c.agent_id == Agent.agent_id)
    ).all()

    for agent_id, scored_block, fb_blk, owner_blk in rows:
        if scored_block is None:
            result.append((agent_id, "new_agent"))
            continue
        activity = max(int(fb_blk or 0), int(owner_blk or 0))
        if activity > int(scored_block):
            result.append((agent_id, "activity"))
    return result


def enqueue_all_agents_for_scoring(session: Session, reason: str = "periodic") -> int:
    """Enqueue every known agent for rescoring (nightly full sweep)."""
    enqueued = 0
    for agent_id in all_agent_ids(session):
        if enqueue_score_refresh(session, agent_id, reason):
            enqueued += 1
    return enqueued


# ── API keys (proposal §6.2) ─────────────────────────────────────────────────


def api_key_hash(plaintext: str) -> str:
    """SHA-256 hex of an API key. Only the hash is ever stored."""
    return hashlib.sha256(plaintext.encode()).hexdigest()


def create_api_key(session: Session, plaintext: str, label: str = "") -> None:
    """Store an API key by hash (idempotent on the hash). The plaintext is never persisted."""
    _insert_ignore(
        session,
        ApiKey,
        {"key_hash": api_key_hash(plaintext), "label": label, "active": True},
        ["key_hash"],
    )


def is_valid_api_key(session: Session, plaintext: str) -> bool:
    """True iff the key exists and is active."""
    if not plaintext:
        return False
    row = session.execute(
        select(ApiKey.active).where(ApiKey.key_hash == api_key_hash(plaintext))
    ).scalar_one_or_none()
    return bool(row)


def api_key_label(session: Session, plaintext: str) -> str | None:
    """Return an active key's label (for metering attribution), or None if invalid."""
    if not plaintext:
        return None
    return session.execute(
        select(ApiKey.label).where(
            ApiKey.key_hash == api_key_hash(plaintext), ApiKey.active.is_(True)
        )
    ).scalar_one_or_none()


# ── B20 token registry (proposal §7.2) ───────────────────────────────────────


def upsert_b20_token(
    session: Session, address: str, symbol: str, decimals: int, active: bool = True
) -> None:
    token = session.get(B20Token, address.lower())
    if token is None:
        token = B20Token(address=address.lower(), symbol=symbol, decimals=decimals)
        session.add(token)
    token.symbol = symbol
    token.decimals = decimals
    token.active = active


def get_b20_token(session: Session, key: str) -> B20Token | None:
    """Resolve a known, active B20 token by contract address or symbol (case-insensitive)."""
    return session.execute(
        select(B20Token).where(
            B20Token.active.is_(True),
            (B20Token.address == key.lower()) | (B20Token.symbol == key),
        )
    ).scalar_one_or_none()


def list_b20_tokens(session: Session, active_only: bool = True) -> list[B20Token]:
    stmt = select(B20Token).order_by(B20Token.symbol)
    if active_only:
        stmt = stmt.where(B20Token.active.is_(True))
    return list(session.execute(stmt).scalars())


# ── usage metering (proposal §9.3) ───────────────────────────────────────────


def record_usage_event(
    session: Session,
    *,
    endpoint: str,
    method: str,
    payer: str,
    payment_kind: str,
    amount_atomic: int = 0,
    asset: str | None = None,
    tx_hash: str | None = None,
) -> None:
    session.add(
        UsageEvent(
            endpoint=endpoint,
            method=method,
            payer=payer,
            payment_kind=payment_kind,
            amount_atomic=amount_atomic,
            asset=asset,
            tx_hash=tx_hash,
        )
    )


@dataclass(frozen=True)
class UsageSummaryRow:
    endpoint: str
    payment_kind: str
    calls: int
    revenue_atomic: int


def usage_summary(session: Session) -> list[UsageSummaryRow]:
    """Per-(endpoint, payment_kind) call counts and revenue (atomic units)."""
    rows = session.execute(
        select(
            UsageEvent.endpoint,
            UsageEvent.payment_kind,
            func.count(),
            func.coalesce(func.sum(UsageEvent.amount_atomic), 0),
        )
        .group_by(UsageEvent.endpoint, UsageEvent.payment_kind)
        .order_by(UsageEvent.endpoint, UsageEvent.payment_kind)
    ).all()
    return [
        UsageSummaryRow(endpoint=e, payment_kind=k, calls=int(c), revenue_atomic=int(rev))
        for e, k, c, rev in rows
    ]

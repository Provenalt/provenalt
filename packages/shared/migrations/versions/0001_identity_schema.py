"""identity index schema: agents, agent_metadata, agent_owner_history, raw_logs, indexer_cursor

Revision ID: 0001_identity_schema
Revises:
Create Date: 2026-09-01
"""

from __future__ import annotations

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "0001_identity_schema"
down_revision: str | None = None
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "raw_logs",
        sa.Column("id", sa.Integer(), primary_key=True, autoincrement=True),
        sa.Column("address", sa.String(length=42), nullable=False),
        sa.Column("block_number", sa.BigInteger(), nullable=False),
        sa.Column("block_hash", sa.String(length=66), nullable=False),
        sa.Column("tx_hash", sa.String(length=66), nullable=False),
        sa.Column("log_index", sa.Integer(), nullable=False),
        sa.Column("topic0", sa.String(length=66), nullable=False),
        sa.Column("topics", sa.JSON(), nullable=False),
        sa.Column("data", sa.String(), nullable=False),
        sa.Column("log_removed", sa.Boolean(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=True),
        sa.UniqueConstraint("tx_hash", "log_index", name="uq_raw_logs_tx_log"),
    )
    op.create_index("ix_raw_logs_block_number", "raw_logs", ["block_number"])
    op.create_index("ix_raw_logs_address_topic0", "raw_logs", ["address", "topic0"])

    op.create_table(
        "agents",
        sa.Column("agent_id", sa.BigInteger(), primary_key=True, autoincrement=False),
        sa.Column("owner", sa.String(length=42), nullable=False),
        sa.Column("agent_uri", sa.String(), nullable=False),
        sa.Column("registered_block", sa.BigInteger(), nullable=False),
        sa.Column("registered_tx_hash", sa.String(length=66), nullable=False),
        sa.Column("registered_log_index", sa.Integer(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=True),
    )

    op.create_table(
        "agent_metadata",
        sa.Column("id", sa.Integer(), primary_key=True, autoincrement=True),
        sa.Column("agent_id", sa.BigInteger(), nullable=False),
        sa.Column("metadata_key", sa.String(), nullable=False),
        sa.Column("indexed_key_hash", sa.String(length=66), nullable=False),
        sa.Column("metadata_value", sa.LargeBinary(), nullable=False),
        sa.Column("block_number", sa.BigInteger(), nullable=False),
        sa.Column("tx_hash", sa.String(length=66), nullable=False),
        sa.Column("log_index", sa.Integer(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=True),
        sa.UniqueConstraint("tx_hash", "log_index", name="uq_agent_metadata_tx_log"),
    )
    op.create_index("ix_agent_metadata_agent_id", "agent_metadata", ["agent_id"])

    op.create_table(
        "agent_owner_history",
        sa.Column("id", sa.Integer(), primary_key=True, autoincrement=True),
        sa.Column("agent_id", sa.BigInteger(), nullable=False),
        sa.Column("from_address", sa.String(length=42), nullable=False),
        sa.Column("to_address", sa.String(length=42), nullable=False),
        sa.Column("block_number", sa.BigInteger(), nullable=False),
        sa.Column("tx_hash", sa.String(length=66), nullable=False),
        sa.Column("log_index", sa.Integer(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=True),
        sa.UniqueConstraint("tx_hash", "log_index", name="uq_agent_owner_history_tx_log"),
    )
    op.create_index("ix_agent_owner_history_agent_id", "agent_owner_history", ["agent_id"])

    op.create_table(
        "indexer_cursor",
        sa.Column("registry", sa.String(length=64), primary_key=True),
        sa.Column("anchor_block", sa.BigInteger(), nullable=False),
        sa.Column("last_indexed_block", sa.BigInteger(), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=True),
    )


def downgrade() -> None:
    op.drop_table("indexer_cursor")
    op.drop_index("ix_agent_owner_history_agent_id", table_name="agent_owner_history")
    op.drop_table("agent_owner_history")
    op.drop_index("ix_agent_metadata_agent_id", table_name="agent_metadata")
    op.drop_table("agent_metadata")
    op.drop_table("agents")
    op.drop_index("ix_raw_logs_address_topic0", table_name="raw_logs")
    op.drop_index("ix_raw_logs_block_number", table_name="raw_logs")
    op.drop_table("raw_logs")

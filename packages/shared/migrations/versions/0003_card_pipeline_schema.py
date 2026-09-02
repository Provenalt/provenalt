"""agent card pipeline schema: agent_cards, card_drift, card_refresh_queue

Revision ID: 0003_card_pipeline_schema
Revises: 0002_reputation_schema
Create Date: 2026-09-02
"""

from __future__ import annotations

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "0003_card_pipeline_schema"
down_revision: str | None = "0002_reputation_schema"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "agent_cards",
        sa.Column("agent_id", sa.BigInteger(), primary_key=True, autoincrement=False),
        sa.Column("token_uri", sa.String(), nullable=False),
        sa.Column("fetch_status", sa.String(length=32), nullable=False),
        sa.Column("http_status", sa.Integer(), nullable=True),
        sa.Column("source", sa.String(), nullable=True),
        sa.Column("content", sa.String(), nullable=True),
        sa.Column("content_hash", sa.String(length=64), nullable=True),
        sa.Column("schema_valid", sa.Boolean(), nullable=True),
        sa.Column("schema_errors", sa.JSON(), nullable=True),
        sa.Column("registration_match", sa.Boolean(), nullable=True),
        sa.Column("wallet_status", sa.String(length=32), nullable=True),
        sa.Column("fetched_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=True),
    )

    op.create_table(
        "card_drift",
        sa.Column("id", sa.Integer(), primary_key=True, autoincrement=True),
        sa.Column("agent_id", sa.BigInteger(), nullable=False),
        sa.Column("token_uri", sa.String(), nullable=False),
        sa.Column("old_content_hash", sa.String(length=64), nullable=True),
        sa.Column("new_content_hash", sa.String(length=64), nullable=True),
        sa.Column("detected_at", sa.DateTime(timezone=True), nullable=True),
    )
    op.create_index("ix_card_drift_agent_id", "card_drift", ["agent_id"])

    op.create_table(
        "card_refresh_queue",
        sa.Column("agent_id", sa.BigInteger(), primary_key=True, autoincrement=False),
        sa.Column("reason", sa.String(length=32), nullable=False),
        sa.Column("attempts", sa.Integer(), nullable=False),
        sa.Column("enqueued_at", sa.DateTime(timezone=True), nullable=True),
    )


def downgrade() -> None:
    op.drop_table("card_refresh_queue")
    op.drop_index("ix_card_drift_agent_id", table_name="card_drift")
    op.drop_table("card_drift")
    op.drop_table("agent_cards")

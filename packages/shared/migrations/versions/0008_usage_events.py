"""usage metering events for gated endpoints

Revision ID: 0008_usage_events
Revises: 0007_b20_tokens
Create Date: 2026-09-03
"""

from __future__ import annotations

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "0008_usage_events"
down_revision: str | None = "0007_b20_tokens"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "usage_events",
        sa.Column("id", sa.Integer(), primary_key=True, autoincrement=True),
        sa.Column("endpoint", sa.String(length=64), nullable=False),
        sa.Column("method", sa.String(length=8), nullable=False),
        sa.Column("payer", sa.String(length=128), nullable=False),
        sa.Column("payment_kind", sa.String(length=16), nullable=False),
        sa.Column("amount_atomic", sa.BigInteger(), nullable=False),
        sa.Column("asset", sa.String(length=42), nullable=True),
        sa.Column("tx_hash", sa.String(length=66), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=True),
    )
    op.create_index("ix_usage_events_endpoint", "usage_events", ["endpoint"])
    op.create_index("ix_usage_events_payer", "usage_events", ["payer"])


def downgrade() -> None:
    op.drop_index("ix_usage_events_payer", table_name="usage_events")
    op.drop_index("ix_usage_events_endpoint", table_name="usage_events")
    op.drop_table("usage_events")

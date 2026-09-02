"""scoring schema: agent_scores, score_refresh_queue

Revision ID: 0004_scoring_schema
Revises: 0003_card_pipeline_schema
Create Date: 2026-09-02
"""

from __future__ import annotations

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "0004_scoring_schema"
down_revision: str | None = "0003_card_pipeline_schema"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "agent_scores",
        sa.Column("agent_id", sa.BigInteger(), primary_key=True, autoincrement=False),
        sa.Column("score", sa.Integer(), nullable=True),
        sa.Column("confidence", sa.String(length=32), nullable=False),
        sa.Column("sufficient", sa.Boolean(), nullable=False),
        sa.Column("breakdown", sa.JSON(), nullable=False),
        sa.Column("weights_version", sa.String(length=16), nullable=False),
        sa.Column("as_of_block", sa.BigInteger(), nullable=False),
        sa.Column("computed_at", sa.DateTime(timezone=True), nullable=True),
    )

    op.create_table(
        "score_refresh_queue",
        sa.Column("agent_id", sa.BigInteger(), primary_key=True, autoincrement=False),
        sa.Column("reason", sa.String(length=32), nullable=False),
        sa.Column("enqueued_at", sa.DateTime(timezone=True), nullable=True),
    )


def downgrade() -> None:
    op.drop_table("score_refresh_queue")
    op.drop_table("agent_scores")

"""reputation schema: feedback, feedback_revocations, feedback_responses + rater_credibility

Revision ID: 0002_reputation_schema
Revises: 0001_identity_schema
Create Date: 2026-09-02
"""

from __future__ import annotations

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "0002_reputation_schema"
down_revision: str | None = "0001_identity_schema"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

# Frozen copy of the rater-credibility view definition as of this migration. A migration
# must be self-contained and immutable, so the SQL is a literal here rather than imported
# from application code. A parity test (test_migrations.py) asserts that the app's current
# ``repository.RATER_CREDIBILITY_SQL`` still equals this literal — if the app SQL changes,
# add a new migration that recreates the view instead of editing this one.
RATER_CREDIBILITY_VIEW = "rater_credibility"
RATER_CREDIBILITY_SQL = """SELECT
    f.client_address AS client_address,
    MIN(f.block_number) AS first_seen_block,
    COUNT(*) AS feedback_count,
    COUNT(DISTINCT f.agent_id) AS distinct_agents_rated,
    SUM(CASE WHEN a.owner = f.client_address THEN 1 ELSE 0 END) AS self_feedback_count
FROM feedback f
LEFT JOIN agents a ON a.agent_id = f.agent_id
GROUP BY f.client_address"""


def upgrade() -> None:
    op.create_table(
        "feedback",
        sa.Column("id", sa.Integer(), primary_key=True, autoincrement=True),
        sa.Column("agent_id", sa.BigInteger(), nullable=False),
        sa.Column("client_address", sa.String(length=42), nullable=False),
        sa.Column("feedback_index", sa.BigInteger(), nullable=False),
        sa.Column("value", sa.Numeric(40, 0), nullable=False),
        sa.Column("value_decimals", sa.Integer(), nullable=False),
        sa.Column("value_scaled", sa.Numeric(60, 18), nullable=False),
        sa.Column("indexed_tag1_hash", sa.String(length=66), nullable=False),
        sa.Column("tag1", sa.String(), nullable=False),
        sa.Column("tag2", sa.String(), nullable=False),
        sa.Column("endpoint", sa.String(), nullable=False),
        sa.Column("feedback_uri", sa.String(), nullable=False),
        sa.Column("feedback_hash", sa.String(length=66), nullable=False),
        sa.Column("block_number", sa.BigInteger(), nullable=False),
        sa.Column("tx_hash", sa.String(length=66), nullable=False),
        sa.Column("log_index", sa.Integer(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=True),
        sa.UniqueConstraint("tx_hash", "log_index", name="uq_feedback_tx_log"),
    )
    op.create_index("ix_feedback_agent_id", "feedback", ["agent_id"])
    op.create_index("ix_feedback_client_address", "feedback", ["client_address"])

    op.create_table(
        "feedback_revocations",
        sa.Column("id", sa.Integer(), primary_key=True, autoincrement=True),
        sa.Column("agent_id", sa.BigInteger(), nullable=False),
        sa.Column("client_address", sa.String(length=42), nullable=False),
        sa.Column("feedback_index", sa.BigInteger(), nullable=False),
        sa.Column("block_number", sa.BigInteger(), nullable=False),
        sa.Column("tx_hash", sa.String(length=66), nullable=False),
        sa.Column("log_index", sa.Integer(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=True),
        sa.UniqueConstraint("tx_hash", "log_index", name="uq_feedback_revocations_tx_log"),
    )
    op.create_index(
        "ix_feedback_revocations_feedback",
        "feedback_revocations",
        ["agent_id", "client_address", "feedback_index"],
    )

    op.create_table(
        "feedback_responses",
        sa.Column("id", sa.Integer(), primary_key=True, autoincrement=True),
        sa.Column("agent_id", sa.BigInteger(), nullable=False),
        sa.Column("client_address", sa.String(length=42), nullable=False),
        sa.Column("feedback_index", sa.BigInteger(), nullable=False),
        sa.Column("responder", sa.String(length=42), nullable=False),
        sa.Column("response_uri", sa.String(), nullable=False),
        sa.Column("response_hash", sa.String(length=66), nullable=False),
        sa.Column("block_number", sa.BigInteger(), nullable=False),
        sa.Column("tx_hash", sa.String(length=66), nullable=False),
        sa.Column("log_index", sa.Integer(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=True),
        sa.UniqueConstraint("tx_hash", "log_index", name="uq_feedback_responses_tx_log"),
    )
    op.create_index(
        "ix_feedback_responses_feedback",
        "feedback_responses",
        ["agent_id", "client_address", "feedback_index"],
    )

    # Rater credibility (§3.4). Materialized on Postgres (production); a plain view on
    # SQLite so tests can query the same shape. The SELECT is the single source of truth
    # in repository.RATER_CREDIBILITY_SQL.
    if op.get_bind().dialect.name == "postgresql":
        op.execute(f"CREATE MATERIALIZED VIEW {RATER_CREDIBILITY_VIEW} AS {RATER_CREDIBILITY_SQL}")
        op.execute(
            f"CREATE UNIQUE INDEX ix_rater_credibility_client "
            f"ON {RATER_CREDIBILITY_VIEW} (client_address)"
        )
    else:
        op.execute(f"CREATE VIEW {RATER_CREDIBILITY_VIEW} AS {RATER_CREDIBILITY_SQL}")


def downgrade() -> None:
    if op.get_bind().dialect.name == "postgresql":
        op.execute(f"DROP MATERIALIZED VIEW IF EXISTS {RATER_CREDIBILITY_VIEW}")
    else:
        op.execute(f"DROP VIEW IF EXISTS {RATER_CREDIBILITY_VIEW}")

    op.drop_index("ix_feedback_responses_feedback", table_name="feedback_responses")
    op.drop_table("feedback_responses")
    op.drop_index("ix_feedback_revocations_feedback", table_name="feedback_revocations")
    op.drop_table("feedback_revocations")
    op.drop_index("ix_feedback_client_address", table_name="feedback")
    op.drop_index("ix_feedback_agent_id", table_name="feedback")
    op.drop_table("feedback")

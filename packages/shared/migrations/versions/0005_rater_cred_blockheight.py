"""rater_credibility: block-height-correct self-feedback

Recreates the ``rater_credibility`` view so self-feedback is judged by the owner of the rated
agent AT THE FEEDBACK'S BLOCK HEIGHT (via agent_owner_history), consistent with the Group 5
scoring engine — replacing the previous current-owner definition. Migrations are immutable, so
this does not edit 0002; it drops and recreates the view with the corrected SQL.

Revision ID: 0005_rater_cred_blockheight
Revises: 0004_scoring_schema
Create Date: 2026-09-02

Note: the revision id is a short slug (<= 32 chars) so it fits Alembic's default
``alembic_version.version_num VARCHAR(32)`` column on Postgres.
"""

from __future__ import annotations

from collections.abc import Sequence

from alembic import op

revision: str = "0005_rater_cred_blockheight"
down_revision: str | None = "0004_scoring_schema"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

RATER_CREDIBILITY_VIEW = "rater_credibility"

# Frozen copy of the corrected view SQL as of this migration. A parity test asserts the app's
# current ``repository.RATER_CREDIBILITY_SQL`` still equals this literal.
RATER_CREDIBILITY_SQL = """SELECT
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
GROUP BY f.client_address"""

# The previous (current-owner) definition, restored by downgrade().
_PREVIOUS_SQL = """SELECT
    f.client_address AS client_address,
    MIN(f.block_number) AS first_seen_block,
    COUNT(*) AS feedback_count,
    COUNT(DISTINCT f.agent_id) AS distinct_agents_rated,
    SUM(CASE WHEN a.owner = f.client_address THEN 1 ELSE 0 END) AS self_feedback_count
FROM feedback f
LEFT JOIN agents a ON a.agent_id = f.agent_id
GROUP BY f.client_address"""


def _recreate_view(sql: str) -> None:
    if op.get_bind().dialect.name == "postgresql":
        op.execute(f"DROP MATERIALIZED VIEW IF EXISTS {RATER_CREDIBILITY_VIEW}")
        op.execute(f"CREATE MATERIALIZED VIEW {RATER_CREDIBILITY_VIEW} AS {sql}")
        op.execute(
            f"CREATE UNIQUE INDEX ix_rater_credibility_client "
            f"ON {RATER_CREDIBILITY_VIEW} (client_address)"
        )
    else:
        op.execute(f"DROP VIEW IF EXISTS {RATER_CREDIBILITY_VIEW}")
        op.execute(f"CREATE VIEW {RATER_CREDIBILITY_VIEW} AS {sql}")


def upgrade() -> None:
    _recreate_view(RATER_CREDIBILITY_SQL)


def downgrade() -> None:
    _recreate_view(_PREVIOUS_SQL)

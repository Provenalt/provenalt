"""b20 tokens registry (known tokenized stocks) + seed the 4 live stocks

Revision ID: 0007_b20_tokens
Revises: 0006_api_keys
Create Date: 2026-09-02
"""

from __future__ import annotations

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "0007_b20_tokens"
down_revision: str | None = "0006_api_keys"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

# Live B20 tokenized stocks (proposal §3, all decimals=8). Addresses stored lowercased.
_SEED = [
    {"address": "0xb200000000000000000000c2e324d24d7eecd1fb", "symbol": "AAPLc", "decimals": 8},
    {"address": "0xb20000000000000000000078ee7ce2fe4908108c", "symbol": "NVDAc", "decimals": 8},
    {"address": "0xb2000000000000000000002d0ba3164cc74f58b7", "symbol": "GOOGLc", "decimals": 8},
    {"address": "0xb2000000000000000000008bc8786b856e61707c", "symbol": "METAc", "decimals": 8},
]


def upgrade() -> None:
    table = op.create_table(
        "b20_tokens",
        sa.Column("address", sa.String(length=42), primary_key=True),
        sa.Column("symbol", sa.String(length=32), nullable=False),
        sa.Column("decimals", sa.Integer(), nullable=False),
        sa.Column("active", sa.Boolean(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=True),
    )
    op.bulk_insert(table, [{**row, "active": True} for row in _SEED])


def downgrade() -> None:
    op.drop_table("b20_tokens")

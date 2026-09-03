#!/usr/bin/env python3
"""Internal usage + revenue summary (proposal §9.3).

Reads the metered usage events and prints per-endpoint call counts and revenue. Run:

    DATABASE_URL=postgresql://... python scripts/usage_report.py
"""

from __future__ import annotations

from decimal import Decimal

from provenalt_shared.db import make_engine, make_session_factory
from provenalt_shared.db import repository as repo
from provenalt_shared.settings import get_settings

USDC_DECIMALS = 6


def main() -> None:
    settings = get_settings()
    if not settings.database_url:
        raise SystemExit("DATABASE_URL is required")

    with make_session_factory(make_engine(settings.database_url))() as session:
        rows = repo.usage_summary(session)

    if not rows:
        print("No usage recorded yet.")
        return

    print(f"{'endpoint':<14}{'kind':<14}{'calls':>10}{'revenue (USDC)':>18}")
    print("-" * 56)
    total_calls = 0
    total_revenue = Decimal(0)
    for r in rows:
        revenue = Decimal(r.revenue_atomic) / (Decimal(10) ** USDC_DECIMALS)
        total_calls += r.calls
        total_revenue += revenue
        print(f"{r.endpoint:<14}{r.payment_kind:<14}{r.calls:>10}{revenue:>18.6f}")
    print("-" * 56)
    print(f"{'TOTAL':<28}{total_calls:>10}{total_revenue:>18.6f}")


if __name__ == "__main__":
    main()

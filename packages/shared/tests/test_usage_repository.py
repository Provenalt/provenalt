"""Unit tests for usage metering repository helpers (proposal §9.3)."""

from __future__ import annotations

import pytest
from sqlalchemy.orm import Session

from provenalt_shared.db import Base, make_engine, make_session_factory
from provenalt_shared.db import repository as repo


@pytest.fixture
def session() -> Session:
    engine = make_engine("sqlite://")
    Base.metadata.create_all(engine)
    with make_session_factory(engine)() as s:
        yield s


def test_record_and_summarize_usage(session: Session) -> None:
    repo.record_usage_event(
        session,
        endpoint="score",
        method="GET",
        payer="0xabc",
        payment_kind="paid",
        amount_atomic=10000,
        asset="0xusdc",
        tx_hash="0xtx",
    )
    repo.record_usage_event(
        session,
        endpoint="score",
        method="GET",
        payer="0xdef",
        payment_kind="paid",
        amount_atomic=10000,
        asset="0xusdc",
        tx_hash="0xtx2",
    )
    repo.record_usage_event(
        session,
        endpoint="score",
        method="GET",
        payer="key:acme",
        payment_kind="api_key",
    )
    repo.record_usage_event(
        session,
        endpoint="eligibility",
        method="GET",
        payer="0xabc",
        payment_kind="paid",
        amount_atomic=10000,
    )
    session.commit()

    summary = {(r.endpoint, r.payment_kind): r for r in repo.usage_summary(session)}
    assert summary[("score", "paid")].calls == 2
    assert summary[("score", "paid")].revenue_atomic == 20000
    assert summary[("score", "api_key")].calls == 1
    assert summary[("score", "api_key")].revenue_atomic == 0
    assert summary[("eligibility", "paid")].revenue_atomic == 10000


def test_api_key_label_resolves_active_key(session: Session) -> None:
    repo.create_api_key(session, "secret", label="acme")
    session.commit()
    assert repo.api_key_label(session, "secret") == "acme"
    assert repo.api_key_label(session, "wrong") is None
    assert repo.api_key_label(session, "") is None

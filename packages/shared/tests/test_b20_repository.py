"""Unit tests for the B20 token registry repository helpers (proposal §7.2)."""

from __future__ import annotations

import pytest
from sqlalchemy.orm import Session

from provenalt_shared.db import Base, make_engine, make_session_factory
from provenalt_shared.db import repository as repo

AAPL = "0xb200000000000000000000C2e324d24d7eEcd1fb"  # mixed case (checksummed)


@pytest.fixture
def session() -> Session:
    engine = make_engine("sqlite://")
    Base.metadata.create_all(engine)
    with make_session_factory(engine)() as s:
        yield s


def test_upsert_and_resolve_by_address_and_symbol(session: Session) -> None:
    repo.upsert_b20_token(session, AAPL, "AAPLc", 8)
    session.commit()

    by_addr = repo.get_b20_token(session, AAPL.lower())
    assert by_addr is not None
    assert by_addr.symbol == "AAPLc"
    assert by_addr.decimals == 8
    assert by_addr.address == AAPL.lower()  # stored lowercased

    # address is matched case-insensitively; symbol matches exactly
    assert repo.get_b20_token(session, AAPL.upper()).symbol == "AAPLc"
    assert repo.get_b20_token(session, "AAPLc").address == AAPL.lower()


def test_unknown_token_returns_none(session: Session) -> None:
    assert repo.get_b20_token(session, "0x" + "00" * 20) is None
    assert repo.get_b20_token(session, "NOPEc") is None


def test_inactive_token_is_not_resolved(session: Session) -> None:
    repo.upsert_b20_token(session, AAPL, "AAPLc", 8, active=False)
    session.commit()
    assert repo.get_b20_token(session, "AAPLc") is None
    assert repo.list_b20_tokens(session) == []
    assert len(repo.list_b20_tokens(session, active_only=False)) == 1


def test_list_orders_by_symbol(session: Session) -> None:
    repo.upsert_b20_token(session, "0x" + "b2" + "0" * 39, "NVDAc", 8)
    repo.upsert_b20_token(session, "0x" + "b2" + "1" * 39, "AAPLc", 8)
    session.commit()
    assert [t.symbol for t in repo.list_b20_tokens(session)] == ["AAPLc", "NVDAc"]

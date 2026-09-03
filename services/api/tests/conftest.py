"""Test fixtures: an in-memory SQLite DB shared between the seeding session and the app."""

from __future__ import annotations

from collections.abc import Iterator

import pytest
from fastapi.testclient import TestClient
from provenalt_shared.db import Base, make_session_factory
from sqlalchemy import create_engine
from sqlalchemy.orm import Session, sessionmaker
from sqlalchemy.pool import StaticPool

from provenalt_api.deps import get_session
from provenalt_api.main import create_app


@pytest.fixture
def factory() -> sessionmaker[Session]:
    # StaticPool keeps a single in-memory connection so the seeding session and the app
    # (via the overridden dependency) see the same database.
    engine = create_engine(
        "sqlite://",
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
    )
    Base.metadata.create_all(engine)
    return make_session_factory(engine)


@pytest.fixture
def session(factory: sessionmaker[Session]) -> Iterator[Session]:
    with factory() as s:
        yield s


@pytest.fixture
def client(factory: sessionmaker[Session]) -> Iterator[TestClient]:
    app = create_app()

    def _override() -> Iterator[Session]:
        with factory() as s:
            yield s

    app.dependency_overrides[get_session] = _override
    # The x402 gate opens its own sessions (for API-key checks + metering); point it at the
    # test database too.
    app.state.db_factory = factory
    with TestClient(app) as c:
        yield c

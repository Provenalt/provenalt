"""Request dependencies: the database session."""

from __future__ import annotations

from collections.abc import Iterator
from functools import lru_cache
from typing import Annotated

from fastapi import Depends
from provenalt_shared.db import make_engine, make_session_factory
from provenalt_shared.settings import get_settings
from sqlalchemy.orm import Session, sessionmaker


@lru_cache(maxsize=1)
def session_factory() -> sessionmaker[Session]:
    settings = get_settings()
    if not settings.database_url:
        raise RuntimeError("DATABASE_URL is required to run the API")
    return make_session_factory(make_engine(settings.database_url))


def get_session() -> Iterator[Session]:
    """Yield a database session (overridden in tests via dependency_overrides)."""
    with session_factory()() as session:
        yield session


# Idiomatic FastAPI dependency alias (avoids `Depends()` in argument defaults).
SessionDep = Annotated[Session, Depends(get_session)]

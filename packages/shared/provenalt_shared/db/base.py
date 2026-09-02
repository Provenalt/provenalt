"""SQLAlchemy declarative base plus engine/session factories.

Postgres is the production database (proposal §4). The models use portable column types
so unit tests can run against in-memory SQLite without a running Postgres.
"""

from __future__ import annotations

from sqlalchemy import Engine, create_engine
from sqlalchemy.orm import DeclarativeBase, Session, sessionmaker


class Base(DeclarativeBase):
    """Declarative base for all Provenalt ORM models."""


def make_engine(url: str, echo: bool = False) -> Engine:
    """Create a SQLAlchemy engine for the given database URL.

    Normalises the bare ``postgresql://`` scheme (as Railway injects it) to the psycopg v3
    driver so no code has to care which driver is installed.
    """
    if url.startswith("postgresql://"):
        url = url.replace("postgresql://", "postgresql+psycopg://", 1)
    return create_engine(url, echo=echo, future=True)


def make_session_factory(engine: Engine) -> sessionmaker[Session]:
    """Create a session factory bound to ``engine``."""
    return sessionmaker(bind=engine, expire_on_commit=False, future=True)

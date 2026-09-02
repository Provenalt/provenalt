"""Verify the Alembic migration builds the schema and matches the ORM models."""

from __future__ import annotations

from pathlib import Path

from alembic import command
from alembic.config import Config
from alembic.script import ScriptDirectory
from sqlalchemy import create_engine, inspect

from provenalt_shared.db import repository as repo
from provenalt_shared.db.base import Base

_SHARED_ROOT = Path(__file__).resolve().parents[1]

_EXPECTED_TABLES = {
    "raw_logs",
    "agents",
    "agent_metadata",
    "agent_owner_history",
    "indexer_cursor",
}


def _alembic_config(db_url: str) -> Config:
    cfg = Config(str(_SHARED_ROOT / "alembic.ini"))
    cfg.set_main_option("script_location", str(_SHARED_ROOT / "migrations"))
    cfg.cmd_opts = type("O", (), {"x": [f"db_url={db_url}"]})()  # -x db_url=...
    return cfg


def test_upgrade_head_creates_all_tables(tmp_path: Path) -> None:
    db_file = tmp_path / "provenalt.db"
    url = f"sqlite:///{db_file}"

    command.upgrade(_alembic_config(url), "head")

    tables = set(inspect(create_engine(url)).get_table_names())
    assert _EXPECTED_TABLES <= tables


def test_downgrade_base_removes_tables(tmp_path: Path) -> None:
    db_file = tmp_path / "provenalt.db"
    url = f"sqlite:///{db_file}"
    cfg = _alembic_config(url)

    command.upgrade(cfg, "head")
    command.downgrade(cfg, "base")

    remaining = set(inspect(create_engine(url)).get_table_names())
    assert _EXPECTED_TABLES.isdisjoint(remaining)


def test_migration_matches_orm_models(tmp_path: Path) -> None:
    """The tables Alembic creates match the tables the ORM metadata declares."""
    db_file = tmp_path / "provenalt.db"
    url = f"sqlite:///{db_file}"

    command.upgrade(_alembic_config(url), "head")

    migrated = set(inspect(create_engine(url)).get_table_names()) - {"alembic_version"}
    declared = set(Base.metadata.tables.keys())
    assert migrated == declared


def _latest_migration_view_sql() -> str:
    """The frozen RATER_CREDIBILITY_SQL literal from the newest migration that defines it."""
    script = ScriptDirectory.from_config(_alembic_config("sqlite://"))
    for revision in script.walk_revisions():  # newest → oldest
        sql = getattr(revision.module, "RATER_CREDIBILITY_SQL", None)
        if sql is not None:
            return str(sql)
    raise AssertionError("no migration defines RATER_CREDIBILITY_SQL")


def test_app_view_sql_matches_latest_migration_literal() -> None:
    """The app's current view SQL must equal the frozen literal in the latest migration.

    Migrations are immutable, so a change to ``repository.RATER_CREDIBILITY_SQL`` must be
    accompanied by a new migration that recreates the view — this test enforces that.
    """
    assert repo.RATER_CREDIBILITY_SQL == _latest_migration_view_sql()

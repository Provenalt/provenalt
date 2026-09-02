"""Unit tests for the settings loader."""

from __future__ import annotations

import pytest

from provenalt_shared.settings import Settings


def test_defaults_are_sane_without_env(monkeypatch: pytest.MonkeyPatch) -> None:
    for var in list(_provenalt_env_vars()):
        monkeypatch.delenv(var, raising=False)
    monkeypatch.delenv("DATABASE_URL", raising=False)

    settings = Settings(_env_file=None)

    assert settings.environment == "development"
    assert settings.log_level == "INFO"
    assert settings.log_format == "console"
    assert settings.finality_depth == 64
    assert settings.getlogs_initial_chunk == 10_000
    assert settings.getlogs_min_chunk == 100
    assert settings.getlogs_max_chunk == 50_000
    assert settings.database_url is None


def test_rpc_urls_parsed_from_comma_separated_string(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setenv(
        "PROVENALT_RPC_URLS",
        "https://mainnet.base.org, https://base.publicnode.com ,https://a.example",
    )
    settings = Settings(_env_file=None)
    assert settings.rpc_urls == [
        "https://mainnet.base.org",
        "https://base.publicnode.com",
        "https://a.example",
    ]


def test_env_prefix_and_database_url_alias(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("PROVENALT_ENVIRONMENT", "production")
    monkeypatch.setenv("PROVENALT_LOG_FORMAT", "json")
    monkeypatch.setenv("PROVENALT_FINALITY_DEPTH", "32")
    # DATABASE_URL is read WITHOUT the prefix (Railway injects it that way).
    monkeypatch.setenv("DATABASE_URL", "postgresql://u:p@localhost:5432/provenalt")

    settings = Settings(_env_file=None)

    assert settings.environment == "production"
    assert settings.log_format == "json"
    assert settings.finality_depth == 32
    assert settings.database_url == "postgresql://u:p@localhost:5432/provenalt"


def test_at_least_one_rpc_url_required_when_empty(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setenv("PROVENALT_RPC_URLS", "")
    with pytest.raises(ValueError):
        Settings(_env_file=None)


def _provenalt_env_vars() -> tuple[str, ...]:
    return (
        "PROVENALT_ENVIRONMENT",
        "PROVENALT_LOG_LEVEL",
        "PROVENALT_LOG_FORMAT",
        "PROVENALT_RPC_URLS",
        "PROVENALT_FINALITY_DEPTH",
        "PROVENALT_GETLOGS_INITIAL_CHUNK",
        "PROVENALT_GETLOGS_MIN_CHUNK",
        "PROVENALT_GETLOGS_MAX_CHUNK",
    )

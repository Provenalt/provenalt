"""Settings loader for Provenalt services.

Values are read from environment variables (prefix ``PROVENALT_``) and an optional
``.env`` file. ``DATABASE_URL`` is read without the prefix because Railway injects it
under that exact name. Secrets never live in the repo — see repo ``CLAUDE.md``.
"""

from __future__ import annotations

from functools import lru_cache
from typing import Annotated, Literal

from pydantic import AliasChoices, Field, field_validator
from pydantic_settings import BaseSettings, NoDecode, SettingsConfigDict


class Settings(BaseSettings):
    """Typed application settings.

    Environment variable names are the field names uppercased with the ``PROVENALT_``
    prefix (e.g. ``PROVENALT_LOG_LEVEL``), except ``database_url`` which maps to
    ``DATABASE_URL``. See ``.env.example`` for the full documented list.
    """

    model_config = SettingsConfigDict(
        env_prefix="PROVENALT_",
        env_file=".env",
        env_file_encoding="utf-8",
        extra="ignore",
        case_sensitive=False,
    )

    # Runtime
    environment: Literal["development", "staging", "production"] = "development"
    log_level: Literal["DEBUG", "INFO", "WARNING", "ERROR"] = "INFO"
    log_format: Literal["json", "console"] = "console"

    # Chain / RPC
    # NoDecode: skip pydantic-settings' JSON decoding so the validator below can accept a
    # plain comma-separated string (RPC URLs are not valid JSON).
    rpc_urls: Annotated[list[str], NoDecode] = Field(
        default_factory=lambda: ["https://mainnet.base.org", "https://base.publicnode.com"]
    )
    finality_depth: int = 64
    getlogs_initial_chunk: int = 10_000
    getlogs_min_chunk: int = 100
    getlogs_max_chunk: int = 50_000

    # Database — read from DATABASE_URL (no prefix), optional until Group 2.
    database_url: str | None = Field(
        default=None,
        validation_alias=AliasChoices("DATABASE_URL", "PROVENALT_DATABASE_URL"),
    )

    @field_validator("rpc_urls", mode="before")
    @classmethod
    def _split_rpc_urls(cls, value: object) -> object:
        """Accept a comma-separated string as well as a native list."""
        if isinstance(value, str):
            return [item.strip() for item in value.split(",") if item.strip()]
        return value

    @field_validator("rpc_urls")
    @classmethod
    def _require_at_least_one_rpc_url(cls, value: list[str]) -> list[str]:
        if not value:
            raise ValueError("at least one RPC URL is required (PROVENALT_RPC_URLS)")
        return value


@lru_cache(maxsize=1)
def get_settings() -> Settings:
    """Return a process-wide cached Settings instance."""
    return Settings()

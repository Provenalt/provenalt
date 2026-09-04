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
    # Conservative starting window for a cold backfill: many free-tier Base RPC providers
    # meter eth_getLogs heavily and rate-limit (429) large scans, so start small (2,000
    # blocks) and let AdaptiveChunkSizer grow toward getlogs_max_chunk on success. Starting
    # high (e.g. 10k) risks exhausting a free provider's quota on the very first requests.
    getlogs_initial_chunk: int = 2_000
    getlogs_min_chunk: int = 100
    getlogs_max_chunk: int = 50_000

    # RPC rate-limit (HTTP 429) backoff. A long-running indexer treats 429 as transient:
    # once every provider has 429'd the same request the client sleeps with exponential
    # backoff (initial seconds, doubling, capped at max, jittered) and retries up to
    # rpc_max_retries times before finally raising — instead of crashing the worker.
    rpc_backoff_initial_seconds: float = 2.0
    rpc_backoff_max_seconds: float = 60.0
    rpc_max_retries: int = 8

    # Database — read from DATABASE_URL (no prefix), optional until Group 2.
    database_url: str | None = Field(
        default=None,
        validation_alias=AliasChoices("DATABASE_URL", "PROVENALT_DATABASE_URL"),
    )

    # Public API — per-IP rate limit for the free tier (API keys bypass it).
    api_rate_limit_requests: int = 60
    api_rate_limit_window_seconds: int = 60
    api_default_page_size: int = 50
    api_max_page_size: int = 200

    # x402 payment gating for the paid tier (score / provenalt / eligibility).
    # Disabled by default; enforcement requires a receiving wallet (never committed).
    x402_enabled: bool = False
    x402_pay_to: str | None = None
    x402_network: str = "eip155:8453"  # Base mainnet (eip155:84532 = Base Sepolia)
    x402_price: str = "$0.01"
    x402_facilitator_url: str = "https://x402.org/facilitator"

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

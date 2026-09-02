"""Registry wiring: binds each ERC-8004 registry to its address, event topics, projection,
and reorg-rewind function, so the generic backfill/follow worker can drive both."""

from __future__ import annotations

from dataclasses import dataclass

from provenalt_indexer import events, reputation
from provenalt_indexer.backfill import IngestFn
from provenalt_indexer.follow import RewindFn
from provenalt_indexer.projection import ingest_logs, rewind_identity
from provenalt_indexer.reputation_projection import (
    ingest_reputation_logs,
    rewind_reputation,
)


@dataclass(frozen=True)
class RegistryConfig:
    name: str
    address: str
    event_topic0s: list[str]
    ingest: IngestFn
    rewind_fn: RewindFn


IDENTITY = RegistryConfig(
    name="identity",
    address=events.IDENTITY_REGISTRY_ADDRESS,
    event_topic0s=events.IDENTITY_EVENT_TOPIC0S,
    ingest=ingest_logs,
    rewind_fn=rewind_identity,
)

REPUTATION = RegistryConfig(
    name="reputation",
    address=reputation.REPUTATION_REGISTRY_ADDRESS,
    event_topic0s=reputation.REPUTATION_EVENT_TOPIC0S,
    ingest=ingest_reputation_logs,
    rewind_fn=rewind_reputation,
)

REGISTRIES: list[RegistryConfig] = [IDENTITY, REPUTATION]

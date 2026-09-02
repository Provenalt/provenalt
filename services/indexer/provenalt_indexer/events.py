"""ABI-driven decoding of ERC-8004 Identity Registry events.

The event ABIs are loaded from the vendored official ``IdentityRegistry.json`` (fetched from
``erc-8004/erc-8004-contracts``). topic0 hashes are computed from the canonical signatures
(``keccak(name(type,...))``) rather than transcribed by hand, and the Registered topic0 is
cross-checked against the proposal's pinned value in the tests.
"""

from __future__ import annotations

from dataclasses import dataclass
from functools import lru_cache
from typing import Any

from provenalt_indexer._abi import (
    ZERO_ADDRESS,
    decode_event,
    event_abis,
    load_abi,
    topic0_of,
)

__all__ = [
    "IDENTITY_REGISTRY_ADDRESS",
    "ZERO_ADDRESS",
    "TOPIC0",
    "IDENTITY_EVENT_TOPIC0S",
    "RegisteredEvent",
    "TransferEvent",
    "URIUpdatedEvent",
    "MetadataSetEvent",
    "DecodedEvent",
    "decode_identity_log",
    "load_identity_abi",
]

# Proposal §3.
IDENTITY_REGISTRY_ADDRESS = "0x8004A169FB4a3325136EB29fA0ceB6D2e539a432"

# Identity events we index (proposal §2.1 / §2.3).
_INDEXED_EVENTS = ("Registered", "MetadataSet", "URIUpdated", "Transfer")


def load_identity_abi() -> list[dict[str, Any]]:
    """Load the vendored Identity Registry ABI (list of ABI entries)."""
    return load_abi("IdentityRegistry.json")


@lru_cache(maxsize=1)
def _event_abis() -> dict[str, dict[str, Any]]:
    return event_abis(load_identity_abi(), _INDEXED_EVENTS)


TOPIC0: dict[str, str] = {name: topic0_of(abi) for name, abi in _event_abis().items()}
TOPIC0_TO_NAME: dict[str, str] = {v: k for k, v in TOPIC0.items()}
IDENTITY_EVENT_TOPIC0S: list[str] = list(TOPIC0.values())


# ── decoded event types ──────────────────────────────────────────────────────


@dataclass(frozen=True)
class RegisteredEvent:
    agent_id: int
    owner: str
    agent_uri: str


@dataclass(frozen=True)
class TransferEvent:
    from_address: str
    to_address: str
    token_id: int


@dataclass(frozen=True)
class URIUpdatedEvent:
    agent_id: int
    new_uri: str
    updated_by: str


@dataclass(frozen=True)
class MetadataSetEvent:
    agent_id: int
    indexed_key_hash: str
    metadata_key: str
    metadata_value: bytes


DecodedEvent = RegisteredEvent | TransferEvent | URIUpdatedEvent | MetadataSetEvent


def decode_identity_log(topics: list[str], data: str) -> DecodedEvent | None:
    """Decode a raw identity log into a typed event, or ``None`` if not one we index."""
    if not topics:
        return None
    name = TOPIC0_TO_NAME.get(topics[0].lower())
    if name is None:
        return None

    values = decode_event(_event_abis()[name], topics, data)

    if name == "Registered":
        return RegisteredEvent(
            agent_id=values["agentId"],
            owner=values["owner"],
            agent_uri=values["agentURI"],
        )
    if name == "Transfer":
        return TransferEvent(
            from_address=values["from"],
            to_address=values["to"],
            token_id=values["tokenId"],
        )
    if name == "URIUpdated":
        return URIUpdatedEvent(
            agent_id=values["agentId"],
            new_uri=values["newURI"],
            updated_by=values["updatedBy"],
        )
    # MetadataSet
    return MetadataSetEvent(
        agent_id=values["agentId"],
        indexed_key_hash=values["indexedMetadataKey"],
        metadata_key=values["metadataKey"],
        metadata_value=values["metadataValue"],
    )

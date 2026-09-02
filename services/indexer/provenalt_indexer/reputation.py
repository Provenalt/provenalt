"""ABI-driven decoding of ERC-8004 Reputation Registry events (proposal §3.1).

Events (from the vendored official ``ReputationRegistry.json``):

* ``NewFeedback``      — a client leaves feedback for an agent (value is a signed int128
                         with a separate decimals scale).
* ``FeedbackRevoked``  — a client revokes a prior feedback entry.
* ``ResponseAppended`` — a responder appends a response to a feedback entry.

The logical feedback identity is ``(agentId, clientAddress, feedbackIndex)``.
"""

from __future__ import annotations

from dataclasses import dataclass
from functools import lru_cache
from typing import Any

from provenalt_indexer._abi import decode_event, event_abis, load_abi, topic0_of

__all__ = [
    "REPUTATION_REGISTRY_ADDRESS",
    "TOPIC0",
    "REPUTATION_EVENT_TOPIC0S",
    "NewFeedbackEvent",
    "FeedbackRevokedEvent",
    "ResponseAppendedEvent",
    "DecodedReputationEvent",
    "decode_reputation_log",
    "load_reputation_abi",
]

# Proposal §3.
REPUTATION_REGISTRY_ADDRESS = "0x8004BAa17C55a88189AE136b182e5fdA19dE9b63"

_INDEXED_EVENTS = ("NewFeedback", "FeedbackRevoked", "ResponseAppended")


def load_reputation_abi() -> list[dict[str, Any]]:
    """Load the vendored Reputation Registry ABI (list of ABI entries)."""
    return load_abi("ReputationRegistry.json")


@lru_cache(maxsize=1)
def _event_abis() -> dict[str, dict[str, Any]]:
    return event_abis(load_reputation_abi(), _INDEXED_EVENTS)


TOPIC0: dict[str, str] = {name: topic0_of(abi) for name, abi in _event_abis().items()}
TOPIC0_TO_NAME: dict[str, str] = {v: k for k, v in TOPIC0.items()}
REPUTATION_EVENT_TOPIC0S: list[str] = list(TOPIC0.values())


# ── decoded event types ──────────────────────────────────────────────────────


@dataclass(frozen=True)
class NewFeedbackEvent:
    agent_id: int
    client_address: str
    feedback_index: int
    value: int
    value_decimals: int
    indexed_tag1_hash: str
    tag1: str
    tag2: str
    endpoint: str
    feedback_uri: str
    feedback_hash: str


@dataclass(frozen=True)
class FeedbackRevokedEvent:
    agent_id: int
    client_address: str
    feedback_index: int


@dataclass(frozen=True)
class ResponseAppendedEvent:
    agent_id: int
    client_address: str
    feedback_index: int
    responder: str
    response_uri: str
    response_hash: str


DecodedReputationEvent = NewFeedbackEvent | FeedbackRevokedEvent | ResponseAppendedEvent


def _to_hex(value: bytes | str) -> str:
    return value if isinstance(value, str) else "0x" + value.hex()


def decode_reputation_log(topics: list[str], data: str) -> DecodedReputationEvent | None:
    """Decode a raw reputation log into a typed event, or ``None`` if not one we index."""
    if not topics:
        return None
    name = TOPIC0_TO_NAME.get(topics[0].lower())
    if name is None:
        return None

    values = decode_event(_event_abis()[name], topics, data)

    if name == "NewFeedback":
        return NewFeedbackEvent(
            agent_id=values["agentId"],
            client_address=values["clientAddress"],
            feedback_index=values["feedbackIndex"],
            value=values["value"],
            value_decimals=values["valueDecimals"],
            indexed_tag1_hash=values["indexedTag1"],
            tag1=values["tag1"],
            tag2=values["tag2"],
            endpoint=values["endpoint"],
            feedback_uri=values["feedbackURI"],
            feedback_hash=_to_hex(values["feedbackHash"]),
        )
    if name == "FeedbackRevoked":
        return FeedbackRevokedEvent(
            agent_id=values["agentId"],
            client_address=values["clientAddress"],
            feedback_index=values["feedbackIndex"],
        )
    # ResponseAppended
    return ResponseAppendedEvent(
        agent_id=values["agentId"],
        client_address=values["clientAddress"],
        feedback_index=values["feedbackIndex"],
        responder=values["responder"],
        response_uri=values["responseURI"],
        response_hash=_to_hex(values["responseHash"]),
    )

"""Generic, ABI-driven event decoding shared by the identity and reputation decoders.

Event ABIs are loaded from vendored official JSON (fetched from ``erc-8004/erc-8004-contracts``).
topic0 hashes are computed from the canonical signatures (``keccak(name(type,...))``) rather
than transcribed by hand; the decoders cross-check known topic0s against the proposal in tests.
"""

from __future__ import annotations

import json
from functools import cache
from importlib import resources
from typing import Any

from eth_abi import decode as abi_decode
from eth_utils import keccak

ZERO_ADDRESS = "0x0000000000000000000000000000000000000000"


@cache
def load_abi(resource_name: str) -> list[dict[str, Any]]:
    """Load a vendored ABI JSON (list of ABI entries) from ``provenalt_indexer.abis``."""
    raw = resources.files("provenalt_indexer.abis").joinpath(resource_name).read_text()
    abi: list[dict[str, Any]] = json.loads(raw)
    return abi


def event_abis(abi: list[dict[str, Any]], names: tuple[str, ...]) -> dict[str, dict[str, Any]]:
    """Return the ABI entries for the named events, in the given order."""
    events = {entry["name"]: entry for entry in abi if entry.get("type") == "event"}
    return {name: events[name] for name in names}


def event_signature(abi: dict[str, Any]) -> str:
    """Canonical signature, e.g. ``Registered(uint256,string,address)``."""
    types = ",".join(inp["type"] for inp in abi["inputs"])
    return f"{abi['name']}({types})"


def topic0_of(abi: dict[str, Any]) -> str:
    digest: bytes = keccak(text=event_signature(abi))
    return "0x" + digest.hex()


def decode_topic(sol_type: str, topic: str) -> Any:
    """Decode a single 32-byte indexed topic by its Solidity type."""
    raw = bytes.fromhex(topic[2:] if topic.startswith("0x") else topic)
    if sol_type == "address":
        return "0x" + raw[-20:].hex()
    if sol_type.startswith("uint"):
        return int.from_bytes(raw, "big")
    if sol_type.startswith("int"):
        return int.from_bytes(raw, "big", signed=True)
    if sol_type == "bool":
        return raw[-1] != 0
    # Dynamic types (string/bytes/arrays) indexed as a keccak hash — not recoverable.
    return "0x" + raw.hex()


def decode_event(abi: dict[str, Any], topics: list[str], data: str) -> dict[str, Any]:
    """Decode a log's indexed topics and non-indexed data into ``{name: value}``."""
    indexed = [i for i in abi["inputs"] if i["indexed"]]
    non_indexed = [i for i in abi["inputs"] if not i["indexed"]]

    values: dict[str, Any] = {}
    for inp, topic in zip(indexed, topics[1:], strict=True):
        values[inp["name"]] = decode_topic(inp["type"], topic)

    if non_indexed:
        raw = bytes.fromhex(data[2:]) if data and data != "0x" else b""
        decoded = abi_decode([i["type"] for i in non_indexed], raw)
        for inp, value in zip(non_indexed, decoded, strict=True):
            values[inp["name"]] = value

    return values

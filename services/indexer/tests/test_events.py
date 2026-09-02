"""Unit tests for ABI-driven identity event decoding.

topic0 values are COMPUTED from the vendored official ABI (keccak of the canonical
signature), not hand-transcribed. The Registered topic0 is cross-checked against the value
pinned in the proposal (§3) as a guard against ABI/keccak mistakes.
"""

from __future__ import annotations

from eth_abi import encode

from provenalt_indexer import events

# Verified on-chain facts (proposal §3).
REGISTERED_TOPIC0 = "0xca52e62c367d81bb2e328eb795f7c7ba24afb478408a26c0e201d155c449bc4a"
# Canonical ERC-721 Transfer(address,address,uint256).
ERC721_TRANSFER_TOPIC0 = "0xddf252ad1be2c89b69c2b068fc378daa952ba7f163c4a11628f55a4df523b3ef"

ADDR_A = "0x1111111111111111111111111111111111111111"
ADDR_B = "0x2222222222222222222222222222222222222222"


def _uint_topic(value: int) -> str:
    return "0x" + value.to_bytes(32, "big").hex()


def _addr_topic(addr: str) -> str:
    return "0x" + bytes(12).hex() + addr[2:].lower()


# ── topic0 computation + cross-check ─────────────────────────────────────────


def test_registered_topic0_matches_proposal() -> None:
    assert events.TOPIC0["Registered"] == REGISTERED_TOPIC0


def test_transfer_topic0_is_canonical_erc721() -> None:
    assert events.TOPIC0["Transfer"] == ERC721_TRANSFER_TOPIC0


def test_identity_event_topic0s_lists_all_four_indexed_events() -> None:
    assert set(events.IDENTITY_EVENT_TOPIC0S) == {
        events.TOPIC0["Registered"],
        events.TOPIC0["MetadataSet"],
        events.TOPIC0["URIUpdated"],
        events.TOPIC0["Transfer"],
    }


# ── decoding ─────────────────────────────────────────────────────────────────


def test_decode_registered() -> None:
    topics = [events.TOPIC0["Registered"], _uint_topic(42), _addr_topic(ADDR_A)]
    data = "0x" + encode(["string"], ["ipfs://card"]).hex()

    decoded = events.decode_identity_log(topics, data)

    assert isinstance(decoded, events.RegisteredEvent)
    assert decoded.agent_id == 42
    assert decoded.owner == ADDR_A
    assert decoded.agent_uri == "ipfs://card"


def test_decode_transfer() -> None:
    topics = [
        events.TOPIC0["Transfer"],
        _addr_topic(ADDR_A),
        _addr_topic(ADDR_B),
        _uint_topic(7),
    ]
    decoded = events.decode_identity_log(topics, "0x")

    assert isinstance(decoded, events.TransferEvent)
    assert decoded.from_address == ADDR_A
    assert decoded.to_address == ADDR_B
    assert decoded.token_id == 7


def test_decode_uri_updated() -> None:
    topics = [events.TOPIC0["URIUpdated"], _uint_topic(9), _addr_topic(ADDR_B)]
    data = "0x" + encode(["string"], ["ipfs://new"]).hex()

    decoded = events.decode_identity_log(topics, data)

    assert isinstance(decoded, events.URIUpdatedEvent)
    assert decoded.agent_id == 9
    assert decoded.new_uri == "ipfs://new"
    assert decoded.updated_by == ADDR_B


def test_decode_metadata_set() -> None:
    key_hash = "0x" + "ab" * 32  # indexed string arrives as a keccak hash
    topics = [events.TOPIC0["MetadataSet"], _uint_topic(5), key_hash]
    data = "0x" + encode(["string", "bytes"], ["agentWallet", b"\xde\xad"]).hex()

    decoded = events.decode_identity_log(topics, data)

    assert isinstance(decoded, events.MetadataSetEvent)
    assert decoded.agent_id == 5
    assert decoded.metadata_key == "agentWallet"
    assert decoded.metadata_value == b"\xde\xad"
    assert decoded.indexed_key_hash == key_hash


def test_decode_unknown_topic_returns_none() -> None:
    assert events.decode_identity_log(["0x" + "00" * 32], "0x") is None

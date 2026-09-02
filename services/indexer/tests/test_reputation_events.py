"""Unit tests for ABI-driven reputation event decoding (proposal §3.1).

topic0s are COMPUTED from the vendored official ABI and cross-checked here against the
values pinned from the canonical signatures in the proposal (§3).
"""

from __future__ import annotations

from eth_abi import encode

from provenalt_indexer import reputation

# topic0 = keccak(canonical signature) — pinned cross-check values.
NEW_FEEDBACK_TOPIC0 = "0x6a4a61743519c9d648a14e6493f47dbe3ff1aa29e7785c96c8326a205e58febc"
FEEDBACK_REVOKED_TOPIC0 = "0x25156fd3288212246d8b008d5921fde376c71ed14ac2e072a506eb06fde6d09d"
RESPONSE_APPENDED_TOPIC0 = "0xb1c6be0b5b8aef6539e2fac0fd131a2faa7b49edf8e505b5eb0ad487d56051d4"

CLIENT = "0x1111111111111111111111111111111111111111"
RESPONDER = "0x3333333333333333333333333333333333333333"


def _uint_topic(value: int) -> str:
    return "0x" + value.to_bytes(32, "big").hex()


def _addr_topic(addr: str) -> str:
    return "0x" + bytes(12).hex() + addr[2:].lower()


def test_reputation_topic0s_match_pinned_values() -> None:
    assert reputation.TOPIC0["NewFeedback"] == NEW_FEEDBACK_TOPIC0
    assert reputation.TOPIC0["FeedbackRevoked"] == FEEDBACK_REVOKED_TOPIC0
    assert reputation.TOPIC0["ResponseAppended"] == RESPONSE_APPENDED_TOPIC0


def test_event_topic0s_lists_all_three() -> None:
    assert set(reputation.REPUTATION_EVENT_TOPIC0S) == set(reputation.TOPIC0.values())


def test_decode_new_feedback_with_negative_value() -> None:
    tag1_hash = "0x" + "cd" * 32
    topics = [
        reputation.TOPIC0["NewFeedback"],
        _uint_topic(42),
        _addr_topic(CLIENT),
        tag1_hash,
    ]
    fb_hash = b"\xaa" * 32
    data = (
        "0x"
        + encode(
            ["uint64", "int128", "uint8", "string", "string", "string", "string", "bytes32"],
            [7, -250, 2, "quality", "speed", "https://api.x", "ipfs://fb", fb_hash],
        ).hex()
    )

    decoded = reputation.decode_reputation_log(topics, data)

    assert isinstance(decoded, reputation.NewFeedbackEvent)
    assert decoded.agent_id == 42
    assert decoded.client_address == CLIENT
    assert decoded.feedback_index == 7
    assert decoded.value == -250  # signed int128 decoded correctly
    assert decoded.value_decimals == 2
    assert decoded.indexed_tag1_hash == tag1_hash
    assert decoded.tag1 == "quality"
    assert decoded.tag2 == "speed"
    assert decoded.endpoint == "https://api.x"
    assert decoded.feedback_uri == "ipfs://fb"
    assert decoded.feedback_hash == "0x" + fb_hash.hex()


def test_decode_feedback_revoked() -> None:
    topics = [
        reputation.TOPIC0["FeedbackRevoked"],
        _uint_topic(42),
        _addr_topic(CLIENT),
        _uint_topic(7),
    ]
    decoded = reputation.decode_reputation_log(topics, "0x")

    assert isinstance(decoded, reputation.FeedbackRevokedEvent)
    assert decoded.agent_id == 42
    assert decoded.client_address == CLIENT
    assert decoded.feedback_index == 7


def test_decode_response_appended() -> None:
    topics = [
        reputation.TOPIC0["ResponseAppended"],
        _uint_topic(42),
        _addr_topic(CLIENT),
        _addr_topic(RESPONDER),
    ]
    resp_hash = b"\xbb" * 32
    data = "0x" + encode(["uint64", "string", "bytes32"], [7, "ipfs://resp", resp_hash]).hex()

    decoded = reputation.decode_reputation_log(topics, data)

    assert isinstance(decoded, reputation.ResponseAppendedEvent)
    assert decoded.agent_id == 42
    assert decoded.client_address == CLIENT
    assert decoded.feedback_index == 7
    assert decoded.responder == RESPONDER
    assert decoded.response_uri == "ipfs://resp"
    assert decoded.response_hash == "0x" + resp_hash.hex()


def test_decode_unknown_topic_returns_none() -> None:
    assert reputation.decode_reputation_log(["0x" + "00" * 32], "0x") is None

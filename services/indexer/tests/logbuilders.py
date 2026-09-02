"""Helpers to build synthetic raw eth_getLogs entries for tests (not a test module)."""

from __future__ import annotations

from typing import Any

from eth_abi import encode

from provenalt_indexer import events, reputation


def _uint_topic(value: int) -> str:
    return "0x" + value.to_bytes(32, "big").hex()


def _addr_topic(addr: str) -> str:
    return "0x" + bytes(12).hex() + addr[2:].lower()


def _log(
    *,
    topics: list[str],
    data: str,
    block: int,
    tx: str,
    log_index: int,
    block_hash: str | None = None,
    address: str = events.IDENTITY_REGISTRY_ADDRESS,
) -> dict[str, Any]:
    return {
        "address": address,
        "blockNumber": hex(block),
        "blockHash": block_hash or f"0x{block:064x}",
        "transactionHash": tx,
        "logIndex": hex(log_index),
        "topics": topics,
        "data": data,
        "removed": False,
    }


def registered_log(
    agent_id: int, owner: str, uri: str, block: int, tx: str, log_index: int = 0, **kw: Any
) -> dict[str, Any]:
    return _log(
        topics=[events.TOPIC0["Registered"], _uint_topic(agent_id), _addr_topic(owner)],
        data="0x" + encode(["string"], [uri]).hex(),
        block=block,
        tx=tx,
        log_index=log_index,
        **kw,
    )


def transfer_log(
    from_addr: str,
    to_addr: str,
    token_id: int,
    block: int,
    tx: str,
    log_index: int = 0,
    **kw: Any,
) -> dict[str, Any]:
    return _log(
        topics=[
            events.TOPIC0["Transfer"],
            _addr_topic(from_addr),
            _addr_topic(to_addr),
            _uint_topic(token_id),
        ],
        data="0x",
        block=block,
        tx=tx,
        log_index=log_index,
        **kw,
    )


def uri_updated_log(
    agent_id: int,
    new_uri: str,
    updated_by: str,
    block: int,
    tx: str,
    log_index: int = 0,
    **kw: Any,
) -> dict[str, Any]:
    return _log(
        topics=[events.TOPIC0["URIUpdated"], _uint_topic(agent_id), _addr_topic(updated_by)],
        data="0x" + encode(["string"], [new_uri]).hex(),
        block=block,
        tx=tx,
        log_index=log_index,
        **kw,
    )


def metadata_log(
    agent_id: int,
    key: str,
    value: bytes,
    block: int,
    tx: str,
    log_index: int = 0,
    key_hash: str | None = None,
    **kw: Any,
) -> dict[str, Any]:
    return _log(
        topics=[
            events.TOPIC0["MetadataSet"],
            _uint_topic(agent_id),
            key_hash or ("0x" + "ab" * 32),
        ],
        data="0x" + encode(["string", "bytes"], [key, value]).hex(),
        block=block,
        tx=tx,
        log_index=log_index,
        **kw,
    )


# ── reputation log builders (address = Reputation Registry) ───────────────────


def _rep_log(*, topics: list[str], data: str, block: int, tx: str, log_index: int, **kw: Any):
    return _log(
        topics=topics,
        data=data,
        block=block,
        tx=tx,
        log_index=log_index,
        address=reputation.REPUTATION_REGISTRY_ADDRESS,
        **kw,
    )


def new_feedback_log(
    agent_id: int,
    client: str,
    value: int,
    feedback_index: int,
    block: int,
    tx: str,
    log_index: int = 0,
    *,
    value_decimals: int = 0,
    tag1: str = "quality",
    tag2: str = "",
    endpoint: str = "",
    feedback_uri: str = "",
    feedback_hash: bytes = b"\x00" * 32,
    tag1_hash: str | None = None,
    **kw: Any,
) -> dict[str, Any]:
    return _rep_log(
        topics=[
            reputation.TOPIC0["NewFeedback"],
            _uint_topic(agent_id),
            _addr_topic(client),
            tag1_hash or ("0x" + "cd" * 32),
        ],
        data="0x"
        + encode(
            ["uint64", "int128", "uint8", "string", "string", "string", "string", "bytes32"],
            [
                feedback_index,
                value,
                value_decimals,
                tag1,
                tag2,
                endpoint,
                feedback_uri,
                feedback_hash,
            ],
        ).hex(),
        block=block,
        tx=tx,
        log_index=log_index,
        **kw,
    )


def feedback_revoked_log(
    agent_id: int,
    client: str,
    feedback_index: int,
    block: int,
    tx: str,
    log_index: int = 0,
    **kw: Any,
) -> dict[str, Any]:
    return _rep_log(
        topics=[
            reputation.TOPIC0["FeedbackRevoked"],
            _uint_topic(agent_id),
            _addr_topic(client),
            _uint_topic(feedback_index),
        ],
        data="0x",
        block=block,
        tx=tx,
        log_index=log_index,
        **kw,
    )


def response_appended_log(
    agent_id: int,
    client: str,
    feedback_index: int,
    responder: str,
    response_uri: str,
    block: int,
    tx: str,
    log_index: int = 0,
    *,
    response_hash: bytes = b"\x00" * 32,
    **kw: Any,
) -> dict[str, Any]:
    return _rep_log(
        topics=[
            reputation.TOPIC0["ResponseAppended"],
            _uint_topic(agent_id),
            _addr_topic(client),
            _addr_topic(responder),
        ],
        data="0x"
        + encode(
            ["uint64", "string", "bytes32"], [feedback_index, response_uri, response_hash]
        ).hex(),
        block=block,
        tx=tx,
        log_index=log_index,
        **kw,
    )

"""Unit tests for ChainClient generic JSON-RPC calls + provider rotation (no network)."""

from __future__ import annotations

import random

import pytest

from provenalt_shared.chain import ChainClient, RateLimitError, RpcError, TransportError


def _client(transport: object, urls: list[str] | None = None) -> ChainClient:
    return ChainClient(
        rpc_urls=urls or ["https://a.example", "https://b.example"],
        transport=transport,  # type: ignore[arg-type]
        initial_chunk=1000,
        min_chunk=100,
        max_chunk=8000,
    )


def test_call_returns_result() -> None:
    def transport(url: str, payload: dict) -> dict:
        return {"jsonrpc": "2.0", "id": payload["id"], "result": "0x2a"}

    client = _client(transport)
    assert client.call("eth_blockNumber", []) == "0x2a"


def test_call_rotates_provider_on_rate_limit_then_succeeds() -> None:
    class RateLimitedA:
        def __init__(self) -> None:
            self.calls: list[str] = []

        def __call__(self, url: str, payload: dict) -> dict:
            self.calls.append(url)
            if url == "https://a.example":
                raise RateLimitError("429")
            return {"jsonrpc": "2.0", "id": payload["id"], "result": "0x1"}

    transport = RateLimitedA()
    client = _client(transport)
    assert client.call("eth_blockNumber", []) == "0x1"
    assert "https://b.example" in transport.calls


def test_call_rotates_on_transport_error() -> None:
    class FlakyA:
        def __call__(self, url: str, payload: dict) -> dict:
            if url == "https://a.example":
                raise TransportError("boom")
            return {"jsonrpc": "2.0", "id": payload["id"], "result": "ok"}

    assert _client(FlakyA()).call("eth_chainId", []) == "ok"


def test_call_raises_rpc_error_without_rotating() -> None:
    def transport(url: str, payload: dict) -> dict:
        return {
            "jsonrpc": "2.0",
            "id": payload["id"],
            "error": {"code": -32601, "message": "method not found"},
        }

    with pytest.raises(RpcError):
        _client(transport).call("nonexistent_method", [])


def test_call_backs_off_then_succeeds_when_rate_limit_clears() -> None:
    class LimitedTwiceThenOk:
        def __init__(self) -> None:
            self.remaining = 2  # both providers 429 once → one full sweep, then recover

        def __call__(self, url: str, payload: dict) -> dict:
            if self.remaining > 0:
                self.remaining -= 1
                raise RateLimitError("429")
            return {"jsonrpc": "2.0", "id": payload["id"], "result": "0x2a"}

    sleeps: list[float] = []
    client = ChainClient(
        rpc_urls=["https://a.example", "https://b.example"],
        transport=LimitedTwiceThenOk(),
        initial_chunk=1000,
        min_chunk=100,
        max_chunk=8000,
        max_retries=5,
        sleep=sleeps.append,
        rng=random.Random(0),
    )
    assert client.call("eth_blockNumber", []) == "0x2a"
    assert len(sleeps) == 1  # one full 429 sweep → one backoff sleep, then success


def test_call_raises_after_max_retries_when_all_providers_rate_limited() -> None:
    class AlwaysLimited:
        def __call__(self, url: str, payload: dict) -> dict:
            raise RateLimitError("429")

    sleeps: list[float] = []
    client = ChainClient(
        rpc_urls=["https://a.example", "https://b.example"],
        transport=AlwaysLimited(),
        initial_chunk=1000,
        min_chunk=100,
        max_chunk=8000,
        max_retries=2,
        sleep=sleeps.append,
        rng=random.Random(0),
    )
    with pytest.raises(RateLimitError):
        client.call("eth_blockNumber", [])
    assert len(sleeps) == 2  # backed off twice before finally raising


def test_get_block_number_parses_hex() -> None:
    def transport(url: str, payload: dict) -> dict:
        assert payload["method"] == "eth_blockNumber"
        return {"jsonrpc": "2.0", "id": payload["id"], "result": "0x10"}

    assert _client(transport).get_block_number() == 16


def test_get_code_passes_block_tag_and_returns_code() -> None:
    seen: dict[str, object] = {}

    def transport(url: str, payload: dict) -> dict:
        seen["method"] = payload["method"]
        seen["params"] = payload["params"]
        return {"jsonrpc": "2.0", "id": payload["id"], "result": "0x6080"}

    client = _client(transport)
    assert client.get_code("0xABC", block=1234) == "0x6080"
    assert seen["method"] == "eth_getCode"
    assert seen["params"] == ["0xABC", hex(1234)]


def test_get_code_defaults_to_latest() -> None:
    seen: dict[str, object] = {}

    def transport(url: str, payload: dict) -> dict:
        seen["params"] = payload["params"]
        return {"jsonrpc": "2.0", "id": payload["id"], "result": "0x"}

    _client(transport).get_code("0xABC")
    assert seen["params"] == ["0xABC", "latest"]


def test_get_block_by_number_returns_block_and_hash() -> None:
    def transport(url: str, payload: dict) -> dict:
        assert payload["method"] == "eth_getBlockByNumber"
        assert payload["params"] == [hex(100), False]
        return {
            "jsonrpc": "2.0",
            "id": payload["id"],
            "result": {"number": hex(100), "hash": "0xdead"},
        }

    block = _client(transport).get_block_by_number(100)
    assert block is not None
    assert block["hash"] == "0xdead"


def test_get_block_by_number_returns_none_for_missing_block() -> None:
    def transport(url: str, payload: dict) -> dict:
        return {"jsonrpc": "2.0", "id": payload["id"], "result": None}

    assert _client(transport).get_block_by_number(999_999_999) is None

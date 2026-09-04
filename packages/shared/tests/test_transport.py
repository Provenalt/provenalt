"""Unit tests for the httpx-backed RPC transport (no real network — httpx MockTransport)."""

from __future__ import annotations

import httpx
import pytest

from provenalt_shared.chain import (
    BlockRangeCapError,
    HttpxTransport,
    RateLimitError,
    RpcError,
    TransportError,
)

_PAYLOAD = {"jsonrpc": "2.0", "id": 1, "method": "eth_getLogs", "params": [{}]}


def _json_rpc_error(code: int, message: str) -> dict:
    return {"jsonrpc": "2.0", "id": 1, "error": {"code": code, "message": message}}


def _client(handler: object) -> httpx.Client:
    return httpx.Client(transport=httpx.MockTransport(handler))  # type: ignore[arg-type]


def test_returns_parsed_json_on_200() -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(200, json={"jsonrpc": "2.0", "id": 1, "result": []})

    transport = HttpxTransport(client=_client(handler))
    result = transport("https://a.example", _PAYLOAD)
    assert result == {"jsonrpc": "2.0", "id": 1, "result": []}


def test_http_429_maps_to_rate_limit_error() -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(429, text="rate limited")

    transport = HttpxTransport(client=_client(handler))
    with pytest.raises(RateLimitError):
        transport("https://a.example", _PAYLOAD)


def test_5xx_maps_to_transport_error_so_client_rotates() -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(503, text="service unavailable")

    transport = HttpxTransport(client=_client(handler))
    with pytest.raises(TransportError):
        transport("https://a.example", _PAYLOAD)


def test_connection_error_maps_to_transport_error() -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        raise httpx.ConnectError("connection refused")

    transport = HttpxTransport(client=_client(handler))
    with pytest.raises(TransportError):
        transport("https://a.example", _PAYLOAD)


# ── HTTP 4xx carrying a JSON-RPC error body (the production bug) ──────────────────


@pytest.mark.parametrize(
    "message",
    [
        # Alchemy returns the range cap as an HTTP 400 with a JSON-RPC error body.
        "Log response size exceeded. You can make eth_getLogs requests with up to a "
        "500 block range.",
        "eth_getLogs is limited to a 10000 block range",  # QuickNode phrasing
        "block range is too large",  # Base public RPC / Geth-family
        "query returned more than 10000 results",  # Infura phrasing
    ],
)
def test_400_with_jsonrpc_range_cap_maps_to_block_range_cap_error(message: str) -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(400, json=_json_rpc_error(-32602, message))

    transport = HttpxTransport(client=_client(handler))
    with pytest.raises(BlockRangeCapError):
        transport("https://a.example", _PAYLOAD)


def test_400_with_unrelated_jsonrpc_error_maps_to_rpc_error_not_range_cap() -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(400, json=_json_rpc_error(-32601, "method not found"))

    transport = HttpxTransport(client=_client(handler))
    with pytest.raises(RpcError) as exc_info:
        transport("https://a.example", _PAYLOAD)
    # It must be a plain RpcError, NOT the range-cap subclass (which would trigger a shrink).
    assert not isinstance(exc_info.value, BlockRangeCapError)


def test_400_with_non_json_body_still_maps_to_transport_error() -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(400, text="<html>Bad Request</html>")

    transport = HttpxTransport(client=_client(handler))
    with pytest.raises(TransportError):
        transport("https://a.example", _PAYLOAD)

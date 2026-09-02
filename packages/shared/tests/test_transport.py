"""Unit tests for the httpx-backed RPC transport (no real network — httpx MockTransport)."""

from __future__ import annotations

import httpx
import pytest

from provenalt_shared.chain import (
    HttpxTransport,
    RateLimitError,
    TransportError,
)

_PAYLOAD = {"jsonrpc": "2.0", "id": 1, "method": "eth_getLogs", "params": [{}]}


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

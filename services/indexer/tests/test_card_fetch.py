"""Unit tests for the agent-card fetcher (proposal §4.1) — no real network (MockTransport)."""

from __future__ import annotations

import base64
import hashlib

import httpx

from provenalt_indexer.cards.fetch import CardFetcher, FetchResult

GATEWAYS = ["https://gw1.example/ipfs/", "https://gw2.example/ipfs/"]
CARD_JSON = '{"type":"https://eips.ethereum.org/EIPS/eip-8004#registration-v1"}'


def _sha256(text: str) -> str:
    return hashlib.sha256(text.encode()).hexdigest()


def _fetcher(handler: object) -> CardFetcher:
    client = httpx.Client(transport=httpx.MockTransport(handler))  # type: ignore[arg-type]
    return CardFetcher(client=client, ipfs_gateways=GATEWAYS)


def test_https_direct_fetch() -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        assert str(request.url) == "https://example.com/agent.json"
        return httpx.Response(200, text=CARD_JSON)

    result = _fetcher(handler).fetch("https://example.com/agent.json")
    assert result.status == "ok"
    assert result.http_status == 200
    assert result.content == CARD_JSON
    assert result.content_hash == _sha256(CARD_JSON)
    assert result.source == "https://example.com/agent.json"


def test_ipfs_gateway_fallback_uses_second_when_first_fails() -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        if request.url.host == "gw1.example":
            return httpx.Response(500, text="boom")
        return httpx.Response(200, text=CARD_JSON)

    result = _fetcher(handler).fetch("ipfs://bafycid/agent.json")
    assert result.status == "ok"
    assert result.content == CARD_JSON
    assert result.source == "https://gw2.example/ipfs/bafycid/agent.json"


def test_ipfs_all_gateways_fail() -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(504, text="gateway timeout")

    result = _fetcher(handler).fetch("ipfs://bafycid")
    assert result.status == "fetch_error"
    assert result.content is None
    assert result.http_status == 504


def test_data_uri_base64_is_decoded_without_network() -> None:
    payload = base64.b64encode(CARD_JSON.encode()).decode()
    uri = f"data:application/json;base64,{payload}"

    # A handler that would fail if the fetcher tried the network.
    def handler(request: httpx.Request) -> httpx.Response:  # pragma: no cover
        raise AssertionError("data: URIs must not hit the network")

    result = _fetcher(handler).fetch(uri)
    assert result.status == "ok"
    assert result.content == CARD_JSON
    assert result.content_hash == _sha256(CARD_JSON)
    assert result.source == "data:"


def test_data_uri_plain_text() -> None:
    uri = "data:application/json,{}"

    def handler(request: httpx.Request) -> httpx.Response:  # pragma: no cover
        raise AssertionError("data: URIs must not hit the network")

    result = _fetcher(handler).fetch(uri)
    assert result.status == "ok"
    assert result.content == "{}"


def test_unsupported_scheme() -> None:
    def handler(request: httpx.Request) -> httpx.Response:  # pragma: no cover
        raise AssertionError("unsupported schemes must not hit the network")

    result = _fetcher(handler).fetch("ar://something")
    assert result.status == "unsupported_scheme"
    assert result.content is None


def test_connection_error_is_reported_as_fetch_error() -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        raise httpx.ConnectError("refused")

    result = _fetcher(handler).fetch("https://example.com/agent.json")
    assert isinstance(result, FetchResult)
    assert result.status == "fetch_error"
    assert result.content is None

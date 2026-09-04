"""Unit tests for the Base chain client: adaptive getLogs chunking + provider rotation.

All transports here are in-memory fakes — no network. Tests that hit a real RPC live in
test_chain_integration.py and are marked `integration` (excluded from default runs).
"""

from __future__ import annotations

import json
import random

import httpx
import pytest

from provenalt_shared.chain import (
    AdaptiveChunkSizer,
    ChainClient,
    HttpxTransport,
    RateLimitError,
    RpcError,
)


class RecordingSleep:
    """Fake sleep: records the requested delays instead of blocking, so tests stay fast."""

    def __init__(self) -> None:
        self.delays: list[float] = []

    def __call__(self, seconds: float) -> None:
        self.delays.append(seconds)


# ─────────────────────────────────────────────────────────────────────────────
# AdaptiveChunkSizer
# ─────────────────────────────────────────────────────────────────────────────


def test_chunker_starts_at_initial_clamped_within_bounds() -> None:
    assert AdaptiveChunkSizer(initial=1000, minimum=100, maximum=10000).size == 1000
    # initial above maximum is clamped down
    assert AdaptiveChunkSizer(initial=99999, minimum=100, maximum=10000).size == 10000
    # initial below minimum is clamped up
    assert AdaptiveChunkSizer(initial=1, minimum=100, maximum=10000).size == 100


def test_chunker_shrink_halves_and_floors_at_minimum() -> None:
    c = AdaptiveChunkSizer(initial=1000, minimum=100, maximum=10000, shrink_factor=0.5)
    c.shrink()
    assert c.size == 500
    c.shrink()
    assert c.size == 250
    c.shrink()
    assert c.size == 125
    c.shrink()  # 62 would be below the minimum → clamp to 100
    assert c.size == 100
    c.shrink()  # already at minimum → stays
    assert c.size == 100
    assert c.at_minimum


def test_chunker_grow_increases_toward_and_caps_at_maximum() -> None:
    c = AdaptiveChunkSizer(initial=100, minimum=100, maximum=1000, grow_factor=1.5)
    c.grow()
    assert c.size == 150
    c.grow()
    assert c.size == 225
    for _ in range(20):
        c.grow()
    assert c.size == 1000  # capped at maximum


# ─────────────────────────────────────────────────────────────────────────────
# Fake transports
# ─────────────────────────────────────────────────────────────────────────────


def _range_of(payload: dict) -> tuple[int, int]:
    params = payload["params"][0]
    return int(params["fromBlock"], 16), int(params["toBlock"], 16)


class CappedTransport:
    """Simulates a provider with a hard eth_getLogs block-range cap.

    Requests spanning more than `cap` blocks return a JSON-RPC block-range error;
    smaller requests succeed and return one synthetic log carrying its range.
    """

    def __init__(self, cap: int) -> None:
        self.cap = cap
        self.calls: list[tuple[int, int]] = []

    def __call__(self, url: str, payload: dict) -> dict:
        fb, tb = _range_of(payload)
        self.calls.append((fb, tb))
        if tb - fb + 1 > self.cap:
            return {
                "jsonrpc": "2.0",
                "id": payload["id"],
                "error": {"code": -32005, "message": "block range is too large"},
            }
        return {
            "jsonrpc": "2.0",
            "id": payload["id"],
            "result": [{"data": "0x", "_range": [fb, tb]}],
        }


class RateLimitedThenOk:
    """Provider A raises 429 for its first `fail_times` calls; provider B always works.

    No block-range cap — used to prove transient 429s cause shrink + provider rotation,
    and that the chunk size then recovers back up toward the maximum.
    """

    def __init__(self, url_a: str, url_b: str, fail_times: int) -> None:
        self.url_a = url_a
        self.url_b = url_b
        self.remaining_fails = fail_times
        self.calls: list[tuple[str, int, int]] = []

    def __call__(self, url: str, payload: dict) -> dict:
        fb, tb = _range_of(payload)
        self.calls.append((url, fb, tb))
        if url == self.url_a and self.remaining_fails > 0:
            self.remaining_fails -= 1
            raise RateLimitError("HTTP 429 Too Many Requests")
        return {
            "jsonrpc": "2.0",
            "id": payload["id"],
            "result": [{"data": "0x", "_range": [fb, tb]}],
        }


class RateLimitedNTimes:
    """429s the first ``fail_times`` calls across ALL providers, then always succeeds.

    Simulates systemic rate limiting (every provider 429ing) that eventually clears — used
    to prove the client backs off and then recovers rather than crashing.
    """

    def __init__(self, fail_times: int) -> None:
        self.remaining_fails = fail_times
        self.calls: list[tuple[str, int, int]] = []

    def __call__(self, url: str, payload: dict) -> dict:
        fb, tb = _range_of(payload)
        self.calls.append((url, fb, tb))
        if self.remaining_fails > 0:
            self.remaining_fails -= 1
            raise RateLimitError("HTTP 429 Too Many Requests")
        return {
            "jsonrpc": "2.0",
            "id": payload["id"],
            "result": [{"data": "0x", "_range": [fb, tb]}],
        }


def _assert_contiguous_coverage(logs: list[dict], start: int, end: int) -> None:
    ranges = sorted(tuple(log["_range"]) for log in logs)
    assert ranges[0][0] == start
    assert ranges[-1][1] == end
    for (_, prev_end), (next_start, _) in zip(ranges, ranges[1:], strict=False):
        assert next_start == prev_end + 1  # no gaps, no overlaps


# ─────────────────────────────────────────────────────────────────────────────
# get_logs: block-range-cap shrink
# ─────────────────────────────────────────────────────────────────────────────


def test_getlogs_shrinks_on_block_range_cap_and_covers_full_range() -> None:
    transport = CappedTransport(cap=500)
    client = ChainClient(
        rpc_urls=["https://a.example", "https://b.example"],
        transport=transport,
        initial_chunk=2000,
        min_chunk=100,
        max_chunk=5000,
    )

    logs = client.get_logs(address="0xabc", topics=[], from_block=0, to_block=6000)

    # Every block in [0, 6000] is covered exactly once.
    _assert_contiguous_coverage(logs, 0, 6000)

    spans = [tb - fb + 1 for fb, tb in transport.calls]
    assert spans[0] == 2000  # first attempt used the initial chunk size
    # It shrank until a request fit under the provider's cap.
    successful_spans = [tb - fb + 1 for fb, tb in transport.calls if tb - fb + 1 <= 500]
    assert successful_spans, "expected at least one request small enough to succeed"
    assert min(spans) <= 500
    assert client.chunk_size <= 500 or client.chunk_size < 2000  # adapted downward


def test_getlogs_never_exceeds_cap_on_successful_requests() -> None:
    transport = CappedTransport(cap=500)
    client = ChainClient(
        rpc_urls=["https://a.example"],
        transport=transport,
        initial_chunk=2000,
        min_chunk=100,
        max_chunk=5000,
    )
    logs = client.get_logs(address="0xabc", topics=[], from_block=0, to_block=3000)
    _assert_contiguous_coverage(logs, 0, 3000)


def test_getlogs_shrinks_and_completes_when_range_cap_arrives_as_http_400() -> None:
    """The production bug: Alchemy rejects an oversized eth_getLogs range with an HTTP 400
    whose body is a JSON-RPC error. End-to-end through the real HttpxTransport, that must
    shrink the chunk on the SAME provider (not rotate away) and cover the whole range."""
    cap = 500
    seen_urls: list[str] = []

    def handler(request: httpx.Request) -> httpx.Response:
        seen_urls.append(str(request.url))
        payload = json.loads(request.content)
        params = payload["params"][0]
        fb, tb = int(params["fromBlock"], 16), int(params["toBlock"], 16)
        if tb - fb + 1 > cap:
            return httpx.Response(
                400,
                json={
                    "jsonrpc": "2.0",
                    "id": payload["id"],
                    # Alchemy's actual phrasing for the range cap.
                    "error": {
                        "code": -32602,
                        "message": "Log response size exceeded. You can make eth_getLogs "
                        "requests with up to a 500 block range.",
                    },
                },
            )
        return httpx.Response(
            200,
            json={"jsonrpc": "2.0", "id": payload["id"], "result": [{"_range": [fb, tb]}]},
        )

    transport = HttpxTransport(client=httpx.Client(transport=httpx.MockTransport(handler)))
    client = ChainClient(
        rpc_urls=["https://a.example", "https://b.example"],
        transport=transport,
        initial_chunk=2000,
        min_chunk=100,
        max_chunk=5000,
    )

    logs = client.get_logs(address="0xabc", topics=[], from_block=0, to_block=3000)

    _assert_contiguous_coverage(logs, 0, 3000)
    assert client.chunk_size < 2000  # adapted downward instead of dying
    # Crucially, the range cap shrank the chunk on ONE provider rather than rotating away.
    assert len(set(seen_urls)) == 1


# ─────────────────────────────────────────────────────────────────────────────
# get_logs: rate-limit (429) shrink + rotate + recover
# ─────────────────────────────────────────────────────────────────────────────


def test_getlogs_recovers_and_grows_after_transient_rate_limit() -> None:
    transport = RateLimitedThenOk("https://a.example", "https://b.example", fail_times=2)
    client = ChainClient(
        rpc_urls=["https://a.example", "https://b.example"],
        transport=transport,
        initial_chunk=1000,
        min_chunk=100,
        max_chunk=8000,
    )

    logs = client.get_logs(address="0xabc", topics=[], from_block=0, to_block=100_000)

    _assert_contiguous_coverage(logs, 0, 100_000)

    # The 429s forced a shrink at some point...
    spans = [tb - fb + 1 for _, fb, tb in transport.calls]
    assert min(spans) < 1000
    # ...the client rotated onto the healthy provider...
    used_urls = {url for url, _, _ in transport.calls}
    assert "https://b.example" in used_urls
    # ...and the chunk size recovered all the way back up to the maximum.
    assert client.chunk_size == 8000


def test_getlogs_backs_off_then_recovers_when_all_providers_rate_limited() -> None:
    # Every provider 429s the first few requests, then the pressure clears. The backfill
    # must sleep (back off) rather than crash, and complete once the transport recovers.
    transport = RateLimitedNTimes(fail_times=3)
    sleeps = RecordingSleep()
    client = ChainClient(
        rpc_urls=["https://a.example", "https://b.example"],
        transport=transport,
        initial_chunk=1000,
        min_chunk=100,
        max_chunk=8000,
        backoff_initial_seconds=2.0,
        backoff_max_seconds=60.0,
        max_retries=5,
        sleep=sleeps,
        rng=random.Random(0),
    )

    logs = client.get_logs(address="0xabc", topics=[], from_block=0, to_block=500)

    _assert_contiguous_coverage(logs, 0, 500)
    # A full provider sweep of 429s triggered at least one exponential-backoff sleep...
    assert len(sleeps.delays) >= 1
    # ...whose first wait is ~initial (2s) with equal jitter → within [1, 2] seconds.
    assert 1.0 <= sleeps.delays[0] <= 2.0
    # ...and each 429 shrank the chunk below the initial size.
    spans = [tb - fb + 1 for _, fb, tb in transport.calls]
    assert min(spans) < 1000


def test_getlogs_shrinks_chunk_on_rate_limit() -> None:
    transport = RateLimitedNTimes(fail_times=1)  # a single 429, then success
    client = ChainClient(
        rpc_urls=["https://a.example", "https://b.example"],
        transport=transport,
        initial_chunk=1000,
        min_chunk=100,
        max_chunk=8000,
        sleep=RecordingSleep(),
        rng=random.Random(0),
    )
    client.get_logs(address="0xabc", topics=[], from_block=0, to_block=2000)
    # The first request used the initial chunk; the 429 shrank the next one.
    spans = [tb - fb + 1 for _, fb, tb in transport.calls]
    assert spans[0] == 1000
    assert spans[1] < 1000


def test_getlogs_raises_after_max_retries_when_rate_limit_never_clears() -> None:
    class AlwaysRateLimited:
        def __call__(self, url: str, payload: dict) -> dict:
            raise RateLimitError("HTTP 429")

    sleeps = RecordingSleep()
    client = ChainClient(
        rpc_urls=["https://a.example", "https://b.example"],
        transport=AlwaysRateLimited(),
        initial_chunk=1000,
        min_chunk=100,
        max_chunk=8000,
        max_retries=3,
        sleep=sleeps,
        rng=random.Random(0),
    )
    with pytest.raises(RateLimitError):
        client.get_logs(address="0xabc", topics=[], from_block=0, to_block=999)
    # It backed off max_retries times before finally giving up — never on the first 429.
    assert len(sleeps.delays) == 3


def test_backoff_delay_doubles_with_jitter_and_caps_at_max() -> None:
    client = ChainClient(
        rpc_urls=["https://a.example"],
        transport=lambda url, payload: {},  # unused: we call _backoff_delay directly
        initial_chunk=100,
        min_chunk=100,
        max_chunk=100,
        backoff_initial_seconds=2.0,
        backoff_max_seconds=60.0,
        rng=random.Random(1),
    )
    # Round 0 base = 2s → equal jitter keeps it in [1, 2].
    assert 1.0 <= client._backoff_delay(0) <= 2.0
    # Round 2 base = 8s → [4, 8].
    assert 4.0 <= client._backoff_delay(2) <= 8.0
    # Round 10 base = 2048s but capped at 60 → [30, 60]; never exceeds the cap.
    assert 30.0 <= client._backoff_delay(10) <= 60.0


def test_getlogs_propagates_non_range_rpc_error() -> None:
    class BadMethod:
        def __call__(self, url: str, payload: dict) -> dict:
            return {
                "jsonrpc": "2.0",
                "id": payload["id"],
                "error": {"code": -32601, "message": "method not found"},
            }

    client = ChainClient(
        rpc_urls=["https://a.example"],
        transport=BadMethod(),
        initial_chunk=1000,
        min_chunk=100,
        max_chunk=8000,
    )
    with pytest.raises(RpcError):
        client.get_logs(address="0xabc", topics=[], from_block=0, to_block=10)

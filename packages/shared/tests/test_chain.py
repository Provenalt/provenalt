"""Unit tests for the Base chain client: adaptive getLogs chunking + provider rotation.

All transports here are in-memory fakes — no network. Tests that hit a real RPC live in
test_chain_integration.py and are marked `integration` (excluded from default runs).
"""

from __future__ import annotations

import pytest

from provenalt_shared.chain import (
    AdaptiveChunkSizer,
    ChainClient,
    RateLimitError,
    RpcError,
)

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


def test_getlogs_raises_when_all_providers_rate_limited() -> None:
    class AlwaysRateLimited:
        def __call__(self, url: str, payload: dict) -> dict:
            raise RateLimitError("HTTP 429")

    client = ChainClient(
        rpc_urls=["https://a.example", "https://b.example"],
        transport=AlwaysRateLimited(),
        initial_chunk=1000,
        min_chunk=100,
        max_chunk=8000,
        max_attempts_per_range=6,
    )
    with pytest.raises(RateLimitError):
        client.get_logs(address="0xabc", topics=[], from_block=0, to_block=999)


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

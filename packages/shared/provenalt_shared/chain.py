"""Base chain client with provider rotation and adaptive eth_getLogs chunking.

Public RPC endpoints impose two independent limits that this client adapts to:

* **Block-range caps** — an ``eth_getLogs`` request spanning too many blocks is rejected
  with a JSON-RPC error. The client shrinks the chunk size and retries the same range.
* **Per-IP rate limits** — bursts return HTTP 429. The client rotates to the next provider
  and shrinks the chunk; once the pressure passes, the chunk size grows back toward the
  configured maximum. When *every* provider has returned 429 for the same request, the
  pressure is systemic, not provider-specific — so the client sleeps with exponential
  backoff (jittered, capped) and retries, up to ``max_retries`` times, before finally
  raising. A long-running indexer must treat 429 as transient rather than crashing.
* **Transient transport failures** — HTTP 5xx, connection errors, and non-JSON 4xx surface
  as ``TransportError``. These are treated exactly like 429s: rotate providers, and when
  every provider has failed the same request, sleep with the same exponential backoff and
  retry up to ``max_retries`` before finally raising. This keeps the worker alive through a
  flaky provider outage — even when only one provider is configured.

The RPC transport is injected (a callable ``(url, payload) -> response``) so the adaptive
behaviour can be unit-tested deterministically with in-memory fakes — no network required.
The ``sleep`` and ``rng`` used for backoff are injected too, so backoff is exercised in
tests without real delays.
"""

from __future__ import annotations

import itertools
import math
import random
import time
from collections.abc import Callable
from typing import Any, Protocol

import httpx

from provenalt_shared.logging import get_logger

log = get_logger("chain.client")

# Sent on every RPC request: some public endpoints reject a missing/blank User-Agent or the
# httpx default. A descriptive UA identifies our traffic and keeps those endpoints happy.
DEFAULT_USER_AGENT = "provenalt-indexer/0.1"

# ─────────────────────────────────────────────────────────────────────────────
# Errors
# ─────────────────────────────────────────────────────────────────────────────


class ChainError(Exception):
    """Base class for all chain client errors."""


class TransportError(ChainError):
    """The transport failed to reach a provider (connection/DNS/timeout)."""


class RateLimitError(ChainError):
    """A provider returned HTTP 429 (per-IP rate limit)."""


class RpcError(ChainError):
    """A provider returned a JSON-RPC error object."""

    def __init__(self, code: int, message: str) -> None:
        super().__init__(f"RPC error {code}: {message}")
        self.code = code
        self.message = message


class BlockRangeCapError(RpcError):
    """A JSON-RPC error indicating the requested block range was too large."""


# Substrings (lowercased) that unambiguously identify an eth_getLogs block-range /
# response-size cap. Phrasings were taken from the errors these providers actually return
# (verified against production responses and each provider's public docs):
#
#   Alchemy      "Log response size exceeded. You can make eth_getLogs requests with up to
#                a 2K block range..." / "...up to a 500 block range..."
#   Base RPC     "block range is too large" (Geth/Reth-family public node)
#   Infura       "query returned more than 10000 results"
#   QuickNode    "eth_getLogs is limited to a 10000 block range"
#   Ankr         "block range is too wide" / "requested too many blocks"
_BLOCK_RANGE_HINTS: tuple[str, ...] = (
    "block range",  # Alchemy, Base RPC, Infura ("try with this block range [..]")
    "range is too large",  # Base RPC / Geth-family
    "range is too wide",  # Ankr
    "too many blocks",  # Ankr ("requested too many blocks")
    "query returned more than",  # Infura ("query returned more than 10000 results")
    "response size exceeded",  # Alchemy ("Log response size exceeded")
    "log response size",  # Alchemy (variant)
    "logs matched by query exceeds",  # Geth-family
    "exceed maximum block range",  # QuickNode / Geth
    "limit exceeded",  # generic providers
)
# Generic "cap" verbs that only mean a range cap when paired with a range/log noun — this
# keeps precision so an unrelated RpcError that merely says "exceeds" (e.g. "exceeds
# balance") is NOT misread as a range cap and needlessly retried.
_CAP_VERBS: tuple[str, ...] = ("limited to", "up to", "exceeds", "should be within")
_CAP_NOUNS: tuple[str, ...] = ("block", "range", "logs", "results")

# JSON-RPC error codes providers commonly use for range/limit rejections.
_BLOCK_RANGE_CODES: frozenset[int] = frozenset({-32005, -32602, -32000, -32600})


def _is_block_range_error(code: int, message: str) -> bool:
    lowered = message.lower()
    if any(hint in lowered for hint in _BLOCK_RANGE_HINTS):
        return True
    # A generic cap verb ("limited to", "up to a N block range", "exceeds", …) paired with a
    # range/log noun — covers Alchemy/QuickNode phrasings without over-matching.
    if any(v in lowered for v in _CAP_VERBS) and any(n in lowered for n in _CAP_NOUNS):
        return True
    # Some providers only signal via a known code plus a vaguer "range"/"limit" message.
    if code in _BLOCK_RANGE_CODES and ("range" in lowered or "limit" in lowered):
        return True
    return False


# ─────────────────────────────────────────────────────────────────────────────
# Adaptive chunk sizer
# ─────────────────────────────────────────────────────────────────────────────


class AdaptiveChunkSizer:
    """Tracks the current eth_getLogs chunk size, shrinking and growing within bounds."""

    def __init__(
        self,
        initial: int,
        minimum: int,
        maximum: int,
        shrink_factor: float = 0.5,
        grow_factor: float = 1.5,
    ) -> None:
        if minimum < 1:
            raise ValueError("minimum chunk size must be >= 1")
        if maximum < minimum:
            raise ValueError("maximum chunk size must be >= minimum")
        if not 0 < shrink_factor < 1:
            raise ValueError("shrink_factor must be in (0, 1)")
        if grow_factor <= 1:
            raise ValueError("grow_factor must be > 1")

        self._minimum = minimum
        self._maximum = maximum
        self._shrink_factor = shrink_factor
        self._grow_factor = grow_factor
        self._size = self._clamp(initial)

    def _clamp(self, value: int) -> int:
        return max(self._minimum, min(self._maximum, value))

    @property
    def size(self) -> int:
        return self._size

    @property
    def at_minimum(self) -> bool:
        return self._size == self._minimum

    def shrink(self) -> int:
        """Shrink toward the minimum. Guaranteed to make progress until the floor."""
        shrunk = math.floor(self._size * self._shrink_factor)
        # Ensure we always drop by at least one block while above the minimum.
        if shrunk >= self._size:
            shrunk = self._size - 1
        self._size = self._clamp(shrunk)
        return self._size

    def grow(self) -> int:
        """Grow toward the maximum. Guaranteed to make progress until the ceiling."""
        grown = math.floor(self._size * self._grow_factor)
        if grown <= self._size:
            grown = self._size + 1
        self._size = self._clamp(grown)
        return self._size


# ─────────────────────────────────────────────────────────────────────────────
# Transport protocol
# ─────────────────────────────────────────────────────────────────────────────


class Transport(Protocol):
    """Sends a JSON-RPC payload to a provider URL and returns the parsed response.

    Implementations must raise :class:`RateLimitError` on HTTP 429 and
    :class:`TransportError` on connection-level failures. JSON-RPC-level errors are
    returned in the response dict under ``"error"`` (not raised).
    """

    def __call__(self, url: str, payload: dict[str, Any]) -> dict[str, Any]: ...


def _extract_rpc_error(response: httpx.Response) -> tuple[int, str] | None:
    """Return ``(code, message)`` if the body is a JSON-RPC error object, else ``None``.

    Some providers reject a request with an HTTP 4xx whose body is nonetheless a JSON-RPC
    error object rather than a 200-with-error — Alchemy does exactly this for an oversized
    ``eth_getLogs`` range. A non-JSON body (HTML error page, empty) yields ``None`` so the
    caller falls back to a generic :class:`TransportError`.
    """
    try:
        body = response.json()
    except ValueError:  # non-JSON body (json.JSONDecodeError subclasses ValueError)
        return None
    if not isinstance(body, dict):
        return None
    error = body.get("error")
    if not isinstance(error, dict):
        return None
    try:
        code = int(error.get("code", 0))
    except (TypeError, ValueError):
        code = 0
    return code, str(error.get("message", ""))


class HttpxTransport:
    """Production transport: POSTs JSON-RPC over HTTP with httpx.

    Maps transport-level conditions to the client's error taxonomy so the
    :class:`ChainClient` can react (rotate providers, shrink chunks, back off):

    * HTTP 429 → :class:`RateLimitError`
    * HTTP 4xx whose body is a JSON-RPC error → :class:`BlockRangeCapError` (range/size cap)
      or :class:`RpcError` (anything else). Providers such as Alchemy return an oversized
      ``eth_getLogs`` rejection as an HTTP 400 with a JSON-RPC error body, not a 200; mapping
      the whole 4xx bucket to ``TransportError`` made the client rotate providers forever
      instead of shrinking the chunk, so the backfill never advanced.
    * HTTP 5xx / non-JSON 4xx / connection failures → :class:`TransportError`
    """

    def __init__(
        self,
        timeout: float = 10.0,
        client: httpx.Client | None = None,
        user_agent: str = DEFAULT_USER_AGENT,
    ) -> None:
        self._client = client if client is not None else httpx.Client(timeout=timeout)
        self._user_agent = user_agent

    def __call__(self, url: str, payload: dict[str, Any]) -> dict[str, Any]:
        try:
            # Send an explicit User-Agent — some public endpoints reject the httpx default.
            response = self._client.post(
                url, json=payload, headers={"User-Agent": self._user_agent}
            )
        except httpx.HTTPError as exc:
            raise TransportError(f"transport failure for {url}: {exc}") from exc

        if response.status_code == 429:
            raise RateLimitError(f"HTTP 429 from {url}")
        if response.status_code >= 500:
            raise TransportError(f"HTTP {response.status_code} from {url}")
        if response.status_code >= 400:
            # A 4xx can still carry a JSON-RPC error (Alchemy does this for range caps).
            # Classify it so range caps shrink the chunk instead of rotating providers.
            rpc_error = _extract_rpc_error(response)
            if rpc_error is not None:
                code, message = rpc_error
                if _is_block_range_error(code, message):
                    raise BlockRangeCapError(code, message)
                raise RpcError(code, message)
            raise TransportError(f"HTTP {response.status_code} from {url}")

        result: dict[str, Any] = response.json()
        return result


# ─────────────────────────────────────────────────────────────────────────────
# Chain client
# ─────────────────────────────────────────────────────────────────────────────


class ChainClient:
    """Provider-rotating JSON-RPC client with adaptive ``eth_getLogs`` chunking."""

    def __init__(
        self,
        rpc_urls: list[str],
        transport: Transport,
        initial_chunk: int,
        min_chunk: int,
        max_chunk: int,
        max_attempts_per_range: int = 32,
        *,
        backoff_initial_seconds: float = 2.0,
        backoff_max_seconds: float = 60.0,
        max_retries: int = 8,
        sleep: Callable[[float], None] = time.sleep,
        rng: random.Random | None = None,
    ) -> None:
        if not rpc_urls:
            raise ValueError("at least one RPC URL is required")
        if backoff_initial_seconds <= 0:
            raise ValueError("backoff_initial_seconds must be > 0")
        if backoff_max_seconds < backoff_initial_seconds:
            raise ValueError("backoff_max_seconds must be >= backoff_initial_seconds")
        if max_retries < 0:
            raise ValueError("max_retries must be >= 0")
        self._rpc_urls = list(rpc_urls)
        self._transport = transport
        self._provider_index = 0
        self._chunker = AdaptiveChunkSizer(
            initial=initial_chunk, minimum=min_chunk, maximum=max_chunk
        )
        self._max_attempts_per_range = max_attempts_per_range
        self._backoff_initial = backoff_initial_seconds
        self._backoff_max = backoff_max_seconds
        self._max_retries = max_retries
        self._sleep = sleep
        self._rng = rng if rng is not None else random.Random()
        self._request_ids = itertools.count(1)

    @property
    def chunk_size(self) -> int:
        return self._chunker.size

    @property
    def current_provider(self) -> str:
        return self._rpc_urls[self._provider_index]

    def _rotate_provider(self) -> None:
        self._provider_index = (self._provider_index + 1) % len(self._rpc_urls)

    def _backoff_delay(self, attempt: int) -> float:
        """Exponential backoff with equal jitter: ~initial, doubling, capped at max.

        ``attempt`` is the zero-based backoff round. The base doubles each round
        (``initial * 2**attempt``) up to ``backoff_max``; equal jitter then keeps the
        actual wait in ``[base/2, base]`` so retries de-synchronise across workers.
        """
        base = min(self._backoff_max, self._backoff_initial * (2.0**attempt))
        return base * 0.5 + self._rng.random() * (base * 0.5)

    def _maybe_backoff(self, backoff_round: int, *, provider: str, error: ChainError) -> int:
        """Every provider has failed this request (429 or transport); the pressure is
        systemic. Sleep with exponential backoff and return the next round, or raise
        ``error`` once the retry budget (``max_retries``) is spent.

        Logs the flaky provider + error so operators can see which endpoint is failing.
        Call only when the failure streak has reached ``len(providers)``.
        """
        if backoff_round >= self._max_retries:
            raise error
        delay = self._backoff_delay(backoff_round)
        log.warning(
            "rpc_backoff",
            provider=provider,
            error=str(error),
            error_type=type(error).__name__,
            backoff_round=backoff_round,
            delay_seconds=round(delay, 3),
        )
        self._sleep(delay)
        return backoff_round + 1

    # ── Generic JSON-RPC ────────────────────────────────────────────────────

    def call(self, method: str, params: list[Any]) -> Any:
        """Make a single JSON-RPC call, rotating providers on 429/transport failures.

        On a transient failure — HTTP 429 (:class:`RateLimitError`) or a transport failure
        (:class:`TransportError`: 5xx, connection error, non-JSON 4xx) — the client rotates
        to the next provider; when *every* provider has failed this request it sleeps with
        exponential backoff and retries, up to ``max_retries`` rounds, before finally
        raising the last error. JSON-RPC-level errors (e.g. method-not-found) raise
        :class:`RpcError` immediately without rotation — they are not provider-specific.
        """
        failure_streak = 0  # consecutive provider failures (429 or transport) this request
        backoff_round = 0  # exponential-backoff rounds already spent
        while True:
            provider = self.current_provider
            payload = {
                "jsonrpc": "2.0",
                "id": next(self._request_ids),
                "method": method,
                "params": params,
            }
            try:
                response = self._transport(provider, payload)
            except (RateLimitError, TransportError) as exc:
                # Transient, provider-level failure: rotate. When every provider has failed
                # this request the pressure is systemic → sleep with backoff and retry.
                self._rotate_provider()
                failure_streak += 1
                if failure_streak >= len(self._rpc_urls):
                    backoff_round = self._maybe_backoff(backoff_round, provider=provider, error=exc)
                    failure_streak = 0
                continue

            error = response.get("error")
            if error is not None:
                raise RpcError(int(error.get("code", 0)), str(error.get("message", "")))
            return response.get("result")

    def get_block_number(self) -> int:
        """Return the current head block number."""
        return int(self.call("eth_blockNumber", []), 16)

    def get_code(self, address: str, block: int | str = "latest") -> str:
        """Return the deployed bytecode at ``address`` for the given block tag."""
        block_tag = block if isinstance(block, str) else hex(block)
        result: str = self.call("eth_getCode", [address, block_tag])
        return result

    def get_block_by_number(
        self, block: int, include_transactions: bool = False
    ) -> dict[str, Any] | None:
        """Return the block object (including its ``hash``) or ``None`` if not found."""
        result: dict[str, Any] | None = self.call(
            "eth_getBlockByNumber", [hex(block), include_transactions]
        )
        return result

    def _build_payload(
        self, address: str, topics: list[Any], from_block: int, to_block: int
    ) -> dict[str, Any]:
        return {
            "jsonrpc": "2.0",
            "id": next(self._request_ids),
            "method": "eth_getLogs",
            "params": [
                {
                    "address": address,
                    "topics": topics,
                    "fromBlock": hex(from_block),
                    "toBlock": hex(to_block),
                }
            ],
        }

    def _get_logs_once(
        self, address: str, topics: list[Any], from_block: int, to_block: int
    ) -> list[dict[str, Any]]:
        """One eth_getLogs call against the current provider.

        Raises RateLimitError / TransportError (transport-level) or
        BlockRangeCapError / RpcError (JSON-RPC-level).
        """
        payload = self._build_payload(address, topics, from_block, to_block)
        response = self._transport(self.current_provider, payload)
        error = response.get("error")
        if error is not None:
            code = int(error.get("code", 0))
            message = str(error.get("message", ""))
            if _is_block_range_error(code, message):
                raise BlockRangeCapError(code, message)
            raise RpcError(code, message)
        result: list[dict[str, Any]] = response.get("result", [])
        return result

    def get_logs(
        self,
        address: str,
        topics: list[Any],
        from_block: int,
        to_block: int,
    ) -> list[dict[str, Any]]:
        """Fetch all logs in ``[from_block, to_block]`` using adaptive chunking.

        Shrinks the chunk on block-range caps and 429s, and grows it back toward the maximum
        after each success. A 429 or transport failure rotates providers; when *every*
        provider has failed the current range the client sleeps with exponential backoff and
        retries up to ``max_retries`` rounds before finally raising — so transient rate
        limits and provider outages never crash a long-running backfill. (A 429 also shrinks
        the chunk; a transport 5xx does not — it is not about range size.)
        """
        if to_block < from_block:
            return []

        logs: list[dict[str, Any]] = []
        start = from_block
        attempts = 0  # block-range-cap attempts for the current range
        failure_streak = 0  # consecutive provider failures (429/transport) for this range
        backoff_round = 0  # exponential-backoff rounds spent on the current range

        while start <= to_block:
            end = min(start + self._chunker.size - 1, to_block)
            provider = self.current_provider
            try:
                chunk_logs = self._get_logs_once(address, topics, start, end)
            except BlockRangeCapError:
                failure_streak = 0
                attempts += 1
                if attempts >= self._max_attempts_per_range:
                    raise
                if self._chunker.at_minimum:
                    # Can't shrink further — try another provider before giving up.
                    self._rotate_provider()
                else:
                    self._chunker.shrink()
                continue
            except (RateLimitError, TransportError) as exc:
                # Transient provider failure: rotate. A 429 also shrinks the chunk (a 5xx
                # does not — it isn't about range size). When every provider has failed this
                # range, sleep with exponential backoff and retry.
                self._rotate_provider()
                if isinstance(exc, RateLimitError):
                    self._chunker.shrink()
                failure_streak += 1
                if failure_streak >= len(self._rpc_urls):
                    backoff_round = self._maybe_backoff(backoff_round, provider=provider, error=exc)
                    failure_streak = 0
                continue

            # Success: record, grow the chunk, advance, and reset every retry budget.
            logs.extend(chunk_logs)
            self._chunker.grow()
            start = end + 1
            attempts = 0
            failure_streak = 0
            backoff_round = 0

        return logs

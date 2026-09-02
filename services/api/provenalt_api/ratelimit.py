"""Per-IP rate limiting for the free tier, with API-key bypass for partners (proposal §6.2).

The limiter is an in-memory sliding window (per API process). Valid partner API keys
(``X-API-Key`` header, checked against the ``api_keys`` table) bypass the limit entirely.
"""

from __future__ import annotations

import time
from collections import defaultdict, deque
from collections.abc import Callable

from fastapi import HTTPException, Request, status
from provenalt_shared.db import repository as repo

from provenalt_api.deps import SessionDep


class SlidingWindowLimiter:
    def __init__(
        self,
        max_requests: int,
        window_seconds: float,
        clock: Callable[[], float] = time.monotonic,
    ) -> None:
        self._max = max_requests
        self._window = window_seconds
        self._clock = clock
        self._hits: dict[str, deque[float]] = defaultdict(deque)

    def allow(self, key: str) -> bool:
        now = self._clock()
        hits = self._hits[key]
        cutoff = now - self._window
        while hits and hits[0] <= cutoff:
            hits.popleft()
        if len(hits) >= self._max:
            return False
        hits.append(now)
        return True


def rate_limit(request: Request, session: SessionDep) -> None:
    """Free-tier per-IP rate limit; valid partner API keys bypass it."""
    api_key = request.headers.get("x-api-key")
    if api_key and repo.is_valid_api_key(session, api_key):
        return

    limiter: SlidingWindowLimiter = request.app.state.limiter
    client_ip = request.client.host if request.client else "unknown"
    if not limiter.allow(client_ip):
        raise HTTPException(
            status_code=status.HTTP_429_TOO_MANY_REQUESTS,
            detail="Rate limit exceeded. Use a partner API key (X-API-Key) for higher limits.",
        )

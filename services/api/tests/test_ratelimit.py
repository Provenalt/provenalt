"""Rate limiter unit tests + per-IP limit / API-key bypass via the API (proposal §6.2)."""

from __future__ import annotations

import seed
from fastapi.testclient import TestClient
from provenalt_shared.db import repository as repo
from sqlalchemy.orm import Session

from provenalt_api.ratelimit import SlidingWindowLimiter


class FakeClock:
    def __init__(self) -> None:
        self.t = 0.0

    def __call__(self) -> float:
        return self.t


def test_sliding_window_allows_up_to_max_then_blocks() -> None:
    clock = FakeClock()
    limiter = SlidingWindowLimiter(max_requests=2, window_seconds=10, clock=clock)
    assert limiter.allow("ip") is True
    assert limiter.allow("ip") is True
    assert limiter.allow("ip") is False  # third within window


def test_sliding_window_recovers_after_window() -> None:
    clock = FakeClock()
    limiter = SlidingWindowLimiter(max_requests=1, window_seconds=10, clock=clock)
    assert limiter.allow("ip") is True
    assert limiter.allow("ip") is False
    clock.t = 11
    assert limiter.allow("ip") is True  # window elapsed


def test_sliding_window_is_per_key() -> None:
    limiter = SlidingWindowLimiter(max_requests=1, window_seconds=10)
    assert limiter.allow("a") is True
    assert limiter.allow("b") is True  # different key, own bucket


def test_api_rate_limit_returns_429(client: TestClient) -> None:
    client.app.state.limiter = SlidingWindowLimiter(max_requests=2, window_seconds=60)
    assert client.get("/v1/stats").status_code == 200
    assert client.get("/v1/stats").status_code == 200
    r = client.get("/v1/stats")
    assert r.status_code == 429
    assert "rate limit" in r.json()["detail"].lower()


def test_paid_tier_is_rate_limited_when_x402_disabled(session: Session, client: TestClient) -> None:
    """Payment gating complements rate limiting; it does not replace it. Even with x402
    disabled (so the gate lets the call through), the per-IP limit still applies to the
    paid-tier routes and a burst returns 429."""
    seed.add_agent(session, 1, "0x" + "11" * 20)
    seed.add_score(session, 1, score=72, confidence="high")
    session.commit()

    client.app.state.limiter = SlidingWindowLimiter(max_requests=2, window_seconds=60)
    assert client.get("/v1/agents/1/score").status_code == 200
    assert client.get("/v1/agents/1/score").status_code == 200
    assert client.get("/v1/agents/1/score").status_code == 429  # burst over the limit


def test_api_key_bypasses_rate_limit(session: Session, client: TestClient) -> None:
    repo.create_api_key(session, "partner-secret", label="partner")
    session.commit()
    seed.add_cursor(session, "identity", anchor=1, last=1)
    session.commit()

    client.app.state.limiter = SlidingWindowLimiter(max_requests=1, window_seconds=60)
    headers = {"X-API-Key": "partner-secret"}
    # Well past the limit, but the valid key bypasses it every time.
    for _ in range(5):
        assert client.get("/v1/stats", headers=headers).status_code == 200

    # An invalid key does not bypass.
    client.app.state.limiter = SlidingWindowLimiter(max_requests=1, window_seconds=60)
    assert client.get("/v1/stats", headers={"X-API-Key": "wrong"}).status_code == 200
    assert client.get("/v1/stats", headers={"X-API-Key": "wrong"}).status_code == 429

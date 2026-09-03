"""FastAPI application for the Provenalt public API (proposal §7).

Free tier (per-IP rate limited; partner API keys bypass):
    GET /v1/agents                    search / list agents (paginated, filters)
    GET /v1/agents/{agentId}          identity + card + metadata + owner history
    GET /v1/agents/{agentId}/feedback feedback timeline
    GET /v1/stats                     registry totals + growth + indexer position

x402-gated tier (payment or partner API key; §7 / §9):
    GET /v1/agents/{agentId}/score    Provenalt Score + per-component breakdown
    GET /v1/provenalt/{agentId}       compact pass/warn/fail verdict
    GET /v1/eligibility               B20 stock eligibility + balances

OpenAPI docs at /docs and /openapi.json.
"""

from __future__ import annotations

from fastapi import Depends, FastAPI
from provenalt_shared.settings import get_settings

from provenalt_api.ratelimit import SlidingWindowLimiter, rate_limit
from provenalt_api.routers import agents, eligibility, score, stats
from provenalt_api.x402_gate import config_from_settings, x402_gate


def create_app() -> FastAPI:
    settings = get_settings()
    app = FastAPI(
        title="Provenalt API",
        version="0.1.0",
        summary="Trust layer for the agentic economy on Base.",
        description=(
            "Read-only access to indexed ERC-8004 agents, their cards, feedback, and the "
            "Provenalt Score. Free-tier endpoints are per-IP rate limited; the score, verdict, "
            "and eligibility endpoints are x402-paid (partners bypass with `X-API-Key`)."
        ),
    )
    app.state.limiter = SlidingWindowLimiter(
        max_requests=settings.api_rate_limit_requests,
        window_seconds=settings.api_rate_limit_window_seconds,
    )
    app.state.x402_config = config_from_settings(settings)
    # Overridden in tests to point at the test database; None → the app's own session factory.
    app.state.db_factory = None

    # x402 payment gate (governs the paid routes; passes free routes through).
    app.middleware("http")(x402_gate)

    @app.get("/healthz", tags=["meta"], summary="Liveness probe")
    def healthz() -> dict[str, str]:
        return {"status": "ok"}

    # Free tier — per-IP rate limited.
    app.include_router(agents.router, dependencies=[Depends(rate_limit)])
    app.include_router(stats.router, dependencies=[Depends(rate_limit)])
    # Paid tier — governed by the x402 gate (no per-IP limit).
    app.include_router(score.router)
    app.include_router(eligibility.router)
    return app


app = create_app()

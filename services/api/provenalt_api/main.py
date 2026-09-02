"""FastAPI application for the Provenalt public API (proposal §7, free tier).

Free-tier endpoints (per-IP rate limited, partner API keys bypass):
    GET /v1/agents                    search / list agents (paginated, filters)
    GET /v1/agents/{agentId}          identity + card + metadata + owner history
    GET /v1/agents/{agentId}/feedback feedback timeline
    GET /v1/stats                     registry totals + indexer position

The x402-gated endpoints (score, provenalt verdict, eligibility) are added in Groups 7 & 9.
OpenAPI docs are published at /docs and /openapi.json.
"""

from __future__ import annotations

from fastapi import Depends, FastAPI
from provenalt_shared.settings import get_settings

from provenalt_api.ratelimit import SlidingWindowLimiter, rate_limit
from provenalt_api.routers import agents, stats


def create_app() -> FastAPI:
    settings = get_settings()
    app = FastAPI(
        title="Provenalt API",
        version="0.1.0",
        summary="Trust layer for the agentic economy on Base — free-tier read API.",
        description=(
            "Read-only access to indexed ERC-8004 agents, their cards, feedback, and the "
            "Provenalt Score. Free-tier endpoints are per-IP rate limited; partners bypass "
            "the limit with an `X-API-Key` header."
        ),
    )
    app.state.limiter = SlidingWindowLimiter(
        max_requests=settings.api_rate_limit_requests,
        window_seconds=settings.api_rate_limit_window_seconds,
    )

    @app.get("/healthz", tags=["meta"], summary="Liveness probe")
    def healthz() -> dict[str, str]:
        return {"status": "ok"}

    app.include_router(agents.router, dependencies=[Depends(rate_limit)])
    app.include_router(stats.router, dependencies=[Depends(rate_limit)])
    return app


app = create_app()

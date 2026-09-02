"""Smoke test against a real database (proposal §6.3).

Marked `integration` and excluded from default runs. Run against a provisioned DB with the
schema migrated (`alembic upgrade head`):

    DATABASE_URL=postgresql://... pytest -m integration

It performs read-only requests only.
"""

from __future__ import annotations

import pytest
from fastapi.testclient import TestClient
from provenalt_shared.settings import get_settings

from provenalt_api.main import create_app

pytestmark = pytest.mark.integration


def test_smoke_against_database() -> None:
    if not get_settings().database_url:
        pytest.skip("DATABASE_URL not set")

    app = create_app()
    with TestClient(app) as client:
        assert client.get("/healthz").json() == {"status": "ok"}

        stats = client.get("/v1/stats")
        assert stats.status_code == 200
        body = stats.json()
        assert "total_agents" in body
        assert "registries" in body

        # Listing must succeed (possibly empty) and be well-formed.
        agents = client.get("/v1/agents", params={"limit": 1})
        assert agents.status_code == 200
        assert set(agents.json()) >= {"items", "total", "limit", "offset"}

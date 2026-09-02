# api

FastAPI service — the Provenalt public API. Deployed as a request/response Railway service
(see [`infra/README.md`](../../infra/README.md)). Depends on
[`packages/shared`](../../packages/shared) for DB models, repository, settings, and scoring.

## Status (Group 6 — Public API, free tier)

Endpoints (proposal §7, free tier — per-IP rate limited, partner API keys bypass):

- `GET /v1/agents` — search/list agents (paginated; `limit`, `offset`, `owner` filter).
- `GET /v1/agents/{agent_id}` — identity + card + metadata + owner history (+ score summary).
- `GET /v1/agents/{agent_id}/feedback` — feedback timeline (with revoked/responded flags).
- `GET /v1/stats` — registry totals + per-registry indexer position.
- `GET /v1/eligibility?wallet=&token=` — B20 tokenized-stock eligibility (native
  PolicyRegistry `isAuthorized`) + multiplier-aware raw/adjusted balances (Group 7). The B20
  token registry is seeded in migration `0007`; the on-chain ABI is documented in
  [`docs/b20-eligibility.md`](../../docs/b20-eligibility.md).
- `GET /healthz` — liveness. OpenAPI at `/openapi.json`, Swagger UI at `/docs`.

The remaining x402-gated endpoints (`/v1/agents/{id}/score`, `/v1/provenalt/{id}`) are added
in Group 9; x402 gating of `/v1/eligibility` also lands in Group 9 (it is per-IP rate limited
for now).

**Rate limiting** (`ratelimit.py`): in-memory per-IP sliding window (configurable via
`PROVENALT_API_RATE_LIMIT_*`). A valid `X-API-Key` (checked against the hashed `api_keys`
table) bypasses the limit. API keys are stored **hashed only** — created via
`repository.create_api_key`, plaintext shown once.

## Run

```bash
pip install -e ../../packages/shared -e ".[dev]"
DATABASE_URL=... uvicorn provenalt_api.main:app --reload   # dev
```

## Tests

```bash
pytest                 # unit (in-memory SQLite via TestClient)
DATABASE_URL=... pytest -m integration   # smoke test against a real DB (read-only)
```

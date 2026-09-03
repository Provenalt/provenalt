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
- `GET /healthz` — liveness. OpenAPI at `/openapi.json`, Swagger UI at `/docs`.

### Paid tier (x402-gated — proposal §7 / §9)

Payment (or a valid partner `X-API-Key`) is required for:

- `GET /v1/agents/{id}/score` — Provenalt Score + **per-component breakdown** + confidence.
- `GET /v1/provenalt/{id}` — compact pass/warn/fail verdict.
- `GET /v1/eligibility?wallet=&token=` — B20 eligibility + multiplier-aware balances (Group 7;
  ABI in [`docs/b20-eligibility.md`](../../docs/b20-eligibility.md)).

The **x402 gate** (`x402_gate.py`) returns a spec-correct `402` with USDC-on-Base payment
terms (built from the official x402 SDK schemas), verifies + settles via a facilitator, and
bypasses for valid partner API keys. Disabled by default; configure via `PROVENALT_X402_*`
(see `.env.example` and [`docs/x402.md`](../../docs/x402.md)). Every gated call is metered in
`usage_events`; run `python scripts/usage_report.py` for a revenue summary.

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

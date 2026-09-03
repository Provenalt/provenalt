# Infrastructure — Manual Provisioning Guide

This document is what the operator needs to provision by hand. **Nothing here is
automated** — Provenalt does not create cloud resources from code. Provision the
resources below, then set the environment variables (documented in
[`../.env.example`](../.env.example)) in each platform's dashboard.

> Reminder (repo `CLAUDE.md`): no secrets in the repo, ever. Real RPC keys, database
> URLs, and tokens live only in the platform dashboards and your local untracked `.env`.

---

## 1. Railway — indexer + api + Postgres

Create one Railway **project** for Provenalt. Inside it, provision:

### 1.1 Postgres database
- Add the **Postgres** plugin/database to the project.
- Railway exposes a `DATABASE_URL` connection variable. Reference it from both services
  (Railway lets you reference another resource's variables).
- No schema is created yet — migrations arrive with Group 2.

### 1.2 Service: `indexer` (long-running worker)
- **Root directory:** `services/indexer`
- **Runtime profile:** long-running worker (no public HTTP port; not request/response).
- **Start command:** the worker entrypoint (defined in Group 2). Placeholder for now.
- **Restart policy:** always/on-failure — the indexer must survive restarts and resume
  from its cursor.
- **Env vars to set** (names from `.env.example`):
  - `DATABASE_URL` (reference the Postgres plugin)
  - `PROVENALT_ENVIRONMENT=production`
  - `PROVENALT_LOG_LEVEL=INFO`
  - `PROVENALT_LOG_FORMAT=json`
  - `PROVENALT_RPC_URLS` (≥2 Base RPC endpoints, comma-separated)
  - `PROVENALT_FINALITY_DEPTH=64`
  - `PROVENALT_GETLOGS_INITIAL_CHUNK`, `PROVENALT_GETLOGS_MIN_CHUNK`, `PROVENALT_GETLOGS_MAX_CHUNK`

### 1.3 Service: `api` (request/response)
- **Root directory:** `services/api`
- **Runtime profile:** request/response HTTP service; Railway assigns a public domain.
- **Start command:** `uvicorn provenalt_api.main:app --host 0.0.0.0 --port $PORT`
- **Pre-deploy / release command:** apply migrations before starting —
  `cd packages/shared && alembic upgrade head` (see §1.5).
- **Env vars to set** (names from `.env.example`):
  - `DATABASE_URL` (reference the Postgres plugin)
  - `PROVENALT_ENVIRONMENT=production`, `PROVENALT_LOG_LEVEL=INFO`, `PROVENALT_LOG_FORMAT=json`
  - `PROVENALT_API_RATE_LIMIT_REQUESTS`, `PROVENALT_API_RATE_LIMIT_WINDOW_SECONDS`
  - `PROVENALT_API_DEFAULT_PAGE_SIZE`, `PROVENALT_API_MAX_PAGE_SIZE`
  - x402 config arrives in Group 9.
- **Partner API keys:** created out-of-band and stored **hashed** in the `api_keys` table
  (`repository.create_api_key`); the plaintext is shown once and never persisted. Partners
  send it via the `X-API-Key` header to bypass the free-tier rate limit **and x402 payment**.
- **x402 (paid tier):** the score / provenalt / eligibility endpoints are payment-gated
  (proposal §7, docs/x402.md). Set `PROVENALT_X402_ENABLED=true`, `PROVENALT_X402_PAY_TO`
  (receiving wallet — a secret, set only in the dashboard), and for **Base mainnet**
  `PROVENALT_X402_FACILITATOR_URL` to the Coinbase CDP facilitator (with CDP credentials).
  Revenue/usage is metered in `usage_events`; see `scripts/usage_report.py`.
- **Docs:** OpenAPI at `/openapi.json`, Swagger UI at `/docs`; liveness at `/healthz`.
- **Smoke test** after deploy (read-only):
  `DATABASE_URL=... pytest -m integration` from `services/api` (hits `/healthz`, `/v1/stats`,
  `/v1/agents`).

> The indexer and api are **separate services on purpose** — different runtime profiles
> (long-running vs request/response) and independent deploys (proposal §4).

### 1.4 Deploy gating
- Configure deploys to require green CI (see `.github/workflows/ci.yml`). No deploy on red.

### 1.5 Database migrations
- The schema lives in Alembic migrations under `packages/shared/migrations`. Apply them
  with `DATABASE_URL=... alembic upgrade head` (run from `packages/shared`).
- Run this as a Railway **release/pre-deploy command** for the services that need the schema
  (at minimum the `api`), so migrations are applied before new code serves traffic.

---

## 2. Vercel — web (Next.js explorer)

- Create a Vercel **project** linked to this repo. Framework preset: Next.js.
- **Root directory:** the explorer reads the repo-root `METHODOLOGY.md` at build. Either:
  - set Root Directory to the **repo root** with build command
    `npm --prefix web ci && npm --prefix web run build` and output `web/.next`; or
  - set Root Directory to `web/` and ensure `METHODOLOGY.md` is reachable (the methodology
    page falls back gracefully if it is not).
- **Env vars to set** (names from `.env.example`):
  - `NEXT_PUBLIC_API_BASE_URL` → the Railway `api` service public URL.
- **OG images:** per-agent social cards are served dynamically at
  `/agents/{id}/opengraph-image` (no extra config).
- **Custom domain:** attach the chosen brand domain to this project (Open Question #1).
- Pages that read the API are dynamic and degrade gracefully when the API is unreachable, so
  a first deploy succeeds even before the API is live.

---

## 3. Domains

- **Explorer (Vercel):** attach the production domain / chosen brand domain to the Vercel
  `web` project. (Final domain is Open Question #1 in the proposal.)
- **API (Railway):** the `api` service gets a Railway-generated domain by default; attach
  a custom `api.` subdomain if desired and point `NEXT_PUBLIC_API_BASE_URL` at it.

---

## 4. Provisioning checklist (operator)

- [ ] Railway project created
- [ ] Postgres database added; `DATABASE_URL` available
- [ ] `indexer` service created (root `services/indexer`), env vars set
- [ ] `api` service created (root `services/api`), env vars set
- [ ] Deploys gated on green CI
- [ ] Vercel project created (root `web/`), `NEXT_PUBLIC_API_BASE_URL` set
- [ ] Domains attached (explorer + optional api subdomain)
- [ ] Confirmed: no secret values committed to the repo

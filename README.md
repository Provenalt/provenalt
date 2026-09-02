# Provenalt

A trust layer for the agentic economy on Base. Provenalt indexes the ERC-8004 Identity
and Reputation registries, validates Agent Cards, scores agents (the **Provenalt Score**),
checks B20 tokenized-stock eligibility natively on-chain, and distributes all of it via a
REST API, x402 pay-per-call, an MCP tool (`check_provenalt`), and a public explorer.

> Phase 1 (MVP). Scope, design, and task tracking live in
> [`openspec/proposal.md`](./openspec/proposal.md) and [`openspec/tasks.md`](./openspec/tasks.md).
> Repo conventions and the STOP protocol are in [`CLAUDE.md`](./CLAUDE.md).

## Repository layout

```
provenalt/
├── services/
│   ├── indexer/   Python worker — backfill + head-follow, writes Postgres
│   ├── api/       FastAPI — public REST + x402-gated endpoints
│   └── mcp/       MCP server exposing check_provenalt (thin client of api)
├── web/           Next.js explorer (Vercel)
├── packages/
│   └── shared/    settings, structured logging, chain client, (later) DB models + scoring
├── infra/         provisioning docs (Railway + Vercel) — see infra/README.md
├── openspec/      proposal + task tracking
└── .github/       CI workflows
```

## Stack

- **Services:** Python 3.12 + FastAPI
- **Web:** Next.js
- **Database:** Postgres
- **Deploy:** Railway (indexer worker + api + Postgres), Vercel (web)

## Getting started

```bash
# 1. Copy the env template and fill in local values (never commit .env)
cp .env.example .env

# 2. Shared package + tests
cd packages/shared
python -m venv .venv && source .venv/bin/activate
pip install -e ".[dev]"
python -m pytest
```

Environment variables are documented in [`.env.example`](./.env.example). Infrastructure
provisioning is documented in [`infra/README.md`](./infra/README.md).

## TODO (operator)

- [ ] **Create the remote repository** and wire up the origin. This local repo has no
      remote yet. Once you have created the GitHub repo:

      ```bash
      git remote add origin <REMOTE_URL>
      git push -u origin main
      ```

      Activating CI (`.github/workflows/`) and the deploy platforms depends on the remote
      existing. See `infra/README.md` for provisioning steps.

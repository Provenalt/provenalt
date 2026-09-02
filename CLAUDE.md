# CLAUDE.md — Provenalt Repo Conventions

Provenalt is a standalone trust layer for the agentic economy on Base. This file is
the contract for how work is done in this repo. Read it at the start of every session.

Source of truth for scope and design: [`openspec/proposal.md`](./openspec/proposal.md).
Task tracking: [`openspec/tasks.md`](./openspec/tasks.md).

---

## Working conventions

- **One task group per session.** Complete the current group in `openspec/tasks.md`,
  then STOP and wait for review before starting the next group. Do not begin a later
  group in the same session.
- **A task is checked off only when its tests pass.** No box in `openspec/tasks.md` is
  ticked on the basis of "written but untested". Run the tests, see them pass, then tick.
- **Test-driven.** New behavior gets a failing test first, then the implementation.
- **English only.** All code, comments, docs, commit messages, and product copy are in
  English. No exceptions.
- **No secrets in the repo, ever.** No API keys, RPC URLs with embedded keys, private
  keys, database URLs, or tokens in tracked files. Secrets live only in the deployment
  platform (Railway/Vercel) and in your local untracked `.env`. `.env.example` documents
  variable *names* only, never values.

## STOP protocol

Stop and ask the operator before any of the following. Do not proceed on assumption:

1. **Any destructive operation** — deleting files/directories you did not create in this
   session, dropping tables, `git reset --hard`, force pushes, rewriting history, or
   removing data.
2. **Any schema change outside the current task group's scope** — the DB schema for a
   group is defined by that group's tasks in the proposal. Touching schema owned by a
   different group (or inventing new tables/columns not in the proposal) requires sign-off.
3. **Any deviation from the proposal** — if the proposal is ambiguous, incomplete, or
   appears wrong, surface it and ask. Do not silently redesign, rename, re-scope, or add
   dependencies/services not described in the proposal.

When in doubt, stop and ask. A short question is cheaper than an unwanted change.

## Repo layout

```
provenalt/
├── services/
│   ├── indexer/   Python worker — backfill + head-follow, writes Postgres
│   ├── api/       FastAPI — public REST + x402-gated endpoints
│   └── mcp/       MCP server exposing check_provenalt (thin client of api)
├── web/           Next.js explorer (Vercel)
├── packages/
│   └── shared/    settings, structured logging, chain client, (later) DB models + scoring
├── infra/         provisioning docs (Railway + Vercel)
├── openspec/      proposal + task tracking
└── .github/       CI workflows
```

## Stack (fixed)

- **Services:** Python 3.12 + FastAPI.
- **Web:** Next.js.
- **Database:** Postgres.
- **Deploy:** Railway (indexer worker + api + Postgres), Vercel (web).

## Running tests

Shared package (Python):

```bash
cd packages/shared
python -m pytest                 # default run — unit tests only
python -m pytest -m integration  # integration tests (hit real RPC; excluded by default)
```

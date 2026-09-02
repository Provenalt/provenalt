# indexer

Python worker that backfills and head-follows the ERC-8004 registries on Base and writes to
Postgres. Deployed as a long-running Railway service (see [`infra/README.md`](../../infra/README.md)).
Depends on [`packages/shared`](../../packages/shared) for settings, logging, the chain client,
and the DB models/repository.

## Status (Group 2 — Identity indexing)

Implemented:

- **Event decoding** (`events.py`) — ABI-driven, from the vendored official
  `abis/IdentityRegistry.json`. topic0s are computed from signatures (the `Registered`
  topic0 is cross-checked against the proposal's pinned value in tests).
- **Deployment-block discovery** (`deploy_block.py`) — binary search on `eth_getCode`,
  used as the backfill anchor.
- **Backfill** (`backfill.py`) — segments the anchor→head range, commits the cursor after
  each segment (resumable), idempotent upserts.
- **Head-follow + reorg handling** (`follow.py`) — compares stored per-event `block_hash`
  against the chain in the unfinalized window; on a fork, rewinds ≤ N blocks, re-derives
  affected agents' owner/URI, and re-indexes forward.
- **Verification harness** (`verify.py`) — sequential agentId continuity check and a
  spot-check comparing indexed `owner`/`agent_uri` against on-chain `ownerOf`/`tokenURI`.
- **Worker entrypoint** (`worker.py`) — bootstrap → catch-up → head-follow loop.

## Status (Group 3 — Reputation indexing)

Implemented, reusing the Group 2 framework (the backfill/follow worker takes an injected
`ingest` projection and `rewind_fn`):

- **Reputation event decoding** (`reputation.py`) — ABI-driven from the vendored
  `abis/ReputationRegistry.json`; topic0s computed from signatures and cross-checked in
  tests. Signed `int128` values are decoded correctly.
- **Schema** — `feedback`, `feedback_revocations`, `feedback_responses` (Alembic migration
  `0002`), with the raw `value`, `value_decimals`, and decoded `value_scaled` numeric.
- **Projection + reorg** (`reputation_projection.py`) — idempotent inserts; reorg rewind is
  a plain tail delete (append-only). Both registries share `raw_logs`, so deletions and
  reorg detection are **scoped by contract address** to keep them isolated.
- **Rater credibility** (`§3.4`) — a Postgres materialized view `rater_credibility`
  (per-rater first-seen, feedback count, distinct agents rated, self-feedback), refreshed
  via `repo.refresh_rater_credibility`. The SELECT lives once in `repo.RATER_CREDIBILITY_SQL`.
- **Registry wiring** (`registries.py`) — the worker now bootstraps, backfills, and
  head-follows **both** the identity and reputation registries.
- **Topics script** — `scripts/print_topics.py` prints all computed topic0s.

The generic worker (`backfill.py`, `follow.py`) is registry-agnostic; identity and
reputation inject their own projection and rewind behaviour.

## Running

Set the environment variables from [`.env.example`](../../.env.example) (at minimum
`DATABASE_URL` and `PROVENALT_RPC_URLS`), then:

```bash
# 1. Apply the database schema (migrations live in packages/shared)
cd packages/shared && DATABASE_URL=... alembic upgrade head

# 2. Run the indexer
cd services/indexer
pip install -e ../../packages/shared -e ".[dev]"
provenalt-indexer            # bootstrap + backfill + head-follow
```

## Tests

```bash
pytest                 # unit only (in-memory SQLite + fake chain)
pytest -m integration  # hits a real Base RPC (skips if unreachable)
```

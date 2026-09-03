# Provenalt — Task Tracking

Mirrors the task groups in [`proposal.md`](./proposal.md) §8. A task is checked off
only when its tests pass. One task group per session (see repo `CLAUDE.md`).

---

## Group 1 — Foundation (repo, infra, conventions)
- [x] 1.1 Init monorepo layout per §4; CLAUDE.md with repo conventions + STOP protocol
      _(GitHub account/repo creation deferred to the operator — see README TODO)_
- [x] 1.2 Document Railway (Postgres + 2 services) and Vercel provisioning in `infra/README.md`;
      every env var documented in `.env.example`
      _(actual provisioning deferred to the operator)_
- [x] 1.3 CI: lint + typecheck + tests on PR; no deploy on red (GitHub Actions, ready to activate)
- [x] 1.4 `packages/shared`: settings loader, structured logging, chain client with provider
      rotation + adaptive getLogs chunking (unit-test chunk shrink/grow on simulated cap errors + 429s)

## Group 2 — Identity indexing
- [x] 2.1 DB schema: `agents`, `agent_metadata`, `agent_owner_history`, `raw_logs` (tx_hash+log_index unique, block_hash column); migration tooling
      _(SQLAlchemy models + Alembic migration `0001`. Added a small `indexer_cursor` table —
      not in the §2.1 list but required by 2.2 anchor persistence / 2.3 resumable cursor.)_
- [x] 2.2 Discover Identity Registry deployment block on Base (binary search on `eth_getCode`); persist as backfill anchor
- [x] 2.3 Backfill worker: `Registered`, `MetadataSet`, `URIUpdated`, `Transfer` from anchor → head; resumable via cursor; idempotent upserts
- [x] 2.4 Head-follow loop with reorg detection (block-hash check, rewind ≤ N)
- [x] 2.5 Verification harness: sequential agentId continuity check + spot-check 20 random agents
      _(spot-check compares against authoritative on-chain `ownerOf`/`tokenURI` via `eth_call`,
      per design decision §5.1 — no third-party subgraph dependency)_

## Group 3 — Reputation indexing
- [x] 3.1 Compute + pin topic0 hashes for all Reputation events from the official spec text (script in repo, not hardcoded by hand)
      _(topic0s computed from the vendored official ABI in `reputation.py`; `scripts/print_topics.py`
      prints them; tests cross-check against pinned values)_
- [x] 3.2 Schema: `feedback`, `feedback_revocations`, `feedback_responses` (+ decoded value/valueDecimals as numeric)
      _(Alembic migration `0002`; `value` raw int128, `value_decimals`, `value_scaled` numeric)_
- [x] 3.3 Backfill + follow for Reputation Registry (reuse Group 2 worker framework)
      _(generalised the backfill/follow worker to inject `ingest` + `rewind_fn`; both registries
      share `raw_logs` so reorg detection/deletion are scoped by contract address)_
- [x] 3.4 Rater-credibility materialized view (per-rater history, first-seen, feedback count, self-feedback detection)
      _(Postgres materialized view on PG / plain view on SQLite; single-source SQL cross-checked
      against the Core select; `refresh_rater_credibility` refreshes it)_

## Group 4 — Agent Card pipeline
- [x] 4.1 Fetch tokenURI content (ipfs:// via ≥2 gateways with fallback, https:// direct); store content + content hash + fetch status
      _(also handles `data:` base64 URIs per the spec; `cards/fetch.py`, injectable httpx client; sha256 content hash)_
- [x] 4.2 Validate against official Agent Card JSON schema (vendored copy, versioned); record validity + errors
      _(schema authored from the EIP-8004 registration-v1 normative structure — no published JSON Schema exists —
      vendored at `cards/schemas/registration-v1.schema.json`, SCHEMA_VERSION=1)_
- [x] 4.3 Refresh queue: re-fetch on `URIUpdated` + periodic sweep; drift log when content hash changes without URI change
      _(`card_refresh_queue`; queue fed from agents with no card or a changed `agent_uri`; `card_drift` table + worker sweep)_
- [x] 4.4 Consistency checks: `agentWallet` metadata vs card contents
      _(agentWallet from indexed MetadataSet vs addresses declared in the card; plus registrations[] binding to agent+registry;
      migration `0003`: `agent_cards`, `card_drift`, `card_refresh_queue`)_

## Group 5 — Scoring engine v1
- [x] 5.1 Implement components per §6 as pure functions over DB state; weights in config
      _(`provenalt_shared/scoring/`: pure `components.py`/`engine.py` over dataclass inputs; DB gather in `inputs.py`; weights in `weights.py`, `WEIGHTS_VERSION=1`)_
- [x] 5.2 Sybil heuristics: fresh-rater burst detection, per-rater influence cap, self/circular feedback flags
      _(self-feedback judged by owner **at the feedback's block height** via `agent_owner_history` — design note b; circular = owner reciprocity; per-rater cap; fresh-burst discount)_
- [x] 5.3 Score persistence + recompute triggers (event-driven for affected agents, nightly full sweep)
      _(migration `0004`: `agent_scores`, `score_refresh_queue`; `scoring/pipeline.py`; enqueue on new/activity + periodic sweep; wired into worker)_
- [x] 5.4 METHODOLOGY.md — public, human-readable, versioned with the weights
      _(root `METHODOLOGY.md`, versioned with `WEIGHTS_VERSION`)_
- [x] 5.5 Golden tests: fixture agents (fresh, established, sybil-boosted, transferred-ownership) with expected score bands
      _(`test_scoring_db.py::test_golden_score_bands`: established > sybil, established > transferred, fresh → insufficient_data)_

> Note: `registration_match` is weighted heavily and the heuristic `wallet_status` lightly
> (design note a). Group 3's `rater_credibility` view was updated (housekeeping, migration
> `0005`) to judge self-feedback by the **owner at the feedback's block height**, consistent
> with the scoring engine.

## Group 6 — Public API
- [x] 6.1 FastAPI service with endpoints per §7 (free tier), pagination, filters; OpenAPI docs published
      _(`services/api`: `/v1/agents` (paginated + `owner` filter), `/v1/agents/{id}`,
      `/v1/agents/{id}/feedback`, `/v1/stats`; OpenAPI at `/openapi.json`, Swagger at `/docs`.
      x402-gated score/provenalt/eligibility deferred to Groups 7 & 9 per the §7 tier split.)_
- [x] 6.2 Rate limiting (per-IP for free tier) + API keys table
      _(in-memory sliding-window per-IP limiter; `api_keys` table (migration `0006`, hash-only)
      with `X-API-Key` bypass)_
- [x] 6.3 Deploy to Railway; smoke tests against production DB
      _(smoke test `test_smoke_integration.py` (integration-marked, read-only) + uvicorn start
      command and release/migration docs in `infra/README.md`; actual Railway deploy deferred
      to the operator, like Group 1.2)_

## Group 7 — Eligibility module (B20, native)
- [x] 7.1 Chain-level `isAuthorized` precompile client (research exact call ABI from official B20 technical docs at base.org/stocks; document findings in repo)
      _(researched from docs.base.org B20 spec → `docs/b20-eligibility.md` (sources + verbatim ABI);
      `provenalt_api/b20.py` — PolicyRegistry `0x8453…0002`, `isAuthorized(uint64,address)`,
      token `policyId(bytes32)`; selectors + `keccak256` scope hashes COMPUTED, cross-checked in tests
      and confirmed against live Base)_
- [x] 7.2 `/v1/eligibility?wallet=&token=` for the 4 live stock contracts (registry of known B20 tokens in DB, extensible as more stocks land)
      _(`b20_tokens` table + migration `0007` seeding AAPLc/NVDAc/GOOGLc/METAc; endpoint resolves token by
      address or symbol, 404 if unknown; per-IP rate limited (x402 gating → Group 9))_
- [x] 7.3 Multiplier-aware balance reader (dividends/splits multiplier — report both raw and adjusted balance)
      _(reports raw `balanceOf` and adjusted `scaledBalanceOf` + the WAD `multiplier()`)_

## Group 8 — Explorer (web MVP)
- [x] 8.1 Next.js app: home (registry stats + growth chart), search, agent profile page (card, score breakdown, feedback timeline, owner history)
      _(`web/` Next.js App Router; dark technical design via the ui-ux-pro-max skill (Fira Code/Fira Sans,
      slate + trust-blue, verdict bands); hand-rolled SVG growth chart from a new `/v1/stats.growth` series;
      score "breakdown" shown as the published composition/weights — the per-agent numeric breakdown stays
      behind the x402-gated /score endpoint per §7)_
- [x] 8.2 Methodology page (renders METHODOLOGY.md); About page
      _(methodology renders the repo-root `METHODOLOGY.md` via react-markdown + remark-gfm)_
- [x] 8.3 Deploy to Vercel, custom domain, OG images for agent pages (shareable on X)
      _(dynamic per-agent OG image at `/agents/[id]/opengraph-image` (renders a PNG); Vercel/root/domain
      steps documented in `infra/README.md` and `web/README.md`; actual deploy deferred to the operator
      like Group 1.2/6.3)_

## Group 9 — Monetized distribution
- [x] 9.1 x402 integration on gated endpoints (USDC on Base, per-call pricing; start $0.01/call) — follow docs.cdp.coinbase.com x402 seller flow
      _(researched → `docs/x402.md`; official `x402` SDK used for schemas/facilitator (not guessed);
      custom `x402_gate.py` returns a spec-correct 402 (USDC on Base, $0.01) offline + verifies/settles
      via the facilitator in prod; API-key bypass; built the two gated endpoints `/v1/agents/{id}/score`
      (score + breakdown) and `/v1/provenalt/{id}` (verdict), and gated `/v1/eligibility`)_
- [x] 9.2 MCP server exposing `check_provenalt(agentId)` and `check_eligibility(wallet, token)`; installable via npx; README quickstart
      _(`services/mcp`: TS `@provenalt/mcp` (npx bin) over stdio; returns full structured objects; thin
      client of the api with `X-API-Key` bypass; smoke-verified tools/list)_
- [x] 9.3 Usage metering + simple revenue dashboard (internal)
      _(`usage_events` table + migration `0008`; gate records per-endpoint/per-payer calls + revenue;
      `scripts/usage_report.py` prints a per-endpoint revenue summary)_

> Notes: the paid tier confirmed per §7 (score/provenalt/eligibility x402-gated; free tier unchanged;
> partner `X-API-Key` bypasses x402 as it bypasses rate limits). x402 is **disabled by default** —
> enable + set the receiving wallet + (Base mainnet) CDP facilitator via env. The verify/settle path
> and MCP-against-live-API are exercised in production, not in offline tests.

## Group 10 — Launch
- [ ] 10.1 Seed content: index fully caught up; top-agents page accurate
- [ ] 10.2 Launch thread (X) + docs site polish; submit to awesome-erc8004 list
- [ ] 10.3 Base Ecosystem Fund / Request for Builders application draft
- [ ] 10.4 Post-launch monitoring: indexer lag alert, API error-rate alert

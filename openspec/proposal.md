# OpenSpec Proposal: Provenalt — Phase 1 (MVP)

> Standalone product. New GitHub account, new repo, own local folder, own deploys.
> No references to any other project in code, docs, or positioning.

---

## 1. Why

- ERC-8004 registries on Base are live and growing fast (~73,800 agents registered; ~1,100 new registrations/day as of 2026-09-01), but the ecosystem only has raw rails: registries, SDKs, a subgraph, scaffolders. No product reads all of it and answers the question that matters: **"Can this agent be trusted?"**
- Coinbase Tokenized Stocks (B20 standard) went live on Base on 2026-08-24. Agents holding real equities raises the stakes of agent trust from academic to urgent. The official day-one ecosystem map has 11 categories (DEX, portfolio, wallets, curators, neobanks, oracle, aggregators, borrow/lend, fintech, trading venues) and **zero** trust/security tooling.
- x402 provides a proven machine-to-machine payment rail (205M+ transactions, $53M volume, 200k sellers). Trust checks can be sold per-query directly to agents.

## 2. What Provenalt Is

A trust layer for the agentic economy on Base:

1. **Indexes** the ERC-8004 Identity + Reputation registries.
2. **Validates** Agent Cards (off-chain JSON) and detects drift.
3. **Scores** agents (Provenalt Score, 0–100, with component breakdown + published methodology).
4. **Checks eligibility**: can wallet W hold/transfer B20 token T (native precompile calls — no external service dependency).
5. **Distributes** via REST API, x402 pay-per-call, MCP tool (`check_provenalt`), and a minimal public explorer.

Out of scope for Phase 1: Validation Registry module (contract pending on mainnet — schema must be validation-ready), multi-chain (Ethereum/Abstract share the same registry addresses; expansion is Phase 2), watchdog/alerting on stock-holding agents (Phase 2).

## 3. Verified On-Chain Facts (baked into this spec)

| Item | Value |
|---|---|
| Identity Registry (Base, Ethereum, Abstract — same address) | `0x8004A169FB4a3325136EB29fA0ceB6D2e539a432` |
| Reputation Registry (mainnet) | `0x8004BAa17C55a88189AE136b182e5fdA19dE9b63` |
| Validation Registry (mainnet) | pending — not deployed per official repo |
| `Registered(uint256,string,address)` topic0 | `0xca52e62c367d81bb2e328eb795f7c7ba24afb478408a26c0e201d155c449bc4a` |
| Identity Registry standard | ERC-721 + URIStorage (no Enumerable; `totalSupply()` reverts; agentIds sequential) |
| Other Identity events | `MetadataSet(uint256,string,string,bytes)` (reserved key: `agentWallet`), `URIUpdated(uint256,string,address)`, ERC-721 `Transfer` |
| Reputation events | `NewFeedback(uint256,address,uint64,int128,uint8,string,string,string,string,string,bytes32)`, `FeedbackRevoked(uint256,address,uint64)`, `ResponseAppended(uint256,address,uint64,address,string,bytes32)` |
| B20 stocks live (all decimals=8) | AAPLc `0xb200000000000000000000C2e324d24d7eEcd1fb`, NVDAc `0xb20000000000000000000078ee7ce2fE4908108C`, GOOGLc `0xb2000000000000000000002D0BA3164cc74f58B7`, METAc `0xb2000000000000000000008bC8786B856E61707C` |
| B20 mechanics | extends ERC-20; dividends/splits via on-chain multiplier (balances never change); transfer authorization via `isAuthorized` precompile; issuer eligibility/KYC/jurisdiction restrictions may apply |

Spec source: `https://github.com/erc-8004/erc-8004-contracts` + `https://eips.ethereum.org/EIPS/eip-8004`. Reference-only (do not depend on): agent0lab/subgraph.

## 4. Architecture

```
provenalt/                  (single repo, new GitHub account)
├── services/
│   ├── indexer/            Python worker — backfill + head-follow, writes Postgres
│   ├── api/                FastAPI — public REST + x402-gated endpoints
│   └── mcp/                MCP server exposing check_provenalt (thin client of api)
├── web/                    Next.js explorer (Vercel)
├── packages/
│   └── shared/             DB models, scoring lib, chain client, config
├── openspec/               this proposal + task tracking
└── CLAUDE.md               repo conventions, STOP protocol
```

- **Deploy**: Railway (indexer worker + api + Postgres), Vercel (web). Indexer and api are separate Railway services — different runtime profiles (long-running vs request/response), independent deploys.
- **RPC**: provider-agnostic chain client with rotation/fallback across ≥2 providers; adaptive `eth_getLogs` chunk sizing (public endpoints have block-range caps and per-IP rate limits — observed 429s on `mainnet.base.org` during bursts).
- **Reorg safety**: store `block_hash` per event row; only finalize rows deeper than N blocks (start N=64, config); on hash mismatch at follow head, rewind and re-index.
- **Idempotency**: natural keys `(tx_hash, log_index)` unique; all writes upsert.

## 5. Design Decisions

1. **Own indexer, not the community subgraph.** Full independence, custom schema (scoring needs rater-credibility joins the subgraph doesn't serve), and no third-party availability risk. The subgraph remains useful as a cross-check in tests.
2. **Agents are transferable NFTs.** ERC-721 `Transfer` on the Identity Registry means agent ownership can change hands. Ownership-transfer history is a first-class scoring signal (a high-score agent sold to a new owner should not keep its full score).
3. **Scoring is transparent.** Methodology doc published in the explorer. A trust product with a black-box score has a credibility problem on day one.
4. **Validation-ready schema.** `validations` table + score component exist from day one, empty until the Validation Registry ships (`validationRequest/validationResponse/getValidationStatus` per spec draft). When it goes live, Provenalt flips the module on — first-mover on the read side.
5. **Eligibility is native.** B20 `isAuthorized` precompile is called directly on-chain. Zero coupling to any external API.
6. **English for all repo artifacts** (code, docs, commits); product surface copy in English.

## 6. Provenalt Score v1 (heuristic, transparent)

Components (weights configurable, published):

| Component | Signal |
|---|---|
| Longevity | registration age; discount if ownership recently transferred |
| Card integrity | tokenURI resolves; JSON matches official Agent Card schema; `agentWallet` metadata consistent; drift/churn history |
| Reputation | feedback volume + values, **weighted by rater credibility** (rater must itself have history; per-rater influence capped; burst-of-feedback-from-fresh-addresses flagged as sybil pattern) |
| Revocations & responses | `FeedbackRevoked` and `ResponseAppended` patterns |
| Wallet behavior | agentWallet age, tx diversity, interaction with flagged contracts |
| Validation | reserved, weight 0 until registry ships |

Output: score 0–100 + per-component breakdown + confidence level (low-data agents get "insufficient data", not a fake precise number).

## 7. API Surface (v1)

```
GET /v1/agents                      search/list (paginated, filters)
GET /v1/agents/{agentId}            identity + card + metadata + owner history
GET /v1/agents/{agentId}/feedback   feedback timeline
GET /v1/agents/{agentId}/score      Provenalt Score + breakdown       [x402-gated tier]
GET /v1/provenalt/{agentId}         compact pass/warn/fail verdict     [x402-gated tier]
GET /v1/eligibility                 ?wallet=&token= → B20 isAuthorized [x402-gated tier]
GET /v1/stats                       registry growth, totals
```

Free tier: identity/browse endpoints, rate-limited. Paid tier: score/provenalt/eligibility via x402 (per-call, USDC on Base) with API-key bypass for partners.

## 8. Task Groups

### Group 1 — Foundation (repo, infra, conventions)
- [ ] 1.1 Create GitHub account + `provenalt` repo; init monorepo layout per §4; CLAUDE.md with repo conventions + STOP protocol
- [ ] 1.2 Provision Railway project (Postgres + 2 services) and Vercel project; wire env/secrets; document every env var in README
- [ ] 1.3 CI: lint + typecheck + tests on PR; no deploy on red
- [ ] 1.4 `packages/shared`: settings loader, structured logging, chain client with provider rotation + adaptive getLogs chunking (unit-test chunk shrink/grow on simulated cap errors)

### Group 2 — Identity indexing
- [ ] 2.1 DB schema: `agents`, `agent_metadata`, `agent_owner_history`, `raw_logs` (tx_hash+log_index unique, block_hash column); migration tooling
- [ ] 2.2 Discover Identity Registry deployment block on Base (binary search on `eth_getCode`); persist as backfill anchor
- [ ] 2.3 Backfill worker: `Registered`, `MetadataSet`, `URIUpdated`, `Transfer` from anchor → head; resumable via cursor; idempotent upserts
- [ ] 2.4 Head-follow loop with reorg detection (block-hash check, rewind ≤ N)
- [ ] 2.5 Verification harness: sequential agentId continuity check + spot-check 20 random agents against a public explorer/subgraph

### Group 3 — Reputation indexing
- [ ] 3.1 Compute + pin topic0 hashes for all Reputation events from the official spec text (script in repo, not hardcoded by hand)
- [ ] 3.2 Schema: `feedback`, `feedback_revocations`, `feedback_responses` (+ decoded value/valueDecimals as numeric)
- [ ] 3.3 Backfill + follow for Reputation Registry (reuse Group 2 worker framework)
- [ ] 3.4 Rater-credibility materialized view (per-rater history, first-seen, feedback count, self-feedback detection)

### Group 4 — Agent Card pipeline
- [ ] 4.1 Fetch tokenURI content (ipfs:// via ≥2 gateways with fallback, https:// direct); store content + content hash + fetch status
- [ ] 4.2 Validate against official Agent Card JSON schema (vendored copy, versioned); record validity + errors
- [ ] 4.3 Refresh queue: re-fetch on `URIUpdated` + periodic sweep; drift log when content hash changes without URI change
- [ ] 4.4 Consistency checks: `agentWallet` metadata vs card contents

### Group 5 — Scoring engine v1
- [ ] 5.1 Implement components per §6 as pure functions over DB state; weights in config
- [ ] 5.2 Sybil heuristics: fresh-rater burst detection, per-rater influence cap, self/circular feedback flags
- [ ] 5.3 Score persistence + recompute triggers (event-driven for affected agents, nightly full sweep)
- [ ] 5.4 METHODOLOGY.md — public, human-readable, versioned with the weights
- [ ] 5.5 Golden tests: fixture agents (fresh, established, sybil-boosted, transferred-ownership) with expected score bands

### Group 6 — Public API
- [ ] 6.1 FastAPI service with endpoints per §7 (free tier), pagination, filters; OpenAPI docs published
- [ ] 6.2 Rate limiting (per-IP for free tier) + API keys table
- [ ] 6.3 Deploy to Railway; smoke tests against production DB

### Group 7 — Eligibility module (B20, native)
- [ ] 7.1 Chain-level `isAuthorized` precompile client (research exact call ABI from official B20 technical docs at base.org/stocks; document findings in repo)
- [ ] 7.2 `/v1/eligibility?wallet=&token=` for the 4 live stock contracts (registry of known B20 tokens in DB, extensible as more stocks land)
- [ ] 7.3 Multiplier-aware balance reader (dividends/splits multiplier — report both raw and adjusted balance)

### Group 8 — Explorer (web MVP)
- [ ] 8.1 Next.js app: home (registry stats + growth chart), search, agent profile page (card, score breakdown, feedback timeline, owner history)
- [ ] 8.2 Methodology page (renders METHODOLOGY.md); About page
- [ ] 8.3 Deploy to Vercel, custom domain, OG images for agent pages (shareable on X)

### Group 9 — Monetized distribution
- [ ] 9.1 x402 integration on gated endpoints (USDC on Base, per-call pricing; start $0.01/call) — follow docs.cdp.coinbase.com x402 seller flow
- [ ] 9.2 MCP server exposing `check_provenalt(agentId)` and `check_eligibility(wallet, token)`; installable via npx; README quickstart
- [ ] 9.3 Usage metering + simple revenue dashboard (internal)

### Group 10 — Launch
- [ ] 10.1 Seed content: index fully caught up; top-agents page accurate
- [ ] 10.2 Launch thread (X) + docs site polish; submit to awesome-erc8004 list
- [ ] 10.3 Base Ecosystem Fund / Request for Builders application draft
- [ ] 10.4 Post-launch monitoring: indexer lag alert, API error-rate alert

## 9. Open Questions (decide before Group 1)

1. Final brand handle/domain (check X handle + domain availability for "provenalt" variants).
2. Which GitHub account: fresh account vs an existing idle one.
3. Score naming surface: "Provenalt Score" everywhere, or "PScore" shorthand in API payloads.
4. x402 pricing after launch data (start $0.01/call, revisit).

## 10. Definition of Done (Phase 1)

- Indexer fully caught up on Base with <2 min head lag, surviving restarts and reorgs.
- Every registered agent has a card-fetch status and a score (or explicit "insufficient data").
- Explorer public, API documented, at least one x402-paid call and one MCP call succeed end-to-end in production.
- METHODOLOGY.md published and linked from every score.

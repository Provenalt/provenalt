# Provenalt Score — Methodology (v1)

**Weights version: `1`**

The Provenalt Score is a transparent, heuristic trust score (0–100) for ERC-8004 agents on
Base. It is computed from on-chain and off-chain data that Provenalt indexes itself; there is
no black box and no third-party dependency. This document is versioned together with the
weights (see `packages/shared/provenalt_shared/scoring/weights.py`, `WEIGHTS_VERSION`). When
any weight or parameter changes, the version is bumped and every persisted score records the
version it was produced under.

Low-data agents receive an explicit **confidence** of `insufficient_data` rather than a
falsely precise number.

## How the score is assembled

Each component produces a normalized value in `[0, 1]`. The final score is the weighted
average of the **available** components (a component with no data is excluded and its weight
is redistributed proportionally), multiplied by 100 and rounded.

| Component | Weight | Signal |
|---|---|---|
| Longevity | 0.20 | Registration age (saturating), discounted if ownership was transferred recently. |
| Card integrity | 0.20 | tokenURI resolves, schema-valid, `registrations[]` binds to the agent, agentWallet consistency, drift penalty. |
| Reputation | 0.35 | Credible, non-self, non-revoked feedback, weighted by rater credibility and capped per rater; sybil bursts discounted. |
| Revocations & responses | 0.10 | Revocation rate (negative) and response rate (positive) over the agent's feedback. |
| Wallet behavior | 0.15 | agentWallet presence + age. **v1 limitation:** tx diversity and flagged-contract interaction are not yet indexed. |
| Validation | 0.00 | Reserved — weight 0 until the Validation Registry ships. |

### Longevity
`age = as_of_block − registered_block`; `base = age / (age + 90 days)`. If a real ownership
transfer (excluding the initial mint) occurred within the last **30 days**, the component is
multiplied by **0.5** — a high-scoring agent sold to a new owner should not keep its full
score (proposal §5, decision 2).

### Card integrity
Sub-weighted combination of: tokenURI fetch OK (0.25), schema valid (0.25),
**`registration_match` (0.45)**, and **wallet consistency (0.05)**, minus a drift penalty
(0.1 per drift event, capped at 0.5).

The `registrations[]` binding is authoritative, so it is weighted heavily. The
agentWallet-vs-card check is **heuristic** (the ERC-8004 card has no mandated wallet field),
so it is weighted lightly, and its ambiguous outcomes (`not_declared`, `wallet_not_set`) are
treated as **neutral** — only a clear `mismatch` applies a (small) penalty. This prevents the
weak signal from producing false negatives.

### Reputation & sybil resistance
- **Self-feedback is excluded**, judged by the owner **at the feedback's block height** (from
  `agent_owner_history`), not the current owner — so selling an agent cannot retroactively
  turn past self-ratings into "external" ones, and vice versa.
- **Revoked feedback is excluded** from the positive signal.
- **Rater credibility** scales with the rater's own history: `credibility =
  clamp((feedback_block − rater_first_seen) / 30 days, 0.1, 1.0)`. A rater with no prior
  history contributes at the 0.1 floor.
- **Per-rater influence cap:** each rater contributes at most **3** feedback entries.
- **Fresh-rater burst detection:** feedback from addresses first seen at the feedback block
  with ≤2 total feedback are "fresh". If fresh raters are ≥3 and ≥50% of the counted feedback,
  the whole reputation component is additionally discounted to **0.3×** and the burst is
  flagged in the breakdown.
- **Circular feedback:** feedback from an address whose agents this agent's owner has itself
  rated (reciprocal rating) is discounted to **0.2×**.
- Feedback values are read as `value / 10^valueDecimals` and clamped to `[-1, 1]` as polarity.
- The credible weighted-positive total `p` is mapped by `p / (p + 5)` into `[0, 1]`.

### Revocations & responses
`clamp(0.5 + 0.5·response_rate − 0.5·revocation_rate, 0, 1)`.

### Wallet behavior
If agentWallet is set: `0.5 + 0.5·(age / (age + 30 days))`. If not set, the component is
excluded. Full wallet-behavior analysis (transaction diversity, interaction with flagged
contracts) is deferred to a later phase.

## Confidence

Confidence is derived from the count of credible (non-self, non-revoked) feedback and whether
a card was successfully fetched:

| Confidence | Condition |
|---|---|
| `insufficient_data` | No credible feedback **and** no successfully fetched card. |
| `low` | Fewer than 3 credible feedback. |
| `medium` | 3–9 credible feedback. |
| `high` | 10+ credible feedback. |

## Notes

- Block-based durations assume Base's ~2s block time (~43,200 blocks/day).
- This methodology is intentionally simple and legible for v1. It will evolve with data; each
  change ships with a new `WEIGHTS_VERSION` and an update to this document.

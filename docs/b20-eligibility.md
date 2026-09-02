# B20 Eligibility — On-chain ABI Research (Group 7)

Findings researched from the **official Base B20 documentation** (do not guess — task 7.1).
This is the authoritative reference for the eligibility module (`services/api`).

## Sources

- Tokenized Stocks on Base — https://docs.base.org/base-chain/specs/reference/b20/tokenized-stocks-on-base
- B20 native token standard (Beryl) — https://docs.base.org/base-chain/specs/upgrades/beryl/b20
- B20 IB20 interface — https://docs.base.org/base-chain/specs/reference/b20/interfaces/IB20/policyId
- B20 Constants & Addresses — https://docs.base.org/specifications/b20/reference/constants-addresses

## How authorization works

B20 tokens (including the tokenized stocks) are **native precompiles** — no per-asset
bytecode on Basescan, but they respond to `eth_call`. Transfers are gated by **policies**: a
token stores one `uint64 policyId` per **policy scope**, and gated operations call the
singleton **PolicyRegistry** precompile's `isAuthorized(policyId, account)`, reverting with
`PolicyForbids` if denied. There is **no** token-level `canSend`/`canReceive` helper — a
read-only eligibility check must do it in two steps.

## Precompile / addresses

| Item | Value |
|---|---|
| PolicyRegistry precompile | `0x8453000000000000000000000000000000000002` |
| Built-in policy id `ALWAYS_ALLOW` | `0` |
| Built-in policy id `ALWAYS_BLOCK` | `0x0100000000000001` |

A scope left at its default resolves to `ALWAYS_ALLOW` (`policyId == 0`), and
`isAuthorized(0, account)` returns `true`. Calling `isAuthorized` with whatever id the token
returns therefore yields the correct answer regardless of whether a policy is set.

## Exact ABI (verbatim signatures)

PolicyRegistry precompile:

```solidity
function isAuthorized(uint64 policyId, address account) external view returns (bool)
```

B20 token (policy scopes + asset variant):

```solidity
function policyId(bytes32 policyScope) external view returns (uint64)
function balanceOf(address account) external view returns (uint256)
function decimals() external view returns (uint8)
function multiplier() external view returns (uint256)          // WAD, 1e18
function scaledBalanceOf(address account) external view returns (uint256)
function toScaledBalance(uint256 raw) external view returns (uint256)
function toRawBalance(uint256 scaled) external view returns (uint256)
```

## Policy scope constants

Scopes are `bytes32` = `keccak256("<SCOPE_NAME>")` (per the Constants & Addresses page).
Computed values (verified in `tests/test_b20_client.py`):

| Scope | Gates | `keccak256(name)` |
|---|---|---|
| `TRANSFER_SENDER_POLICY` | the `from` of transfer/transferFrom (can **send**) | `0xb81736c875ab819dd97f59f2a6542cfb731ad52b4ae15a6f24df2fb02b0327f5` |
| `TRANSFER_RECEIVER_POLICY` | the `to` of transfer/transferFrom (can **hold/receive**) | `0x8a4b3fa2d8b921852bc0089c6ef0958aa6961897be36fd731330fe2cd23f8363` |
| `TRANSFER_EXECUTOR_POLICY` | `msg.sender` of `transferFrom` | `0x10be5173aff2a44e748bd9acd8b19fe34689581398a9db7ba2fb671e786ff7d8` |
| `MINT_RECEIVER_POLICY` | the `to` of `mint` (issuer/AP flow) | `0xa0d5ae037e66a09119acf080a1d807abb9b6d03b6b9130eb19f7c1e6bdb8ffc8` |

## Computed function selectors

| Function | Selector |
|---|---|
| `policyId(bytes32)` | `0xdb3de624` |
| `isAuthorized(uint64,address)` | `0x55a1179e` |
| `balanceOf(address)` | `0x70a08231` |
| `decimals()` | `0x313ce567` |
| `multiplier()` | `0x1b3ed722` |
| `scaledBalanceOf(address)` | `0x1da24f3e` |

## Eligibility flow (what the module does)

For `token T`, `wallet W`:

1. **Can hold / receive** = `PolicyRegistry.isAuthorized(T.policyId(TRANSFER_RECEIVER_POLICY), W)`.
2. **Can send / transfer out** = `PolicyRegistry.isAuthorized(T.policyId(TRANSFER_SENDER_POLICY), W)`.

Both are `eth_call` reads; selectors and scope hashes are **computed** at runtime from the
signatures (never hand-transcribed).

## Multiplier-aware balances (task 7.3)

- **Raw balance** (token units, `decimals = 8` for the live stocks) = `T.balanceOf(W)`.
- **Adjusted balance** (redeemable shares) = `T.scaledBalanceOf(W)`; equivalently
  `raw * multiplier / 1e18`. One token does **not** permanently equal one share — always apply
  the current `multiplier()` (WAD).

## Live confirmation

Verified against Base mainnet (`test_b20_integration.py`, marked `integration`). For AAPLc
(`0xb200…d1fb`) all reads decode cleanly: `policyId(TRANSFER_RECEIVER_POLICY)` and
`policyId(TRANSFER_SENDER_POLICY)` both return policy id `5`, `isAuthorized(5, wallet)`
returns a bool, and `multiplier()` returns `1e18` (WAD, currently 1:1). This confirms the
computed selectors, scope hashes, and PolicyRegistry address are correct on-chain.

## Notes

- The hold↔receiver / send↔sender scope mapping follows the documented gating of a transfer's
  `to`/`from` — the natural, spec-supported reading, now confirmed by a live decode.
- B20 precompiles have no bytecode, so `eth_getCode` is empty — irrelevant here (we only
  `eth_call`; we do not index B20).

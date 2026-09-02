"""B20 tokenized-stock eligibility + multiplier-aware balances via native precompiles.

All selectors and policy-scope hashes are COMPUTED from the official signatures/names at
import time (never hand-transcribed). See ``docs/b20-eligibility.md`` for the researched ABI
and sources. Every read is a plain ``eth_call`` — B20 stocks are precompiles with no bytecode.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Protocol

from eth_abi import decode as abi_decode
from eth_abi import encode as abi_encode
from eth_utils import function_signature_to_4byte_selector, keccak

# PolicyRegistry singleton precompile (official B20 Constants & Addresses).
POLICY_REGISTRY = "0x8453000000000000000000000000000000000002"
WAD = 10**18

# Policy scopes are bytes32 = keccak256("<NAME>").
SCOPE_TRANSFER_SENDER = keccak(text="TRANSFER_SENDER_POLICY")  # gates the `from` (can send)
SCOPE_TRANSFER_RECEIVER = keccak(text="TRANSFER_RECEIVER_POLICY")  # gates the `to` (can hold)

_SEL_POLICY_ID = function_signature_to_4byte_selector("policyId(bytes32)")
_SEL_IS_AUTHORIZED = function_signature_to_4byte_selector("isAuthorized(uint64,address)")
_SEL_BALANCE_OF = function_signature_to_4byte_selector("balanceOf(address)")
_SEL_MULTIPLIER = function_signature_to_4byte_selector("multiplier()")
_SEL_SCALED_BALANCE_OF = function_signature_to_4byte_selector("scaledBalanceOf(address)")


class SupportsCall(Protocol):
    def call(self, method: str, params: list[object]) -> str: ...


@dataclass(frozen=True)
class Eligibility:
    token: str
    wallet: str
    can_hold: bool  # authorized as transfer receiver
    can_send: bool  # authorized as transfer sender
    receiver_policy_id: int
    sender_policy_id: int
    raw_balance: int  # token units (decimals = 8 for live stocks)
    adjusted_balance: int  # multiplier-applied (redeemable shares)
    multiplier: int  # WAD (1e18)

    @property
    def eligible(self) -> bool:
        """Can both acquire/hold and transfer the token."""
        return self.can_hold and self.can_send


class B20Client:
    """Reads B20 policy authorization and balances via ``eth_call``."""

    def __init__(self, chain: SupportsCall, policy_registry: str = POLICY_REGISTRY) -> None:
        self._chain = chain
        self._registry = policy_registry

    # ── low-level calls ──────────────────────────────────────────────────────

    def _eth_call(self, to: str, data: bytes) -> bytes:
        result: str = self._chain.call(
            "eth_call", [{"to": to, "data": "0x" + data.hex()}, "latest"]
        )
        return bytes.fromhex(result[2:] if result.startswith("0x") else result)

    def policy_id(self, token: str, scope: bytes) -> int:
        raw = self._eth_call(token, _SEL_POLICY_ID + abi_encode(["bytes32"], [scope]))
        (value,) = abi_decode(["uint64"], raw)
        return int(value)

    def is_authorized(self, policy_id: int, account: str) -> bool:
        raw = self._eth_call(
            self._registry,
            _SEL_IS_AUTHORIZED + abi_encode(["uint64", "address"], [policy_id, account]),
        )
        (value,) = abi_decode(["bool"], raw)
        return bool(value)

    def balance_of(self, token: str, account: str) -> int:
        raw = self._eth_call(token, _SEL_BALANCE_OF + abi_encode(["address"], [account]))
        (value,) = abi_decode(["uint256"], raw)
        return int(value)

    def scaled_balance_of(self, token: str, account: str) -> int:
        raw = self._eth_call(token, _SEL_SCALED_BALANCE_OF + abi_encode(["address"], [account]))
        (value,) = abi_decode(["uint256"], raw)
        return int(value)

    def multiplier(self, token: str) -> int:
        (value,) = abi_decode(["uint256"], self._eth_call(token, _SEL_MULTIPLIER))
        return int(value)

    # ── high-level ───────────────────────────────────────────────────────────

    def eligibility(self, token: str, wallet: str) -> Eligibility:
        receiver_policy = self.policy_id(token, SCOPE_TRANSFER_RECEIVER)
        sender_policy = self.policy_id(token, SCOPE_TRANSFER_SENDER)
        return Eligibility(
            token=token,
            wallet=wallet,
            can_hold=self.is_authorized(receiver_policy, wallet),
            can_send=self.is_authorized(sender_policy, wallet),
            receiver_policy_id=receiver_policy,
            sender_policy_id=sender_policy,
            raw_balance=self.balance_of(token, wallet),
            adjusted_balance=self.scaled_balance_of(token, wallet),
            multiplier=self.multiplier(token),
        )

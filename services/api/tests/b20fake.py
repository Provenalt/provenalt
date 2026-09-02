"""A fake chain that answers B20 eth_call reads (not a test module)."""

from __future__ import annotations

from typing import Any

from eth_abi import decode as abi_decode
from eth_abi import encode as abi_encode

from provenalt_api import b20


class FakeB20Chain:
    def __init__(
        self,
        *,
        receiver_policy: int,
        sender_policy: int,
        authorized: dict[int, bool],
        balance: int,
        scaled: int,
        multiplier: int,
    ) -> None:
        self.receiver_policy = receiver_policy
        self.sender_policy = sender_policy
        self.authorized = authorized
        self.balance = balance
        self.scaled = scaled
        self._multiplier = multiplier

    def call(self, method: str, params: list[Any]) -> str:
        assert method == "eth_call"
        to = params[0]["to"].lower()
        data = bytes.fromhex(params[0]["data"][2:])
        selector, args = data[:4], data[4:]

        if selector == b20._SEL_POLICY_ID:
            (scope,) = abi_decode(["bytes32"], args)
            if scope == b20.SCOPE_TRANSFER_RECEIVER:
                pid = self.receiver_policy
            elif scope == b20.SCOPE_TRANSFER_SENDER:
                pid = self.sender_policy
            else:
                pid = 0
            return "0x" + abi_encode(["uint64"], [pid]).hex()

        if to == b20.POLICY_REGISTRY.lower() and selector == b20._SEL_IS_AUTHORIZED:
            pid, _account = abi_decode(["uint64", "address"], args)
            return "0x" + abi_encode(["bool"], [self.authorized.get(int(pid), False)]).hex()

        if selector == b20._SEL_BALANCE_OF:
            return "0x" + abi_encode(["uint256"], [self.balance]).hex()
        if selector == b20._SEL_SCALED_BALANCE_OF:
            return "0x" + abi_encode(["uint256"], [self.scaled]).hex()
        if selector == b20._SEL_MULTIPLIER:
            return "0x" + abi_encode(["uint256"], [self._multiplier]).hex()

        raise AssertionError(f"unexpected eth_call selector {selector.hex()}")

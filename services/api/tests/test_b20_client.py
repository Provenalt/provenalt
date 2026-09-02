"""Unit tests for the B20 eligibility client (selectors/scope hashes + eth_call decoding)."""

from __future__ import annotations

from b20fake import FakeB20Chain

from provenalt_api import b20

WAD = 10**18
TOKEN = "0xb200000000000000000000c2e324d24d7eecd1fb"  # AAPLc
WALLET = "0x00000000000000000000000000000000000000aa"


def test_scope_hashes_match_official_keccak_values() -> None:
    # keccak256("<NAME>") per the Base B20 Constants & Addresses page (docs/b20-eligibility.md).
    assert (
        "0x" + b20.SCOPE_TRANSFER_SENDER.hex()
        == "0xb81736c875ab819dd97f59f2a6542cfb731ad52b4ae15a6f24df2fb02b0327f5"
    )
    assert (
        "0x" + b20.SCOPE_TRANSFER_RECEIVER.hex()
        == "0x8a4b3fa2d8b921852bc0089c6ef0958aa6961897be36fd731330fe2cd23f8363"
    )


def test_function_selectors_match() -> None:
    assert "0x" + b20._SEL_POLICY_ID.hex() == "0xdb3de624"
    assert "0x" + b20._SEL_IS_AUTHORIZED.hex() == "0x55a1179e"
    assert "0x" + b20._SEL_BALANCE_OF.hex() == "0x70a08231"
    assert "0x" + b20._SEL_MULTIPLIER.hex() == "0x1b3ed722"
    assert "0x" + b20._SEL_SCALED_BALANCE_OF.hex() == "0x1da24f3e"


def test_policy_registry_address() -> None:
    assert b20.POLICY_REGISTRY == "0x8453000000000000000000000000000000000002"


def test_eligibility_hold_yes_send_no() -> None:
    chain = FakeB20Chain(
        receiver_policy=5,
        sender_policy=7,
        authorized={5: True, 7: False},  # can receive/hold, cannot send
        balance=1_000,
        scaled=2_000,
        multiplier=2 * WAD,
    )
    result = b20.B20Client(chain).eligibility(TOKEN, WALLET)

    assert result.can_hold is True
    assert result.can_send is False
    assert result.eligible is False  # needs both
    assert result.receiver_policy_id == 5
    assert result.sender_policy_id == 7
    assert result.raw_balance == 1_000
    assert result.adjusted_balance == 2_000
    assert result.multiplier == 2 * WAD


def test_eligibility_fully_eligible() -> None:
    chain = FakeB20Chain(
        receiver_policy=0,  # ALWAYS_ALLOW
        sender_policy=0,
        authorized={0: True},
        balance=42,
        scaled=42,
        multiplier=WAD,
    )
    result = b20.B20Client(chain).eligibility(TOKEN, WALLET)
    assert result.can_hold is True
    assert result.can_send is True
    assert result.eligible is True


def test_low_level_calls_decode_correctly() -> None:
    chain = FakeB20Chain(
        receiver_policy=9,
        sender_policy=3,
        authorized={9: True},
        balance=5,
        scaled=10,
        multiplier=WAD,
    )
    client = b20.B20Client(chain)
    assert client.policy_id(TOKEN, b20.SCOPE_TRANSFER_RECEIVER) == 9
    assert client.is_authorized(9, WALLET) is True
    assert client.is_authorized(3, WALLET) is False
    assert client.balance_of(TOKEN, WALLET) == 5
    assert client.scaled_balance_of(TOKEN, WALLET) == 10
    assert client.multiplier(TOKEN) == WAD

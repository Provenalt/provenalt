"""Startup guard: refuse to start when x402 is enabled on a mainnet network but pointed at
the public x402.org facilitator (which only supports testnets). Base mainnet settlement
requires the Coinbase CDP facilitator. (Group 9 housekeeping.)"""

from __future__ import annotations

import pytest

from provenalt_api.x402_gate import is_public_x402_facilitator, validate_x402_settings

PUBLIC = "https://x402.org/facilitator"
CDP = "https://api.cdp.coinbase.com/platform/v2/x402"


def test_is_public_x402_facilitator() -> None:
    assert is_public_x402_facilitator(PUBLIC) is True
    assert is_public_x402_facilitator("https://www.x402.org/facilitator") is True
    assert is_public_x402_facilitator(CDP) is False
    assert is_public_x402_facilitator("https://facilitator.internal/x402") is False


def test_refuses_mainnet_plus_public_facilitator() -> None:
    with pytest.raises(RuntimeError) as exc:
        validate_x402_settings(enabled=True, network="eip155:8453", facilitator_url=PUBLIC)
    msg = str(exc.value)
    assert "CDP facilitator" in msg
    assert "mainnet" in msg.lower()


def test_allows_mainnet_with_cdp_facilitator() -> None:
    # No raise: mainnet is fine once a non-public (CDP) facilitator is configured.
    validate_x402_settings(enabled=True, network="eip155:8453", facilitator_url=CDP)


def test_allows_testnet_with_public_facilitator() -> None:
    # No raise: the public facilitator supports testnets (Base Sepolia).
    validate_x402_settings(enabled=True, network="eip155:84532", facilitator_url=PUBLIC)


def test_no_guard_when_disabled() -> None:
    # No raise when x402 is off, regardless of network/facilitator.
    validate_x402_settings(enabled=False, network="eip155:8453", facilitator_url=PUBLIC)

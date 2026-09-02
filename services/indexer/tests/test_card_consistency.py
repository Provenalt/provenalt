"""Unit tests for agent-card consistency checks (proposal §4.4)."""

from __future__ import annotations

from provenalt_indexer import events
from provenalt_indexer.cards.consistency import check_consistency

REGISTRY = events.IDENTITY_REGISTRY_ADDRESS
WALLET = "0x00000000000000000000000000000000000000aa"
OTHER = "0x00000000000000000000000000000000000000bb"


def _card(registrations: list[dict], services: list[dict] | None = None) -> dict:
    return {
        "type": "https://eips.ethereum.org/EIPS/eip-8004#registration-v1",
        "registrations": registrations,
        "services": services or [],
    }


def test_registration_match_true_when_agent_and_registry_match() -> None:
    card = _card([{"agentId": 22, "agentRegistry": f"eip155:8453:{REGISTRY}"}])
    result = check_consistency(card, agent_id=22, agent_wallet=None)
    assert result.registration_match is True


def test_registration_match_false_on_wrong_agent_id() -> None:
    card = _card([{"agentId": 99, "agentRegistry": f"eip155:8453:{REGISTRY}"}])
    assert check_consistency(card, agent_id=22, agent_wallet=None).registration_match is False


def test_registration_match_false_on_wrong_registry() -> None:
    card = _card([{"agentId": 22, "agentRegistry": "eip155:8453:0xdeadbeef"}])
    assert check_consistency(card, agent_id=22, agent_wallet=None).registration_match is False


def test_registration_match_is_case_insensitive_on_address() -> None:
    card = _card([{"agentId": 22, "agentRegistry": f"eip155:8453:{REGISTRY.upper()}"}])
    assert check_consistency(card, agent_id=22, agent_wallet=None).registration_match is True


def test_wallet_not_set() -> None:
    card = _card([{"agentId": 22, "agentRegistry": f"eip155:8453:{REGISTRY}"}])
    assert check_consistency(card, agent_id=22, agent_wallet=None).wallet_status == "wallet_not_set"


def test_wallet_not_declared_when_card_has_no_wallet_addresses() -> None:
    # Only the registry contract address appears (in registrations), which is not a wallet.
    card = _card([{"agentId": 22, "agentRegistry": f"eip155:8453:{REGISTRY}"}])
    assert check_consistency(card, agent_id=22, agent_wallet=WALLET).wallet_status == "not_declared"


def test_wallet_match_when_card_declares_the_wallet() -> None:
    card = _card(
        [{"agentId": 22, "agentRegistry": f"eip155:8453:{REGISTRY}"}],
        services=[{"name": "wallet", "endpoint": f"eip155:8453:{WALLET}"}],
    )
    assert check_consistency(card, agent_id=22, agent_wallet=WALLET).wallet_status == "match"


def test_wallet_mismatch_when_card_declares_a_different_wallet() -> None:
    card = _card(
        [{"agentId": 22, "agentRegistry": f"eip155:8453:{REGISTRY}"}],
        services=[{"name": "wallet", "endpoint": f"eip155:8453:{OTHER}"}],
    )
    assert check_consistency(card, agent_id=22, agent_wallet=WALLET).wallet_status == "mismatch"

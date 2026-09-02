"""Unit tests for agent-card schema validation (proposal §4.2)."""

from __future__ import annotations

import json

from provenalt_indexer.cards.schema import (
    SCHEMA_VERSION,
    load_registration_schema,
    validate_card,
)

REGISTRY = "eip155:8453:0x8004A169FB4a3325136EB29fA0ceB6D2e539a432"

VALID_CARD = {
    "type": "https://eips.ethereum.org/EIPS/eip-8004#registration-v1",
    "name": "myAgent",
    "description": "does things",
    "image": "https://example.com/i.png",
    "services": [{"name": "A2A", "endpoint": "https://agent.example/card.json"}],
    "x402Support": False,
    "active": True,
    "registrations": [{"agentId": 22, "agentRegistry": REGISTRY}],
    "supportedTrust": ["reputation"],
}


def test_schema_loads_and_is_versioned() -> None:
    schema = load_registration_schema()
    assert schema["$id"].endswith("registration-v1.schema.json")
    assert SCHEMA_VERSION == 1


def test_valid_card_passes() -> None:
    result = validate_card(VALID_CARD)
    assert result.valid
    assert result.errors == []


def test_extra_fields_are_allowed() -> None:
    card = {**VALID_CARD, "somethingCustom": {"nested": True}}
    assert validate_card(card).valid


def test_missing_type_fails() -> None:
    card = {k: v for k, v in VALID_CARD.items() if k != "type"}
    result = validate_card(card)
    assert not result.valid
    assert any("type" in e for e in result.errors)


def test_wrong_type_const_fails() -> None:
    card = {**VALID_CARD, "type": "https://example.com/not-erc8004"}
    assert not validate_card(card).valid


def test_missing_registrations_fails() -> None:
    card = {k: v for k, v in VALID_CARD.items() if k != "registrations"}
    result = validate_card(card)
    assert not result.valid
    assert any("registrations" in e for e in result.errors)


def test_registration_entry_missing_agent_id_fails() -> None:
    card = {**VALID_CARD, "registrations": [{"agentRegistry": REGISTRY}]}
    assert not validate_card(card).valid


def test_empty_registrations_fails() -> None:
    card = {**VALID_CARD, "registrations": []}
    assert not validate_card(card).valid


def test_invalid_json_string_reports_error() -> None:
    result = validate_card("{not valid json")
    assert not result.valid
    assert any("json" in e.lower() for e in result.errors)


def test_accepts_json_string_input() -> None:
    assert validate_card(json.dumps(VALID_CARD)).valid

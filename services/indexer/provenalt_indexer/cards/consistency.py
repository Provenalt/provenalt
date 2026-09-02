"""Consistency checks between a card and on-chain state (proposal §4.4).

Two checks:

* **registration_match** — the card's ``registrations[]`` binds back to this agent: an entry
  whose ``agentId`` equals the on-chain agentId and whose ``agentRegistry`` address equals the
  Identity Registry (the canonical ERC-8004 "the registration file corresponds to the on-chain
  agent" check).
* **wallet_status** — the on-chain ``agentWallet`` metadata compared against wallet addresses
  the card declares. The ERC-8004 card has no mandated wallet field (wallets are advertised
  loosely via endpoints/services), so this scans for declared addresses, excluding registry
  contract addresses. Result: ``match`` | ``mismatch`` | ``not_declared`` | ``wallet_not_set``.
"""

from __future__ import annotations

import re
from dataclasses import dataclass
from typing import Any

from provenalt_indexer.events import IDENTITY_REGISTRY_ADDRESS

_ADDRESS_RE = re.compile(r"0x[0-9a-fA-F]{40}")


@dataclass(frozen=True)
class ConsistencyResult:
    registration_match: bool
    wallet_status: str


def _registry_address_of(agent_registry: str) -> str:
    """Extract the contract address from a CAIP-style ``namespace:chainId:address``."""
    return agent_registry.rsplit(":", 1)[-1].lower()


def check_registration_match(card: dict[str, Any], agent_id: int, registry_address: str) -> bool:
    registry = registry_address.lower()
    for entry in card.get("registrations", []) or []:
        if not isinstance(entry, dict):
            continue
        if (
            entry.get("agentId") == agent_id
            and _registry_address_of(str(entry.get("agentRegistry", ""))) == registry
        ):
            return True
    return False


def _iter_strings(value: Any) -> list[str]:
    if isinstance(value, str):
        return [value]
    if isinstance(value, dict):
        return [s for v in value.values() for s in _iter_strings(v)]
    if isinstance(value, list):
        return [s for v in value for s in _iter_strings(v)]
    return []


def declared_wallet_addresses(card: dict[str, Any], registry_address: str) -> set[str]:
    """All 0x addresses found in the card, excluding registry contract addresses."""
    found: set[str] = set()
    for text in _iter_strings(card):
        for match in _ADDRESS_RE.findall(text):
            found.add(match.lower())

    excluded = {registry_address.lower()}
    for entry in card.get("registrations", []) or []:
        if isinstance(entry, dict):
            excluded.add(_registry_address_of(str(entry.get("agentRegistry", ""))))
    return found - excluded


def check_wallet_status(
    card: dict[str, Any], agent_wallet: str | None, registry_address: str
) -> str:
    if agent_wallet is None:
        return "wallet_not_set"
    declared = declared_wallet_addresses(card, registry_address)
    if not declared:
        return "not_declared"
    return "match" if agent_wallet.lower() in declared else "mismatch"


def check_consistency(
    card: dict[str, Any],
    *,
    agent_id: int,
    agent_wallet: str | None,
    registry_address: str = IDENTITY_REGISTRY_ADDRESS,
) -> ConsistencyResult:
    return ConsistencyResult(
        registration_match=check_registration_match(card, agent_id, registry_address),
        wallet_status=check_wallet_status(card, agent_wallet, registry_address),
    )

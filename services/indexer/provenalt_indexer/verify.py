"""Verification harness for the identity index (proposal §2.5).

Two independent checks:

* **Continuity** — ERC-8004 agentIds are sequential, so the indexed set must be exactly
  ``1..max`` with no gaps. A gap means a missed ``Registered`` event.
* **Spot check** — sample agents and compare the indexed ``owner``/``agent_uri`` against the
  authoritative on-chain values (``ownerOf`` / ``tokenURI`` via ``eth_call``). Reading the
  contract directly is stronger than a subgraph and keeps zero third-party dependency
  (design decision §5.1); the subgraph remains available only as an optional cross-check.
"""

from __future__ import annotations

import random
from dataclasses import dataclass
from typing import Protocol

from eth_abi import decode as abi_decode
from eth_abi import encode as abi_encode
from eth_utils import function_signature_to_4byte_selector
from provenalt_shared.db import Agent
from provenalt_shared.db import repository as repo
from sqlalchemy.orm import Session

# ── continuity ───────────────────────────────────────────────────────────────


@dataclass(frozen=True)
class ContinuityReport:
    max_agent_id: int | None
    missing_ids: list[int]

    @property
    def ok(self) -> bool:
        return not self.missing_ids


def check_continuity(session: Session) -> ContinuityReport:
    return ContinuityReport(
        max_agent_id=repo.max_agent_id(session),
        missing_ids=repo.missing_agent_ids(session),
    )


# ── spot check ───────────────────────────────────────────────────────────────


class AgentReader(Protocol):
    def owner_of(self, agent_id: int) -> str: ...
    def token_uri(self, agent_id: int) -> str: ...


@dataclass(frozen=True)
class SpotCheckResult:
    agent_id: int
    field: str
    db_value: str
    chain_value: str
    ok: bool


@dataclass(frozen=True)
class SpotCheckReport:
    results: list[SpotCheckResult]
    checked: int

    @property
    def ok(self) -> bool:
        return all(r.ok for r in self.results)


def sample_agent_ids(
    session: Session, sample_size: int, rng: random.Random | None = None
) -> list[int]:
    """Return up to ``sample_size`` distinct agentIds sampled from the index."""
    rng = rng or random.Random()
    ids = repo.all_agent_ids(session)
    if len(ids) <= sample_size:
        return ids
    return rng.sample(ids, sample_size)


def spot_check_agents(
    session: Session, reader: AgentReader, agent_ids: list[int]
) -> SpotCheckReport:
    """Compare indexed owner/URI against on-chain values for the given agents."""
    results: list[SpotCheckResult] = []
    for agent_id in agent_ids:
        agent = session.get(Agent, agent_id)
        if agent is None:
            continue
        owner_chain = reader.owner_of(agent_id).lower()
        results.append(
            SpotCheckResult(agent_id, "owner", agent.owner, owner_chain, agent.owner == owner_chain)
        )
        uri_chain = reader.token_uri(agent_id)
        results.append(
            SpotCheckResult(
                agent_id, "agent_uri", agent.agent_uri, uri_chain, agent.agent_uri == uri_chain
            )
        )
    return SpotCheckReport(results=results, checked=len(agent_ids))


# ── on-chain reader ──────────────────────────────────────────────────────────

_OWNER_OF = function_signature_to_4byte_selector("ownerOf(uint256)")
_TOKEN_URI = function_signature_to_4byte_selector("tokenURI(uint256)")


class SupportsCall(Protocol):
    def call(self, method: str, params: list[object]) -> str: ...


class OnChainReader:
    """Reads ``ownerOf`` / ``tokenURI`` from the Identity Registry via ``eth_call``."""

    def __init__(self, client: SupportsCall, address: str) -> None:
        self._client = client
        self._address = address

    def _eth_call(self, selector: bytes, agent_id: int) -> bytes:
        data = "0x" + (selector + abi_encode(["uint256"], [agent_id])).hex()
        result: str = self._client.call("eth_call", [{"to": self._address, "data": data}, "latest"])
        return bytes.fromhex(result[2:] if result.startswith("0x") else result)

    def owner_of(self, agent_id: int) -> str:
        (owner,) = abi_decode(["address"], self._eth_call(_OWNER_OF, agent_id))
        return str(owner).lower()

    def token_uri(self, agent_id: int) -> str:
        (uri,) = abi_decode(["string"], self._eth_call(_TOKEN_URI, agent_id))
        return str(uri)

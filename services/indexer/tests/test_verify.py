"""Unit tests for the verification harness (proposal §2.5)."""

from __future__ import annotations

import pytest
from provenalt_shared.db import Base, make_engine, make_session_factory
from provenalt_shared.db import repository as repo
from sqlalchemy.orm import Session

from provenalt_indexer.verify import (
    OnChainReader,
    check_continuity,
    sample_agent_ids,
    spot_check_agents,
)

OWNER_A = "0x1111111111111111111111111111111111111111"
OWNER_B = "0x2222222222222222222222222222222222222222"


@pytest.fixture
def session() -> Session:
    engine = make_engine("sqlite://")
    Base.metadata.create_all(engine)
    with make_session_factory(engine)() as s:
        yield s


def _register(s: Session, agent_id: int, owner: str, uri: str) -> None:
    repo.upsert_agent(
        s,
        agent_id=agent_id,
        owner=owner,
        agent_uri=uri,
        registered_block=100 + agent_id,
        registered_tx_hash=f"0x{agent_id:064x}",
        registered_log_index=0,
    )


# ── continuity ───────────────────────────────────────────────────────────────


def test_continuity_ok_when_sequential(session: Session) -> None:
    for i in range(1, 6):
        _register(session, i, OWNER_A, "ipfs://x")
    session.commit()

    report = check_continuity(session)
    assert report.ok
    assert report.max_agent_id == 5
    assert report.missing_ids == []


def test_continuity_flags_gaps(session: Session) -> None:
    for i in (1, 2, 4, 5):
        _register(session, i, OWNER_A, "ipfs://x")
    session.commit()

    report = check_continuity(session)
    assert not report.ok
    assert report.missing_ids == [3]


# ── spot check ───────────────────────────────────────────────────────────────


class FakeReader:
    def __init__(self, owners: dict[int, str], uris: dict[int, str]) -> None:
        self._owners = owners
        self._uris = uris

    def owner_of(self, agent_id: int) -> str:
        return self._owners[agent_id]

    def token_uri(self, agent_id: int) -> str:
        return self._uris[agent_id]


def test_spot_check_passes_when_db_matches_chain(session: Session) -> None:
    _register(session, 1, OWNER_A, "ipfs://a")
    _register(session, 2, OWNER_B, "ipfs://b")
    session.commit()

    reader = FakeReader({1: OWNER_A, 2: OWNER_B}, {1: "ipfs://a", 2: "ipfs://b"})
    report = spot_check_agents(session, reader, [1, 2])
    assert report.ok
    assert report.checked == 2


def test_spot_check_flags_owner_mismatch(session: Session) -> None:
    _register(session, 1, OWNER_A, "ipfs://a")
    session.commit()

    reader = FakeReader({1: OWNER_B}, {1: "ipfs://a"})  # chain owner differs
    report = spot_check_agents(session, reader, [1])
    assert not report.ok
    mismatches = [r for r in report.results if not r.ok]
    assert len(mismatches) == 1
    assert mismatches[0].field == "owner"


def test_sample_agent_ids_is_bounded_and_deterministic_with_seed(session: Session) -> None:
    import random

    for i in range(1, 51):
        _register(session, i, OWNER_A, "ipfs://x")
    session.commit()

    ids = sample_agent_ids(session, sample_size=20, rng=random.Random(42))
    assert len(ids) == 20
    assert len(set(ids)) == 20  # no repeats
    assert all(1 <= i <= 50 for i in ids)
    # same seed → same sample
    assert ids == sample_agent_ids(session, sample_size=20, rng=random.Random(42))


# ── on-chain reader (calldata + decode) ──────────────────────────────────────


def test_onchain_reader_builds_ownerof_calldata_and_decodes() -> None:
    from eth_abi import encode

    seen: dict[str, object] = {}

    class FakeClient:
        def call(self, method: str, params: list) -> str:
            seen["method"] = method
            seen["to"] = params[0]["to"]
            seen["data"] = params[0]["data"]
            # ownerOf(uint256) selector = 0x6352211e
            assert params[0]["data"].startswith("0x6352211e")
            return "0x" + encode(["address"], [OWNER_A]).hex()

    reader = OnChainReader(FakeClient(), "0xregistry")
    assert reader.owner_of(42).lower() == OWNER_A
    assert seen["method"] == "eth_call"
    assert seen["to"] == "0xregistry"

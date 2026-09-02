"""Unit tests for the agent-card pipeline orchestration (proposal §4.3 / §4)."""

from __future__ import annotations

import json

import pytest
from provenalt_shared.db import Base, make_engine, make_session_factory
from provenalt_shared.db import repository as repo
from sqlalchemy.orm import Session

from provenalt_indexer import events
from provenalt_indexer.cards import pipeline
from provenalt_indexer.cards.fetch import FetchResult

OWNER = "0x1111111111111111111111111111111111111111"
WALLET = "0x00000000000000000000000000000000000000aa"
REGISTRY = events.IDENTITY_REGISTRY_ADDRESS


def _card_json(agent_id: int, wallet: str | None = None) -> str:
    card: dict = {
        "type": "https://eips.ethereum.org/EIPS/eip-8004#registration-v1",
        "registrations": [{"agentId": agent_id, "agentRegistry": f"eip155:8453:{REGISTRY}"}],
        "services": [],
    }
    if wallet is not None:
        card["services"].append({"name": "wallet", "endpoint": f"eip155:8453:{wallet}"})
    return json.dumps(card)


class FakeFetcher:
    def __init__(self, results: dict[str, FetchResult]) -> None:
        self.results = results

    def fetch(self, token_uri: str) -> FetchResult:
        return self.results[token_uri]


@pytest.fixture
def session() -> Session:
    engine = make_engine("sqlite://")
    Base.metadata.create_all(engine)
    with make_session_factory(engine)() as s:
        yield s


def _agent(s: Session, agent_id: int, uri: str) -> None:
    repo.upsert_agent(
        s,
        agent_id=agent_id,
        owner=OWNER,
        agent_uri=uri,
        registered_block=1,
        registered_tx_hash=f"0x{agent_id:064x}",
        registered_log_index=0,
    )


def _ok(content: str, content_hash: str, source: str = "ipfs://x") -> FetchResult:
    return FetchResult(
        status="ok", content=content, content_hash=content_hash, http_status=200, source=source
    )


def test_process_agent_persists_full_card_state(session: Session) -> None:
    _agent(session, 1, "ipfs://card1")
    repo.insert_metadata(
        session,
        agent_id=1,
        metadata_key="agentWallet",
        indexed_key_hash="0x" + "00" * 32,
        metadata_value=bytes.fromhex(WALLET[2:]),
        block_number=1,
        tx_hash="0xw",
        log_index=0,
    )
    session.commit()

    content = _card_json(1, wallet=WALLET)
    fetcher = FakeFetcher({"ipfs://card1": _ok(content, "hash1")})
    pipeline.process_agent(session, fetcher, 1)
    session.commit()

    card = repo.get_agent_card(session, 1)
    assert card.fetch_status == "ok"
    assert card.content_hash == "hash1"
    assert card.schema_valid is True
    assert card.schema_errors is None
    assert card.registration_match is True
    assert card.wallet_status == "match"


def test_process_agent_records_invalid_schema(session: Session) -> None:
    _agent(session, 1, "ipfs://bad")
    session.commit()
    fetcher = FakeFetcher({"ipfs://bad": _ok('{"not":"a card"}', "h")})
    pipeline.process_agent(session, fetcher, 1)
    session.commit()

    card = repo.get_agent_card(session, 1)
    assert card.schema_valid is False
    assert card.schema_errors  # non-empty
    assert card.wallet_status == "wallet_not_set"


def test_process_agent_stores_fetch_error(session: Session) -> None:
    _agent(session, 1, "ar://unsupported")
    session.commit()
    fetcher = FakeFetcher({"ar://unsupported": FetchResult(status="unsupported_scheme")})
    pipeline.process_agent(session, fetcher, 1)
    session.commit()

    card = repo.get_agent_card(session, 1)
    assert card.fetch_status == "unsupported_scheme"
    assert card.schema_valid is None
    assert card.content_hash is None


def test_drift_recorded_when_content_changes_without_uri_change(session: Session) -> None:
    _agent(session, 1, "ipfs://stable")
    session.commit()
    content = _card_json(1)

    pipeline.process_agent(session, FakeFetcher({"ipfs://stable": _ok(content, "h1")}), 1)
    session.commit()
    # Same URI, different content hash on the next fetch → drift.
    pipeline.process_agent(session, FakeFetcher({"ipfs://stable": _ok(content, "h2")}), 1)
    session.commit()

    drift = session.query(repo.CardDrift).all()
    assert len(drift) == 1
    assert drift[0].old_content_hash == "h1"
    assert drift[0].new_content_hash == "h2"
    assert repo.get_agent_card(session, 1).content_hash == "h2"


def test_no_drift_when_uri_changed(session: Session) -> None:
    _agent(session, 1, "ipfs://v1")
    session.commit()
    pipeline.process_agent(session, FakeFetcher({"ipfs://v1": _ok(_card_json(1), "h1")}), 1)
    session.commit()

    # URIUpdated changed the agent_uri; a new fetch of the new URI is not "drift".
    session.get(repo.Agent, 1).agent_uri = "ipfs://v2"
    session.commit()
    pipeline.process_agent(session, FakeFetcher({"ipfs://v2": _ok(_card_json(1), "h2")}), 1)
    session.commit()

    assert session.query(repo.CardDrift).count() == 0
    assert repo.get_agent_card(session, 1).token_uri == "ipfs://v2"


def test_run_once_enqueues_and_processes(session: Session) -> None:
    _agent(session, 1, "ipfs://a")
    _agent(session, 2, "ipfs://b")
    session.commit()
    fetcher = FakeFetcher(
        {"ipfs://a": _ok(_card_json(1), "ha"), "ipfs://b": _ok(_card_json(2), "hb")}
    )

    processed = pipeline.run_once(session, fetcher)
    assert processed == 2
    assert repo.get_agent_card(session, 1) is not None
    assert repo.get_agent_card(session, 2) is not None
    assert repo.list_pending_card_refresh(session) == []  # queue drained

    # Nothing to do on a second pass (URIs unchanged, all fetched).
    assert pipeline.run_once(session, fetcher) == 0

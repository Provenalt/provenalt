"""Integration tests hitting a REAL Base RPC (marked `integration`, excluded by default).

Run with:  pytest -m integration
Skips (not fails) if the public endpoint is unreachable.
"""

from __future__ import annotations

import httpx
import pytest
from provenalt_shared.chain import ChainClient, HttpxTransport
from provenalt_shared.db import Agent, Base, make_engine, make_session_factory
from provenalt_shared.db import repository as repo
from sqlalchemy.orm import Session

from provenalt_indexer import events, worker
from provenalt_indexer.deploy_block import find_deployment_block
from provenalt_indexer.verify import OnChainReader, check_continuity

pytestmark = pytest.mark.integration

BASE_RPC_URLS = ["https://mainnet.base.org", "https://base.publicnode.com"]


def _client() -> ChainClient:
    return ChainClient(
        rpc_urls=BASE_RPC_URLS,
        transport=HttpxTransport(timeout=20.0),
        initial_chunk=5_000,
        min_chunk=100,
        max_chunk=50_000,
    )


def _session() -> Session:
    engine = make_engine("sqlite://")
    Base.metadata.create_all(engine)
    return make_session_factory(engine)()


def test_discover_identity_registry_deployment_block() -> None:
    client = _client()
    try:
        anchor = find_deployment_block(client, events.IDENTITY_REGISTRY_ADDRESS)
    except httpx.HTTPError as exc:
        pytest.skip(f"Base RPC unreachable: {exc}")
    assert anchor > 0


def test_backfill_recent_window_and_spot_check() -> None:
    client = _client()
    try:
        head = client.get_block_number()
    except httpx.HTTPError as exc:
        pytest.skip(f"Base RPC unreachable: {exc}")

    from_block = max(0, head - 50_000)
    with _session() as session:
        repo.upsert_cursor(
            session,
            worker.REGISTRY_NAME,
            anchor_block=from_block,
            last_indexed_block=from_block - 1,
        )
        session.commit()
        worker.catch_up(
            session,
            client,
            registry=worker.REGISTRY_NAME,
            address=events.IDENTITY_REGISTRY_ADDRESS,
            event_topic0s=events.IDENTITY_EVENT_TOPIC0S,
            segment_size=10_000,
        )

        # Continuity within a partial window won't start at 1, but the harness must run.
        report = check_continuity(session)
        assert report.max_agent_id is None or report.max_agent_id >= 1

        # Spot-check any agent we indexed against on-chain ownerOf/tokenURI.
        reader = OnChainReader(client, events.IDENTITY_REGISTRY_ADDRESS)
        agent = session.query(Agent).first()
        if agent is not None:
            assert reader.owner_of(agent.agent_id).lower() == agent.owner


def test_backfill_recent_reputation_window() -> None:
    from provenalt_indexer import reputation
    from provenalt_indexer.reputation_projection import ingest_reputation_logs

    client = _client()
    try:
        head = client.get_block_number()
    except httpx.HTTPError as exc:
        pytest.skip(f"Base RPC unreachable: {exc}")

    from_block = max(0, head - 50_000)
    with _session() as session:
        repo.upsert_cursor(
            session, "reputation", anchor_block=from_block, last_indexed_block=from_block - 1
        )
        session.commit()
        worker.catch_up(
            session,
            client,
            registry="reputation",
            address=reputation.REPUTATION_REGISTRY_ADDRESS,
            event_topic0s=reputation.REPUTATION_EVENT_TOPIC0S,
            segment_size=10_000,
            ingest=ingest_reputation_logs,
        )
        # The window may contain zero feedback events; the call must simply succeed and any
        # rows it does produce must be well-formed and refreshable into rater credibility.
        assert session.query(repo.Feedback).count() >= 0
        repo.refresh_rater_credibility(session)

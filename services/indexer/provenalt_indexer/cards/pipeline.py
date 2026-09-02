"""Agent-card pipeline orchestration (proposal §4.3).

For each queued agent: fetch its current ``agentURI``, hash + validate the content, run the
consistency checks, and persist the latest card state. If the content hash changed while the
URI stayed the same, a drift row is logged. The refresh queue is fed from agents that were
never fetched (``new_agent``) or whose ``agent_uri`` changed since the last fetch
(``uri_updated`` — i.e. a ``URIUpdated`` event landed); a periodic sweep can enqueue all.
"""

from __future__ import annotations

import json
from typing import Any, Protocol

from provenalt_shared.db import Agent
from provenalt_shared.db import repository as repo
from sqlalchemy.orm import Session

from provenalt_indexer.cards.consistency import check_consistency
from provenalt_indexer.cards.fetch import OK, FetchResult
from provenalt_indexer.cards.schema import validate_card


class SupportsFetch(Protocol):
    def fetch(self, token_uri: str) -> FetchResult: ...


def process_agent(session: Session, fetcher: SupportsFetch, agent_id: int) -> None:
    """Fetch, validate, consistency-check, and persist one agent's card; log drift."""
    agent = session.get(Agent, agent_id)
    if agent is None:
        return
    token_uri = agent.agent_uri
    previous = repo.get_agent_card(session, agent_id)

    result = fetcher.fetch(token_uri)

    schema_valid: bool | None = None
    schema_errors: list[str] | None = None
    registration_match: bool | None = None
    wallet_status: str | None = None

    if result.status == OK and result.content is not None:
        validation = validate_card(result.content)
        schema_valid = validation.valid
        schema_errors = validation.errors or None

        parsed = _safe_json(result.content)
        if isinstance(parsed, dict):
            wallet = repo.get_agent_wallet(session, agent_id)
            consistency = check_consistency(parsed, agent_id=agent_id, agent_wallet=wallet)
            registration_match = consistency.registration_match
            wallet_status = consistency.wallet_status

    _maybe_record_drift(session, agent_id, token_uri, previous, result)

    repo.upsert_agent_card(
        session,
        agent_id=agent_id,
        token_uri=token_uri,
        fetch_status=result.status,
        http_status=result.http_status,
        source=result.source,
        content=result.content,
        content_hash=result.content_hash,
        schema_valid=schema_valid,
        schema_errors=schema_errors,
        registration_match=registration_match,
        wallet_status=wallet_status,
    )


def _safe_json(content: str) -> Any:
    try:
        return json.loads(content)
    except json.JSONDecodeError:
        return None


def _maybe_record_drift(
    session: Session,
    agent_id: int,
    token_uri: str,
    previous: Any,
    result: FetchResult,
) -> None:
    if (
        previous is not None
        and previous.token_uri == token_uri
        and previous.content_hash is not None
        and result.content_hash is not None
        and previous.content_hash != result.content_hash
    ):
        repo.record_card_drift(
            session,
            agent_id=agent_id,
            token_uri=token_uri,
            old_content_hash=previous.content_hash,
            new_content_hash=result.content_hash,
        )


def enqueue_pending(session: Session) -> int:
    """Enqueue agents that need a (re)fetch (new or URI-changed). Returns count newly queued."""
    count = 0
    for agent_id, reason in repo.agents_needing_card_refresh(session):
        if repo.enqueue_card_refresh(session, agent_id, reason):
            count += 1
    return count


def process_queue(session: Session, fetcher: SupportsFetch, limit: int = 100) -> int:
    """Process pending refresh entries. Returns the number processed."""
    pending = repo.list_pending_card_refresh(session, limit=limit)
    for entry in pending:
        process_agent(session, fetcher, entry.agent_id)
        repo.delete_card_refresh(session, entry.agent_id)
    session.commit()
    return len(pending)


def run_once(session: Session, fetcher: SupportsFetch, limit: int = 100) -> int:
    """One pipeline pass: enqueue stale agents, then drain the queue. Returns count processed."""
    enqueue_pending(session)
    session.commit()
    return process_queue(session, fetcher, limit=limit)

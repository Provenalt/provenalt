"""Seed helpers for API tests (not a test module)."""

from __future__ import annotations

from decimal import Decimal

from provenalt_shared.db import repository as repo
from sqlalchemy.orm import Session

ZERO = "0x" + "00" * 20


def add_agent(s: Session, agent_id: int, owner: str, uri: str = "ipfs://x", block: int = 1) -> None:
    repo.upsert_agent(
        s,
        agent_id=agent_id,
        owner=owner,
        agent_uri=uri,
        registered_block=block,
        registered_tx_hash=f"0x{agent_id:064x}",
        registered_log_index=0,
    )
    repo.append_owner_history(
        s,
        agent_id=agent_id,
        from_address=ZERO,
        to_address=owner,
        block_number=block,
        tx_hash=f"0xmint{agent_id}",
        log_index=0,
    )


def add_card(s: Session, agent_id: int, *, fetch_status: str = "ok") -> None:
    repo.upsert_agent_card(
        s,
        agent_id=agent_id,
        token_uri="ipfs://x",
        fetch_status=fetch_status,
        content_hash="h",
        schema_valid=True,
        registration_match=True,
        wallet_status="match",
    )


def add_score(s: Session, agent_id: int, score: int, confidence: str = "medium") -> None:
    repo.upsert_agent_score(
        s,
        agent_id=agent_id,
        score=score,
        confidence=confidence,
        sufficient=True,
        breakdown=[{"name": "longevity", "value": 0.5}],
        weights_version="1",
        as_of_block=1000,
    )


def add_metadata(s: Session, agent_id: int, key: str, value: bytes, block: int = 1) -> None:
    repo.insert_metadata(
        s,
        agent_id=agent_id,
        metadata_key=key,
        indexed_key_hash="0x" + "00" * 32,
        metadata_value=value,
        block_number=block,
        tx_hash=f"0xmeta{agent_id}{key}",
        log_index=0,
    )


def add_transfer(s: Session, agent_id: int, frm: str, to: str, block: int) -> None:
    repo.append_owner_history(
        s,
        agent_id=agent_id,
        from_address=frm,
        to_address=to,
        block_number=block,
        tx_hash=f"0xt{agent_id}{block}",
        log_index=0,
    )
    repo.set_agent_owner(s, agent_id, to)


def add_feedback(
    s: Session, agent_id: int, client: str, index: int, block: int, value: int = 1
) -> None:
    repo.insert_feedback(
        s,
        agent_id=agent_id,
        client_address=client,
        feedback_index=index,
        value=value,
        value_decimals=0,
        value_scaled=Decimal(value),
        indexed_tag1_hash="0x" + "00" * 32,
        tag1="quality",
        tag2="",
        endpoint="",
        feedback_uri="ipfs://fb",
        feedback_hash="0x" + "00" * 32,
        block_number=block,
        tx_hash=f"0xf{agent_id}{client[-4:]}{index}",
        log_index=index,
    )


def add_revocation(s: Session, agent_id: int, client: str, index: int, block: int) -> None:
    repo.insert_feedback_revocation(
        s,
        agent_id=agent_id,
        client_address=client,
        feedback_index=index,
        block_number=block,
        tx_hash=f"0xrev{agent_id}{index}",
        log_index=0,
    )


def add_response(
    s: Session, agent_id: int, client: str, index: int, responder: str, block: int
) -> None:
    repo.insert_feedback_response(
        s,
        agent_id=agent_id,
        client_address=client,
        feedback_index=index,
        responder=responder,
        response_uri="ipfs://r",
        response_hash="0x" + "00" * 32,
        block_number=block,
        tx_hash=f"0xresp{agent_id}{index}",
        log_index=0,
    )


def add_cursor(s: Session, registry: str, anchor: int, last: int) -> None:
    repo.upsert_cursor(s, registry, anchor_block=anchor, last_indexed_block=last)

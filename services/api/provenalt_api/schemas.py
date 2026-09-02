"""Pydantic response models for the public API (v1)."""

from __future__ import annotations

from pydantic import BaseModel


class ScoreSummary(BaseModel):
    score: int | None
    confidence: str
    sufficient: bool
    weights_version: str
    as_of_block: int


class CardSummary(BaseModel):
    token_uri: str
    fetch_status: str
    http_status: int | None
    content_hash: str | None
    schema_valid: bool | None
    registration_match: bool | None
    wallet_status: str | None


class AgentListItem(BaseModel):
    agent_id: int
    owner: str
    agent_uri: str
    registered_block: int
    score: int | None
    confidence: str | None


class AgentPage(BaseModel):
    items: list[AgentListItem]
    total: int
    limit: int
    offset: int


class OwnerHistoryEntry(BaseModel):
    from_address: str
    to_address: str
    block_number: int
    tx_hash: str
    log_index: int


class MetadataEntry(BaseModel):
    metadata_key: str
    value_hex: str
    block_number: int


class AgentDetail(BaseModel):
    agent_id: int
    owner: str
    agent_uri: str
    registered_block: int
    registered_tx_hash: str
    card: CardSummary | None
    score: ScoreSummary | None
    metadata: list[MetadataEntry]
    owner_history: list[OwnerHistoryEntry]


class FeedbackEntry(BaseModel):
    client_address: str
    feedback_index: int
    value: str
    value_scaled: str
    value_decimals: int
    tag1: str
    tag2: str
    block_number: int
    revoked: bool
    responded: bool
    feedback_uri: str
    feedback_hash: str


class FeedbackPage(BaseModel):
    items: list[FeedbackEntry]
    total: int
    limit: int
    offset: int


class RegistryStatus(BaseModel):
    registry: str
    anchor_block: int
    last_indexed_block: int


class Stats(BaseModel):
    total_agents: int
    max_agent_id: int | None
    total_feedback: int
    total_scored: int
    total_cards: int
    registries: list[RegistryStatus]

// Response shapes mirroring the Provenalt API (services/api schemas).

export interface AgentListItem {
  agent_id: number;
  owner: string;
  agent_uri: string;
  registered_block: number;
  score: number | null;
  confidence: string | null;
}

export interface AgentPage {
  items: AgentListItem[];
  total: number;
  limit: number;
  offset: number;
}

export interface ScoreSummary {
  score: number | null;
  confidence: string;
  sufficient: boolean;
  weights_version: string;
  as_of_block: number;
}

export interface CardSummary {
  token_uri: string;
  fetch_status: string;
  http_status: number | null;
  content_hash: string | null;
  schema_valid: boolean | null;
  registration_match: boolean | null;
  wallet_status: string | null;
}

export interface MetadataEntry {
  metadata_key: string;
  value_hex: string;
  block_number: number;
}

export interface OwnerHistoryEntry {
  from_address: string;
  to_address: string;
  block_number: number;
  tx_hash: string;
  log_index: number;
}

export interface AgentDetail {
  agent_id: number;
  owner: string;
  agent_uri: string;
  registered_block: number;
  registered_tx_hash: string;
  card: CardSummary | null;
  score: ScoreSummary | null;
  metadata: MetadataEntry[];
  owner_history: OwnerHistoryEntry[];
}

export interface FeedbackEntry {
  client_address: string;
  feedback_index: number;
  value: string;
  value_scaled: string;
  value_decimals: number;
  tag1: string;
  tag2: string;
  block_number: number;
  revoked: boolean;
  responded: boolean;
  feedback_uri: string;
  feedback_hash: string;
}

export interface FeedbackPage {
  items: FeedbackEntry[];
  total: number;
  limit: number;
  offset: number;
}

export interface RegistryStatus {
  registry: string;
  anchor_block: number;
  last_indexed_block: number;
}

export interface GrowthPoint {
  block: number;
  cumulative_agents: number;
}

export interface Stats {
  total_agents: number;
  max_agent_id: number | null;
  total_feedback: number;
  total_scored: number;
  total_cards: number;
  registries: RegistryStatus[];
  growth: GrowthPoint[];
}

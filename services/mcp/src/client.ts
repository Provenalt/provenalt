// Thin, typed client of the Provenalt API used by the MCP tools.

export interface ScoreDetail {
  agent_id: number;
  score: number | null;
  confidence: string;
  sufficient: boolean;
  weights_version: string;
  as_of_block: number;
  breakdown: Record<string, unknown>[];
}

export interface EligibilityResponse {
  token_address: string;
  symbol: string;
  decimals: number;
  wallet: string;
  can_hold: boolean;
  can_send: boolean;
  eligible: boolean;
  receiver_policy_id: string;
  sender_policy_id: string;
  raw_balance: string;
  adjusted_balance: string;
  multiplier: string;
}

export interface ProvenaltResult extends ScoreDetail {
  verdict: "pass" | "warn" | "fail" | "insufficient";
}

export type FetchLike = (
  url: string,
  init?: { headers?: Record<string, string> },
) => Promise<{ ok: boolean; status: number; json: () => Promise<unknown> }>;

/** Map a score + confidence to a compact verdict (mirrors the API/explorer). */
export function verdictFor(
  score: number | null,
  confidence: string,
): "pass" | "warn" | "fail" | "insufficient" {
  if (score === null || confidence === "insufficient_data") return "insufficient";
  if (score >= 70) return "pass";
  if (score >= 45) return "warn";
  return "fail";
}

export function buildUrl(
  base: string,
  path: string,
  params?: Record<string, string>,
): string {
  const url = new URL(path, base.endsWith("/") ? base : base + "/");
  if (params) for (const [k, v] of Object.entries(params)) url.searchParams.set(k, v);
  return url.toString();
}

export class ProvenaltError extends Error {
  constructor(
    message: string,
    readonly status: number,
  ) {
    super(message);
  }
}

export class ProvenaltClient {
  constructor(
    private readonly baseUrl: string,
    private readonly apiKey?: string,
    private readonly fetchImpl: FetchLike = globalThis.fetch as unknown as FetchLike,
  ) {}

  headers(): Record<string, string> {
    const h: Record<string, string> = { Accept: "application/json" };
    // Partner API key bypasses x402 on the gated endpoints (score / eligibility).
    if (this.apiKey) h["X-API-Key"] = this.apiKey;
    return h;
  }

  private async get<T>(path: string, params?: Record<string, string>): Promise<T> {
    const url = buildUrl(this.baseUrl, path, params);
    const res = await this.fetchImpl(url, { headers: this.headers() });
    if (res.status === 402) {
      throw new ProvenaltError(
        "Payment required (x402). Set PROVENALT_API_KEY for partner access.",
        402,
      );
    }
    if (!res.ok) throw new ProvenaltError(`API error ${res.status} for ${path}`, res.status);
    return (await res.json()) as T;
  }

  async checkProvenalt(agentId: number): Promise<ProvenaltResult> {
    const score = await this.get<ScoreDetail>(`v1/agents/${agentId}/score`);
    return { ...score, verdict: verdictFor(score.score, score.confidence) };
  }

  async checkEligibility(wallet: string, token: string): Promise<EligibilityResponse> {
    return this.get<EligibilityResponse>("v1/eligibility", { wallet, token });
  }
}

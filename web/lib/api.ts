import type {
  AgentDetail,
  AgentPage,
  FeedbackPage,
  Stats,
} from "@/lib/types";

export const API_BASE_URL =
  process.env.NEXT_PUBLIC_API_BASE_URL ?? "http://localhost:8000";

export type QueryParams = Record<string, string | number | undefined>;

/** Build a fully-qualified API URL with query params (pure — unit tested). */
export function apiUrl(path: string, params?: QueryParams): string {
  const url = new URL(path, API_BASE_URL.endsWith("/") ? API_BASE_URL : API_BASE_URL + "/");
  if (params) {
    for (const [key, value] of Object.entries(params)) {
      if (value !== undefined && value !== "") url.searchParams.set(key, String(value));
    }
  }
  return url.toString();
}

/** GET JSON, returning null on any error so pages can render a graceful empty state. */
async function getJson<T>(path: string, params?: QueryParams): Promise<T | null> {
  try {
    const res = await fetch(apiUrl(path, params), { cache: "no-store" });
    if (!res.ok) return null;
    return (await res.json()) as T;
  } catch {
    return null;
  }
}

export const api = {
  stats: () => getJson<Stats>("v1/stats"),
  agents: (params?: QueryParams) => getJson<AgentPage>("v1/agents", params),
  agent: (agentId: number | string) => getJson<AgentDetail>(`v1/agents/${agentId}`),
  feedback: (agentId: number | string, params?: QueryParams) =>
    getJson<FeedbackPage>(`v1/agents/${agentId}/feedback`, params),
};

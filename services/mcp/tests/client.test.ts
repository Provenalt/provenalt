import { describe, expect, it } from "vitest";
import {
  ProvenaltClient,
  ProvenaltError,
  buildUrl,
  verdictFor,
  type FetchLike,
} from "../src/client.js";

function fakeFetch(
  status: number,
  body: unknown,
  captured?: { url?: string; headers?: Record<string, string> },
): FetchLike {
  return async (url, init) => {
    if (captured) {
      captured.url = url;
      captured.headers = init?.headers;
    }
    return { ok: status >= 200 && status < 300, status, json: async () => body };
  };
}

describe("verdictFor", () => {
  it("maps bands and insufficient data", () => {
    expect(verdictFor(80, "high")).toBe("pass");
    expect(verdictFor(50, "medium")).toBe("warn");
    expect(verdictFor(10, "low")).toBe("fail");
    expect(verdictFor(null, "insufficient_data")).toBe("insufficient");
    expect(verdictFor(90, "insufficient_data")).toBe("insufficient");
  });
});

describe("buildUrl", () => {
  it("joins base + path and query params", () => {
    const u = buildUrl("http://api.test", "v1/eligibility", { wallet: "0xA", token: "AAPLc" });
    expect(u).toContain("/v1/eligibility");
    expect(u).toContain("wallet=0xA");
    expect(u).toContain("token=AAPLc");
  });
});

describe("ProvenaltClient", () => {
  it("checkProvenalt returns score + computed verdict", async () => {
    const client = new ProvenaltClient(
      "http://api.test",
      undefined,
      fakeFetch(200, {
        agent_id: 7,
        score: 72,
        confidence: "high",
        sufficient: true,
        weights_version: "1",
        as_of_block: 1000,
        breakdown: [{ name: "longevity", value: 0.5 }],
      }),
    );
    const r = await client.checkProvenalt(7);
    expect(r.score).toBe(72);
    expect(r.verdict).toBe("pass");
    expect(r.breakdown.length).toBe(1);
  });

  it("sends X-API-Key when configured", async () => {
    const captured: { headers?: Record<string, string> } = {};
    const client = new ProvenaltClient(
      "http://api.test",
      "secret",
      fakeFetch(200, { eligible: true }, captured),
    );
    await client.checkEligibility("0xA", "AAPLc");
    expect(captured.headers?.["X-API-Key"]).toBe("secret");
  });

  it("omits X-API-Key when not configured", async () => {
    const captured: { headers?: Record<string, string> } = {};
    const client = new ProvenaltClient("http://api.test", undefined, fakeFetch(200, {}, captured));
    await client.checkEligibility("0xA", "AAPLc");
    expect(captured.headers?.["X-API-Key"]).toBeUndefined();
  });

  it("maps 402 to a clear payment-required error", async () => {
    const client = new ProvenaltClient("http://api.test", undefined, fakeFetch(402, {}));
    await expect(client.checkProvenalt(7)).rejects.toBeInstanceOf(ProvenaltError);
    await expect(client.checkProvenalt(7)).rejects.toMatchObject({ status: 402 });
  });
});

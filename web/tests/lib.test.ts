import { describe, expect, it } from "vitest";
import { apiUrl } from "@/lib/api";
import { truncate, formatInt, formatBlock, shortenUri } from "@/lib/format";
import { scoreBand, confidenceLabel, growthPaths } from "@/lib/score";
import type { GrowthPoint } from "@/lib/types";

describe("apiUrl", () => {
  it("joins base + path and appends params", () => {
    const url = apiUrl("v1/agents", { limit: 10, offset: 0, owner: "0xABC" });
    expect(url).toContain("/v1/agents");
    expect(url).toContain("limit=10");
    expect(url).toContain("owner=0xABC");
  });

  it("omits undefined and empty params", () => {
    const url = apiUrl("v1/agents", { owner: undefined, offset: "" });
    expect(url).not.toContain("owner");
    expect(url).not.toContain("offset");
  });
});

describe("format", () => {
  it("truncates addresses in the middle", () => {
    expect(truncate("0x1111111111111111111111111111111111111111")).toBe("0x111111…1111");
    expect(truncate("short")).toBe("short");
  });
  it("formats integers and blocks", () => {
    expect(formatInt(73800)).toBe("73,800");
    expect(formatInt(null)).toBe("—");
    expect(formatBlock(12345678)).toBe("#12,345,678");
  });
  it("shortens long URIs", () => {
    const long = "ipfs://" + "a".repeat(80);
    expect(shortenUri(long).length).toBeLessThan(long.length);
    expect(shortenUri("ipfs://short")).toBe("ipfs://short");
  });
});

describe("scoreBand", () => {
  it("maps score ranges to verdict bands", () => {
    expect(scoreBand(85, "high").verdict).toBe("pass");
    expect(scoreBand(55, "medium").verdict).toBe("warn");
    expect(scoreBand(20, "low").verdict).toBe("fail");
  });
  it("reports insufficient data instead of a number", () => {
    expect(scoreBand(null, "insufficient_data").verdict).toBe("none");
    expect(scoreBand(90, "insufficient_data").verdict).toBe("none");
    expect(scoreBand(90, "insufficient_data").label).toBe("Insufficient data");
  });
  it("labels confidence", () => {
    expect(confidenceLabel("high")).toBe("High confidence");
    expect(confidenceLabel(null)).toBe("Unknown");
  });
});

describe("growthPaths", () => {
  const series: GrowthPoint[] = [
    { block: 100, cumulative_agents: 1 },
    { block: 200, cumulative_agents: 4 },
    { block: 300, cumulative_agents: 9 },
  ];
  it("builds a line path and a closed area path", () => {
    const { line, area } = growthPaths(series, 100, 50);
    expect(line.startsWith("M")).toBe(true);
    expect(line).toContain("L");
    expect(area.endsWith("Z")).toBe(true);
  });
  it("returns empty paths for an empty series", () => {
    expect(growthPaths([], 100, 50)).toEqual({ line: "", area: "" });
  });
});

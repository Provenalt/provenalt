import type { GrowthPoint } from "@/lib/types";

export type Verdict = "pass" | "warn" | "fail" | "none";

export interface ScoreBand {
  verdict: Verdict;
  label: string;
  /** Full CSS colour for inline styles (SVG stroke, dots). */
  colorVar: string;
}

/**
 * Map a score + confidence to a trust verdict band. Low-data agents are reported as
 * "Insufficient data" rather than a falsely precise verdict (proposal §6).
 */
export function scoreBand(score: number | null, confidence: string | null): ScoreBand {
  if (score === null || confidence === "insufficient_data" || confidence === null) {
    return { verdict: "none", label: "Insufficient data", colorVar: "rgb(var(--none))" };
  }
  if (score >= 70) return { verdict: "pass", label: "Trusted", colorVar: "rgb(var(--pass))" };
  if (score >= 45) return { verdict: "warn", label: "Caution", colorVar: "rgb(var(--warn))" };
  return { verdict: "fail", label: "Elevated risk", colorVar: "rgb(var(--fail))" };
}

/** Published Provenalt Score v1 composition (mirrors METHODOLOGY.md, WEIGHTS_VERSION=1). */
export const SCORE_COMPONENTS: { name: string; weight: number; blurb: string }[] = [
  { name: "Longevity", weight: 0.2, blurb: "Registration age; discounted after a recent transfer." },
  { name: "Card integrity", weight: 0.2, blurb: "Card resolves, schema-valid, registration binds, wallet consistent." },
  { name: "Reputation", weight: 0.35, blurb: "Credible feedback, weighted by rater history; sybil bursts discounted." },
  { name: "Revocations & responses", weight: 0.1, blurb: "Revocation and response patterns over feedback." },
  { name: "Wallet behavior", weight: 0.15, blurb: "agentWallet presence and age (v1)." },
  { name: "Validation", weight: 0.0, blurb: "Reserved until the Validation Registry ships." },
];

export function confidenceLabel(confidence: string | null): string {
  switch (confidence) {
    case "high":
      return "High confidence";
    case "medium":
      return "Medium confidence";
    case "low":
      return "Low confidence";
    case "insufficient_data":
      return "Insufficient data";
    default:
      return "Unknown";
  }
}

export interface ChartPaths {
  line: string;
  area: string;
}

/**
 * Build SVG line + area paths for a growth series within a `width`×`height` box.
 * X is spread evenly across points; Y is scaled to the max cumulative value.
 */
export function growthPaths(
  series: GrowthPoint[],
  width: number,
  height: number,
  pad = 2,
): ChartPaths {
  if (series.length === 0) return { line: "", area: "" };
  const maxY = Math.max(...series.map((p) => p.cumulative_agents), 1);
  const innerW = width - pad * 2;
  const innerH = height - pad * 2;
  const n = series.length;
  const coords = series.map((p, i) => {
    const x = pad + (n === 1 ? innerW : (innerW * i) / (n - 1));
    const y = pad + innerH - (innerH * p.cumulative_agents) / maxY;
    return { x, y };
  });
  const line = coords
    .map((c, i) => `${i === 0 ? "M" : "L"}${c.x.toFixed(2)},${c.y.toFixed(2)}`)
    .join(" ");
  const first = coords[0];
  const last = coords[coords.length - 1];
  const area = `${line} L${last.x.toFixed(2)},${(height - pad).toFixed(2)} L${first.x.toFixed(
    2,
  )},${(height - pad).toFixed(2)} Z`;
  return { line, area };
}

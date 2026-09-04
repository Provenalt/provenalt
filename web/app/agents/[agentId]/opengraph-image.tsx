import { ImageResponse } from "next/og";
import { api } from "@/lib/api";
import { scoreBand, type Verdict } from "@/lib/score";

export const size = { width: 1200, height: 630 };
export const contentType = "image/png";
export const alt = "Provenalt agent trust profile";

// Editorial-light verdict palette (forest / ochre / brick / warm gray).
const VERDICT_HEX: Record<Verdict, string> = {
  pass: "#2F6B3C",
  warn: "#8F6410",
  fail: "#A8432E",
  none: "#8A8171",
};

const PAPER = "#F4F0E6";
const INK = "#1F1B16";
const MUTED = "#5A5246";
const FAINT = "#797060";
const OXBLOOD = "#6E1F2E";

export default async function OgImage({ params }: { params: Promise<{ agentId: string }> }) {
  const { agentId } = await params;
  const agent = await api.agent(agentId);
  const score = agent?.score?.score ?? null;
  const confidence = agent?.score?.confidence ?? null;
  const band = scoreBand(score, confidence);
  const accent = VERDICT_HEX[band.verdict];

  return new ImageResponse(
    (
      <div
        style={{
          width: "100%",
          height: "100%",
          display: "flex",
          flexDirection: "column",
          justifyContent: "space-between",
          background: PAPER,
          padding: "64px",
          color: INK,
          fontFamily: "serif",
          // Editorial "edition rule" across the top.
          borderTop: `12px solid ${OXBLOOD}`,
        }}
      >
        <div style={{ display: "flex", alignItems: "baseline", gap: "16px" }}>
          <div style={{ fontSize: 40, fontWeight: 700, letterSpacing: -1, color: INK }}>
            Provenalt
          </div>
          <div style={{ fontSize: 24, letterSpacing: 4, color: FAINT, fontFamily: "monospace" }}>
            THE AGENT LEDGER
          </div>
        </div>

        <div style={{ display: "flex", alignItems: "flex-end", justifyContent: "space-between" }}>
          <div style={{ display: "flex", flexDirection: "column" }}>
            <div style={{ fontSize: 30, letterSpacing: 3, color: MUTED, fontFamily: "monospace" }}>
              ERC-8004 AGENT
            </div>
            <div
              style={{
                display: "flex",
                fontSize: 140,
                fontWeight: 700,
                lineHeight: 1,
                letterSpacing: -3,
                fontFamily: "monospace",
              }}
            >
              {`#${agentId}`}
            </div>
            <div style={{ fontSize: 36, color: accent, marginTop: 12, fontWeight: 600 }}>
              {band.label}
            </div>
          </div>
          <div style={{ display: "flex", flexDirection: "column", alignItems: "flex-end" }}>
            <div
              style={{
                fontSize: 210,
                fontWeight: 700,
                color: accent,
                lineHeight: 1,
                fontFamily: "monospace",
              }}
            >
              {score === null ? "—" : score}
            </div>
            <div style={{ fontSize: 28, color: FAINT, fontFamily: "monospace", letterSpacing: 1 }}>
              PROVENALT SCORE / 100
            </div>
          </div>
        </div>
      </div>
    ),
    size,
  );
}

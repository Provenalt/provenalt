import { ImageResponse } from "next/og";
import { api } from "@/lib/api";
import { scoreBand, type Verdict } from "@/lib/score";

export const size = { width: 1200, height: 630 };
export const contentType = "image/png";
export const alt = "Provenalt agent trust profile";

const VERDICT_HEX: Record<Verdict, string> = {
  pass: "#46b98a",
  warn: "#e0a63c",
  fail: "#e5564b",
  none: "#7a8395",
};

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
          background: "#0a0c10",
          padding: "64px",
          color: "#e7ebf2",
          fontFamily: "monospace",
        }}
      >
        <div style={{ display: "flex", alignItems: "center", gap: "16px", color: "#4c86f0" }}>
          <div style={{ width: 22, height: 22, borderRadius: 6, background: "#4c86f0" }} />
          <div style={{ fontSize: 30, letterSpacing: 1 }}>provenalt</div>
        </div>

        <div style={{ display: "flex", alignItems: "flex-end", justifyContent: "space-between" }}>
          <div style={{ display: "flex", flexDirection: "column" }}>
            <div style={{ fontSize: 34, color: "#9aa3b4" }}>ERC-8004 Agent</div>
            <div style={{ display: "flex", fontSize: 128, fontWeight: 700, lineHeight: 1 }}>
              {`#${agentId}`}
            </div>
            <div style={{ fontSize: 34, color: accent, marginTop: 8 }}>{band.label}</div>
          </div>
          <div style={{ display: "flex", flexDirection: "column", alignItems: "flex-end" }}>
            <div style={{ fontSize: 200, fontWeight: 700, color: accent, lineHeight: 1 }}>
              {score === null ? "—" : score}
            </div>
            <div style={{ fontSize: 30, color: "#6b7382" }}>Provenalt Score / 100</div>
          </div>
        </div>
      </div>
    ),
    size,
  );
}

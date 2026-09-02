import type { ReactNode } from "react";

type Tone = "ok" | "warn" | "fail" | "neutral" | "accent";

const TONE: Record<Tone, string> = {
  ok: "border-pass/30 text-pass bg-pass/10",
  warn: "border-warn/30 text-warn bg-warn/10",
  fail: "border-fail/40 text-fail bg-fail/10",
  neutral: "border-border-strong text-fg-muted bg-panel-2",
  accent: "border-accent/40 text-accent-fg bg-accent/10",
};

export function Chip({ tone = "neutral", children }: { tone?: Tone; children: ReactNode }) {
  return (
    <span
      className={`inline-flex items-center gap-1 rounded-full border px-2 py-0.5 text-xs font-medium ${TONE[tone]}`}
    >
      {children}
    </span>
  );
}

/** Chip for a nullable boolean/enum status (e.g. schema_valid, registration_match). */
export function StatusChip({
  value,
  labels = { yes: "Valid", no: "Invalid", unknown: "Unknown" },
}: {
  value: boolean | null;
  labels?: { yes: string; no: string; unknown: string };
}) {
  if (value === null) return <Chip tone="neutral">{labels.unknown}</Chip>;
  return value ? <Chip tone="ok">{labels.yes}</Chip> : <Chip tone="fail">{labels.no}</Chip>;
}

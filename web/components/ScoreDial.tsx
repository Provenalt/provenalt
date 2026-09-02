import { scoreBand, confidenceLabel } from "@/lib/score";

/** Large radial score gauge for the agent profile. */
export function ScoreDial({
  score,
  confidence,
}: {
  score: number | null;
  confidence: string | null;
}) {
  const band = scoreBand(score, confidence);
  const size = 168;
  const stroke = 12;
  const r = (size - stroke) / 2;
  const c = 2 * Math.PI * r;
  const pct = score === null ? 0 : Math.max(0, Math.min(100, score)) / 100;

  return (
    <div className="flex flex-col items-center gap-3">
      <div className="relative" style={{ width: size, height: size }}>
        <svg width={size} height={size} viewBox={`0 0 ${size} ${size}`} aria-hidden>
          <circle
            cx={size / 2}
            cy={size / 2}
            r={r}
            fill="none"
            stroke="rgb(var(--border))"
            strokeWidth={stroke}
          />
          <circle
            cx={size / 2}
            cy={size / 2}
            r={r}
            fill="none"
            stroke={band.colorVar}
            strokeWidth={stroke}
            strokeLinecap="round"
            strokeDasharray={c}
            strokeDashoffset={c * (1 - pct)}
            transform={`rotate(-90 ${size / 2} ${size / 2})`}
          />
        </svg>
        <div className="absolute inset-0 flex flex-col items-center justify-center">
          <span className="mono text-4xl font-600 leading-none text-fg">
            {score === null ? "—" : score}
          </span>
          <span className="mt-1 text-eyebrow font-mono uppercase text-fg-faint">/ 100</span>
        </div>
      </div>
      <div className="text-center">
        <div className="text-sm font-600" style={{ color: band.colorVar }}>
          {band.label}
        </div>
        <div className="text-xs text-fg-faint">{confidenceLabel(confidence)}</div>
      </div>
    </div>
  );
}

/** Compact inline score for lists/tables. */
export function ScorePill({
  score,
  confidence,
}: {
  score: number | null;
  confidence: string | null;
}) {
  const band = scoreBand(score, confidence);
  return (
    <span className="inline-flex items-center gap-2">
      <span
        className="h-2 w-2 shrink-0 rounded-full"
        style={{ backgroundColor: band.colorVar }}
        aria-hidden
      />
      <span className="mono text-sm font-600 text-fg">{score === null ? "—" : score}</span>
    </span>
  );
}

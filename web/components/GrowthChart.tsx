import { growthPaths } from "@/lib/score";
import { formatInt } from "@/lib/format";
import type { GrowthPoint } from "@/lib/types";

/** Hand-drawn SVG area chart of cumulative registry growth (no chart library). */
export function GrowthChart({ series }: { series: GrowthPoint[] }) {
  const width = 720;
  const height = 200;
  const paths = growthPaths(series, width, height, 4);
  const latest = series.length ? series[series.length - 1].cumulative_agents : 0;

  return (
    <div className="panel overflow-hidden">
      <div className="flex items-baseline justify-between border-b border-border px-4 py-3">
        <div className="eyebrow">Registry growth</div>
        <div className="mono text-sm text-fg-muted">
          {formatInt(latest)} <span className="text-fg-faint">agents</span>
        </div>
      </div>
      <div className="px-2 pb-2 pt-3">
        {series.length === 0 ? (
          <div className="flex h-[200px] items-center justify-center text-sm text-fg-faint">
            No registry data yet.
          </div>
        ) : (
          <svg
            viewBox={`0 0 ${width} ${height}`}
            className="h-[200px] w-full"
            preserveAspectRatio="none"
            role="img"
            aria-label={`Cumulative agent registrations, currently ${latest}`}
          >
            <defs>
              <linearGradient id="growthFill" x1="0" y1="0" x2="0" y2="1">
                <stop offset="0%" stopColor="rgb(var(--accent))" stopOpacity="0.28" />
                <stop offset="100%" stopColor="rgb(var(--accent))" stopOpacity="0" />
              </linearGradient>
            </defs>
            <path d={paths.area} fill="url(#growthFill)" />
            <path
              d={paths.line}
              fill="none"
              stroke="rgb(var(--accent))"
              strokeWidth={2}
              vectorEffect="non-scaling-stroke"
            />
          </svg>
        )}
      </div>
    </div>
  );
}

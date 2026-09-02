import Link from "next/link";
import { ScorePill } from "@/components/ScoreDial";
import { scoreBand } from "@/lib/score";
import { truncate, formatBlock } from "@/lib/format";
import type { AgentListItem } from "@/lib/types";

export function AgentTable({ items }: { items: AgentListItem[] }) {
  if (items.length === 0) {
    return (
      <div className="panel px-4 py-10 text-center text-sm text-fg-faint">
        No agents to show yet.
      </div>
    );
  }
  return (
    <div className="panel overflow-hidden">
      <table className="w-full text-sm">
        <thead>
          <tr className="border-b border-border text-left">
            <th className="eyebrow px-4 py-2.5 font-medium">Agent</th>
            <th className="eyebrow px-4 py-2.5 font-medium">Owner</th>
            <th className="eyebrow hidden px-4 py-2.5 font-medium sm:table-cell">Registered</th>
            <th className="eyebrow px-4 py-2.5 text-right font-medium">Score</th>
          </tr>
        </thead>
        <tbody>
          {items.map((a) => {
            const band = scoreBand(a.score, a.confidence);
            return (
              <tr
                key={a.agent_id}
                className="group border-b border-border/60 last:border-0 hover:bg-panel-2"
              >
                <td className="px-4 py-3">
                  <Link
                    href={`/agents/${a.agent_id}`}
                    className="mono font-600 text-fg group-hover:text-accent-fg"
                  >
                    #{a.agent_id}
                  </Link>
                </td>
                <td className="mono px-4 py-3 text-fg-muted">{truncate(a.owner)}</td>
                <td className="mono hidden px-4 py-3 text-fg-faint sm:table-cell">
                  {formatBlock(a.registered_block)}
                </td>
                <td className="px-4 py-3">
                  <div className="flex items-center justify-end gap-2">
                    <ScorePill score={a.score} confidence={a.confidence} />
                    <span
                      className="hidden w-24 text-right text-xs md:inline"
                      style={{ color: band.colorVar }}
                    >
                      {band.label}
                    </span>
                  </div>
                </td>
              </tr>
            );
          })}
        </tbody>
      </table>
    </div>
  );
}

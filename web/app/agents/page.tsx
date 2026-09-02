import Link from "next/link";
import { api } from "@/lib/api";
import { truncate, formatInt } from "@/lib/format";
import { SearchBar } from "@/components/SearchBar";
import { AgentTable } from "@/components/AgentTable";
import { Chip } from "@/components/Chip";

export const dynamic = "force-dynamic";
export const metadata = { title: "Agents" };

const LIMIT = 25;

export default async function AgentsPage({
  searchParams,
}: {
  searchParams: Promise<{ owner?: string; offset?: string }>;
}) {
  const { owner, offset: offsetParam } = await searchParams;
  const offset = Math.max(0, Number.parseInt(offsetParam ?? "0", 10) || 0);
  const page = await api.agents({ limit: LIMIT, offset, owner });

  const total = page?.total ?? 0;
  const shownFrom = total === 0 ? 0 : offset + 1;
  const shownTo = Math.min(offset + LIMIT, total);
  const hasPrev = offset > 0;
  const hasNext = offset + LIMIT < total;

  const qs = (o: number) => {
    const p = new URLSearchParams();
    if (owner) p.set("owner", owner);
    if (o > 0) p.set("offset", String(o));
    const s = p.toString();
    return s ? `/agents?${s}` : "/agents";
  };

  return (
    <div className="space-y-6">
      <div>
        <h1 className="text-2xl font-600 tracking-tight text-fg">Agents</h1>
        <p className="mt-1 text-sm text-fg-muted">
          {formatInt(total)} indexed · showing {shownFrom}–{shownTo}
        </p>
      </div>

      <div className="max-w-xl">
        <SearchBar />
      </div>

      {owner ? (
        <div className="flex items-center gap-2 text-sm text-fg-muted">
          <span>Filtered by owner</span>
          <Chip tone="accent">
            <span className="mono">{truncate(owner)}</span>
          </Chip>
          <Link href="/agents" className="text-accent hover:text-accent-fg">
            clear
          </Link>
        </div>
      ) : null}

      <AgentTable items={page?.items ?? []} />

      <div className="flex items-center justify-between">
        {hasPrev ? (
          <Link href={qs(Math.max(0, offset - LIMIT))} className="text-sm text-accent hover:text-accent-fg">
            ← Previous
          </Link>
        ) : (
          <span className="text-sm text-fg-faint">← Previous</span>
        )}
        {hasNext ? (
          <Link href={qs(offset + LIMIT)} className="text-sm text-accent hover:text-accent-fg">
            Next →
          </Link>
        ) : (
          <span className="text-sm text-fg-faint">Next →</span>
        )}
      </div>
    </div>
  );
}

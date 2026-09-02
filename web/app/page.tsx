import Link from "next/link";
import { api } from "@/lib/api";
import { formatInt, formatBlock } from "@/lib/format";
import { SearchBar } from "@/components/SearchBar";
import { StatCard } from "@/components/StatCard";
import { GrowthChart } from "@/components/GrowthChart";
import { AgentTable } from "@/components/AgentTable";

export const dynamic = "force-dynamic";

export default async function HomePage() {
  const [stats, agents] = await Promise.all([
    api.stats(),
    api.agents({ limit: 8 }),
  ]);

  const headBlock =
    stats && stats.registries.length
      ? Math.max(...stats.registries.map((r) => r.last_indexed_block))
      : null;

  return (
    <div className="space-y-14">
      <section className="pt-6">
        <p className="eyebrow">Trust layer · ERC-8004 · Base</p>
        <h1 className="mt-3 max-w-3xl text-balance text-4xl font-600 leading-[1.1] tracking-tight text-fg sm:text-5xl">
          Can this agent be trusted?
        </h1>
        <p className="mt-4 max-w-prose text-fg-muted">
          Provenalt reads the ERC-8004 Identity and Reputation registries on Base, validates
          each agent&rsquo;s off-chain card, and computes a transparent Provenalt Score — so a
          number, a card, and a history stand behind every agent.
        </p>
        <div className="mt-6 max-w-xl">
          <SearchBar />
        </div>
      </section>

      <section aria-label="Registry statistics">
        <div className="grid grid-cols-2 gap-3 sm:grid-cols-3 lg:grid-cols-5">
          <StatCard label="Agents indexed" value={formatInt(stats?.total_agents)} />
          <StatCard label="Feedback signals" value={formatInt(stats?.total_feedback)} />
          <StatCard label="Agents scored" value={formatInt(stats?.total_scored)} />
          <StatCard label="Cards fetched" value={formatInt(stats?.total_cards)} />
          <StatCard label="Indexer head" value={headBlock === null ? "—" : formatBlock(headBlock)} />
        </div>
      </section>

      <section>
        <GrowthChart series={stats?.growth ?? []} />
      </section>

      <section>
        <div className="mb-3 flex items-center justify-between">
          <h2 className="text-lg font-600 text-fg">Recent agents</h2>
          <Link href="/agents" className="text-sm text-accent hover:text-accent-fg">
            Browse all →
          </Link>
        </div>
        <AgentTable items={agents?.items ?? []} />
      </section>
    </div>
  );
}

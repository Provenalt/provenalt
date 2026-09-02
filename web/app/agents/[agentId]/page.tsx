import Link from "next/link";
import { notFound } from "next/navigation";
import type { Metadata } from "next";
import { ArrowLeft } from "lucide-react";
import { api } from "@/lib/api";
import { truncate, formatBlock, shortenUri } from "@/lib/format";
import { SCORE_COMPONENTS } from "@/lib/score";
import { ScoreDial } from "@/components/ScoreDial";
import { Chip, StatusChip } from "@/components/Chip";
import { DetailRow, Panel } from "@/components/DetailRow";

export const dynamic = "force-dynamic";

export async function generateMetadata({
  params,
}: {
  params: Promise<{ agentId: string }>;
}): Promise<Metadata> {
  const { agentId } = await params;
  return {
    title: `Agent #${agentId}`,
    description: `Provenalt trust profile for ERC-8004 agent #${agentId} on Base.`,
  };
}

const WALLET_TONE: Record<string, "ok" | "warn" | "fail" | "neutral"> = {
  match: "ok",
  mismatch: "fail",
  not_declared: "neutral",
  wallet_not_set: "neutral",
};

export default async function AgentPage({
  params,
}: {
  params: Promise<{ agentId: string }>;
}) {
  const { agentId } = await params;
  const [agent, feedback] = await Promise.all([
    api.agent(agentId),
    api.feedback(agentId, { limit: 20 }),
  ]);
  if (!agent) notFound();

  const card = agent.card;

  return (
    <div className="space-y-8">
      <Link href="/agents" className="inline-flex items-center gap-1.5 text-sm text-fg-muted hover:text-fg">
        <ArrowLeft className="h-4 w-4" aria-hidden /> All agents
      </Link>

      <header className="flex flex-wrap items-end justify-between gap-4">
        <div>
          <p className="eyebrow">ERC-8004 Agent</p>
          <h1 className="mono mt-2 text-3xl font-600 tracking-tight text-fg">
            #{agent.agent_id}
          </h1>
          <p className="mono mt-2 text-sm text-fg-muted">
            owner {truncate(agent.owner)} · registered {formatBlock(agent.registered_block)}
          </p>
        </div>
      </header>

      <div className="grid gap-6 lg:grid-cols-3">
        <div className="space-y-6 lg:col-span-2">
          {/* Score */}
          <section className="panel">
            <div className="flex flex-col gap-6 p-5 sm:flex-row sm:items-center">
              <ScoreDial score={agent.score?.score ?? null} confidence={agent.score?.confidence ?? null} />
              <div className="flex-1">
                <h2 className="text-sm font-600 text-fg">Provenalt Score</h2>
                <p className="mt-1 text-sm text-fg-muted">
                  A transparent 0–100 trust score. Weights are published and versioned.
                </p>
                <dl className="mt-3">
                  <DetailRow label="Confidence">{agent.score?.confidence ?? "—"}</DetailRow>
                  <DetailRow label="Weights version">
                    {agent.score ? `v${agent.score.weights_version}` : "—"}
                  </DetailRow>
                  <DetailRow label="Computed at block">
                    {agent.score ? formatBlock(agent.score.as_of_block) : "—"}
                  </DetailRow>
                </dl>
              </div>
            </div>
            <div className="border-t border-border px-5 py-4">
              <div className="flex items-center justify-between">
                <h3 className="eyebrow">Composition (v1)</h3>
                <Link href="/methodology" className="text-xs text-accent hover:text-accent-fg">
                  Full methodology →
                </Link>
              </div>
              <ul className="mt-3 space-y-2">
                {SCORE_COMPONENTS.map((c) => (
                  <li key={c.name} className="flex items-center gap-3">
                    <span className="mono w-12 shrink-0 text-right text-xs text-fg-muted">
                      {Math.round(c.weight * 100)}%
                    </span>
                    <span className="h-1.5 flex-1 overflow-hidden rounded-full bg-panel-2">
                      <span
                        className="block h-full rounded-full bg-accent/70"
                        style={{ width: `${Math.max(2, c.weight * 100)}%` }}
                      />
                    </span>
                    <span className="w-40 shrink-0 text-sm text-fg">{c.name}</span>
                  </li>
                ))}
              </ul>
            </div>
          </section>

          {/* Card integrity */}
          <Panel title="Agent card">
            {card ? (
              <dl>
                <DetailRow label="Fetch status">
                  <Chip tone={card.fetch_status === "ok" ? "ok" : "fail"}>{card.fetch_status}</Chip>
                </DetailRow>
                <DetailRow label="Schema valid">
                  <StatusChip value={card.schema_valid} />
                </DetailRow>
                <DetailRow label="Registration binds">
                  <StatusChip value={card.registration_match} labels={{ yes: "Bound", no: "Mismatch", unknown: "Unknown" }} />
                </DetailRow>
                <DetailRow label="agentWallet check">
                  <Chip tone={WALLET_TONE[card.wallet_status ?? ""] ?? "neutral"}>
                    {card.wallet_status ?? "n/a"}
                  </Chip>
                </DetailRow>
                <DetailRow label="tokenURI">{shortenUri(card.token_uri)}</DetailRow>
                <DetailRow label="Content hash">
                  {card.content_hash ? truncate(`0x${card.content_hash}`, 8, 6) : "—"}
                </DetailRow>
              </dl>
            ) : (
              <p className="py-2 text-sm text-fg-faint">No card has been fetched yet.</p>
            )}
          </Panel>

          {/* Feedback */}
          <Panel title={`Feedback${feedback ? ` · ${feedback.total}` : ""}`}>
            {feedback && feedback.items.length > 0 ? (
              <ul className="divide-y divide-border/60">
                {feedback.items.map((f) => (
                  <li key={`${f.client_address}-${f.feedback_index}`} className="py-3">
                    <div className="flex items-center justify-between gap-3">
                      <span className="mono text-sm text-fg-muted">{truncate(f.client_address)}</span>
                      <div className="flex items-center gap-2">
                        {f.revoked ? <Chip tone="fail">revoked</Chip> : null}
                        {f.responded ? <Chip tone="accent">responded</Chip> : null}
                        <span className="mono text-sm font-600 text-fg">{f.value_scaled}</span>
                      </div>
                    </div>
                    <div className="mt-1 flex items-center gap-2 text-xs text-fg-faint">
                      {f.tag1 ? <span>{f.tag1}</span> : null}
                      {f.tag2 ? <span>· {f.tag2}</span> : null}
                      <span className="mono ml-auto">{formatBlock(f.block_number)}</span>
                    </div>
                  </li>
                ))}
              </ul>
            ) : (
              <p className="py-2 text-sm text-fg-faint">No feedback recorded yet.</p>
            )}
          </Panel>
        </div>

        {/* Sidebar */}
        <aside className="space-y-6">
          <Panel title="Identity">
            <dl>
              <DetailRow label="Agent ID">#{agent.agent_id}</DetailRow>
              <DetailRow label="Owner">{truncate(agent.owner)}</DetailRow>
              <DetailRow label="Registered">{formatBlock(agent.registered_block)}</DetailRow>
              <DetailRow label="Mint tx">{truncate(agent.registered_tx_hash, 6, 6)}</DetailRow>
            </dl>
          </Panel>

          <Panel title="On-chain metadata">
            {agent.metadata.length > 0 ? (
              <dl>
                {agent.metadata.map((m, i) => (
                  <DetailRow key={`${m.metadata_key}-${i}`} label={m.metadata_key}>
                    {truncate(m.value_hex, 8, 6)}
                  </DetailRow>
                ))}
              </dl>
            ) : (
              <p className="py-2 text-sm text-fg-faint">No metadata set.</p>
            )}
          </Panel>

          <Panel title="Ownership history">
            <ol className="space-y-3">
              {agent.owner_history.map((h, i) => (
                <li key={`${h.tx_hash}-${i}`} className="flex items-start gap-3">
                  <span className="mt-1.5 h-2 w-2 shrink-0 rounded-full bg-accent/70" aria-hidden />
                  <div className="min-w-0">
                    <p className="mono text-sm text-fg">
                      {truncate(h.from_address)} → {truncate(h.to_address)}
                    </p>
                    <p className="mono text-xs text-fg-faint">{formatBlock(h.block_number)}</p>
                  </div>
                </li>
              ))}
            </ol>
          </Panel>
        </aside>
      </div>
    </div>
  );
}

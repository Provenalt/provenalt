import type { ReactNode } from "react";

export function DetailRow({ label, children }: { label: string; children: ReactNode }) {
  return (
    <div className="flex items-start justify-between gap-4 border-b border-border/60 py-2.5 last:border-0">
      <dt className="text-sm text-fg-muted">{label}</dt>
      <dd className="mono text-right text-sm text-fg">{children}</dd>
    </div>
  );
}

export function Panel({ title, children }: { title: string; children: ReactNode }) {
  return (
    <section className="panel">
      <h2 className="border-b border-border px-4 py-2.5 font-mono text-[0.72rem] font-medium uppercase tracking-[0.12em] text-fg-muted">
        {title}
      </h2>
      <div className="px-4 py-3">{children}</div>
    </section>
  );
}

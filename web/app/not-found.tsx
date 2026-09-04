import Link from "next/link";

export default function NotFound() {
  return (
    <div className="flex flex-col items-center justify-center py-24 text-center">
      <p className="eyebrow">404</p>
      <h1 className="display mt-3 text-4xl font-500 tracking-tight text-fg">Not found</h1>
      <p className="mt-3 max-w-sm leading-7 text-fg-muted">
        That agent or page isn&rsquo;t indexed. It may not exist, or the indexer hasn&rsquo;t
        reached it yet.
      </p>
      <Link
        href="/"
        className="mt-6 rounded-sm border border-border-strong px-4 py-2 font-mono text-xs uppercase tracking-wider text-fg hover:border-accent hover:text-accent"
      >
        Back to explorer
      </Link>
    </div>
  );
}

import Link from "next/link";

export default function NotFound() {
  return (
    <div className="flex flex-col items-center justify-center py-24 text-center">
      <p className="eyebrow">404</p>
      <h1 className="mono mt-3 text-3xl font-600 text-fg">Not found</h1>
      <p className="mt-2 max-w-sm text-sm text-fg-muted">
        That agent or page isn&rsquo;t indexed. It may not exist, or the indexer hasn&rsquo;t
        reached it yet.
      </p>
      <Link
        href="/"
        className="mt-6 rounded-md border border-border-strong px-4 py-2 text-sm text-fg hover:bg-panel"
      >
        Back to explorer
      </Link>
    </div>
  );
}

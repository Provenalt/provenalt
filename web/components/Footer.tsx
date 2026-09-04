import Link from "next/link";

export function Footer() {
  return (
    <footer className="mt-24 border-t border-border">
      <div className="mx-auto flex max-w-6xl flex-col gap-3 px-5 py-8 text-sm text-fg-faint sm:flex-row sm:items-center sm:justify-between">
        <p>
          <span className="display font-500 text-fg-muted">Provenalt</span>
          <span className="font-mono"> · trust layer for the agentic economy on Base</span>
        </p>
        <nav className="flex items-center gap-4 font-mono text-[0.72rem] uppercase tracking-[0.1em]">
          <Link href="/methodology" className="hover:text-accent">
            Methodology
          </Link>
          <Link href="/about" className="hover:text-accent">
            About
          </Link>
          <span className="text-border-strong">·</span>
          <span>ERC-8004</span>
        </nav>
      </div>
    </footer>
  );
}

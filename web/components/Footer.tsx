import Link from "next/link";

export function Footer() {
  return (
    <footer className="mt-24 border-t border-border">
      <div className="mx-auto flex max-w-6xl flex-col gap-3 px-5 py-8 text-sm text-fg-faint sm:flex-row sm:items-center sm:justify-between">
        <p className="mono">
          provenalt · trust layer for the agentic economy on Base
        </p>
        <nav className="flex items-center gap-4">
          <Link href="/methodology" className="hover:text-fg">
            Methodology
          </Link>
          <Link href="/about" className="hover:text-fg">
            About
          </Link>
          <span className="text-border-strong">·</span>
          <span>ERC-8004</span>
        </nav>
      </div>
    </footer>
  );
}

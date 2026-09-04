import Link from "next/link";

const NAV = [
  { href: "/agents", label: "Agents" },
  { href: "/methodology", label: "Methodology" },
  { href: "/about", label: "About" },
];

export function Header() {
  return (
    <header className="sticky top-0 z-40 border-t-2 border-accent bg-bg/90 backdrop-blur">
      <div className="mx-auto flex h-16 max-w-6xl items-center justify-between gap-4 border-b border-border px-5">
        <Link href="/" className="group flex items-baseline gap-2.5" aria-label="Provenalt home">
          <span className="display text-2xl font-600 tracking-tight text-fg">Provenalt</span>
          <span className="hidden font-mono text-eyebrow uppercase text-fg-faint sm:inline">
            The Agent Ledger
          </span>
        </Link>
        <nav className="flex items-center gap-5 font-mono text-[0.7rem] uppercase tracking-[0.12em]">
          {NAV.map((item) => (
            <Link
              key={item.href}
              href={item.href}
              className="text-fg-muted underline-offset-4 hover:text-accent hover:underline"
            >
              {item.label}
            </Link>
          ))}
        </nav>
      </div>
    </header>
  );
}

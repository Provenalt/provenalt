import Link from "next/link";
import { ShieldCheck } from "lucide-react";

const NAV = [
  { href: "/agents", label: "Agents" },
  { href: "/methodology", label: "Methodology" },
  { href: "/about", label: "About" },
];

export function Header() {
  return (
    <header className="sticky top-0 z-40 border-b border-border bg-bg/80 backdrop-blur">
      <div className="mx-auto flex h-14 max-w-6xl items-center justify-between px-5">
        <Link href="/" className="group flex items-center gap-2" aria-label="Provenalt home">
          <ShieldCheck className="h-5 w-5 text-accent" aria-hidden />
          <span className="mono text-[0.95rem] font-600 tracking-tight text-fg">
            provenalt
          </span>
        </Link>
        <nav className="flex items-center gap-1 text-sm">
          {NAV.map((item) => (
            <Link
              key={item.href}
              href={item.href}
              className="rounded-md px-3 py-1.5 text-fg-muted hover:bg-panel hover:text-fg"
            >
              {item.label}
            </Link>
          ))}
        </nav>
      </div>
    </header>
  );
}

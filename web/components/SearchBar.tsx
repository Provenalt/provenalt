"use client";

import { useRouter } from "next/navigation";
import { Search } from "lucide-react";
import { useState } from "react";

/**
 * Search routes intelligently: a number → that agent's profile; an address → agents owned
 * by it; anything else → the agent list.
 */
export function SearchBar({ autoFocus = false }: { autoFocus?: boolean }) {
  const router = useRouter();
  const [value, setValue] = useState("");

  function onSubmit(e: React.FormEvent) {
    e.preventDefault();
    const q = value.trim();
    if (/^\d+$/.test(q)) {
      router.push(`/agents/${q}`);
    } else if (/^0x[0-9a-fA-F]{40}$/.test(q)) {
      router.push(`/agents?owner=${q}`);
    } else {
      router.push("/agents");
    }
  }

  return (
    <form onSubmit={onSubmit} role="search" className="w-full">
      <div className="flex items-center gap-2 rounded-lg border border-border-strong bg-panel px-3 py-2.5 focus-within:border-accent">
        <Search className="h-4 w-4 shrink-0 text-fg-faint" aria-hidden />
        <input
          // eslint-disable-next-line jsx-a11y/no-autofocus
          autoFocus={autoFocus}
          value={value}
          onChange={(e) => setValue(e.target.value)}
          placeholder="Search by agent ID or owner address…"
          aria-label="Search agents by ID or owner address"
          className="mono w-full bg-transparent text-sm text-fg placeholder:text-fg-faint focus:outline-none"
        />
        <button
          type="submit"
          className="rounded-md bg-accent px-3 py-1 text-sm font-500 text-white hover:brightness-110"
        >
          Search
        </button>
      </div>
    </form>
  );
}

/** Truncate a 0x address/hash to `0x1234…abcd`. */
export function truncate(value: string, lead = 6, tail = 4): string {
  if (!value.startsWith("0x")) return value;
  if (value.length <= lead + tail + 2) return value;
  return `${value.slice(0, 2 + lead)}…${value.slice(-tail)}`;
}

/** Thousands-separated integer, e.g. 73800 → "73,800". */
export function formatInt(n: number | null | undefined): string {
  if (n === null || n === undefined) return "—";
  return n.toLocaleString("en-US");
}

/** Block number as `#12,345,678`. */
export function formatBlock(n: number | null | undefined): string {
  if (n === null || n === undefined) return "—";
  return `#${n.toLocaleString("en-US")}`;
}

/** Shorten a tokenURI for display while keeping the scheme + tail. */
export function shortenUri(uri: string, max = 42): string {
  if (uri.length <= max) return uri;
  const head = uri.slice(0, max - 12);
  return `${head}…${uri.slice(-8)}`;
}

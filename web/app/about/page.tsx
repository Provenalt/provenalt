import Link from "next/link";

export const metadata = {
  title: "About",
  description: "What Provenalt is and why it exists.",
};

const FACTS = [
  { label: "Identity Registry", value: "0x8004A169…9a432" },
  { label: "Reputation Registry", value: "0x8004BAa1…9De9b63" },
  { label: "Chain", value: "Base" },
  { label: "Standard", value: "ERC-8004" },
];

export default function AboutPage() {
  return (
    <div className="space-y-10">
      <header>
        <p className="eyebrow">About</p>
        <h1 className="mt-3 text-3xl font-600 tracking-tight text-fg">
          A trust layer for the agentic economy
        </h1>
      </header>

      <div className="prose-md">
        <p>
          ERC-8004 registries on Base are live and growing fast, but the ecosystem has only raw
          rails — registries, SDKs, a subgraph. No product reads all of it and answers the
          question that matters: <strong>can this agent be trusted?</strong>
        </p>
        <p>Provenalt is that layer. It:</p>
        <ul>
          <li>Indexes the ERC-8004 Identity and Reputation registries directly from Base.</li>
          <li>Validates each agent&rsquo;s off-chain card and detects drift.</li>
          <li>
            Computes a transparent <Link href="/methodology">Provenalt Score</Link> (0–100) with a
            published, versioned methodology.
          </li>
          <li>
            Checks B20 tokenized-stock eligibility natively — can a wallet hold or transfer a
            given stock — with no external service dependency.
          </li>
        </ul>
        <p>
          The score is a heuristic, not a guarantee. Every input is public and every weight is
          documented, so the number is auditable rather than a black box.
        </p>
      </div>

      <section>
        <h2 className="mb-3 text-sm font-600 text-fg">On-chain facts</h2>
        <dl className="grid grid-cols-2 gap-3 sm:grid-cols-4">
          {FACTS.map((f) => (
            <div key={f.label} className="panel px-4 py-3">
              <dt className="eyebrow">{f.label}</dt>
              <dd className="mono mt-1.5 text-sm text-fg">{f.value}</dd>
            </div>
          ))}
        </dl>
      </section>
    </div>
  );
}

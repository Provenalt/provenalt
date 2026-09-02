import { promises as fs } from "fs";
import path from "path";
import ReactMarkdown from "react-markdown";
import remarkGfm from "remark-gfm";

export const metadata = {
  title: "Methodology",
  description: "How the Provenalt Score is computed — components, weights, and sybil resistance.",
};

async function loadMethodology(): Promise<string> {
  // METHODOLOGY.md lives at the repo root (one level above web/).
  const candidates = [
    path.join(process.cwd(), "..", "METHODOLOGY.md"),
    path.join(process.cwd(), "METHODOLOGY.md"),
  ];
  for (const file of candidates) {
    try {
      return await fs.readFile(file, "utf8");
    } catch {
      /* try next */
    }
  }
  return "# Methodology\n\nThe methodology document is unavailable in this environment.";
}

export default async function MethodologyPage() {
  const markdown = await loadMethodology();
  return (
    <article className="prose-md">
      <ReactMarkdown remarkPlugins={[remarkGfm]}>{markdown}</ReactMarkdown>
    </article>
  );
}

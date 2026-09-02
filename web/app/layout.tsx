import type { Metadata } from "next";
import "./globals.css";
import { Header } from "@/components/Header";
import { Footer } from "@/components/Footer";

export const metadata: Metadata = {
  metadataBase: new URL("https://provenalt.example"),
  title: {
    default: "Provenalt — Can this agent be trusted?",
    template: "%s · Provenalt",
  },
  description:
    "A trust layer for the agentic economy on Base. Provenalt indexes the ERC-8004 registries, validates Agent Cards, and scores agents — so you can answer the question that matters: can this agent be trusted?",
  openGraph: {
    title: "Provenalt — Can this agent be trusted?",
    description:
      "Trust scores, agent-card integrity, feedback, and ownership history for ERC-8004 agents on Base.",
    siteName: "Provenalt",
    type: "website",
  },
};

export default function RootLayout({ children }: { children: React.ReactNode }) {
  return (
    <html lang="en">
      <body className="min-h-dvh">
        <Header />
        <main className="mx-auto max-w-6xl px-5 py-10">{children}</main>
        <Footer />
      </body>
    </html>
  );
}

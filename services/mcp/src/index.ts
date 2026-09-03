#!/usr/bin/env node
/**
 * Provenalt MCP server.
 *
 * Exposes two tools over stdio — a thin client of the Provenalt API:
 *   - check_provenalt(agentId): full Provenalt Score + per-component breakdown + verdict.
 *   - check_eligibility(wallet, token): B20 eligibility (can_hold/can_send/eligible) + balances.
 *
 * Config via env: PROVENALT_API_BASE_URL (default http://localhost:8000), PROVENALT_API_KEY
 * (partner key to bypass x402 on the gated endpoints).
 */

import { McpServer } from "@modelcontextprotocol/sdk/server/mcp.js";
import { StdioServerTransport } from "@modelcontextprotocol/sdk/server/stdio.js";
import { z } from "zod";
import { ProvenaltClient, ProvenaltError } from "./client.js";

const BASE_URL = process.env.PROVENALT_API_BASE_URL ?? "http://localhost:8000";
const API_KEY = process.env.PROVENALT_API_KEY;

const client = new ProvenaltClient(BASE_URL, API_KEY);

function toText(value: unknown) {
  return { content: [{ type: "text" as const, text: JSON.stringify(value, null, 2) }] };
}

function toError(err: unknown) {
  const message = err instanceof ProvenaltError ? err.message : String(err);
  return { isError: true, content: [{ type: "text" as const, text: message }] };
}

export function buildServer(): McpServer {
  const server = new McpServer({ name: "provenalt", version: "0.1.0" });

  server.registerTool(
    "check_provenalt",
    {
      title: "Check Provenalt Score",
      description:
        "Return the full Provenalt trust profile for an ERC-8004 agent on Base: the 0–100 " +
        "score, confidence, per-component breakdown, and a compact verdict.",
      inputSchema: { agentId: z.number().int().nonnegative().describe("ERC-8004 agent id") },
    },
    async ({ agentId }) => {
      try {
        return toText(await client.checkProvenalt(agentId));
      } catch (err) {
        return toError(err);
      }
    },
  );

  server.registerTool(
    "check_eligibility",
    {
      title: "Check B20 stock eligibility",
      description:
        "For a wallet and a B20 tokenized stock (address or symbol), return whether the wallet " +
        "can hold/transfer it plus multiplier-aware raw and adjusted balances.",
      inputSchema: {
        wallet: z.string().describe("Wallet address (0x…)"),
        token: z.string().describe("B20 token contract address or symbol (e.g. AAPLc)"),
      },
    },
    async ({ wallet, token }) => {
      try {
        return toText(await client.checkEligibility(wallet, token));
      } catch (err) {
        return toError(err);
      }
    },
  );

  return server;
}

async function main(): Promise<void> {
  const server = buildServer();
  await server.connect(new StdioServerTransport());
}

// Run only when executed directly (not when imported by tests).
if (import.meta.url === `file://${process.argv[1]}`) {
  main().catch((err) => {
    console.error("provenalt-mcp fatal:", err);
    process.exit(1);
  });
}

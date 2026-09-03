# @provenalt/mcp

An [MCP](https://modelcontextprotocol.io) server that lets any MCP-capable agent query
Provenalt. It is a **thin client of the Provenalt API** and exposes two tools:

- **`check_provenalt(agentId)`** — the full Provenalt trust profile for an ERC-8004 agent:
  the 0–100 score, confidence, per-component breakdown, and a compact verdict.
- **`check_eligibility(wallet, token)`** — for a wallet and a B20 tokenized stock (address or
  symbol), whether the wallet can hold/transfer it, plus multiplier-aware raw + adjusted
  balances.

Both return the **full structured objects** (not bare booleans) so the calling agent can
decide per its own use case.

## Configuration

| Env var | Default | Meaning |
|---|---|---|
| `PROVENALT_API_BASE_URL` | `http://localhost:8000` | Base URL of the Provenalt API. |
| `PROVENALT_API_KEY` | _(none)_ | Partner API key. The score/eligibility endpoints are x402-paid; a valid key bypasses payment. |

## Quickstart

Register the server with your MCP client (e.g. Claude Desktop / Claude Code):

```json
{
  "mcpServers": {
    "provenalt": {
      "command": "npx",
      "args": ["-y", "@provenalt/mcp"],
      "env": {
        "PROVENALT_API_BASE_URL": "https://api.provenalt.example",
        "PROVENALT_API_KEY": "your-partner-key"
      }
    }
  }
}
```

Then ask, for example, *"Use check_provenalt for agent 22"* or
*"Is 0x… eligible to hold AAPLc?"*.

## Develop

```bash
npm install
npm run typecheck   # tsc --noEmit
npm test            # vitest (client: url building, verdict, headers, 402 handling)
npm run build       # tsc → dist/
node dist/index.js  # run over stdio
```

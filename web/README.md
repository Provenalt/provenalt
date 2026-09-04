# web

The Provenalt public explorer — a Next.js (App Router) app deployed to Vercel. Reads the
public API at `NEXT_PUBLIC_API_BASE_URL`.

## Status (Group 8 — Explorer MVP)

- **Home** (`/`) — hero, search, registry stat cards, a hand-drawn SVG **growth chart**
  (from `/v1/stats`), and recent agents.
- **Agents** (`/agents`) — paginated list with an `owner` filter; search routes an agent ID
  to its profile and an address to its owned agents.
- **Agent profile** (`/agents/[id]`) — Provenalt Score dial + verdict, published score
  composition, agent-card integrity, on-chain metadata, ownership history, and the feedback
  timeline.
- **Methodology** (`/methodology`) — renders the repo-root `METHODOLOGY.md`.
- **About** (`/about`).
- **OG images** — dynamic per-agent social card at `/agents/[id]/opengraph-image`.

### Design

**Editorial light** — "the Provenalt ledger" (design direction via the ui-ux-pro-max skill).
A warm cream paper with warm-ink body text and a single deep **oxblood** accent used sparingly
(links, masthead rule, active states) — deliberately distinct from the dark slate-blue
dashboards common to the category. Verdicts keep their semantic roles in a warmer, editorial
palette (forest green / mustard-ochre / brick red rather than neon). Typography-driven:
**Fraunces** (variable serif) for display/mastheads, **Newsreader** (variable serif) for body
and prose, and **IBM Plex Mono** reserved strictly for data — agent IDs, addresses, hashes,
block numbers, scores, and letterspaced section labels. Tabular figures throughout; hairline
rules instead of drop shadows. No chart library — the growth chart is hand-rolled SVG.

## Develop

```bash
npm install
NEXT_PUBLIC_API_BASE_URL=http://localhost:8000 npm run dev
```

## Gates

```bash
npm run lint        # eslint (next/core-web-vitals)
npm run typecheck   # tsc --noEmit
npm test            # vitest (lib: formatting, score bands, chart paths, api url)
npm run build       # next build
```

## Deploy (Vercel)

Deferred to the operator (see `infra/README.md`): create a Vercel project with **Root
Directory = repo root** (so `METHODOLOGY.md` is readable at build) and a build command of
`npm --prefix web ci && npm --prefix web run build` with output `web/.next`, or set Root =
`web` and provide the methodology another way. Set `NEXT_PUBLIC_API_BASE_URL` to the Railway
`api` URL. Pages that read the API are dynamic and degrade gracefully when it is unreachable.

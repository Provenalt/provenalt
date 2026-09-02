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

Dark, technical, high-contrast (design direction via the ui-ux-pro-max skill): slate
neutrals with a restrained trust-blue accent and a traffic-light verdict system for the
score; **Fira Code** (mono) for the wordmark, score, and all data, **Fira Sans** for body;
tabular figures throughout. No chart library — the growth chart is hand-rolled SVG.

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

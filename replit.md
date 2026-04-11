# Workspace

## Overview

pnpm workspace monorepo using TypeScript. Each package manages its own dependencies.

## Stack

- **Monorepo tool**: pnpm workspaces
- **Node.js version**: 24
- **Package manager**: pnpm
- **TypeScript version**: 5.9
- **API framework**: Express 5
- **Database**: PostgreSQL + Drizzle ORM
- **Validation**: Zod (`zod/v4`), `drizzle-zod`
- **API codegen**: Orval (from OpenAPI spec)
- **Build**: esbuild (CJS bundle)

## Key Commands

- `pnpm run typecheck` — full typecheck across all packages
- `pnpm run build` — typecheck + build all packages
- `pnpm --filter @workspace/api-spec run codegen` — regenerate API hooks and Zod schemas from OpenAPI spec
- `pnpm --filter @workspace/db run push` — push DB schema changes (dev only)
- `pnpm --filter @workspace/api-server run dev` — run API server locally
- `pnpm --filter @workspace/ai-toolkit run dev` — run AI Toolkit web app

## Artifacts

### ai-toolkit (React + Vite, previewPath: /)
A Chinese-language web portal for the [AI-Account-Toolkit](https://github.com/adminlove520/AI-Account-Toolkit) project.
- **Purpose**: Navigation dashboard showcasing 29+ AI account tools
- **Files**: `artifacts/ai-toolkit/src/`
  - `data/tools.ts` — all tool metadata (name, description, features, tags, etc.)
  - `pages/Home.tsx` — main page with sidebar nav, search, filter
  - `components/ToolCard.tsx` — tool card grid item
  - `components/ToolDetail.tsx` — modal drawer with full tool details
  - `components/StatsBar.tsx` — stats summary at top
  - `components/SearchBar.tsx` — search + filter controls
- **Features**: Category filtering, full-text search, Web UI filter, tool detail modal with GitHub links

### api-server (Express, previewPath: /api)
Shared backend API server.

### mockup-sandbox (Design, previewPath: /__mockup)
UI component sandbox.

See the `pnpm-workspace` skill for workspace structure, TypeScript setup, and package details.

## Outlook Batch Registration — Architecture

### How it works
1. Frontend (`FullWorkflow.tsx`) POSTs to `POST /api/tools/outlook/register`
2. Node.js spawns `artifacts/api-server/outlook_register.py` as a subprocess
3. Python uses **patchright** (patched Chromium) + SOCKS5 relay to register accounts
4. Node.js polls Python's stdout for JSON log lines and streams them to the frontend every 2s
5. On completion, Node.js saves successful accounts to PostgreSQL `accounts` table

### CAPTCHA bypass (FREE, no paid service needed)
- Microsoft FunCaptcha shows an **accessibility icon** (wheelchair ♿) during registration
- We click it via `locator.click(force=True)` then `dispatch_event("click")` as fallback
- This bypasses the visual press-and-hold challenge entirely
- Works in **headless mode** — no display required
- Achieved via patchright's CDP iframe cross-origin interaction
- **Key fix** (Apr 2026): replaced `bounding_box()` + `page.mouse.click()` (which returns None in headless) with `locator.click()` + `dispatch_event()` fallback

### Proxy pool
- 100 quarkip residential US proxies (sessid 177593745410000–177593745410099)
- `socks5_relay.py` creates a local unauthenticated SOCKS5 relay because Chromium can't use authenticated SOCKS5 directly
- Each registration gets a fresh relay on an ephemeral port

### Key files
- `artifacts/api-server/outlook_register.py` — main Python registration script with PatchrightController
- `artifacts/api-server/socks5_relay.py` — SOCKS5 relay for authenticated proxies
- `artifacts/api-server/src/routes/tools.ts` — Node.js route spawning Python + streaming logs + DB save
- `artifacts/ai-toolkit/src/pages/FullWorkflow.tsx` — UI for registration with live log streaming

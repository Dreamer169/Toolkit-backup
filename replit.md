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

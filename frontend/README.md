# TOUCHE COMMERCE — Frontend

Next.js 16 App Router shell for TOUCHE COMMERCE (Stage 0).

* Status screen: `src/app/page.tsx` (server component, `force-dynamic`).
* Typed API client: `src/lib/api/client.ts`; DTOs are generated into
  `src/lib/api/schema.d.ts` — never edit that file by hand.
* UI primitives: `src/components/ui` (shadcn/ui conventions); `components.json`
  keeps the CLI compatible.
* Design tokens: `src/app/globals.css` (`@theme`).

| Command | Purpose |
| ------- | ------- |
| `npm run dev` | Development server on port 3000 |
| `npm run build` / `npm start` | Production build / serve |
| `npm run lint` | ESLint (flat config, Next + Prettier) |
| `npm run typecheck` | `next typegen` + `tsc --noEmit` |
| `npm test` | Vitest (jsdom + Testing Library) |
| `npm run format` | Prettier write |
| `npm run api:types` | Regenerate types from `openapi/openapi.json` |

The OpenAPI document is exported from the backend with
`scripts/generate-api-types.ps1` (or `python backend/scripts/export_openapi.py`).
See the repository root `README.md`.

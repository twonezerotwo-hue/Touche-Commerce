# TOUCHE COMMERCE — Frontend

Next.js 16 App Router application for TOUCHE COMMERCE (Stage 1A: identity,
sessions, tenancy).

## Routes

| Route               | Access            | Purpose                                                             |
| ------------------- | ----------------- | ------------------------------------------------------------------- |
| `/login`            | public            | Sign in (Argon2id credentials, generic errors, rate-limit feedback) |
| `/select-company`   | session           | Choose the active company (multi-membership accounts)               |
| `/`                 | session + company | Command Center: identity, company, permissions, live probes         |
| `/account`          | session + company | Profile, memberships, permissions, session policy                   |
| `/status`           | public            | Read-only infrastructure status (no session data)                   |
| `/api/v1/[...path]` | —                 | Same-origin proxy to FastAPI (allow-listed headers/cookies)         |

`(app)/layout.tsx` validates the session on the server and redirects anonymous
visitors to `/login?next=<path>`; accounts without an active company go to
`/select-company`. `src/proxy.ts` exposes the pathname as `x-pathname` so the
redirect preserves the destination.

## Structure

- `src/lib/auth/*` — session loading (`session.ts`, server-only), route decisions
  (`guard.ts`, pure + unit tested), browser client (`client.ts`).
- `src/lib/api/client.ts` — transport-only typed client for health probes; DTOs
  are generated into `src/lib/api/schema.d.ts` — never edit that file by hand.
- `src/components/auth/*` — login form, logout button, company switcher, account
  summary, session-unavailable state.
- `src/components/ui` — shadcn/ui style primitives owned in-repo.
- `src/app/globals.css` — design tokens (`@theme`).
- Security: the session cookie is `HttpOnly`; the CSRF token is a server-rendered
  prop sent back as `X-CSRF-Token`; **no token is ever stored in localStorage or
  sessionStorage**.

## Commands

| Command                       | Purpose                                      |
| ----------------------------- | -------------------------------------------- |
| `npm run dev`                 | Development server on port 3000              |
| `npm run build` / `npm start` | Production build / serve                     |
| `npm run lint`                | ESLint (flat config, Next + Prettier)        |
| `npm run typecheck`           | `next typegen` + `tsc --noEmit`              |
| `npm test`                    | Vitest (jsdom + Testing Library)             |
| `npm run format`              | Prettier write                               |
| `npm run api:types`           | Regenerate types from `openapi/openapi.json` |

The OpenAPI document is exported from the backend with
`scripts/generate-api-types.ps1` (or `python backend/scripts/export_openapi.py`).
See the repository root `README.md` for the full startup and verification flow.

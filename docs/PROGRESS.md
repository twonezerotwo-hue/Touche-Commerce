# TOUCHE COMMERCE — Progress

**Last updated:** 2026-10-24 (local)
**Current stage:** Stages 11–20 local mission — LOCAL_OPERATIONAL candidate, not accepted (see the 2026-10-24 entry and `docs/STAGE11_20_STATUS.md`)
**Current milestone:** Stage 10 GitHub Actions 40030032968 PASS (585 backend / 192 frontend; 4/4 CI jobs)
**Stage 6:** PASSED on Stage 6 local reported evidence (551 backend / 192 frontend, mock provider)
**Stage 7A:** PASSED in GitHub CI (555 backend / 192 frontend, OpenAPI current; PR #1 merged); Windows browser acceptance not run
**Stage 7B:** PASSED in GitHub CI (558 backend / 192 frontend, PR #2 merged)
**Stage 7C1:** PASSED in GitHub CI (561 backend / 192 frontend, PR #3 merged); live providers and browser acceptance not verified

Statuses are restricted to `NOT_STARTED`, `IN_PROGRESS`, `BLOCKED`, `PASSED`,
`FAILED`. Nothing is marked `PASSED` without an executed command in this file.

---

## 2026-10-24 — Stages 11–20 engineering mission (local, one Windows PC)

Evidence, not claims. Full matrix: `docs/STAGE11_20_STATUS.md`; operator guide: `docs/LOCAL_RELEASE.md`.

* **11** Launcher survives port collisions (`-AutoPorts`), isolated acceptance stack, plain and
  encrypted backup restored into a scratch database (`RESTORE_VERIFIED`), 18 Windows-specific test
  failures fixed. LAN/MacBook over HTTPS: not built.
* **12** Cookie-based server-rendered TR/EN; sign-in, Command Center, import, company profile, documents,
  CRM, products, deals and sales orders translated; the rest is still English
  (`docs/STAGE12B_BILINGUAL_SCREENS.md`).
* **12E** Sourcing and pricing in Turkish (RFQ, supplier quotes, landed cost, sales quotes, FX), with
  locale-aware numbers and dates (`tr-TR` separators and month names; UTC; amounts unchanged).
  Frontend 266 tests, backend 724 collected.
* **13** CSV/XLSX import wizard (atomic, idempotent), company profile (migration 0014), TR/EN
  documents in four formats; Commerce invoices are always drafts.
* **16** Local `qwen3:8b` fallback verified live; DeepSeek not connected (no key).
* **18** Encrypted backups (AES-256-GCM); dependency scan (`npm audit` clean; `cryptography`
  advisory fixed by requiring 50.x). No MFA, no offsite copy.
* **19** Playwright suite: 88 specs on Chromium and WebKit (87 passed in the last full run, one
  timing-related failure in the concurrency spec passed on re-run); two P1s found and fixed (the
  "New counterparty" and "Open a trade deal" forms could never open), plus a conversion that the
  API refused when done within a minute of the approval, and a phone-width page overflow in WebKit.
* **14** Finance live check, with your permission: Finance's real server on a snapshot of the real
  ledger; Commerce read it end to end (6 browser specs on Chromium and WebKit); `C:\ai-excel` proven
  unchanged (4,173 files, 0 differences). See `docs/STAGE14_FINANCE_LIVE_CHECK.md`.
* **15** E-YAY live check, with your permission: only its HTTP API, from a code-only copy, paper-only
  and on its mock price feed; Commerce read it (4 browser runs on Chromium and WebKit) and degraded
  cleanly when it stopped; 27 requests served, all `GET` of the two documented endpoints;
  `C:\dev\clean-e-yay` proven unchanged (49,997 files, 0 differences). See
  `docs/STAGE15_EYAY_LIVE_CHECK.md`.
* **17** No Gmail/WhatsApp/social connector exists.

## 1. Status summary

| Area | Status | Evidence |
| ---- | ------ | -------- |
| Environment inspection | PASSED | §2 |
| Repository initialisation (Git, structure) | PASSED | commit `9ab289b` |
| Architecture documentation set | PASSED | 5 documents under `docs/` |
| Backend application (config, logging, errors, middleware) | PASSED | ruff, mypy, pytest |
| Database layer + session/transaction foundation | PASSED | integration tests |
| Alembic initial migration | PASSED | `upgrade head` → `0001_foundation` |
| `GET /api/v1/health/live` | PASSED | 200 manually + tests |
| `GET /api/v1/health/ready` (PostgreSQL) | PASSED | 200 with `PostgreSQL 17.6 … touche_app` |
| Two least-privilege DB roles | PASSED | `pg_roles` + privilege queries |
| Frontend shell (Next.js 16, dark premium UI) | PASSED | dev server + production build |
| Frontend displays real backend/DB status | PASSED | HTML assertions (nominal, degraded, unreachable) |
| OpenAPI → TypeScript generation | PASSED | deterministic regeneration, hashes identical |
| Backend tests | PASSED | 38 passed |
| Frontend tests | PASSED | 22 passed |
| Frontend lint / typecheck / format / build | PASSED | `scripts\verify.ps1` |
| Documentation updated | PASSED | this file + README |
| Docker Compose execution | BLOCKED | Docker is not installed on this workstation |
| GitHub Actions remote run | BLOCKED | no remote repository configured, no run performed |
| Cline / DeepSeek model check | BLOCKED | no provider credentials available in this environment |
| Authentication, sessions, RLS policies, audit | PASSED | Stage 1A — §11–§18 |
| CRM, catalogue, deal state machine, dashboard | PASSED | Stage 1B — §20 |
| Sourcing, landed cost, FX snapshots, sales quotes | PASSED | Stage 3 — §21 |
| Sales orders, procurement, shipments, trade documents | PASSED | Stage 4 — §22 |
| Finance read-only connector (Stage 5C) | PASSED | §24 — 20 connector + 18 API tests, isolated HTTP |
| Financial reconciliation (Stage 5D) | PASSED | §25 — evidence runs, review, discrepancies; isolated HTTP |
| Financial intelligence (Stage 5E) | PASSED | §26 — 402 backend / 160 frontend tests; isolated HTTP and a real-browser review (defects and cosmetic findings fixed; a few minor items remain, §26.6) |
| Accounting, payments, external integrations, AI assistants | NOT_STARTED | no accounting write path exists |

> This table records the **Stage 0** baseline. Stage 1A results are in
> §11–§19 below; the Stage 0 numbers were re-verified as a regression during
> Stage 1A (all Stage 0 tests still pass).

---

## 2. Environment detected

| Item | Detected value |
| ---- | -------------- |
| OS | Windows 11, kernel 10.0.26200, PowerShell 5.1 |
| Working directory | `C:\Users\twone\OneDrive\Desktop\touche-commerce` (empty at start, no Git repo) |
| Git | 2.55.0.windows.3 |
| Node.js / npm | v24.18.0 / 11.16.0 |
| Python / pip | 3.12.10 / 25.0.1 |
| Poetry / uv | not installed |
| Docker / Docker Compose | **not installed** |
| WSL | **not installed** (install prompt declined) |
| PostgreSQL | not installed system-wide → portable 17.6 used |
| Ports before start | 3000, 5432, 8000 all free |
| Cline provider credentials | `DEEPSEEK_API_KEY` absent (presence checked only; no secret was read) |

Resolution for the missing database: downloaded the official EDB PostgreSQL
17.6 Windows binaries into `infra/.local` (git-ignored), initialised a cluster in
`infra/.local/pgdata`, and started it on `127.0.0.1:5432`. The Docker path
remains the documented team default.

---

## 3. Completed items

### Repository and documentation

* Git repository initialised (`main`), `.gitignore`, `.env.example`,
  `README.md`, `frontend/`, `backend/`, `infra/`, `docs/`, `scripts/`,
  `.github/workflows/`.
* `docs/ARCHITECTURE.md`, `docs/API_CONTRACTS.md`, `docs/ROADMAP.md`,
  `docs/DECISIONS.md` (18 binding ADRs), `docs/PROGRESS.md`.

### Backend (Stage 0 scope only)

* `create_app()` factory, explicit validated settings (`TOUCHE_*`), `SecretStr`
  DSNs, production fail-safe checks.
* JSON logging with secret redaction and request-id injection; access log
  middleware implemented as raw ASGI middleware.
* Standard error envelope + handlers (404, 405, 422, 500, readiness 503) with
  `Cache-Control: no-store`.
* `GET /api/v1/health/live` (no DB dependency) and
  `GET /api/v1/health/ready` (real PostgreSQL probe, sanitised failures).
* SQLAlchemy engine/pool, session and transaction context managers,
  `apply_company_context()` SET LOCAL primitive, `touche.outbox_event` model.
* Alembic environment using the migration DSN and migration
  `0001_foundation` (schema `touche`, outbox table, indexes, least-privilege
  grants, revoked schema CREATE for the runtime role).
* CORS restricted to the local frontend origins.

### Infrastructure and scripts

* `infra/docker-compose.yml`: `postgres:17.6-alpine`, persistent named volume,
  health check, init hook sharing the role bootstrap SQL.
* `scripts/db/01-roles-and-database.sql`, `02-schema-grants.sql`,
  `bootstrap-roles.sh`, `bootstrap-local-postgres.ps1`,
  `start-local-postgres.ps1`, `stop-local-postgres.ps1`.
* `scripts/setup.ps1|sh`, `migrate.ps1|sh`, `dev-backend.ps1|sh`,
  `dev-frontend.ps1|sh`, `verify.ps1|sh`, `generate-api-types.ps1`.

### Frontend

* Next.js 16.4.2 App Router, React 19.3, TypeScript strict, Tailwind 4,
  shadcn/ui-style primitives (`button`, `card`, `badge`, `separator`), Lucide
  icons, `components.json`.
* Premium dark shell: charcoal/navy canvas, hairline grid, champagne accents,
  display-serif headings, compact sidebar with all nine requested placeholders
  labelled with their target stage (disabled, not dead links).
* Status screen with four real probes (frontend render, liveness, readiness,
  OpenAPI operations), explicit operational/degraded/unreachable states,
  request id, latency, DB role/version, remediation hints, "Re-check status".
* Transport-only typed client built on the generated OpenAPI types; pure status
  helpers; no fabricated KPIs or "connected" integration labels.

### CI

* `.github/workflows/ci.yml`: backend job with a PostgreSQL 17 service
  (roles bootstrap → Alembic → ruff → mypy → pytest), frontend job
  (format → lint → typecheck → vitest → build), contract-drift job.
  **Not executed remotely** (see blockers).

---

## 4. Pending items

Stage 1A (NOT_STARTED — waiting for instruction):

1. Migration `0002_identity`: `user`, `company`, `membership`, `session`,
   `audit_record`, `idempotency_record`, `login_attempt`, composite
   `UNIQUE (id, company_id)` + composite FKs, RLS policies.
2. Session service: hashed tokens, rotation, idle/absolute timeouts, CSRF,
   login rate limiting, logout, revocation.
3. `POST /api/v1/session/company` with membership verification, rotation and
   audit; membership removal revokes company-bound sessions.
4. Role/permission matrix with `finance.approve` independent from admin.
5. Audit writer (redacted, append-only) and idempotency/concurrency helpers.
6. Cleanup jobs for expired sessions and idempotency records.
7. RLS isolation matrix tests (design in `ARCHITECTURE.md §7.2`).
8. Frontend login/company switcher and permission-aware navigation (Stage 1B).

Stage 2+: trade workspace, orders, CRM/RFQ/quotes/products/logistics, finance,
integrations and AI Office — see `docs/ROADMAP.md`.

---

## 5. Blockers

| # | Blocker | Impact | Mitigation / required action |
| - | ------- | ------ | ---------------------------- |
| B1 | **Docker and Docker Compose are not installed** | `infra/docker-compose.yml` could not be executed; only YAML structure was validated | Stage 0 verified with portable PostgreSQL 17.6 (same role SQL). Install Docker Desktop, then `docker compose -f infra/docker-compose.yml up -d` and re-run `scripts/verify.ps1` |
| B2 | **No Git remote / no GitHub Actions run** | CI workflow is authored but unexecuted; remote success cannot be claimed | Create/authorise a remote, push `main`, then read the Actions result before claiming CI status |
| B3 | **Cline / DeepSeek provider check** — preferred model `deepseek-flash` at `https://api.deepseek.com`; no credentials/model configured here (`DEEPSEEK_API_KEY` absent) | Simple-response and file-edit tool verification could not be executed → `BLOCKED`; provider-specific tests stopped, project work unaffected | In Cline: API Provider → DeepSeek, Base URL `https://api.deepseek.com`, model `deepseek-flash` (or the account equivalent), paste the key into Cline's secret storage. Never put the key in `.env` or a committed file. Re-run a harmless prompt plus one file edit to confirm tool calls |
| B4 | No browser automation tool in this environment | Visual rendering could not be screenshot-verified | Verified by HTTP status, rendered-HTML assertions for nominal/degraded/unreachable, lint/typecheck and a production build. A human visual check of `http://localhost:3000` is recommended |
| B5 | No POSIX shell available on this Windows host | The `.sh` scripts and `bootstrap-roles.sh` could not be executed here (PowerShell equivalents were verified) | Author them as CI/Linux parity; validate on the first Linux run or in CI. `bash -n` / a Linux smoke run is still pending |

---

## 6. Commands executed (highlights)

```powershell
# Environment
python --version                  # Python 3.12.10
node --version                    # v24.18.0
npm --version                     # 11.16.0
git --version                     # 2.55.0.windows.3
docker --version                  # not recognised  -> B1

# Setup
git init -b main
python -m venv backend\.venv
backend\.venv\Scripts\python.exe -m pip install -e './backend[dev]'

# Database (portable PostgreSQL 17.6 because Docker is absent)
scripts\db\bootstrap-local-postgres.ps1
scripts\migrate.ps1                # alembic upgrade head

# Servers (equivalent to the published scripts)
backend\.venv\Scripts\python.exe -m uvicorn app.main:create_app --factory --host 127.0.0.1 --port 8000
npm run dev -- --port 3000         # from frontend/

# Verification
scripts\verify.ps1                 # ruff, mypy, pytest, prettier, eslint, typecheck, vitest, next build
scripts\generate-api-types.ps1     # export OpenAPI + openapi-typescript

# Git
git add -A; git commit             # 9ab289b7c00fd98946d290fe3da7fed88120b046
```

Manual checks used:

```powershell
Invoke-WebRequest http://127.0.0.1:8000/api/v1/health/live
Invoke-WebRequest http://127.0.0.1:8000/api/v1/health/ready
Invoke-WebRequest http://localhost:3000
psql -h 127.0.0.1 -U touche_admin -d touche_commerce -c "SELECT version_num FROM alembic_version;"
```

---

## 7. Actual test results

### Backend (`scripts\verify.ps1` → `python -m pytest`)

```
38 passed in 2.77s
tests/test_api_errors.py ........         (8)
tests/test_config.py ..........          (10)
tests/test_database_foundation.py ...... (6, live PostgreSQL integration)
tests/test_health_live.py .....          (5)
tests/test_health_ready.py ....          (4, includes live readiness)
tests/test_logging.py .....              (5)
```

* `ruff check .` → **All checks passed!**
* `mypy` → **Success: no issues found in 31 source files**
* Integration tests genuinely connected to PostgreSQL 17.6 as `touche_app`
  (no skips in this run).

### Frontend (`npm test`)

```
Test Files  3 passed (3)
Tests      22 passed (22)
  src/lib/status.test.ts                              (10)
  src/lib/api/client.test.ts                          (10)
  src/components/system-status/probe-card.test.tsx    (2)
```

* `npm run format:check` → all files use Prettier style
* `npm run lint` → 0 problems
* `npm run typecheck` → passed (`next typegen && tsc --noEmit`)
* `npm run build` → compiled successfully; `/` rendered as **dynamic** (ƒ)

### Manual HTTP / integration evidence

| Check | Result |
| ----- | ------ |
| `GET /api/v1/health/live` | `200` `{"status":"ok","service":"touche-commerce-api","version":"0.1.0","environment":"local",…}` with `X-Request-ID` |
| `GET /api/v1/health/ready` | `200`, detail `PostgreSQL 17.6 reachable as role 'touche_app'.` |
| `GET http://localhost:3000` | `200`, 88 044 bytes, contains "All probes nominal", "PostgreSQL 17.6", "touche_app", "operations exposed by the v1 document" |
| Backend stopped, page reloaded | `200` with "Unreachable", "API unreachable", "need attention" |
| PostgreSQL stopped, page reloaded | `200` with "Degraded", "Database not ready", `DATABASE_UNAVAILABLE`, "connection timeout" |
| PostgreSQL restarted, page reloaded | `200` with "All probes nominal" (no server restart required) |
| Alembic state | `version_num = 0001_foundation` |
| Role attributes | `touche_migrator` / `touche_app`: `rolsuper=f`, `rolbypassrls=f`, `rolcreatedb=f`, `rolcreaterole=f` |
| Privileges | app: SELECT/INSERT/DELETE on `touche.outbox_event`; `CREATE` on schema `touche` = **false** |
| OpenAPI regeneration | exported + regenerated twice with identical file hashes (`environment=test`, no DB needed) |
| Compose YAML | parses; services=`postgres`, image `postgres:17.6-alpine`, healthcheck and named volume present (semantics unexecuted — B1) |

### Resolved issues found during verification

1. `pg_ctl start/stop` blocked the shell on Windows → scripts redirect `pg_ctl`
   output to files and detach the server process.
2. SQL typo `\gexec;` aborted the role bootstrap after its first run → fixed and
   re-run (the script is idempotent).
3. Duplicate `[tool.setuptools]` table broke the editable install → pyproject
   corrected.
4. Starlette 1.9 `TestClient` requires `httpx2`; the dev extra now installs
   `httpx2` instead of `httpx`.
5. Readiness test raced the client timeout (both 5 s) → frontend probe timeout
   raised to 10 s and DB connect timeout reduced to 3 s, so a database outage
   renders as **Degraded** (verified).
6. Next.js 16 `cacheComponents` conflicted with per-request status rendering →
   disabled; the page is `force-dynamic`.
7. `status.ts` imported `./client` instead of `./api/client` → caught by
   `tsc --noEmit`, fixed.

---

## 8. Files changed (Stage 0)

100 files in the initial commit, grouped:

| Area | Files | Highlights |
| ---- | ----- | ---------- |
| Backend app | 24 | `app/main.py`, `core/{config,logging,errors,middleware,context}.py`, `db/{engine,health,tenant,models/*}.py`, `api/**` |
| Backend tooling | 19 | `alembic.ini`, `alembic/env.py`, `alembic/versions/20261022_0001_foundation.py`, `scripts/export_openapi.py` |
| Backend tests | 7 | `conftest.py` plus API/health/config/logging/DB integration suites |
| Frontend | 35 | `src/app/{layout,page,globals.css}`, `components/{shell,ui,system-status}`, `lib/{api,status,navigation,utils}`, tests, generated schema, configs |
| Scripts | 19 | setup/migrate/dev/verify/generate-api-types + DB bootstrap (PowerShell & bash) |
| Infra | 2 | `infra/docker-compose.yml`, `infra/postgres/init/01-roles.sh` |
| Docs | 5 | `ARCHITECTURE`, `API_CONTRACTS`, `ROADMAP`, `DECISIONS`, `PROGRESS` |
| CI / root | 4 | `.github/workflows/ci.yml`, `.gitignore`, `.env.example`, `README.md` |

Resolved dependency versions (installed): FastAPI 0.159.1 · Pydantic 2.14.1 ·
pydantic-settings 2.16.1 · SQLAlchemy 2.1.6 · Alembic 1.20.0 · psycopg 3.3.6 ·
Uvicorn 0.54.0 · pytest 9.1.1 · ruff 0.17.1 · mypy 2.4.0 · httpx2 2.16.0 ·
Next.js 16.4.2 · React 19.3.0 · TypeScript 5.x · Tailwind CSS 4.x ·
Vitest 5.0.5 · openapi-typescript 7.13.0 · PostgreSQL 17.6.

---

## 9. Git

* Branch: `main`
* Stage 0 implementation commit: **`9ab289b7c00fd98946d290fe3da7fed88120b046`**
  (`feat(stage0): foundation for TOUCHE COMMERCE (Next.js + FastAPI + PostgreSQL)`)
* This progress record is committed in the follow-up `docs:` commit.
* No remote is configured; nothing was pushed. No existing repository was
  modified (the workspace was empty).

---

## 10. Next recommended task (as recorded at the end of Stage 0)

**Stage 1A — milestone 1A.1: identity schema + RLS foundation.**

> **Superseded.** Stage 1A was started on explicit instruction and is complete
> (see §11–§19). The next recommended task is now Stage 1B, recorded in §19.

Original first steps (all completed):

1. Add migration `0002_identity` creating `app_user`, `company`, `membership`,
   `auth_session`, `audit_record`, `idempotency_record`, `login_attempt` with
   `UNIQUE (id, company_id)` and composite FKs.
2. Enable RLS + policies on tenant-owned tables (`current_setting` based), keep
   `touche_app` without `BYPASSRLS`, grant only DML.
3. Implement the RLS isolation matrix tests from `ARCHITECTURE.md §7.2` **before**
   any endpoint is written, then the session/company services.

Verification gate for 1A.1 (met): two seeded companies cannot see or mutate each
other's rows; no context means no rows; all tests run on a real PostgreSQL.





---

# Stage 1A — Identity, authentication, authorization and multi-company isolation

**Started:** 22 Oct 2026 · **Completed:** 22 Oct 2026 (verified locally)
**Scope guardrails honoured:** no business features, no CRM/deals/quotes/logistics,
no financial integrations, no AI agents, Stage 1B not started.

## 11. Status summary

| Area | Result |
| ---- | ------ |
| Database | `0002_identity` applied to `touche_commerce` and `touche_commerce_test` |
| Authentication | login / logout / me implemented with Argon2id + server-side sessions |
| Company selection | `GET /companies`, `POST /session/company` with rotation |
| Tenant isolation | RLS on 6 tables, 16 live isolation tests green |
| Audit | append-only, 8 action types, redacted details, `request_id` correlation |
| Frontend | `/login`, `/select-company`, authenticated shell, `/account`, public `/status` |
| Backend tests | **120 passed** (38 Stage 0 + 82 Stage 1A) |
| Frontend tests | **45 passed** (22 Stage 0 + 23 Stage 1A) |
| Live identity checks | **31/31 passed** (`scripts\verify-identity.ps1`) |
| Lint / typecheck / build | backend ruff + mypy clean; frontend eslint + tsc + `next build` clean |
| Contract determinism | `scripts\generate-api-types.ps1 -Check` re-run after commit (see §19) |

Stage 0 acceptance criteria remain satisfied; the Stage 0 regression suite is part
of the same run.

## 12. Database changes

Migration: `backend/alembic/versions/20261022_0002_identity.py`
(`revision = "0002_identity"`, `down_revision = "0001_foundation"`).

New tables (schema `touche`):

| Table | Key elements |
| ----- | ------------ |
| `app_user` | UUID PK, unique normalised `email` (`CHECK email = lower(email)`), `password_hash`, `status`, `last_login_at`, timestamps |
| `company` | UUID PK, `name`, ISO-3166 `country`, ISO-4217 `default_currency`, `status`, timestamps |
| `membership` | `(user_id, company_id)` unique, `role` CHECK (viewer/trader/approver/admin), `status` + `revoked_at` consistency CHECK, `UNIQUE (id, company_id)` for future composite FKs |
| `auth_session` | `token_hash` (64 hex, unique), `csrf_token`, `user_id`, nullable `company_id`, `created_at`, `last_activity_at`, `expires_at`, `revoked_at`, `revoked_reason`, `ip_address inet`, `user_agent` |
| `login_attempt` | `email_normalized`, `ip_address`, `succeeded`, `reason`, `attempted_at` + rate-limit indexes |
| `audit_record` | `actor_type`, `actor_id`, nullable `company_id` (FK RESTRICT), `action` CHECK, `outcome`, `request_id`, `occurred_at`, `ip_address`, `user_agent`, `resource_*`, JSONB `details` |
| `idempotency_record` | unique `(actor_id, company_id, key)`, fingerprint, status, response snapshot, expiry (middleware in 1B/2) |
| `company_settings` | one row per company, `UNIQUE (id, company_id)` (composite-FK target) |
| `company_setting_entry` | `(settings_id, company_id)` composite FK → `company_settings`, unique `(settings_id, key)` |

Functions and policies:

* `touche.current_company_id()` / `touche.current_actor_id()` — `STABLE` SQL
  functions returning `NULL` when the transaction-scoped setting is absent.
* RLS enabled on `company`, `membership`, `company_settings`,
  `company_setting_entry`, `idempotency_record`, `audit_record` with explicit
  SELECT/INSERT/UPDATE/DELETE policies (no implicit `ALL` policy).
* `company` read policy requires an active membership for the actor; `membership`
  read policy allows own rows or the active company.
* `audit_record`: tenant-scoped SELECT; INSERT allowed with
  `company_id IS NULL` or the active company; no UPDATE/DELETE policy.
* Append-only enforcement: grants `SELECT, INSERT` only for `touche_app`,
  `REVOKE UPDATE/DELETE/TRUNCATE`, plus `touche.reject_audit_mutation()` triggers
  for `UPDATE`, `DELETE` and `TRUNCATE` (owner included).
* Grants: DML on all tables except audit; no `CREATE` on the schema; no
  `TRUNCATE`.

Seed/demo data is **not** part of the migration. Two companies, two users and
their memberships were created in the local environment with the privileged CLI
(§15).


## 13. API and frontend delivered

Backend (`backend/app`):

* `security/passwords.py` — Argon2id hashing, policy, dummy verification,
  `needs_rehash`.
* `security/tokens.py` — 256-bit session/CSRF tokens, SHA-256 digests,
  constant-time comparison.
* `security/permissions.py` — `Role`, `Permission`, matrix with a module-level
  assertion that `admin` never holds `finance.approve`.
* `db/models/{identity,audit,tenant_data}.py` + registry; `db/tenant.py` extended
  with actor context, `clear_tenant_context`, `current_actor_setting`.
* `services/audit.py` — single writer, redaction, bounded values, Core INSERT.
* `services/auth.py` — login, resolve, switch_company, logout, rate limiting,
  expiry/revocation with audit, membership re-validation.
* `services/admin.py` — bootstrap/grant/revoke/list primitives (also used by tests).
* `api/security.py` — `current_session`, `require_csrf`, `require_permission`,
  `require_company_context`, client IP/User-Agent extraction.
* `api/v1/{cookies,presenters}.py`, `schemas/auth.py`, `routes/{auth,companies}.py`.
* `core/middleware.py` — `OriginValidationMiddleware`.
* `core/config.py` — cookie policy, Argon2 cost, password policy, rate limits,
  test database name, derived test DSNs.
* `core/errors.py` — `SESSION_EXPIRED`, `ORIGIN_REJECTED`, `CSRF_REJECTED` and
  their exception classes.
* `cli.py` — `bootstrap`, `create-user`, `create-company`, `membership
  grant/revoke`, `set-password`, `list`.
* `alembic/versions/20261022_0002_identity.py`.

Frontend (`frontend/src`):

* `app/api/v1/[...path]/route.ts` — allow-listed same-origin proxy (cookie +
  `Set-Cookie` forwarding, `no-store`, JSON 502 on upstream failure).
* `app/(auth)/{layout,login,select-company}` — premium split sign-in and company
  selection screens.
* `app/(app)/{layout,page,account}` — authenticated shell, Command Center, account
  page; `app/status/page.tsx` — public read-only status.
* `components/auth/{login-form,logout-button,company-switcher,account-summary,session-unavailable}`.
* `components/ui/{input,label,alert}.tsx`; sidebar/top-bar now show identity and
  company.
* `lib/auth/{types,guard,session,client}.ts`; `lib/navigation.ts` updated;
  `src/proxy.ts` adds `x-pathname`.
* `lib/api/config.ts` adds `API_PROXY_TARGET` / `BROWSER_API_PREFIX`.

Scripts: `scripts/db/setup-test-database.ps1`, `scripts/bootstrap-admin.ps1`,
`scripts/bootstrap-admin.sh`, `scripts/verify-identity.ps1`.

## 14. Milestones executed (in order)

1. **Inspection** — read the repository, all five docs, migrations, tests and
   scripts; confirmed Stage 0 baseline (38 backend / 22 frontend tests).
2. **Schema** — models, migration `0002_identity`, RLS helpers, policies,
   triggers, grants; migrated `touche_commerce`.
3. **Security core** — Argon2id service, token helpers, permission matrix.
4. **Services** — audit writer, auth service, admin service.
5. **API** — schemas, presenters, cookie helpers, routes, Origin middleware,
   dependency wiring.
6. **CLI** — bootstrap and membership administration (no default passwords).
7. **Tests** — isolated test database fixture, unit tests, auth/session
   integration tests, RLS isolation matrix; fixed three real defects (§16).
8. **Contract** — exported OpenAPI and regenerated `schema.d.ts`.
9. **Frontend** — proxy, auth libraries, login/select-company/shell/account/status
   screens, 23 tests.
10. **Live verification** — restarted API and web shell, bootstrapped two
    companies + two users via CLI, ran `verify-identity.ps1` (31/31) and the
    revocation scenario (session revoked, next request 401, colleague unaffected).
11. **Regression** — full backend and frontend suites, lint, typecheck, build.
12. **Documentation** — README, ARCHITECTURE, API_CONTRACTS, ROADMAP, DECISIONS,
    PROGRESS.


## 15. Actual test results and live verification

### 15.1 Backend — `backend\.venv\Scripts\python -m pytest -q`

```
........................................................................ [ 60%]
................................................                         [100%]
120 passed
```

Breakdown:

| File | Tests | Type |
| ---- | ----- | ---- |
| `test_api_errors.py`, `test_config.py`, `test_health_live.py`, `test_health_ready.py`, `test_logging.py` | 38 | Stage 0 unit/integration (regression) |
| `test_security_primitives.py` | 38 | unit: Argon2id, tokens, permissions, redaction, config, CSRF context |
| `test_auth_api.py` | 27 | integration: login, sessions, CSRF, Origin, rate limit, switch, revocation, audit |
| `test_rls_isolation.py` | 16 | integration: RLS matrix with the runtime role |
| `test_database_foundation.py` (existing) | included above | migration head + role checks |

* `ruff check .` → `All checks passed!`
* `mypy` → `Success: no issues found in 54 source files`
* Integration tests run against `touche_commerce_test` only (DSN derived by
  swapping the database name; schema upgraded by the session fixture).

### 15.2 Frontend — `npm test`, `npm run lint`, `npm run typecheck`, `npm run build`

```
Test Files  8 passed (8)
     Tests  45 passed (45)
```

| File | Tests |
| ---- | ----- |
| `client.test.ts` | 10 (Stage 0) |
| `status.test.ts` | 10 (Stage 0) |
| `probe-card.test.tsx` | 2 (Stage 0) |
| `guard.test.ts` | 9 (route guard + `next` sanitisation) |
| `login-form.test.tsx` | 7 (validation, success routing, generic error, rate limit, no storage) |
| `company-switcher.test.tsx` | 4 (listing, active state, switch, refusal) |
| `logout-button.test.tsx` | 2 |
| `account-summary.test.tsx` | 2 |

* `npm run lint` → clean (0 warnings)
* `npm run typecheck` → clean (`next typegen && tsc --noEmit`)
* `npm run build` → routes `/`, `/account`, `/api/v1/[...path]`, `/login`,
  `/select-company`, `/status`; all dynamic where required.

### 15.3 Live HTTP verification — `scripts\verify-identity.ps1`

31/31 checks passed against the running API (`127.0.0.1:8000`) and web shell
(`localhost:3000`). Recorded output (abridged):

```
==> Direct API checks
  [pass] GET /health/live returns 200 -> HTTP 200
  [pass] GET /health/ready returns ready -> HTTP 200
  [pass] login without Origin is rejected -> HTTP 403 ORIGIN_REJECTED
  [pass] invalid credentials return the generic 401 -> HTTP 401
  [pass] login succeeds -> HTTP 200
  [pass] session cookie is HttpOnly
  [pass] session cookie is SameSite=Lax
  [pass] login body carries no token or password hash
  [pass] login body exposes memberships -> 2 membership(s)
  [pass] CSRF token issued
  [pass] GET /auth/me returns the actor -> HTTP 200
  [pass] GET /companies lists only memberships -> 2 company(ies)
  [pass] company switch without CSRF is rejected -> HTTP 403 CSRF_REJECTED
  [pass] company switch succeeds -> HTTP 200
  [pass] session token rotated on switch
  [pass] switch to a non-member company is forbidden -> HTTP 403 FORBIDDEN
  [pass] logout succeeds -> HTTP 200
  [pass] session is invalid after logout -> HTTP 401

==> Same-origin proxy and web shell
  [pass] GET /login renders -> HTTP 200
  [pass] unauthenticated /account redirects to login -> HTTP 307 -> /login?next=%2Faccount
  [pass] public /status renders without a session -> HTTP 200
  [pass] login through the same-origin proxy succeeds -> HTTP 200
  [pass] proxy forwards Set-Cookie intact
  [pass] proxy login answer contains no token
  [pass] multi-company session is sent to company selection -> HTTP 307 -> /select-company
  [pass] company switch works through the proxy -> HTTP 200
  [pass] authenticated dashboard renders the signed-in user -> HTTP 200
  [pass] authenticated /account renders -> HTTP 200
  [pass] proxy preserves CSRF rejection -> HTTP 403 CSRF_REJECTED
  [pass] logout through the proxy succeeds -> HTTP 200
  [pass] dashboard redirects to login after logout -> HTTP 307 -> /login?next=%2F

All identity checks passed.
```

### 15.4 Live membership revocation

```
auto_selected_company=Meridian Commodities role=trader
me_before=bilal@touche.example
Membership revoked
  Sessions revoked  1
me_after=401
memberships_after_revocation=0
```

The membership was re-granted afterwards; logging in again auto-selected the
company with the `trader` role. No company, user or membership beyond this
scenario was changed.

### 15.5 Audit rows observed in `touche_commerce`

```
action                  | outcome | count | rows with company
access.denied           | denied  |     2 | 0
auth.login.failure      | failure |     2 | 0
auth.login.success      | success |     8 | 2
auth.logout             | success |     4 | 4
membership.changed      | success |     5 | 5
session.company.switch  | success |     4 | 4
session.revoked         | success |     1 | 1
```

Sample `details` (verified free of credentials/emails): `{"reason":
"invalid_password"}`, `{"reason": "membership_revoked", "count": 1}`,
`{"membership_count": 1, "company_auto_selected": true}`.

### 15.6 Local credentials

The local administrator password was supplied through `--password-stdin` during
verification and is **not** recorded here, in `.env.example` or in any script.
There is no default password; `scripts\bootstrap-admin.ps1` prompts with hidden
input and enforces the policy.


## 16. Issues found and fixed during Stage 1A

1. **Audit insert blocked by the read policy.** PostgreSQL applies the SELECT
   policy to `INSERT ... RETURNING`, so a system-level audit row
   (`company_id IS NULL`) failed with "new row violates row-level security
   policy". Fixed by inserting audit rows with a Core `INSERT`, a client-side
   UUID and **no** `RETURNING`, keeping the read policy strict (ADR-009/023).
2. **Doubled CHECK constraint names.** The Stage 0 naming convention prefixed
   `ck_%(table_name)s_` while authored names already carried the table prefix,
   producing `ck_auth_session_ck_auth_session_expiry_order`. The convention now
   emits `%(constraint_name)s`; the test database was recreated and re-migrated.
3. **Stale Next.js type artefacts.** Deleting `src/app/page.tsx` left
   `.next/dev/types/validator.ts` referencing it; `tsc` failed until `.next` and
   `tsconfig.tsbuildinfo` were removed.
4. **`middleware.ts` deprecation.** Next.js 16 warns in favour of the `proxy`
   file convention; renamed `src/middleware.ts` → `src/proxy.ts` with a `proxy()`
   export (build warning gone).
5. **Stale Stage 0 assertions.** Two Stage 0 tests encoded Stage 0 assumptions:
   the 405 test now sends a trusted `Origin` (Origin validation is new), and the
   migration test asserts the *current head* discovered from `alembic/versions`
   instead of a hardcoded revision. A new test asserts that a stateless `POST`
   without `Origin` is rejected.
6. **Shell environment leakage while verifying.** A `TOUCHE_DATABASE_MIGRATION_URL`
   exported in an earlier terminal step caused one CLI run to write fixtures into
   the test database. Detected by inspecting both databases; the test database is
   reset by its fixture anyway, and all subsequent commands set the DSNs
   explicitly. Documented here so it is not repeated.
7. **Verification-script assumptions.** The script initially assumed a dashboard
   render immediately after login (multi-membership accounts are correctly sent to
   `/select-company` first) and looked up API cookies under the web origin. Both
   assumptions were corrected in the script, not worked around in the app.
8. **Windows PowerShell 5.1** does not load `System.Net.Http` automatically and
   strips embedded quotes when passing JSON to native `curl.exe`; the script adds
   `Add-Type -AssemblyName System.Net.Http` and uses `HttpClient` instead of
   shelling out.

## 17. Security limitations (explicit)

| Limitation | Impact | Mitigation / target |
| ---------- | ------ | ------------------- |
| `app_user`, `auth_session`, `login_attempt` are not RLS-protected | A compromised runtime role could read them (`NOBYPASSRLS` does not help: no policies exist) | No API exposure; separate secrets; ADR-023; `SECURITY DEFINER` functions required before any exposure |
| No CSRF protection for `GET` (correct) and no per-request nonce | Idempotent reads can be triggered cross-site | Reads expose only the caller's own data; mutations require Origin + CSRF |
| Login rate limiting is per account + per source IP, not distributed | A botnet with many IPs can spread attempts | Database-backed counters; add IP reputation/WAF at the platform edge |
| Pending: no MFA, no password reset, no invitation flow | Operators set passwords manually | Stage 1B+; no partial UI is exposed |
| Pending: no idempotency middleware | A retried mutation would execute twice | No mutating business endpoint exists yet; table + contract ready |
| Pending: no session/idempotency cleanup job | Expired rows accumulate | Expiry is enforced synchronously on use; job deferred (ADR-016) |
| Audit retention not enforced | Audit grows without bound | Deliberate: the append-only trigger must be disabled by the owner; policy decision deferred |
| Access tokens never appear in the browser | — | Cookie only; verified in tests and live checks |
| Browser automation unavailable | No real-browser click-through evidence | HTTP-level verification + server-rendered HTML assertions; recorded honestly (§15.3) |

Known environmental blockers carried forward from Stage 0: Docker/Compose not
installed, no git remote (CI never executed remotely), no POSIX shell on the host
(`.sh` scripts unexecuted), no browser automation.


## 18. Files changed (Stage 1A)

Backend (new unless noted): `app/security/{__init__,passwords,tokens,permissions}.py`,
`app/db/models/{identity,audit,tenant_data}.py`,
`app/services/{__init__,audit,auth,admin}.py`,
`app/api/security.py`, `app/api/v1/{cookies,presenters}.py`,
`app/api/v1/schemas/auth.py`, `app/api/v1/routes/{auth,companies}.py`,
`app/cli.py`, `alembic/versions/20261022_0002_identity.py`,
`tests/{__init__,support}.py`, `tests/test_security_primitives.py`,
`tests/test_auth_api.py`, `tests/test_rls_isolation.py`.
Modified: `app/core/{config,errors,middleware}.py`, `app/main.py`,
`app/api/v1/router.py`, `app/db/{engine,tenant}.py`,
`app/db/models/{__init__,base}.py`, `pyproject.toml`, `tests/conftest.py`,
`tests/test_api_errors.py`, `tests/test_config.py`,
`tests/test_database_foundation.py`.

Frontend: `src/app/api/v1/[...path]/route.ts`,
`src/app/(auth)/{layout,login/page,select-company/page}.tsx`,
`src/app/(app)/{layout,page,account/page}.tsx`, `src/app/status/page.tsx`,
`src/app/layout.tsx`, `src/proxy.ts`, `src/components/auth/*` (5 components +
4 test files), `src/components/ui/{input,label,alert}.tsx`,
`src/components/shell/{app-sidebar,top-bar}.tsx`,
`src/lib/auth/{types,guard,session,client}.ts`, `src/lib/auth/guard.test.ts`,
`src/lib/navigation.ts`, `src/lib/api/config.ts`, `openapi/openapi.json`,
`src/lib/api/schema.d.ts`, `package.json`/`package-lock.json`
(`@testing-library/user-event`).

Scripts/docs: `scripts/db/setup-test-database.ps1`,
`scripts/bootstrap-admin.{ps1,sh}`, `scripts/verify-identity.ps1`,
`.env.example`, `frontend/.env.example`, `README.md`,
`docs/{ARCHITECTURE,API_CONTRACTS,ROADMAP,DECISIONS,PROGRESS}.md`.

Deleted: `frontend/src/app/page.tsx` (moved into `(app)/page.tsx`),
`frontend/src/middleware.ts` (renamed to `proxy.ts`).

## 19. Git and next task

* Branch `main`.
* Stage 1A implementation commit: **`16c5860`**
  (`feat(stage1a): identity, sessions, authorization and multi-company isolation`,
  87 files changed, 10 384 insertions, 619 deletions).
* Follow-up documentation commit records this report (the commit that contains
  this section).
* `scripts\generate-api-types.ps1 -Check` was re-run **after** the implementation
  commit and reported "generated API types are up to date" (contract is
  deterministic).
* Nothing pushed: no remote is configured, and pushing requires explicit approval.

**Next recommended task: Stage 1B — product UI foundation** (only on explicit
instruction). Prerequisites already in place: session context on the server,
permission-aware navigation data, generated types, design primitives.

Stage 1B candidates, in order: design-system expansion (form fields, table,
dialog, toast), permission-aware navigation driven by `permissions`, settings
screens backed by `company_settings` with `If-Match`/`version`, membership and
audit read APIs for admins, idempotency middleware on the first mutating endpoint,
session/idempotency cleanup command, and password reset/invitation flows.

Do not start Stage 1B automatically.



---

## 20. Stage 1B — trade workspace (executed 2026-10-22)

### 20.1 Scope delivered

| Part | Delivered |
| ---- | --------- |
| 1. Schema | `0003_trade`: `counterparty`, `product`, `deal`, `deal_item`, `deal_transition`; RLS, composite FKs, versions, CHECK constraints, append-only history |
| 2. State machine | Explicit graph, terminal states with mandatory reasons, `WON` disabled, row-locked transitions, atomic history + audit, `PATCH` status bypass blocked |
| 3. APIs | Counterparties/products/deals CRUD (header updates), transitions, dashboard; permissions, cursor pagination, `ETag`/`If-Match`, transactional `Idempotency-Key`, request ids, audit |
| 4/5. Frontend | `/crm`, `/products`, `/deals`, `/deals/new`, `/deals/[id]`, live dashboard, permission-aware affordances, dark premium design |
| 7. Demo data | `python -m app.cli seed-demo` (local/test/ci only, explicit, labelled, non-destructive) |
| 8/9. Verification | Backend 191 tests, frontend 60 tests, contract generation, production build, 15-step live workflow (39 checks) |
| 11. Documentation | This section, ARCHITECTURE §19, API_CONTRACTS §3–5/§7, ADR-024…027, ROADMAP |

### 20.2 Milestones

| Milestone | Status | Evidence |
| --------- | ------ | -------- |
| M1B.1 Migration `0003_trade` applies and reverses | PASSED | `alembic upgrade head`, `downgrade -1`, `upgrade head`, `alembic_version = 0003_trade` |
| M1B.2 RLS + composite FKs enforce tenant isolation | PASSED | `test_trade_api.py::TestTenantIsolation` (4 tests) |
| M1B.3 State machine validated server-side | PASSED | `test_deal_state.py` (14), `TestTransitions` (8) |
| M1B.4 Idempotent, replay-safe transitions | PASSED | `TestIdempotency` (4) + live replay step |
| M1B.5 Optimistic concurrency | PASSED | 428/409/200 `If-Match` matrix in tests and live workflow |
| M1B.6 Permission model (trader writes, others read) | PASSED | 403 assertions for admin/viewer, live admin 403 |
| M1B.7 Frontend pages render real API data | PASSED | build + server-render checks (`/`, `/crm`, `/products`, `/deals`, `/deals/new`, `/deals/{id}`) |
| M1B.8 Audit trail records trade actions | PASSED | `TestAudit` + SQL query of `touche.audit_record` |
| M1B.9 Demo seeding is guarded | PASSED | `test_cli_seed.py` (9), environment gate |
| M1B.10 Contract generation deterministic | PASSED | `generate-api-types.ps1 -Check` after the implementation commit |
| M1B.11 Docker Compose path | BLOCKED | Docker is not installed on this workstation |
| M1B.12 Remote CI run | BLOCKED | no git remote configured |

### 20.3 Database changes

* New revision `0003_trade` (revises `0002_identity`).
* Tables and indexes as listed in ARCHITECTURE §6.1; each trade table has four
  RLS policies driven by `touche.current_company_id()`.
* `deal_transition` grants only `SELECT, INSERT` to `touche_app` (append-only).
* `idempotency_record` gained `endpoint` and
  `UNIQUE (actor_id, company_id, endpoint, key)` (ADR-026).
* `ck_audit_action` was widened with `counterparty.created`, `counterparty.updated`,
  `product.created`, `product.updated`, `deal.created`, `deal.updated`,
  `deal.transitioned`.
* Executed verification: `upgrade` → `downgrade -1` → `upgrade` succeeded on the
  isolated test database; the development database was migrated in place without
  dropping data (2 companies and 3 users preserved).

Live schema evidence (development database):

```
revision: 0003_trade
trade tables: counterparty, product, deal, deal_item, deal_transition
app grants: counterparty:DELETE,INSERT,SELECT,UPDATE
            product:DELETE,INSERT,SELECT,UPDATE
            deal:DELETE,INSERT,SELECT,UPDATE
            deal_item:DELETE,INSERT,SELECT,UPDATE
            deal_transition:INSERT,SELECT
```


### 20.4 Commands executed and actual results

| # | Command | Result |
| - | ------- | ------ |
| 1 | `backend\.venv\Scripts\python.exe -m alembic upgrade head` (test DB) | `0002_identity → 0003_trade` |
| 2 | `alembic downgrade -1` then `alembic upgrade head` | both succeeded (reversible) |
| 3 | `alembic upgrade head` (development DB, `.env` loaded) | `alembic_version = 0003_trade` |
| 4 | `python -m ruff check .` (backend) | `All checks passed!` |
| 5 | `python -m mypy` (backend, strict) | `Success: no issues found in 73 source files` |
| 6 | `python -m pytest -q --junitxml=…` (backend) | **tests=191 failures=0 errors=0 skipped=0** |
| 7 | `python -m app.cli seed-demo` | guard tests 9 passed; executed once with `--force`, creating a clearly labelled demo set |
| 8 | `scripts\generate-api-types.ps1` | `openapi.json` + `schema.d.ts` regenerated (16 paths) |
| 9 | `npm run format` / `format:check` | passed |
| 10 | `npm run lint` | `eslint .` clean |
| 11 | `npm run typecheck` | `next typegen && tsc --noEmit` clean |
| 12 | `npm test` | **11 files, 60 tests passed** |
| 13 | `npm run build` | compiled; routes `/`, `/crm`, `/products`, `/deals`, `/deals/new`, `/deals/[id]` present |
| 14 | `backend\.venv\Scripts\python.exe scripts\verify_trade_workflow.py` | **39/39 checks passed** (see §20.5) |
| 15 | `scripts\generate-api-types.ps1 -Check` | passed after the implementation commit (no drift) |

Backend test groups added in Stage 1B (71 tests): `test_deal_state` 14,
`test_pagination_idempotency` 15, `test_trade_api` 33, `test_cli_seed` 9.
Frontend tests added (15): `trade/format.test.ts` 6, `trade/client.test.ts` 4,
`transition-panel.test.tsx` 5.

### 20.5 Live 15-step workflow (development database, real HTTP)

Executed with `scripts\verify-trade.ps1` (wrapper) →
`backend/scripts/verify_trade_workflow.py`; 39 checks, all passed:

1. trader sign-in, auto-selected company, role `trader`, `trade.write` present;
2. counterparty created, `ETag "v1"`;
3. product created;
4. deal created as `DRAFT`, total `61250.00`, one history row, allowed
   `["OPEN","CANCELLED"]`;
5. list search finds it; detail returns `ETag "v1"`;
6. `PATCH` without `If-Match` → 428; with `"v1"` → v2; stale `"v1"` → 409
   `VERSION_CONFLICT`;
7. `PATCH {"status":"WON"}` → 422 `VALIDATION_ERROR`, deal still `DRAFT`;
8. transition without key → 400 `IDEMPOTENCY_KEY_REQUIRED`;
9. `DRAFT → OPEN`, two history rows;
10. `OPEN → NEGOTIATION`;
11. `→ WON` → 409 `TRANSITION_DISABLED`, deal unchanged;
12. `→ LOST` without reason → 422 `REASON_REQUIRED`;
13. `→ LOST` with reason → 200, `closed_at` set, no targets left, reason stored;
14. replay of the same key → `Idempotent-Replay: true`, identical body, history
    unchanged; a further transition → 409 `INVALID_TRANSITION`;
15. foreign administrator: 404 for the deal, absent from its list, 403 on write;
    dashboard scoped to the trader company and showing `deal.transitioned`.

Frontend: `/deals/{id}` returned 200 and the rendered HTML contained the deal
reference and the terminal status; `/`, `/crm`, `/products`, `/deals` and
`/deals/new` also returned 200 with their expected headings.

Database evidence after the runs (development database):

```
trade rows: counterparty=5 product=5 deal=5 deal_item=5 deal_transition=11
audit actions: deal.transitioned, deal.updated, deal.created, product.created, counterparty.created
idempotency_record: 25 completed
latest deal: T-2610-74633A  LOST  version 5  closed_at set
```

A later, explicitly requested `seed-demo --force` run added one labelled demo set
(3 counterparties, 3 products, 3 deals), so the live counts now exceed the numbers
above; nothing was deleted or overwritten.


### 20.6 Issues found and fixed during Stage 1B

| Issue | Resolution |
| ----- | ---------- |
| First draft allowed `status` through `PATCH` | Update schemas use `extra="forbid"` and the service refuses closed deals; tested live and in unit tests |
| Dashboard mixed currencies into one number | Pipeline is grouped per currency; per-status values stay per deal |
| Idempotency row could outlive a failed request | One transaction for record + change; rollback removes the row |
| `If-Match` parsing would have accepted an unquoted value silently | `parse_if_match` accepts `"v7"` and `v7` but rejects anything else with 400 |
| PowerShell 5.1 could not read error bodies reliably for the workflow | Verification moved to dependency-free `backend/scripts/verify_trade_workflow.py`; the `.ps1` is a thin wrapper |
| Cursor reuse across filters returned a misleading page | Cursors embed a filter fingerprint and are rejected with 422 |

### 20.7 Blockers (unchanged, environmental)

| Item | Status | Reason |
| ---- | ------ | ------ |
| Docker / Compose execution | BLOCKED | Docker is not installed; the portable PostgreSQL 17.6 cluster is used |
| Remote CI (`api-contract`, backend, frontend jobs) | BLOCKED | no git remote configured; workflow exists and was not executed remotely |
| POSIX shell scripts (`.sh`) | BLOCKED | no POSIX shell on this host; PowerShell paths were used |
| Browser automation (Playwright) | BLOCKED | not installed; verification uses HTTP + server-rendered HTML |
| DeepSeek/Cline provider check | BLOCKED | no credentials in this environment |

### 20.8 Deliberate deviations from the earlier Stage 1B plan

The original roadmap described Stage 1B as a "product UI foundation" (settings
screens, design-system expansion, invitations). The instruction for this stage
was a full trade workflow, so the following roadmap items remain **not
implemented** and are recorded in `docs/ROADMAP.md`:

* `company_settings` screens with `If-Match`/`version`;
* membership and audit read APIs with an admin UI;
* invitation, password reset and MFA flows;
* idempotency/session cleanup scheduler;
* documents interface, dialogs and toasts beyond what the trade screens need.

### 20.9 Local development accounts used for verification

Created with `python -m app.cli` in the **development** database only:

| Account | Role | Company | Purpose |
| ------- | ---- | ------- | ------- |
| `stage1b.trader@touche.example` | trader | Meridian Commodities | write workflow |
| `stage1b.admin@touche.example` | admin | TOUCHE Trading | cross-tenant and read-only checks |

Passwords were supplied through the environment
(`TOUCHE_VERIFY_TRADER_PASSWORD`, `TOUCHE_VERIFY_ADMIN_PASSWORD`) and are not
stored in the repository. They are throw-away local credentials.

### 20.10 Git and next task

* Branch `stage-1b`, created from `main` at `16a0ab5`.
* Implementation commit: **`c510722`**
  (`feat(stage1b): CRM, catalogue and a validated deal workspace`,
  57 files changed, 13 714 insertions, 755 deletions).
* Documentation commit: the commit that contains this section (immediately after
  `c510722`; amending it changes the documentation hash only).
* `scripts\generate-api-types.ps1 -Check` was re-run after the implementation
  commit and reported "generated API types are up to date".
* Nothing pushed: no remote is configured.

**Next recommended task: Stage 2 — sales orders and the `WON` transition**
(only on explicit instruction). Prerequisites in place: the deal aggregate, its
state machine and history, transactional idempotency, and the outbox table.

Do not start Stage 2 automatically.



---

## 21. Stage 3 - sourcing, landed cost and sales quotes (executed 2026-10-22)

### 21.1 Scope delivered

| Part | Delivered |
| ---- | --------- |
| Schema | `0004_sourcing`: 12 tables (FX, RFQ + items + revisions, supplier quote + items + revisions, pricing scenario + components, sales quote + items + revisions), RLS, composite FKs, append-only revision grants, widened audit action CHECK |
| Engine | Pure `pricing_engine` (explicit FX, largest-remainder allocation, LINE/ORDER costs, margin or markup, derived status, calculation version) |
| Services | `fx`, `rfqs`, `supplier_quotes`, `pricing`, `sales_quotes` with audit, idempotency, ETags, revision snapshots |
| API | 29 endpoints across FX, RFQs, supplier quotes, pricing scenarios and sales quotes; permissions and error codes per API_CONTRACTS 7B |
| Frontend | `/rfq`, `/rfq/new`, `/rfq/[id]`, `/quotes`, `/quotes/[id]`, `/pricing`, `/pricing/[id]`, `/sales-quotes`, `/sales-quotes/[id]`, `/fx-rates`; sourcing navigation and breadcrumbs |
| Tests | 45 new backend tests (21 engine unit + 24 API integration); 9 new frontend tests (4 component + 5 helper) |

### 21.2 Milestones

| Milestone | Status | Evidence |
| --------- | ------ | -------- |
| M3.1 Migration applies, reverses and matches models | PASSED | `downgrade 0003_trade` -> `upgrade head`; `alembic current = 0004_sourcing`; `alembic check` reports no sourcing drift |
| M3.2 Tenant isolation and composite FKs | PASSED | `TestTenantIsolationAndAudit::test_another_company_cannot_read_sourcing_records` |
| M3.3 One RFQ per supplier, batch atomicity | PASSED | `TestRfqCreation::test_one_rfq_per_supplier_in_one_transaction` |
| M3.4 PREPARED is not SENT; evidence and reason gates | PASSED | `TestRfqLifecycle` (4 tests) |
| M3.5 Quote revisions and withdrawals are immutable | PASSED | `TestSupplierQuotes` (4 tests) |
| M3.6 FX never inferred; wrong pair rejected | PASSED | Engine tests + `test_cross_currency_needs_a_matching_explicit_fx_snapshot` |
| M3.7 Deterministic allocation and margin math | PASSED | `test_pricing_engine.py` (21) + `test_order_cost_is_allocated_and_margin_prices_the_lines` |
| M3.8 Recalculation is explicit and versioned | PASSED | `test_recalculation_requires_if_match_and_replaces_components` |
| M3.9 Approval needs verified inputs, finance.approve and a second person | PASSED | `TestSalesQuotes` (4 tests) |
| M3.10 Contract generation deterministic | PASSED | `generate-api-types.ps1` re-run (39 paths, 22 sourcing paths) |
| M3.11 Live end-to-end run | PASSED | `scripts\verify-sourcing.ps1` -> `backend/scripts/verify_sourcing_workflow.py`: **53/53 checks** against the local API and SSR (`docs/PROGRESS.md` 21.6) |

### 21.3 Database changes

* New revision `0004_sourcing` (revises `0003_trade`); applied to the development DB
  in place (no data dropped) and reversed/re-applied once during development to add
  `pricing_cost_component.product_id` before release.
* Twelve tables with RLS policies driven by `touche.current_company_id()`; revision
  tables grant only `SELECT, INSERT` to `touche_app`.
* `ck_audit_action` widened with `rfq.*`, `supplier_quote.*`, `fx_rate.recorded`,
  `pricing_scenario.*`, `sales_quote.*`.
* `pricing_cost_component` carries a nullable composite `product_id` FK plus a CHECK
  that LINE costs name a product and ORDER costs do not.

### 21.4 Commands executed and results

| # | Command | Result |
| - | ------- | ------ |
| 1 | `python -m alembic upgrade head` / `current` / `check` (development DB) | `0004_sourcing (head)`; check shows only pre-existing drift unrelated to sourcing |
| 2 | `python -m ruff check app tests` | `All checks passed!` |
| 3 | `python -m mypy app` | `Success: no issues found in 72 source files` |
| 4 | `python -m pytest` | **236 passed** (191 existing + 45 new) |
| 5 | `python scripts/export_openapi.py` | OpenAPI regenerated (39 paths) |
| 6 | `npm run api:types` | `schema.d.ts` regenerated |
| 7 | `npm test` | **13 files, 71 tests passed** |
| 8 | `npm run lint` | clean |
| 9 | `npx prettier --check src/**/*.{ts,tsx}` | clean |
| 10 | `npm run typecheck` | clean |
| 11 | `npm run build` | compiled; all 10 sourcing routes present |
| 12 | `backend\.venv\Scripts\python.exe scripts\verify_sourcing_workflow.py` | **53/53 checks passed** (see 21.6) |

### 21.5 Live 11-step workflow (development database, real HTTP)

Executed with `backend\scripts\verify_sourcing_workflow.py` against the local API
(`127.0.0.1:8000`) and the Next.js dev server (`127.0.0.1:3000`); **53 checks, 0
failed, 0 skipped**:

1. trader session: active company, `trade.write` present, `finance.approve`
   absent; approver session holds `finance.approve`;
2. supplier, buyer, product and deal created;
3. `POST /rfqs` created exactly one RFQ (DRAFT, generated `RFQ-` reference);
4. `DRAFT -> SENT` rejected (`409 INVALID_TRANSITION`); transition without an
   `Idempotency-Key` rejected (`400`); `PREPARED` stored revision 1 whose snapshot
   contains the requested product; `SENT` without evidence rejected (`400`);
   `SENT` with channel + evidence accepted and `sent_at` set;
5. EUR quote recorded (total `160.00`), RFQ moved to `RESPONDED`;
6. cross-currency pricing blocked without a snapshot (`400`); an EUR/USD 1.10
   snapshot recorded;
7. scenario priced: purchase `176.00`, freight `40.00` allocated to the line,
   landed `216.00`, status `VERIFIED_INPUTS`, calculation version stored;
8. stale `If-Match` → `409 VERSION_CONFLICT`; recalculation with `"v1"` → version 2
   and landed `236.00`;
9. sales quote drafted (`295.00` = landed / 0.8), submitted (`PENDING_APPROVAL`),
   trader approval refused (`403 FORBIDDEN`), approver approval accepted with the
   approval pair recorded and no transitions left; a revision then produced
   revision 2 (DRAFT) while the approved row kept `APPROVED` + `superseded_by`;
10. a viewer from another company received `404 NOT_FOUND` for the RFQ and an
    empty RFQ list;
11. `/rfq`, `/quotes`, `/pricing`, `/sales-quotes` and `/fx-rates` rendered for the
    authenticated trader with their expected headings.

Local verification accounts were created with the CLI
(`stage3.trader@`, `stage3.approver@` in Meridian Commodities,
`stage3.outsider@` as a viewer in TOUCHE Trading). Their throwaway password was
generated per run, passed through the process environment and never written to
this repository.

### 21.6 Issues found and fixed during Stage 3

| Issue | Resolution |
| ----- | ---------- |
| The scenario inputs could not bind a LINE cost to its product | `pricing_cost_component.product_id` added with a composite FK and a basis CHECK; migration re-applied before release |
| Decimal values reached JSONB and psycopg refused to serialise them | `pricing_inputs` renders money, percentages and ids as strings; results already used string totals |
| The pricing engine file was corrupted by a partial edit | Re-read and repaired; ruff/mypy/tests now guard the module |
| `list` as a method name shadowed the builtin in a type annotation | The annotation uses `Sequence` instead |
| `ruff format` reformatted unrelated Stage 1B services | Reverted those files so the Stage 3 diff stays reviewable |
| A sent-RFQ edit test used a stale ETag | The test re-reads the RFQ first and expects `409 CONFLICT` (not `VERSION_CONFLICT`) |

### 21.7 Files changed

New backend: `app/db/models/sourcing.py`,
`alembic/versions/20261022_0004_sourcing.py`,
`app/services/{pricing_engine,fx,rfqs,supplier_quotes,pricing,sales_quotes}.py`,
`app/api/v1/schemas/sourcing.py`, `app/api/v1/presenters_sourcing.py`,
`app/api/v1/routes/{fx_rates,rfqs,supplier_quotes,pricing_scenarios,sales_quotes}.py`,
`tests/{test_pricing_engine.py,test_sourcing_api.py}`.

Modified backend: `app/db/models/{__init__,audit}.py`, `app/api/v1/router.py`.

New frontend: `src/lib/sourcing/{types,format,client}.ts` and `format.test.ts`,
`src/components/sourcing/{status-badge,rfq-actions,rfq-form,quote-form,pricing-form,
sales-quote-form,sales-quote-actions,fx-form}.tsx` plus `rfq-actions.test.tsx`,
`src/app/(app)/{rfq,rfq/new,rfq/[id],quotes,quotes/[id],pricing,pricing/[id],
sales-quotes,sales-quotes/[id],fx-rates}/page.tsx`.

Modified frontend: `src/lib/navigation.ts`, `openapi/openapi.json`,
`src/lib/api/schema.d.ts`.

Docs: this section, `ARCHITECTURE.md` 20, `API_CONTRACTS.md` 7B and the endpoint
map, `DECISIONS.md` ADR-028..031, `ROADMAP.md` Stage 3 status.

### 21.8 Known limitations

* No sales *order* exists yet, so `WON` remains disabled and a sales quote is the
  last recorded commitment.
* FX snapshots are recorded manually; there is no bank-feed import.
* `scripts\verify-sourcing.ps1` needs three pre-created local accounts (trader,
  approver, outsider) and their passwords in the process environment. It drives
  HTTP and server-side rendering; it is not a browser automation suite.

---

## 22. Stage 4 - sales orders, procurement, logistics and trade documents (executed 2026-10-22)

### 22.1 Scope delivered

| Part | Delivered |
| ---- | --------- |
| 4A Sales orders | `customer_acceptance_evidence`, `sales_order`, `sales_order_item`, `sales_order_transition`, `order_amendment`; atomic conversion service; idempotent replay; immutable accepted-terms snapshot; cancellation/amendment history |
| 4B Procurement | `purchase_order` (+ items, transitions); optional for brokerage; approval separated from operational transitions; `RECORDED_SENT` and `SUPPLIER_CONFIRMED` evidence gates |
| 4C Logistics | `shipment` (+ items, events, references, costs); partial allocation with decimal quantities; over-allocation refusal; evidence-gated milestones; derived fulfilment; cost provenance |
| 4D Documents | `trade_document`; private local storage adapter; streaming upload limits; SHA-256; versioning; archive-not-delete; two-layer authorisation; DRAFT invoice/packing-list previews |
| 4E Frontend | `/orders`, `/orders/[id]`, `/purchase-orders`, `/purchase-orders/[id]`, `/shipments`, `/shipments/new`, `/shipments/[id]`, `/documents`; deal conversion action; dashboard operational metrics; execution navigation |

### 22.2 Milestones

| Milestone | Status | Evidence |
| --------- | ------ | -------- |
| 4A Conversion gate, atomic WON, idempotency | PASSED | `tests/test_operations_api.py` (`TestOrderConversionGate`, `TestOrderConversion`), live checks 6-16 |
| 4A Order lifecycle and snapshot | PASSED | cancellation/amendment tests, snapshot test after quote revision and catalogue change |
| 4B Procurement and evidence | PASSED | `TestProcurement`, live checks 17-22 |
| 4C Partial shipments and fulfilment | PASSED | `TestShipments` (4 tests), live checks 23-31 |
| 4D Documents and previews | PASSED | `TestDocuments` (4 tests), live checks 32-42 |
| 4E Frontend and dashboard | PASSED | 17 new vitest tests, `next build`, 8 SSR pages in the live run |
| 4F Stabilisation | PASSED | 284 backend tests, 88 frontend tests, ruff/mypy/eslint/prettier/tsc clean, drift check clean |

### 22.3 Database changes

* `0005_orders` (revises `0004_sourcing`) adds **14** tables:
  `customer_acceptance_evidence`, `sales_order`, `sales_order_item`,
  `sales_order_transition`, `order_amendment`, `purchase_order`,
  `purchase_order_item`, `purchase_order_transition`, `shipment`,
  `shipment_item`, `shipment_event`, `shipment_reference`, `shipment_cost`,
  `trade_document`.
  Every child row uses a composite `(id, company_id)` foreign key; every table
  has RLS enabled; history tables (`*_transition`, `order_amendment`,
  `customer_acceptance_evidence`, `shipment_event`) are append-only for the
  runtime role. The audit-action CHECK is widened; no existing table or row is
  otherwise altered.
* `0006_shipment_dispatch` drops `ck_shipment_dispatch_order`. The original
  rule required `actual_dispatch_at >= planned_dispatch_at`, which rejects a
  legitimate early dispatch (and surfaced as HTTP 500). Arrival and delivery
  ordering constraints remain.
* `0007_purchase_order_dispatch` replaces `ck_purchase_order_dispatched_at`.
  The original rule tied `dispatched_at IS NOT NULL` exactly to
  `status = 'RECORDED_SENT'`, so the next legitimate transition
  (`SUPPLIER_CONFIRMED`) failed. The corrected rule only forbids a dispatch
  time before the order was sent.
* Applied in place to the development database: `0005_orders` ->
  `0006_shipment_dispatch` -> `0007_purchase_order_dispatch`; current head is
  `0007_purchase_order_dispatch`. No table or row was dropped and no database
  was reset.
* `alembic check` still reports only the documented pre-existing drift:
  `remove_table alembic_version` plus three missing table comments on
  `company_setting_entry`, `company_settings` and `idempotency_record` (all
  Stage 1 tables). **No Stage 4 drift is reported.**

### 22.4 API endpoints (all under `/api/v1`)

| Area | Endpoints |
| ---- | --------- |
| Conversion and acceptance | `POST /deals/{id}/customer-acceptance`, `GET /deals/{id}/customer-acceptance`, `POST /deals/{id}/sales-order` (Idempotency-Key required) |
| Sales orders | `GET /sales-orders`, `GET /sales-orders/{id}`, `GET /sales-orders/{id}/fulfilment`, `POST /sales-orders/{id}/transitions`, `POST /sales-orders/{id}/amendments` |
| Procurement | `GET /purchase-orders`, `POST /purchase-orders`, `GET /purchase-orders/{id}`, `POST /purchase-orders/{id}/transitions` |
| Shipments | `GET /shipments`, `POST /shipments`, `GET /shipments/{id}`, `POST /shipments/{id}/transitions`, `POST /shipments/{id}/events`, `POST /shipments/{id}/costs`, `POST /shipments/{id}/references` |
| Documents | `GET /documents`, `POST /documents` (multipart), `GET /documents/{id}`, `GET /documents/{id}/download`, `GET /documents/{id}/history`, `POST /documents/{id}/archive`, `POST /documents/{id}/verification`, `GET /sales-orders/{id}/documents/preview` |
| Operations | `GET /operations/summary` |

Total documented operations: **62 OpenAPI paths** (was 39 at Stage 3).

### 22.5 Frontend

New pages: `/orders`, `/orders/[id]`, `/purchase-orders`,
`/purchase-orders/[id]`, `/shipments`, `/shipments/new`, `/shipments/[id]`,
`/documents`. Modified: the Command Center (operational counters), the deal
detail page (customer-acceptance + conversion panel) and the navigation
(Execution group; Logistics moved out of the roadmap).

New components live in `frontend/src/components/operations/`: status badge,
order conversion, order actions, purchase-order actions, shipment planning,
shipment milestones, extra shipment records, document upload, document actions.
All browser mutations use the same conventions as Stage 3: same-origin proxy,
CSRF header, a new `Idempotency-Key` per action and `If-Match` for updates.

### 22.6 Verification and exact counts

| Gate | Result |
| ---- | ------ |
| `pytest` (backend, live PostgreSQL) | **284 passed** (236 Stage 0-3 + 19 state-machine unit + 29 Stage 4 integration) |
| `ruff check app tests` | clean |
| `mypy app` | clean (85 source files) |
| `mypy app tests` | 98 pre-existing test-only errors remain (`test_sourcing_api.py` 88, `test_pricing_engine.py` 10); no new errors in Stage 4 tests |
| `alembic current` / `alembic upgrade head` | `0007_purchase_order_dispatch` |
| `alembic check` | only the documented pre-existing drift; no Stage 4 drift |
| `vitest` | **88 passed** in 16 files (71 Stage 1-3 + 17 Stage 4) |
| `eslint .` | clean |
| `prettier --check .` | clean |
| `tsc --noEmit` | clean |
| `next build` | passed; 30 routes including the 8 new pages |
| `generate-api-types.ps1 -Check` | "generated API types are up to date" (62 paths) |

### 22.7 Live end-to-end verification

`scripts\verify-operations.ps1` -> `backend/scripts/verify_operations_workflow.py`
drove the running API (uvicorn, real PostgreSQL) and the running Next.js server
with three isolated development accounts:

* `stage4.trader@touche.example` (trader) and `stage4.approver@touche.example`
  (approver) in **Stage 4 Trading**;
* `stage4.outsider@touche.example` (viewer) in **Stage 4 Outsider**.

Passwords were generated per run, passed through the process environment and
never written to this repository.

Result: **45/45 checks passed**, covering all 26 acceptance steps:
permissions; deal/quote approval through the real Stage 3 flow; conversion
refusal without acceptance; `TRANSITION_DISABLED` for a direct WON; acceptance
with evidence; atomic order + WON; frozen snapshot; idempotent replay; a
different key refused with `ALREADY_WON`; purchase-order draft, approval
segregation, dispatch evidence and supplier confirmation; a 40-of-100 partial
shipment that does **not** fulfil the order; over-allocation refusal; evidence
gates at dispatch/arrival/delivery; logistics cost provenance; a second
shipment that completes fulfilment; private document upload, checksum,
authorised download, cross-tenant 404, foreign-link 404; DRAFT invoice and
packing-list previews; real operational counters; no invoice/payment endpoint;
and SSR rendering of all eight new pages with real data.

This is an HTTP + server-render verification. **No browser automation was
executed**, so no claim is made about interactive browser behaviour beyond the
component tests.

### 22.8 Issues found and fixed during Stage 4

| Issue | Resolution |
| ----- | ---------- |
| `ck_shipment_dispatch_order` rejected an early dispatch with HTTP 500 | Migration `0006_shipment_dispatch` removes the plan-vs-actual ordering rule; arrival/delivery ordering stay |
| `ck_purchase_order_dispatched_at` made `SUPPLIER_CONFIRMED` impossible after a recorded send | Migration `0007_purchase_order_dispatch`; only a dispatch *before* sending is forbidden |
| Purchase-order approval was unreachable: the route required `trade.write`, which approvers do not hold | The route now requires `finance.approve` for `APPROVED` and `trade.write` for every other transition; the service still refuses self-approval |
| Document download returned 404 because the service queried under RLS without a tenant context | `download`, `archive` and `set_verification` now call `apply_company_context` |
| Invoice/packing-list preview returned 404 because the seller join is protected by a membership policy | `preview` also binds the actor (`apply_actor_context`), with the actor id supplied by the route |
| `python-multipart` was not installed, so the multipart route could not start | Added to `backend/pyproject.toml` and installed in the local virtualenv |
| A test fixture used the ACL-restricted pytest temp directory and failed at setup | The Stage 4 tests create their storage under the ignored `backend/var` tree instead |
| The live verifier initially assumed a fresh order register | It now scopes the "no order yet" check to the deal under test |

### 22.9 Files changed

New backend: `app/db/models/orders.py`,
`alembic/versions/20261022_0005_orders.py`,
`alembic/versions/20261022_0006_shipment_dispatch.py`,
`alembic/versions/20261022_0007_purchase_order_dispatch.py`,
`app/services/{order_state,sales_orders,procurement,shipments,documents,operations}.py`,
`app/api/v1/schemas/operations.py`, `app/api/v1/presenters_operations.py`,
`app/api/v1/routes/{orders,purchase_orders,shipments,documents}.py`,
`tests/{test_operations_api,test_operations_state}.py`,
`scripts/verify_operations_workflow.py`.

Modified backend: `app/api/v1/router.py`, `app/core/{config,errors}.py`,
`app/db/models/{__init__,audit}.py`, `pyproject.toml`.

New frontend: `src/lib/operations/{types,format,client}.ts` and
`format.test.ts`, `src/components/operations/*` (8 components + 2 tests),
`src/app/(app)/{orders,orders/[id],purchase-orders,purchase-orders/[id],
shipments,shipments/new,shipments/[id],documents}/page.tsx`.

Modified frontend: `src/app/(app)/page.tsx`,
`src/app/(app)/deals/[id]/page.tsx`, `src/lib/navigation.ts`,
`openapi/openapi.json`, `src/lib/api/schema.d.ts`.

Tooling and docs: `scripts/verify-operations.ps1`, `.gitignore`, this section,
`ARCHITECTURE.md` 21, `API_CONTRACTS.md` 7C, `DECISIONS.md` ADR-032..037,
`ROADMAP.md`, `README.md`.

### 22.10 Git

* Branch `stage-4`, created from the verified `stage-3` HEAD (`1007571`).
* `4ef39cd` - `feat(stage4): sales orders, procurement, shipments and trade documents`
* `070b332` - `feat(stage4): execution workspace for orders, procurement, shipments and documents`
* Documentation commit: the commit containing this section.
* No remote is configured; nothing was pushed, merged or reset.

### 22.11 Known limitations and outstanding controls

* **No malware scanning.** Uploads are type-checked, size-limited, hashed and
  stored privately, but a virus/AI content scanner is a remaining control.
* **No external carrier integration.** Tracking provenance is `MANUAL` or
  `DOCUMENT_EVIDENCE` only; `VERIFIED_EXTERNAL` is refused. No live container
  map or carrier feed exists, and none is displayed.
* **No accounting.** Closing an order is an administrative milestone; no
  revenue, invoice, payment or ledger entry is posted anywhere. `/invoices` and
  `/payments` do not exist.
* **No automatic messaging.** Recording a purchase-order dispatch is evidence
  that a human sent it elsewhere; TOUCHE sends no email or WhatsApp.
* **Local document storage only.** The adapter is private and
  traversal-resistant but single-node; object storage and signed URLs would be
  a deployment change (ADR-037).
* **Cancellation does not unwind shipments.** Cancelling an order is recorded
  with a reason and leaves the accepted snapshot and WON history intact; it does
  not automatically cancel live shipments or reverse allocations.
* **Partial amendments are conservative.** A line quantity cannot be reduced
  below what shipments already allocate.
* **Frontend verification is component + SSR level.** No browser automation
  suite runs in this repository yet.
* **Pre-existing test typing debt.** `mypy app` is clean; `mypy app tests`
  still reports 98 errors confined to the Stage 3 test modules.





---

## 23. Stage 5A - Finance discovery and read-only connector (executed 2026-10-22)

### 23.1 Scope delivered

Stage 5A connects Commerce to the **verified** TOUCHE FINANCE boundary without
creating a second accounting engine. Finance remains the financial source of
truth; Commerce remains the commercial operational source of truth.

Delivered:

* read-only discovery of the live Finance tree, SQLite ledger and Excel workbook;
* a concrete Commerce → Finance mapping and an exact missing-interface list;
* a disabled-by-default, loopback-only Finance health connector;
* `GET /api/v1/integrations/finance/status`, which always reports
  `scope="health_only"` and `accounting_writes_enabled=false`;
* a read-only verification script that hashes the DB/workbook before and after
  and never starts Finance;
* ADR-038 (Finance source of truth), ADR-039 (read-only-first loopback), ADR-040
  (proposed authenticated Finance contract).

Explicitly **not** delivered, because Finance has no supported interface for it:
business-data reads, invoices, payments, ledger postings, outbox delivery to
Finance, counterparty auto-matching and reconciliation writes.

### 23.2 Milestones

| Milestone | Result |
| --------- | ------ |
| 5A.1 Verify the real Finance worktree and revision | `C:\ai-excel`, `main`, `8dce8245`; remote HEAD identical |
| 5A.2 Inspect API, auth, models, engine, Excel and persistence | completed read-only (see `docs/STAGE5_FINANCE_DISCOVERY.md`) |
| 5A.3 Build the mapping and missing-interface specification | completed, including proposed HMAC contract and additive tables |
| 5A.4 Implement the safe connector slice | health client + status endpoint + config + tests |
| 5A.5 Prove read-only behaviour | probe PASS; DB/workbook hashes unchanged; Finance not started |

### 23.3 What the discovery proved

* Finance is a Python 3.12 stdlib HTTP server on `127.0.0.1:8765`, with a
  vanilla-JS UI, SQLite ledger and one Excel master/backup pair.
* Only `/api/health`, `/api/demo/status`, `/api/session` and
  `/api/session/pair` are unauthenticated; every business endpoint requires a
  loopback/Tailscale session.
* A loopback request is treated as `OWNER`; there is no API key, HMAC contract,
  webhook receiver or remote-write endpoint.
* The live ledger has 31 tables, 3 activities, 22 accounts, 24 journal headers,
  48 journal lines and **0 structured counterparties**. Counterparties are
  free-text `fisler.cari`.
* Invoices are not a structured table; a posted document is a `fisler` header
  plus lines. AR/AP aging is derived by `kurumsal_finans.cari_yaslandirma`.
* `/api/health` calls `recovery_health()`, which explicitly never initialises the
  schema or writes. Finance was still not started because startup recovery can
  legitimately write.

### 23.4 Database changes

None. Stage 5A does not add a Commerce table, migration or Finance table.
Commerce's existing `outbox_event` table remains unused until a Finance ingestion
contract exists.

### 23.5 Commands executed and actual results

```text
backend> .venv\Scripts\python -m pytest -q
317 tests passed (284 Stage 4 + 33 Stage 5A); no failures.

backend> .venv\Scripts\python -m ruff check app tests
All checks passed.

backend> .venv\Scripts\python -m mypy app
Success: no issues found in 92 source files.

backend> .venv\Scripts\python -m mypy app tests
98 pre-existing errors, all in Stage 3 test modules (unchanged).

scripts> generate-api-types.ps1
OpenAPI + schema.d.ts regenerated; no drift.

scripts> verify-finance-readonly.ps1
PASSED: True (DB and workbook hashes unchanged; Finance not listening).
```


### 23.6 Read-only verification (exact)

```text
Finance worktree : C:\ai-excel [main] 8dce8245c013ec74b81cf93927a067a4cc334c78
Remote HEAD      : 8dce8245c013ec74b81cf93927a067a4cc334c78
Dirty files      : 1 (untracked .claude/ only)
DB SHA-256       : C9BA0EB7EC82F1DE50105F1E0019CA695B48843319B7E1D2184296632EF52BE1
DB unchanged     : True
WB SHA-256       : E03740DA624522EA9AC4869D3ADDDFB008C96DC7D2A78759CE760D810B0FA51E
WB unchanged     : True
Schema ok        : True
Health           : skipped (Finance not listening; not started)
PASSED           : True
```

### 23.7 Issues found

* **Finance has no service-to-service interface.** The local session is a
  network-position grant, not a scoped service credential. The connector
  therefore stops at `/api/health`; ADR-040 defines what must be built in Finance
  before business data can move.
* **No structured counterparties.** `karsi_taraflar` is empty and Commerce has no
  tax/VKN field. Automatic name matching would be unsafe; a manual mapping
  registry is required.
* **No invoice line entity in Finance.** `hakedisler` stores header totals only.
  A draft-only event contract must not pretend a ledger line is an invoice line.
* **The original Stage 5 roadmap assumed invoices/payments in Commerce.** That
  conflicts with the source-of-truth constraint and is superseded by ADR-038.

### 23.8 Files changed

Backend: `app/core/config.py`, `app/main.py`, `app/api/v1/router.py`,
`app/api/v1/routes/integrations.py`, `app/api/v1/schemas/integrations.py`,
`app/integrations/__init__.py`, `app/integrations/finance/{__init__,client,contracts,service}.py`,
`tests/test_finance_integration.py`.

Scripts: `scripts/finance_readonly_probe.py`, `scripts/verify-finance-readonly.ps1`.

Contracts: `frontend/openapi/openapi.json`, `frontend/src/lib/api/schema.d.ts`.

Docs: `docs/STAGE5_FINANCE_DISCOVERY.md`, `docs/PROGRESS.md`,
`docs/ARCHITECTURE.md`, `docs/API_CONTRACTS.md`, `docs/DECISIONS.md`,
`docs/ROADMAP.md`, `README.md`, `.env.example`.

### 23.9 Git

* Branch: `stage-5`, created from the verified Stage 4 HEAD (`ace7204`).
* Commit `4cb6459` - `feat(stage5a): read-only Finance discovery and health
  connector`.
* No remote configured; nothing pushed or merged. The Finance repository
  received no commit or file change.

### 23.10 Known limitations and next gate

* The connector reports only health; no Finance balance is shown.
* The probe is an offline verification tool, not a runtime data source.
* Finance's actual `/api/health` response was not observed live because starting
  Finance could write during recovery. The contract was verified statically and
  the client is tested against a local stub.
* Stage 5B is blocked until Finance implements and verifies the authenticated
  read-only `/api/integration/v1` contract in `docs/STAGE5_FINANCE_DISCOVERY.md`
  §8.1. Stage 5C additionally requires §8.2/§8.3 and remains draft-only.


---

## 24. Stage 5C — real read-only Finance integration (2026-10-22)

### 24.1 Verified revisions

| Item | Verified value |
| ---- | -------------- |
| Commerce branch | `stage-5c`, created from clean `stage-5` at `6381f59` |
| Finance branch | `feat/finance-integration-v1` |
| Finance HEAD | `107c30e2ae4b5e4c22891f01ca730d3284994de5` |
| Finance base | `main` at `8dce8245c013ec74b81cf93927a067a4cc334c78` |
| Finance repository changes | none, read-only |
| Migration | `0008_finance_mapping` (`finance_company_mapping`) |

### 24.2 Delivered

* Server-only key id/secret settings (`SecretStr`), disabled by default and
  restricted to loopback HTTP.
* Authenticated `FinanceIntegrationClient` for Finance v1: bounded paths,
  1 MiB response cap, no redirects, JSON/contract/read-only validation and
  service headers. No cookies, Tailscale or owner fallback.
* `FinanceConnector` verifying the explicit mapping against Finance
  capabilities and authorized company list; explicit currency selection.
* Normalized Commerce errors preserving `details.finance_code` and
  `finance_request_id`.
* Tenant-scoped `finance_company_mapping` with RLS and runtime `SELECT` only;
  admin-only CLI `finance-map set/list/disable` with live verification and audit.
* Five `/api/v1/finance/*` endpoints, all GET only; every successful read audited.
* Premium `/finance` workspace: connection state, mapped company, currencies,
  data-through, source balances, accounts, receivable/payable FIFO aging and open
  Finance source ids. Invoice/payment data is explicitly “Not available”.
* Stage 5A health endpoint retained unchanged.

### 24.3 Configuration without secret values

```text
TOUCHE_FINANCE_INTEGRATION_ENABLED=true|false
TOUCHE_FINANCE_INTEGRATION_BASE_URL=http://127.0.0.1:8765
TOUCHE_FINANCE_INTEGRATION_KEY_ID=key_<16 hex>
TOUCHE_FINANCE_INTEGRATION_SECRET=<server-side only>
TOUCHE_FINANCE_INTEGRATION_TIMEOUT_SECONDS=2
```

Mapping command:

```powershell
python -m app.cli finance-map set --company "<Commerce company>" `
  --finance-company gursar_mimarlik --actor "<company admin email>"
```

### 24.4 Automated results

| Command | Result |
| ------- | ------ |
| `pytest` (backend) | **355 passed** (317 Stage 5A baseline + 38 Stage 5C) |
| new connector tests | **20 passed** |
| new API integration tests | **18 passed** |
| `ruff check app tests` | passed |
| `mypy app` | passed (98 files) |
| `npm test` | **96 passed / 17 files** |
| `npm run lint` | passed |
| `npm run typecheck` | passed |
| `npm run format:check` | passed |
| `npm run build` | passed; `/finance` present |
| OpenAPI regeneration | passed; no drift after regeneration |

### 24.5 Real HTTP acceptance

Executed with `backend/scripts/verify_finance_http.py` against a disposable
Finance runtime (synthetic SQLite ledger, temporary key, port 8877), the
isolated Commerce test PostgreSQL database, the Commerce CLI mapping, the real
Commerce API and Next.js server.

```text
verification              ISOLATED_HTTP_VERIFIED
finance_company           gursar_mimarlik
currencies                EUR, TL
summary_currency          TL
accounts_returned         2
receivable_items          1
payable_items             1
frontend_routes           overview, accounts, receivables, payables
cross_tenant_isolated     true
write_route_rejected      405
credentials_in_responses  false
finance_db_unchanged      true
finance_workbook_unchanged true
```

The verifier refuses occupied ports, confirms every Finance path resolves inside
its temporary base, and stops only the isolated processes it started. The live
Finance application was not started.

### 24.6 Live source hash evidence

```text
C:\ai-excel\veri\finans.db
C9BA0EB7EC82F1DE50105F1E0019CA695B48843319B7E1D2184296632EF52BE1

C:\Users\twone\OneDrive\Desktop\Touche\Touche Holding - AI Ready Finans Yönetim Sistemi.xlsx
E03740DA624522EA9AC4869D3ADDDFB008C96DC7D2A78759CE760D810B0FA51E
```

Both hashes are unchanged before and after the Stage 5C work.

### 24.7 Honest limitations

* HTTP verification is **isolated**, not a live Finance connection. Live Finance
  was deliberately not started and no live credential was read.
* Finance has no structured invoice/payment/counterparty/project/report
  endpoints; Commerce does not invent them.
* TLS/mTLS, remote deployment, Windows ACL proof and HSM/KMS are not verified.
* The mapping CLI currently supports one Finance company per Commerce company
  (`UNIQUE(company_id)`).
* Stage 5D reconciliation has not begun.

### 24.8 Next safe milestone

Stage 5D may begin with **read-only reconciliation** only: persist deterministic
source-to-Finance matching evidence, report variances, require human exception
approval, and never auto-post a journal, invoice or payment. A real Commerce →
Finance mapping must be configured first.


### 24.9 Git

* Branch: `stage-5c`, created from the clean Stage 5A HEAD `6381f59`.
* `e03114b` — `feat(stage5c): add read-only Finance connector and explicit mapping`
  (backend, migration, CLI, tests, verifier, generated OpenAPI, env example).
* `521e230` — `feat(stage5c): add premium read-only Finance workspace`
  (navigation, `/finance`, components and frontend tests).
* `876d52d` — `style(stage5c): normalize file endings`.
* The documentation commit containing this section.
* No merge, push, deployment or Finance repository change was performed.

---

## 25. Stage 5D — evidence-based financial reconciliation

### 25.1 Scope and boundary

Stage 5D adds a Commerce-owned reconciliation evidence layer only. Finance remains
the source of accounting truth. No Finance write, journal, invoice, payment or
settlement was introduced.

**Branch:** `stage-5d`, from verified Stage 5C HEAD `3e35ef1`.
**Migration:** `0009_reconciliation`.
**Finance revision verified:** `feat/finance-integration-v1` at `107c30e`.

### 25.2 Delivered

* Five tenant-scoped tables: run, Finance source reference, evidence link,
  discrepancy and append-only review. RLS, composite FKs, no runtime DELETE,
  evidence update limited to reviewer verification columns.
* Decimal analysis of accepted value, commitments, estimated landed cost,
  recorded operational costs, variance and commitment-based margin. Mixed
  currencies are never added; `TRY`/`TL` is an alias only.
* Deterministic discrepancies and explicit unavailable states. No actual profit
  or document-supported margin is fabricated.
* `finance.reconcile` permission granted to approver only; admin never inherits
  it; creator cannot self-review.
* Ten API endpoints with CSRF, idempotency, If-Match/ETag, audit, idempotent
  replay and `no-store`.
* Premium `/finance/reconciliation`, `/finance/reconciliation/[id]`,
  `/finance/discrepancies` and `/finance/orders/[id]` screens with real backend
  APIs and generated OpenAPI types.
* Extended isolated HTTP verifier that creates a real accepted order via Stage
  3/4 APIs.

### 25.3 Automated results

| Command | Result |
| ------- | ------ |
| `pytest` (backend) | **379 passed**, 0 failed, 0 skipped |
| new pure calculation tests | **12 passed** |
| new reconciliation API tests | **12 passed** |
| `ruff check app tests` | passed |
| `mypy app` | passed |
| `npm test -- --run` | **102 passed / 18 files** |
| `npm run lint` | passed |
| `npm run typecheck` | passed |
| `npm run format:check` | passed |
| `npm run build` | passed; all four new routes present |
| OpenAPI regeneration | passed after commit; no drift |
| Alembic migration | `0009` applied; new tables have no model drift |

The inherited `alembic check` still reports the pre-existing unrelated drift
(`public.alembic_version`, comments on three Stage 1 tenant tables).

### 25.4 Isolated HTTP acceptance

`backend/scripts/verify_finance_http.py` was extended to seed a synthetic USD
receivable `F-USD-AR-1` for `250.00`, create a complete Commerce order through
Stage 3/4 HTTP endpoints, and exercise reconciliation through real Commerce and
Next.js HTTP with synthetic Finance on `127.0.0.1:8877`.

```text
verification                 ISOLATED_HTTP_VERIFIED
order_total                  250.00
finance_source               F-USD-AR-1
finance_source_amount        250.00
run_status                   VERIFIED
evidence_status              VERIFIED
review_decision              CONFIRM
unauthorized_review          FORBIDDEN
unlinked_run_cannot_verify   true
frontend_routes              reconciliation, reconciliation_run,
                             discrepancies, order_finance
cross_tenant_isolated        true
write_route_rejected         405
credentials_in_responses     false
finance_db_unchanged        true
finance_workbook_unchanged  true
```

The live Finance application was **not** started. Live DB/workbook hashes remain:

```text
C:\ai-excel\veri\finans.db
C9BA0EB7EC82F1DE50105F1E0019CA695B48843319B7E1D2184296632EF52BE1

C:\Users\twone\OneDrive\Desktop\Touche\Touche Holding - AI Ready Finans Yönetim Sistemi.xlsx
E03740DA624522EA9AC4869D3ADDDFB008C96DC7D2A78759CE760D810B0FA51E
```

### 25.5 Honest limitations

* Verification is isolated, not live.
* Finance has no structured invoice/payment/counterparty/project/report source;
  document-supported margin and actual profit stay unavailable.
* One Finance company per Commerce company.
* Remote/TLS/mTLS, Windows ACL proof and HSM/KMS remain unverified.
* No production mapping or live Finance startup was performed.
* No automatic accounting entry exists in Commerce.
* Migration downgrade after Stage 5D audit rows exist requires explicit audit
  cleanup, consistent with the append-only audit policy.

### 25.6 Git

* Branch `stage-5d`, created from the verified Stage 5C HEAD `3e35ef1`.
* `0e9a1af` — `feat(stage5d): add evidence reconciliation backend`
  (migration, models, pure calculations, service, API, tests, extended isolated
  verifier, generated OpenAPI/types).
* `0ce2658` — `feat(stage5d): add premium reconciliation workspace`
  (overview/run/discrepancy/order screens, components, client, navigation and
  frontend tests).
* `f949003` — `docs(stage5d): record reconciliation contract and acceptance evidence`.
* The close-out documentation commit containing the refreshed milestone header.
* Nothing was pushed, merged or deployed; the Finance repository was not
  modified.


---

## 26. Stage 5E — read-only financial intelligence

### 26.1 Scope and boundary

Stage 5E turns facts Commerce already holds into an operational profitability
analysis. It reads accepted sales orders, the accepted quote and its pricing
scenario with stored FX snapshots, purchase orders, shipment costs and the Stage 5D
runs, evidence and discrepancies. It does **not** call Finance, create a
migration, write any row (apart from one `finance.read` audit row per CSV export)
or compute an actual profit. Finance remains the financial source of truth.

**Branch:** `stage-5e`, from the verified Stage 5D HEAD `2be76ce`.
**Migration:** none (head stays `0009_reconciliation`).
**Calculation version:** `stage5e-1.0.0`.

### 26.2 Delivered

* A pure, I/O-free calculation module keeping two bases apart: `ESTIMATED`
  (accepted value minus the Stage 3 landed-cost scenario, recoverable
  `VAT_CASHFLOW` excluded) and `COMMITTED`/`DOCUMENTED` (accepted value minus
  committed purchase orders and shipment costs recorded as `INCURRED` or
  `DOCUMENTED`). `QUOTED`/`ESTIMATED` shipment costs are forecasts and never enter
  the documented basis. There is deliberately no `actual_profit` field.
* Seven `GET` endpoints under `/api/v1/finance/intelligence` (`summary`, `orders`,
  `orders/{id}`, `cost-variance`, `coverage`, `exceptions`, `export`), all behind
  `company.view`, `no-store`, with `read_only=true` and
  `accounting_writes_enabled=false`. See API_CONTRACTS §12.
* Four premium screens in the Stage 5C/5D design language:
  `/finance/intelligence`, `/finance/intelligence/orders`,
  `/finance/intelligence/orders/[id]`, `/finance/intelligence/exceptions`, plus a
  CSV export button. Five CSS/SVG charts (no new dependency) with a legend, a table
  view and a keyboard/hover tooltip; series colours were checked with the dataviz
  validator against the real panel surface.
* The same-origin proxy now also forwards `content-disposition` and
  `x-content-type-options`, so the export keeps its file name and `nosniff`.
* `backend/scripts/verify_finance_http.py` gained a Stage 5E step.

### 26.3 Automated results

| Command | Result |
| ------- | ------ |
| `pytest` (backend, run alone against the isolated test database) | **402 passed**, 0 failed, 0 skipped |
| new pure calculation tests | **18 passed** (incl. the CSV loss regression) |
| new intelligence API tests | **5 passed** (live PostgreSQL, real order) |
| `ruff check app tests` / `ruff check scripts/verify_finance_http.py` | passed |
| `mypy app` | passed (109 source files) |
| `npm test -- --run` | **160 passed / 22 files** (102 earlier + 58 new) |
| `npm run lint` · `typecheck` · `format:check` | passed |
| `npm run build` | passed; the four new routes are listed |
| `scripts\generate-api-types.ps1 -Check` | passed after the contract commit (7 paths and 28 schemas added; nothing removed or changed) |

`ruff format --check` is not enforced repo-wide (64 older files differ); only the
files touched by this stage are formatted. The inherited `alembic check` drift
noted in §25.3 was not re-run: no model or migration changed.

### 26.4 Isolated HTTP acceptance

`backend/scripts/verify_finance_http.py` now continues from the Stage 5D order:
100 kg sold for `250.00` USD, a `160.00` USD approved purchase order, a `40.00` USD
freight estimate, 10 kg shipped and `20.00` USD of freight incurred. The expected
figures are derived from those inputs, not from the code under test. Synthetic
Finance runs on `127.0.0.1:8877`, Commerce on the isolated test database, and the
screens are rendered by Next.js from the live API.

```text
verification                                   ISOLATED_HTTP_VERIFIED
sales_value / estimated_landed_cost            250.00 / 200.00
estimated_gross_profit / margin_pct            50.00 / 20.00
committed_purchase_cost                        160.00
documented_operational_cost                    20.00
committed_profit_withheld_while_partly_shipped true
actual_profit_available                        false
cost_variance_orders / excluded                0 / 1
open_exceptions before -> after resolution     3 -> 2
trader_resolution                              FORBIDDEN
export_rows                                    1
export_via_proxy_keeps_filename_and_nosniff    true
frontend_routes                                dashboard, orders, variance,
                                               order_detail, exceptions
cross_tenant_isolated                          true
write_route_rejected                           405
credentials_in_responses                       false
finance_db_unchanged / workbook_unchanged      true / true
```

Also checked: filters (`EUR`, `BROKERAGE`, a reversed date range, an unknown order),
a reviewer resolving an exception from the enriched queue, the empty-status
filter, malformed filters on the dashboard, the reviewer/trader hints on the
exceptions screen, and another company seeing no order, count, exception, export
row or screen.

Live source hashes, read only, identical before and after the run (and to §25.4):

```text
C:\ai-excel\veri\finans.db
C9BA0EB7EC82F1DE50105F1E0019CA695B48843319B7E1D2184296632EF52BE1

C:\Users\twone\OneDrive\Desktop\Touche\Touche Holding - AI Ready Finans Yönetim Sistemi.xlsx
E03740DA624522EA9AC4869D3ADDDFB008C96DC7D2A78759CE760D810B0FA51E
```

The live Finance application was **not** started.

### 26.5 Issues found and fixed during the stage

| Finding | Found by | Resolution |
| ------- | -------- | ---------- |
| The five API tests failed at a fixture helper: two `GET` calls omitted the `/api/v1` prefix, so no endpoint had been exercised. A local constant named `ORDERS` also shadowed the imported one. | first full backend run, ruff `F811` | prefixes via the shared constants; import aliased to `SALES_ORDERS` |
| CSV export prefixed every value that starts with `-`, including negative amounts, so a loss (`-50.00`) became text (`'-50.00`). | code review of the export route, then a runnable check | formula escaping now applies to text columns only; regression test added |
| A metric with nothing to show carried the kind the API names for it (`COMMITTED`) beside “Not available”. | the first isolated run (an assertion of mine was also wrong) | the card shows `UNAVAILABLE` when it has no figure; test added; backend contract unchanged (ADR-047) |
| Six `UniqueViolation` errors in one backend run. | two suites sharing `touche_commerce_test` | not defects; suites must run one at a time against the test database |
| Order and exceptions tables were too narrow: at 1024 px only five of nine columns were visible, the order number broke into three lines, the finding column was 106 px wide and the resolution control was scrolled out of view. | real-browser review | status folded into the order cell, order number `nowrap`, customer name clamped, wrapping headers; exceptions table reduced to three columns with the resolution control under the finding (commit `697c94d`) |
| Twelve months in the monthly chart widened the page on a phone (layout 666 px on a 375 px screen). A first fix (scrolling plot) was not enough: the panel, a grid item, still grew to the plot. | real-browser review, then a re-measure | plot scrolls inside a `min-w-0` panel; labels `nowrap`; edge tooltips anchored inside the plot; tested |
| Order detail: “Documented cost” read “Not available” beside a DOCUMENTED badge; “Cost variance” read “Not available of estimate”; the tooltip said “1 orders”; the coverage metric carried a green VERIFIED badge at 0.00%. | real-browser review | operational cost shown with the total as unavailable; badges fall back to UNAVAILABLE without a figure; VERIFIED never shown on a metric; pluralisation fixed; all tested |
| Cosmetic findings: filter labels beside their inputs; chart empty state as a panel inside a panel; category names truncated without a hover title; sub-pixel completeness segments; tooltips overhanging their panel; an odd coverage panel alone in a row; a loss that looked like a gain. | real-browser review | block labels (bar and exceptions form); plain-text chart empty state; two-line category labels with a `title`; 4 px minimum segment; edge-anchored tooltips; `ChartGrid` (odd last panel spans both columns); losses tinted `crimson-400` with the minus sign kept and cost variance deliberately not tinted (commit `8510b52`) |
| The loss percentage line used `text-crimson-400/80`, about 4.1:1 on the top of the panel gradient, below the 4.5:1 AA threshold. | contrast computed while closing out the browser checks | full-strength `crimson-400` (5.5–6.6:1); test asserts it (commit `46d49fb`) |

The first isolated run failed on the committed-profit assertion before the third
fix above; the recorded result is from the second, clean run.

**Real-browser review (2026-10-23).** The screens were opened in the in-app browser
against the isolated environment (synthetic Finance, test database, throw-away
accounts) with the real Stage 5D order, plus a temporary page of clearly labelled
**synthetic** data (12 months, three currencies, 12-million amounts, an 80-character
customer name) that was deleted afterwards and never committed. Widths 375, 1024,
1280 and 1440 px. Thirteen findings were reported; the six that affected
readability or truth of a figure were fixed and re-measured in the same environment
(`697c94d`), the HTTP verifier was re-run (`ISOLATED_HTTP_VERIFIED`) and the live
Finance hashes were unchanged. The remaining findings were then fixed in `8510b52`.

**Close-out verification (2026-10-23, after `8510b52`).** Run against a fresh isolated
environment with the real order plus the same kind of temporary, labelled synthetic
page (deleted, never committed), at 1280 and 375 px:

* Exceptions-form labels: all six (Status, Severity, Code, Currency, From, To) are
  `display:block`, sit above their control in the same column, and none is orphaned.
* Margin-chart tooltips at both edges: all five bands anchor correctly (`left-0`,
  `left-0`, centred, `right-0`, `right-0`) and stay inside the panel with a 17 px
  margin at the first and last band; at 375 px they also stay inside the viewport.
  Real keyboard `Tab` focus opens the tooltip: on the first band with a visible focus
  ring, on the last band (accessible name `30+: 3 orders`) with the tooltip shown
  inside the panel.
* Small segments: shares of 1, 1, 1 against 5000 render at the 4 px minimum with no
  overflow of the bar (427 px and 309 px bars).
* Long category names: wrap to two lines with the full text in `title` and in the
  list item's accessible name; a 74-character key is clamped at two lines, its full
  text still available; every row is focusable.
* Negative formatting: losses on KPI lines, estimated/committed profit and margin on
  detail tiles and in the order table render in `rgb(224, 122, 114)` with the minus
  sign in the text; gains stay in the normal colour; cost variance is not tinted.
  Contrast of the loss colour on the panel surfaces is 5.5–6.6:1.
* Empty chart state: no panel nested inside the chart panel; odd last panel spans
  both columns (938 px against 461 px); no page-level horizontal overflow at either
  width.

Then: backend `402 passed` (ruff, mypy clean), frontend `160 passed` (ESLint,
Prettier, typecheck and `next build` clean), the OpenAPI drift check clean, the HTTP
verifier `ISOLATED_HTTP_VERIFIED` again (estimated profit `50.00`, committed profit
withheld while part-shipped, unauthorized resolution `FORBIDDEN`, one export row,
export through the proxy keeping its file name and `nosniff`, cross-tenant
isolation, write route `405`, no credentials in responses, Finance database and
workbook unchanged), and the live Finance hashes identical to §25.4.

### 26.6 Honest limitations

* Verification is isolated: HTTP/SSR level plus the real-browser review in §26.5.
  Not covered: tablet width (768 px), a full accessibility audit (only contrast,
  labels, accessible names and keyboard focus were checked; no screen reader) and the
  Export CSV download in the browser (a download needs explicit permission, so it was
  verified over HTTP only).
* Cosmetic findings from the browser review: **all fixed and re-verified** (§26.5,
  `8510b52`, `46d49fb`). Minor items that remain, none affecting a figure:
  * Where a table is empty, `EmptyState` (itself a panel) still sits inside the page's
    panel wrapper, so “No financial exceptions” and “No orders match” show as a box
    within a box. The chart empty state was fixed; the shared component was not
    changed.
  * Secondary text in `text-mist-600` (the customer name under an order number, small
    captions) measures about 3.0:1 on the panel, below the 4.5:1 AA threshold. It is
    the existing design-system muted tier, shared with the Stage 5C/5D screens, and
    was not changed in this stage.
  * A year of months needs horizontal scrolling inside the two-column monthly chart
    (about 44 px per month); the page itself never overflows. At 1024 px the order
    table still scrolls horizontally (two of eight columns off-screen).
  * Pre-existing and unchanged: the shell footer still reads “STAGE 5D” and the
    sidebar highlights “Finance” and “Intelligence” together.
* The isolated order is a single USD order. Multi-currency behaviour is proven by
  the pure and API tests (`test_currency_totals_are_never_mixed`, the currency
  isolation API test), not by the isolated run.
* The analysis never reads Finance. Finance data reaches it only through Stage 5D
  runs and evidence, so its freshness is the freshness of the latest run.
* A single analysis covers at most 5000 orders and 731 days; beyond that the API
  answers `400 BAD_REQUEST` and the export button shows the refusal. The orders
  screen also requests the summary for its filter options, so the backend analyses
  twice per page; a lightweight filter-options endpoint is the remedy if it is slow.
* The summary metrics keep a fixed `classification` (the metric's kind) even when
  `available` is false; `available` is the authority. The screens compensate; the
  contract is unchanged.
* Export is available to every role with `company.view` (ADR-046), including
  viewers, and is audited. Whether profitability should need a narrower capability
  is an open product decision.
* No saved views, scheduled reports or custom sorting; lists are newest first.
* Actual profit and document-supported margin stay unavailable: Finance exposes no
  transaction-level invoice or payment source.
* The sidebar highlights “Finance” on every `/finance/*` route (prefix match,
  unchanged since Stage 5D).
* Docker Compose and a GitHub Actions run were not executed.
* No migration, so there is no downgrade consideration for this stage.

### 26.7 Git

* Branch `stage-5e`, created from the verified Stage 5D HEAD `2be76ce`.
* `15c0028` — `feat(stage5e): add read-only financial intelligence backend`.
* `cb25759` — `feat(stage5e): regenerate OpenAPI contract and TypeScript types`.
* `e0b723e` — `feat(stage5e): add financial intelligence workspace`.
* `b2e5d19` — `fix(stage5e): label a figure-less metric UNAVAILABLE`.
* `dd4e458` — `test(stage5e): add financial intelligence to the isolated HTTP verifier`.
* `639eb82` — `docs(stage5e): record financial intelligence contract and verification evidence`.
* `697c94d` — `fix(stage5e): fix table, chart and label defects found in the browser review`.
* `0521567` — `docs(stage5e): record the browser review, its fixes and the open items`.
* `8510b52` — `fix(stage5e): polish filter labels, empty states, small shares, tooltips and losses`.
* `46d49fb` — `fix(stage5e): give the loss percentage line full-strength contrast`.
* The close-out documentation commit (this update).
* Nothing was pushed, merged or deployed; the Finance repository was not
  modified.

## 27. Stage 6 — AI Trade Director

### 27.1 Scope and boundary

Stage 6 adds an assistant that analyses the company's real records, explains them,
cites its sources and proposes drafts and tasks for a person to approve. It reads
through sixteen read-only tools that wrap existing services; it never calls Finance,
never sends a message and cannot change a deal, order, shipment, document or the
accounting. Approving a proposal records a human decision only.

**Branch:** `stage-6`, from the verified Stage 5E HEAD `3cb60c8`.
**Migration:** `0010_ai_office` (conversation, run, message, tool call, proposal; eleven
`ai.*` audit actions).
**Prompt version:** `trade_director@1.0.0`.
**Provider verification:** `MOCK_PROVIDER_VERIFIED` and `REAL_PROVIDER_BLOCKED` — no AI
credential is configured for Commerce, so no live provider call was made. A provider key that
belongs to another tool exists in the workstation's environment; it was neither read nor
used, because it was not issued for Commerce and using it would send commercial data to a
third party without the acknowledgement ADR-048 requires.

### 27.2 Delivered

* **6A** — `app/ai/gateway.py`, `providers/` (`mock`, OpenAI-compatible, Anthropic),
  `prompts.py`, budgets, limiter, cancel registry; settings and ADR-048.
* **6B** — `app/ai/tools/registry.py` (executor, closed-schema validation, blocked
  actions) and `readonly.py` (16 tools).
* **6C** — `app/ai/evidence.py` (registry, validator, basis rules), `director.py`
  (bounded loop, run lifecycle).
* **6D** — `app/ai/proposals.py`, `app/services/ai_office.py` (edit/approve/reject with
  live permission, state, version and target re-validation).
* **API** — `/api/v1/ai/*` (API_CONTRACTS §13), OpenAPI and TypeScript types regenerated.
* **6E** — `/ai` workspace: thread, validated answers with a basis badge per claim and
  links to the cited records, live tool progress with cancel, draft preview, permission-
  aware approve/edit/reject, history, activity, tool registry, provider status.
* **6F** — untrusted-text sanitiser and injection withholding, resource limits, failure
  handling, redaction; ADRs 049–053.
* **6I** — AA muted text, single navigation highlight, current footer, embedded empty
  states, 768 px verified.
* `backend/scripts/verify_finance_http.py` gained a Stage 6 step.

### 27.3 Automated results

| Command | Result |
| --- | --- |
| `pytest` (backend, isolated test database) | ``551 passed`` (402 before Stage 6) |
| of which new: `test_ai_api.py` / `test_ai_providers.py` / `test_ai_units.py` | 41 / 55 / 53 |
| `ruff check app tests` · `mypy app` | clean · no issues in 131 source files |
| `vitest` | ``192 passed` across 25 files` (160 before Stage 6) |
| `eslint .` · `prettier --check .` · `tsc --noEmit` | clean |
| `next build` | passes; `/ai` listed |
| `scripts\generate-api-types.ps1 -Check` | no drift |
| Alembic `0009 → 0010 → 0009 → 0010` (dev and test databases) | pass |
| `alembic check` | reports only the three differences that already existed (the `alembic_version` table and the table comments on three Stage 1A tables); none concern an AI table |
| `verify_finance_http.py` | `ISOLATED_HTTP_VERIFIED` (Stage 5C/5D/5E steps unchanged and passing) |

Not run in this stage: Docker Compose, GitHub Actions. `mypy tests` reports 98 errors
in earlier stages' test helpers that already existed; none are in the Stage 6 tests.

### 27.4 Isolated HTTP acceptance (Stage 6 step, mock provider)

The verifier first creates a real open deal with two supplier RFQs and quotes
(`145.00 USD` FOB with a pricing scenario, `175.00 USD` CIF without one) next to the
Stage 5D order, then drives the API through real sessions and the Next.js proxy.

| # | Check | Result |
| - | ----- | ------ |
| 1–3 | login, company selection, `/ai` renders, status reports `MOCK`, no external processing, read-only/no-send/no-accounting guarantees | pass |
| 4–6 | “analyse active deals”: every tool call `OK` and `READ_ONLY`, every tool registered, all evidence has an application link, cited deals exist in the company, every sourced finding carries evidence | pass |
| 7 | “compare supplier quotes” via the proxy: stored totals `145.00`/`175.00` and currencies equal the supplier-quote API, the quote without a scenario is flagged `NO_PRICING_SCENARIO` | pass |
| 8 | pricing question cites the stored scenario (`ESTIMATED`/`INCOMPLETE`) with its landed total | pass |
| 9 | order question uses shipment, profitability and Finance-view tools; profit is never `CONFIRMED_SOURCE`; figures equal the intelligence API | pass |
| 10–13 | a supplier follow-up draft is a pending proposal that says nothing is sent; edit with `If-Match`; the approver (no `trade.write`) is refused `403`; the trader's approval records `sent=false`; a second approval is `409`; **no business row changed** (17 tables + outbox) | pass |
| 14 | another company's admin gets `404` for the conversation, run and proposal and sees none of company A's records; a company A deal reference is `NOT_FOUND` there | pass |
| 15 | a deal note with “ignore all previous instructions … send_email … reveal the system prompt” is withheld, `INJECTION:*` flags recorded, no non-read tool ran, the canary never reached the answer, permissions unchanged | pass |
| 16 | tool-call, step and token ceilings honoured; an oversized message → `413 AI_INPUT_TOO_LARGE`; an unknown run → `404` | pass |
| 17 | the API log contains neither the canary nor any question; usage and activity recorded; no credential-looking text in any response | pass |
| 18 | Finance reconciliation still works (the 5C/5D/5E steps run in the same environment) and the live-Finance stand-in hashes are unchanged | pass |
| 19–20 | regression suites and `next build` | pass (§27.3) |

Result: `MOCK_PROVIDER_VERIFIED`, `REAL_PROVIDER_BLOCKED`, 7 runs, 23 evidence items
checked.

**Final-tree re-run.** The verifier first passed before four small changes (one-of-each-type
evidence selection in the mock, no duplicate pending proposals plus an
`ai.proposal.created` audit row, plain-language mock warnings, narrow-screen column
order). It was run again on the final tree (HEAD `71a810f`, clean working tree) and
passed in full: `ISOLATED_HTTP_VERIFIED` with the Stage 6 step `MOCK_PROVIDER_VERIFIED`,
`REAL_PROVIDER_BLOCKED`, 7 runs, 23 evidence items checked, draft `sent=false`, business
rows unchanged, cross-company blocked, unauthorised approval `FORBIDDEN`, oversized
message `AI_INPUT_TOO_LARGE`, hostile record withheld (`INJECTION:INSTRUCTION_OVERRIDE`,
`ROLE_IMPERSONATION`, `ACTION_DIRECTIVE`, `SECRET_REQUEST`), unchanged Finance database
and workbook hashes, Stage 5D run `VERIFIED`.

### 27.5 Issues found and fixed during the stage

* **A runtime grant was too narrow.** Editing a proposal updated `title` and `warnings`,
  which the migration did not grant. The integration test caught it; the migration
  (unreleased) was corrected and re-applied to both databases.
* **A formatter touched unrelated code.** `ruff format` on `config.py` rewrapped
  existing lines; the unrelated hunks were reverted before committing. Only new files
  are formatted.
* **“Active deals” was empty in the isolated order flow** because the Stage 5D deal is
  `WON`. The acceptance now creates a real open opportunity.
* **The mock crowded out categories.** With many discrepancies the Finance-view
  evidence fell outside the first eight cited items; the mock now cites one record of
  each type first.
* **Duplicate proposals.** Asking the same question twice created identical pending
  tasks; an identical pending proposal is no longer created again (test added), and
  every creation is audited (`ai.proposal.created`).
* **Raw warning codes in plain text.** Mock answers now use lower-case words.
* **Optional fields in the generated types.** Defaulted response fields were optional in
  OpenAPI; they are now required in the response schema.
* **Narrow-screen order.** Below 1280 px the conversation now comes first, then the
  proposals, then context and history.
* **A port conflict.** Dev servers started by another tool occupied 8000 and 3000; with
  the user's approval they were stopped so the isolated environment could run.

### 27.6 Browser review (isolated environment, real data, 1440 and 768 px)

`/ai` was exercised in the built-in browser against the isolated environment: a
suggested question was sent, the live “Records read” status completed, the validated
answer showed basis badges, figures and links to the quotes and the deal, a suggested
task was approved (“Approved by a person”), history reopened an earlier conversation
(with its loading state), and the earlier edited-and-approved draft showed “Preview —
not sent”. At 768 px the page stacks without horizontal overflow; `/finance/intelligence`,
its orders and exceptions pages, `/deals`, `/orders` and `/finance/reconciliation` also
fit. On `/finance/intelligence` only “Intelligence” is highlighted, the footer reads
“Stage 6 · AI Trade Director · Read-only, human-approved”, the muted token measures
`#7a8ba2`, and an empty exceptions list is one panel, not two.

Not reviewed in a browser: the provider-disabled state and a failed run (covered by
component tests), switching company in the UI (covered by the keyed-remount test and
the API isolation checks), 375 px for `/ai`.

### 27.7 Honest limitations and remaining debt

* **No live provider.** Wire formats are verified against local stubs of the documented
  APIs only. A first live call may reveal provider-specific behaviour (token accounting,
  tool-argument quirks); the gateway already tolerates invalid tool-argument JSON and
  missing usage.
* **The mock is not a model.** It plans by keywords and writes templated sentences from
  tool results; it cannot judge quality. The validator is what keeps a real model honest,
  and it is stricter than a human reviewer would be (a correct derived percentage is
  flagged).
* **Injection detection is pattern-based.** It withholds the common phrasings and hidden
  characters; a novel phrasing passes to the model, which is why authority never depends
  on it (ADR-052). A legitimate note that reads like an instruction is withheld from the
  assistant.
* **Single-process limits.** The cancellation registry and concurrency limiter live in
  the API process; a multi-process deployment needs shared state and a job runner. A run
  interrupted by a restart is marked failed after the deadline plus a minute.
* **Cost accounting is only as good as the configured prices**, which default to zero.
* **No outbound channel.** An approved draft must be copied by a person.
* **Conversations are private to the user; proposals are company-visible.** Whether a
  second person should see a colleague's conversation is an open product decision.
* **Search and pagination.** Tools return at most 20 items (configurable to 50) and say
  when more exist; there is no cursor tool.
* **Accessibility.** Contrast was fixed and measured; names, roles and keyboard focus
  were checked in components and the browser; no screen reader or full audit was run.
  The tool-progress region is `aria-live="polite"` and was not tested with assistive
  technology.
* **Empty conversations** (created by a refused message) stay in the history list.
* Docker Compose and a GitHub Actions run were not executed.

### 27.8 Git

* Branch `stage-6`, created from the verified Stage 5E HEAD `3cb60c8`.
* `c1d3268` — `feat(stage6): AI gateway, provider adapters and evidence model (6A)`.
* `242b82f` — `feat(stage6): read-only tools, Trade Director, approvals and /ai API (6B-6D, 6F)`.
* `0529995` — `feat(stage6): AI Office UI and Stage 6I interface debt (6E, 6I)`.
* `86b0448` — `fix(stage6): isolated acceptance step, proposal de-duplication, narrow-screen layout`.
* The close-out documentation commit (this update).
* Nothing was pushed, merged or deployed; the Finance repository was not modified.


---

## 28. Stage 7A — Communications groundwork (IN_PROGRESS)

Base: `stage-6` HEAD `4cf4f86`, fast-forwarded to `main` on GitHub.
Feature branch: `stage-7a`.

Initial implementation:
* New `communications.send` capability, explicitly assigned to **no role**.
* `GET /api/v1/communications/status`: DRAFT_ONLY; email and WhatsApp unconfigured, no sending.
* `GET /api/v1/communications/drafts`: bounded, tenant-RLS-scoped existing AI draft proposals only.
* `/communications`: draft listing plus honest channel state, no send buttons.
* New API tests for permission separation, bounded listing, unsent drafts and missing send endpoint.

**Verification pending:** tests and formatting have not been run in the user's Windows
PostgreSQL/Next.js environment for this branch. OpenAPI schema/client regeneration,
full backend/frontend regressions, migration head check, browser and isolated HTTP
acceptance are required before this milestone may be called PASSED.

**Scope deliberately excluded:** OAuth, SMTP, WhatsApp credentials/webhooks,
outbound sends, scheduled jobs, accounting writes, live Finance startup.


## 29. Stage 7B — Preflight for messaging (CI VERIFIED)

Branch `stage-7b` starts from Stage 7A merge commit `1db9b73`.
Only an authorized trader may POST `/api/v1/communications/preflight` with an
existing draft id/version, selected EMAIL/WHATSAPP_BUSINESS channel and an operator-
entered recipient. It validates the draft through active-company RLS, checks approval
and version and validates email format without DNS/network calls or phone E.164
shape. It **always responds `sendable=false`**, because neither provider is
configured nor the separate `communications.send` permission is granted.
Recipients are not persisted, echoed or delivered. The Communications UI presents
readiness blockers but has no send button or transport capability.

**Verification:** GitHub Actions workflow run `40019149502` PASSED (backend 558,
frontend 192, Ruff, mypy application source, Prettier, ESLint, TypeScript,
Next.js production build and OpenAPI drift). The new negative test exposed a
missing CSRF check, fixed in `e160815`. Stage 7B PR #2 merged into `main` at
`1140b06`. This acceptance is CI-only; no Windows browser or live provider
verification was performed.

**Open future work:** provider-specific OAuth/keys and lifecycle, revocation,
independent send approval, verified recipient association, immutable intent, queue
and idempotency, audit, webhook authenticity, delivery reconciliation and per-tenant
isolation. No live external calls or Finance writes.


---

## 30. Stage 7C1 — CRM recipient provenance, NOT provider authentication (CI VERIFIED)

Branch: `stage-7c`, based on Stage 7B docs HEAD `f44f405`.

* Preflight accepts optional `counterparty_id` with the operator-entered recipient.
* A private service compares the recipient with **one active counterparty
  in the authenticated active company**, applying PostgreSQL company RLS.
  It never returns, logs, saves, or sends a recipient address.
* Missing, archived, cross-company, or nonmatching CRM sources yield
  `CRM_RECIPIENT_MISMATCH`.
* Matching CRM data is not independently verified ownership or consent;
  `CONSENT_UNDOCUMENTED` is always emitted. `sendable=false` remains invariant.
* Communications UI lists up to 50 active CRM counterparties by name as
  provenance selectors and never displays their contact addresses.
* No OAuth, token store, Gmail/WhatsApp provider credentials, send endpoint,
  scheduled job, money handling, or Finance integration change.

**Verification:** GitHub Actions workflow `40021727161` PASSED: 561 backend,
192 frontend, Ruff, mypy app, ESLint, Prettier, TypeScript, Next.js production
build and OpenAPI drift. The new tests also caught and fixed an E.164 phone
regex escaping issue (`ac3c4ad`). PR #3 merged to `main` at `7624c33`.
**Not verified:** Windows interactive browser acceptance, contact ownership,
channel-specific consent, Gmail/WhatsApp provider auth, real delivery.

**Future Stage 7C:** verified contact control, independently audited
channel-specific consent evidence, opt-out/suppression, authorized provider
connection setup, revocation, dedicated send approval and delivery executor.


---

## 31. Stage 7C2 — Do-not-contact ledger (CI VERIFIED)

Feature branch: `stage-7c2`, based on CI-verified Stage 7C1 main
(`e26b93a`). Migration: `0011_communication_suppression`.

* Append-only `touche.communication_suppression`: tenant company, CRM
  counterparty, EMAIL/WHATSAPP_BUSINESS channel, bounded reason, administrator,
  timestamp, unique company+counterparty+channel. **No address/phone stored**.
* Strict composite foreign key to CRM, runtime SELECT+INSERT only, RLS
  tenant policies and no UPDATE/DELETE. Downgrade blocks if evidence exists.
* `communications.suppress` independent administrator-only permission;
  `communications.send` remains granted to no role.
* Admin-only GET/POST suppression APIs; POST requires session, active-company
  role, CSRF and a required Idempotency-Key, uses an atomic audit event
  (`communications.suppression.recorded`). Duplicate blocks preserve
  original reason and actor; no additional event.
* Existing preflight includes `RECIPIENT_SUPPRESSED` when applicable and
  continues to always return `sendable=false`.
* Communications workspace displays an admin-only do-not-contact panel
  requiring explicit acknowledgement of permanence.
* Backend tests target replay, duplication, permission refusal, audit,
  preflight denial and cross-company isolation.

**Verification:** GitHub Actions `40025166931` passed: backend 565, frontend
192, Ruff, mypy app, ESLint, Prettier, TypeScript, Next.js production build,
and OpenAPI drift. The `0011` migration applied successfully to ephemeral
PostgreSQL. PR #4 merged into main at `5bc7bdc`.
**Not verified:** Windows interactive browser, deployed permission checks,
provider authentication, contact control, opt-in evidence or actual delivery.
This remains **not** a provider or consent integration; sending is disabled.


## 32. Stage 7C3 — No-send provider requirements (IN_PROGRESS)
Introduces a structured, authenticated prerequisites contract and automated
assertions showing neither Gmail nor WhatsApp is connected, credentialed or
send-capable. GitHub CI is pending. This is not real provider integration,
verified consent, live sending or operational acceptance.


## 34. Stage 8 — Clean E-YAY paper-safe market context (IN PROGRESS)

A new default-disabled, authenticated Commerce GET at
`/api/v1/integrations/eyay/market` reads only E-YAY's **published**
`/api/v1/system/health` and `/api/v1/regime-report/current` interfaces from
literal 127.0.0.1/::1 loopback. Paper-safe and no-execution gates must be true.
Only an explicitly timestamped, <=15 minute old regime, up to 20 validated
public symbol signals and provenance are shown. No paper portfolio, positions,
orders, prices, finance data, real trading or business write paths are imported.

The implementation was prepared using the OpenAPI contract of
`twonezerotwo-hue/clean-e-yay` (main on 2026-10-23). Tests mock source GET
and verify disabled/unsafe/stale/protocol failure, SSRF host validation, and
that no position data leaks. GitHub CI / live E-YAY connectivity not yet verified.

Stage 8 **cannot be marked a live connected integration** until an isolated
HTTP acceptance run starts the actual E-YAY local runtime in an approved sandbox.


## 35. Stage 9 — Local operations and CI safety (IN PROGRESS)

- Added `scripts/start-local.ps1` to launch backend and frontend in separate
  Windows terminals with loopback-only ports and positive HTTP readiness probes.
  Refuses missing dependencies and occupied ports; does not bootstrap/delete
  a database or enable any external providers. Alembic is opt-in via
  `-ApplyMigrations` and requires an operator-verified backup.
- Changed `scripts/verify.ps1` to run `mypy app` (same shipped app scope as CI)
  and **fail** rather than report success when frontend dependencies are missing.
- Added Windows Actions job to parse both operational PowerShell scripts
  and static regression assertions. No live Windows deployment or backup/restore
  acceptance is claimed until exercised separately.

**Verification pending:** stacked PR and GitHub CI including Windows parser.


---

## 34. Stage 10 — Release-readiness contract (CI VERIFIED)

Stage 9's CI suite passed (backend, frontend, contract and Windows PowerShell
AST syntax) and PR #7 merged at `40a69d8`. This does not prove the local
Windows workstation was started or production operations are ready.

Stage 10 introduces a non-invasive, stdlib-only release gate:
`python scripts/release-gate.py --target ci|local|production`. CI checks
required repository files and refuses claims of enabled Gmail, WhatsApp,
Finance ledger writes, trading execution or production readiness. Local and
production targets deliberately fail closed until evidence that static CI
cannot provide is gathered separately. See
`docs/STAGE10_RELEASE_READINESS.md` for actual acceptance conditions.

**GitHub CI evidence:** workflow `40030032968` passed all four jobs:
585 backend tests (including new release-gate tests), 192 frontend tests,
PostgreSQL/Alembic, Ruff, mypy app, lint, Prettier, typecheck, Next.js build,
OpenAPI drift, and Windows PowerShell parsing. PR #8 merged as `4ff5518`.
This milestone verifies source/CI checks only: LOCAL_ACCEPTED and
PRODUCTION_APPROVED remain BLOCKED pending external evidence. No live Finance
data, provider accounts or financial operations were touched.

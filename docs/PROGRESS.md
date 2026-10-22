# TOUCHE COMMERCE — Progress

**Last updated:** 2026-10-22 (local)
**Current stage:** Stage 1B — Trade workspace (CRM, catalogue, deals)
**Current milestone:** M1B.1 — verified end-to-end with a real trader and administrator
**Stage 1C / Stage 2:** NOT_STARTED (must not begin without an explicit instruction)

Statuses are restricted to `NOT_STARTED`, `IN_PROGRESS`, `BLOCKED`, `PASSED`,
`FAILED`. Nothing is marked `PASSED` without an executed command in this file.

---

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
| Business modules beyond Stage 1B / integrations / AI agents | NOT_STARTED | Stage 2+ |

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



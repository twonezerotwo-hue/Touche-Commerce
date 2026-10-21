# TOUCHE COMMERCE — Progress

**Last updated:** 2026-10-22 (local) / 2026-10-21T22:5x UTC
**Current stage:** Stage 0 — Foundation
**Current milestone:** M0.1 — running skeleton verified end-to-end
**Stage 1A:** NOT_STARTED (must not begin without an explicit instruction)

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
| Authentication, sessions, RLS policies, audit | NOT_STARTED | Stage 1A |
| Business modules / integrations / AI agents | NOT_STARTED | Stage 2+ |

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

## 10. Next recommended task

**Stage 1A — milestone 1A.1: identity schema + RLS foundation.**

Concrete first step (requires an explicit instruction before starting):

1. Add migration `0002_identity` creating `user`, `company`, `membership`,
   `session`, `audit_record`, `idempotency_record`, `login_attempt` with
   `UNIQUE (id, company_id)` and composite FKs.
2. Enable RLS + policies on tenant-owned tables (`current_setting` based), keep
   `touche_app` without `BYPASSRLS`, grant only DML.
3. Implement the RLS isolation matrix tests from `ARCHITECTURE.md §7.2` **before**
   any endpoint is written, then the session/company services.

Verification gate for 1A.1: two seeded companies cannot see or mutate each
other's rows; no context means no rows; all tests run on a real PostgreSQL.

Do not start Stage 1A automatically.




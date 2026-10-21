# TOUCHE COMMERCE

Independent, premium international trade management — **Stage 0: foundation**.

A Next.js 16 web shell, a FastAPI service and PostgreSQL 17, wired together with
real health probes, structured logging, a standard error contract, a typed
OpenAPI pipeline and the documentation that governs later stages.

> Stage 0 contains **no business features, no AI agents, no CRM, no quotation
> workflow and no external integrations**. The UI states this explicitly and
> never displays fabricated KPIs or "connected" labels.

---

## Status

| Area | State |
| ---- | ----- |
| Frontend shell (`localhost:3000`) | ✅ verified |
| API (`127.0.0.1:8000`) | ✅ verified |
| PostgreSQL 17 + migration `0001_foundation` | ✅ verified |
| `/api/v1/health/live` · `/api/v1/health/ready` | ✅ 200 |
| Backend tests (unit + live DB) | ✅ 38 passed |
| Frontend tests / lint / typecheck / build | ✅ 22 passed, clean |
| Docker Compose path | ⚠️ not executed — Docker is not installed on this workstation |
| GitHub Actions run | ⚠️ workflow authored, no remote run performed |

Details, commands and raw results: **`docs/PROGRESS.md`**.

---

## Repository layout

```
frontend/     Next.js App Router shell, typed API client, generated OpenAPI types
backend/      FastAPI app, SQLAlchemy models, Alembic migrations, tests
infra/        docker-compose.yml, PostgreSQL init hook, local runtime (git-ignored)
scripts/      setup / migrate / dev / verify / db bootstrap (PowerShell + bash)
docs/         ARCHITECTURE, API_CONTRACTS, ROADMAP, PROGRESS, DECISIONS
.github/      CI workflow (lint → typecheck → test → build)
```

---

## Prerequisites

* Python **3.12** (tested with 3.12.10)
* Node.js **≥ 20.9** (tested with 24.18.0) and npm ≥ 10 (tested with 11.16.0)
* Git
* PostgreSQL 17 — either **Docker Compose** (recommended) or a local/portable
  installation (fallback used on this machine)

The detected workstation is Windows 11 with no Docker/WSL, so the scripts
include a portable-PostgreSQL bootstrap that needs no admin rights.

---

## Quick start (Windows / PowerShell)

```powershell
# 1. Environment + dependencies (idempotent)
scripts\setup.ps1

# 2. Database
#    a) Docker path (preferred when Docker exists):
docker compose -f infra\docker-compose.yml up -d
#    b) No Docker? Portable PostgreSQL 17.6 (downloads ~330 MB into infra\.local)
scripts\db\bootstrap-local-postgres.ps1

# 3. Migrations
scripts\migrate.ps1

# 4. Run (two terminals)
scripts\dev-backend.ps1      # http://127.0.0.1:8000  (docs: /docs)
scripts\dev-frontend.ps1     # http://localhost:3000

# 5. Verify everything
scripts\verify.ps1
```

## Quick start (Linux / macOS / CI)

```bash
bash scripts/setup.sh
docker compose -f infra/docker-compose.yml up -d
bash scripts/migrate.sh
bash scripts/dev-backend.sh    # terminal 1
bash scripts/dev-frontend.sh   # terminal 2
bash scripts/verify.sh
```

---

## What you should see

`http://localhost:3000` renders **Foundation status** with four live probes:

1. **Frontend** — proven by the successful server render.
2. **FastAPI service** — liveness status, HTTP code, latency and the echoed
   `X-Request-ID`.
3. **PostgreSQL** — readiness status, server version, runtime role
   (`touche_app`) and probe latency.
4. **OpenAPI v1** — the number of operations in the served contract.

Explicit failure states are implemented and were verified end-to-end:

| Scenario | Rendered state |
| -------- | -------------- |
| Everything up | "All probes nominal" |
| API stopped | "Unreachable", "API unreachable", remediation command |
| PostgreSQL stopped | "Degraded", "Database not ready", `DATABASE_UNAVAILABLE` |

No status is hardcoded: every value comes from an HTTP request made during that
server render (`force-dynamic`).

---

## API

| Method | Path | Purpose |
| ------ | ---- | ------- |
| `GET` | `/` | Service descriptor |
| `GET` | `/api/v1/health/live` | Liveness — never touches PostgreSQL |
| `GET` | `/api/v1/health/ready` | Readiness — verifies PostgreSQL via the runtime role |
| `GET` | `/api/v1/openapi.json` | OpenAPI 3.1 document |
| `GET` | `/docs` | Interactive documentation (disabled in production) |

Contracts and error codes: `docs/API_CONTRACTS.md`.

---

## Environment configuration

Copy `.env.example` → `.env` (done by the setup script). All backend settings use
the `TOUCHE_` prefix; secrets are wrapped and never logged.

| Variable | Purpose |
| -------- | ------- |
| `TOUCHE_ENVIRONMENT` | `local` · `test` · `ci` · `staging` · `production` |
| `TOUCHE_DATABASE_URL` | Runtime DSN (`touche_app`, DML only) |
| `TOUCHE_DATABASE_MIGRATION_URL` | Migration DSN (`touche_migrator`, DDL) |
| `TOUCHE_DATABASE_CONNECT_TIMEOUT_SECONDS` | Readiness connect budget (default 3) |
| `TOUCHE_CORS_ALLOWED_ORIGINS` | JSON array of allowed browser origins |
| `TOUCHE_SESSION_IDLE_TIMEOUT_SECONDS` / `..._ABSOLUTE_...` | Session policy (Stage 1A) |
| `TOUCHE_IDEMPOTENCY_TTL_HOURS` | Idempotency retention (24) |
| `TOUCHE_PAGINATION_DEFAULT_LIMIT` / `..._MAX_LIMIT` | 25 / 100 |
| `NEXT_PUBLIC_API_BASE_URL` | Browser-visible API base URL |
| `NEXT_PUBLIC_API_TIMEOUT_MS` | Client probe timeout (10 s, above the readiness budget) |

In `staging`/`production` the service **refuses to start** with an insecure
session cookie, non-HTTPS or loopback CORS origins, `debug=true` or non-JSON
logging.

Development credentials in `.env.example` are throw-away local values. Never
commit `.env`; never reuse those values in a real environment.

---

## Verification

```powershell
scripts\verify.ps1                    # backend lint/typecheck/tests + frontend checks + build
scripts\verify.ps1 -SkipBuild         # faster inner loop
backend\.venv\Scripts\python -m pytest -m integration   # live database only
```

```bash
bash scripts/verify.sh
```

The generated API artefacts must stay in sync:

```powershell
scripts\generate-api-types.ps1 -Check   # fails on drift
```

---

## Troubleshooting

| Symptom | Fix |
| ------- | --- |
| "Cannot reach the API" | Start `scripts\dev-backend.ps1`; confirm nothing else owns port 8000 |
| Readiness returns 503 | Start PostgreSQL (`scripts\db\start-local-postgres.ps1` or Docker) and run `scripts\migrate.ps1` |
| `docker` not recognised | Use the portable path: `scripts\db\bootstrap-local-postgres.ps1` |
| Port already in use | `Get-NetTCPConnection -LocalPort 3000`, then stop the owning process |
| Backend cannot import `app` | Run commands from `backend/` or use the provided scripts (they set the working directory) |
| Alembic cannot connect | Check `TOUCHE_DATABASE_MIGRATION_URL`; migrations use the migration role, not the runtime role |
| Frontend shows a stale status | The page is `force-dynamic`; use "Re-check status" or reload |
| Windows: `pg_ctl start` appears to hang | Fixed in the scripts by redirecting pg_ctl output to files; pull the latest scripts |

---

## Documentation

* `docs/ARCHITECTURE.md` — system structure, data, tenancy, security boundaries.
* `docs/API_CONTRACTS.md` — envelopes, health contracts, pagination,
  idempotency, concurrency, session switching.
* `docs/DECISIONS.md` — 18 binding ADRs with verification plans.
* `docs/ROADMAP.md` — Stage 0 → Stage 5 with exit criteria.
* `docs/PROGRESS.md` — executed commands, real test results, blockers, next task.

---

## Stage 0 acceptance

| # | Criterion | Result |
| - | --------- | ------ |
| 1 | Frontend starts | PASS |
| 2 | Backend starts | PASS |
| 3 | PostgreSQL reachable | PASS |
| 4 | Alembic migration succeeds | PASS |
| 5 | `/api/v1/health/live` → 200 | PASS |
| 6 | `/api/v1/health/ready` → 200 | PASS |
| 7 | Frontend displays real backend + DB status | PASS |
| 8 | Required local tests pass | PASS |
| 9 | Documentation updated | PASS |
| 10 | No application secrets committed | PASS |

Blocked / unverified: Docker Compose execution and remote GitHub Actions
(environment limitations, not code failures). See `docs/PROGRESS.md`.

Stage 1A has **not** been started.


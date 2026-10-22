# TOUCHE COMMERCE

Independent, premium international trade management — **Stage 4: sales orders,
procurement, logistics and trade documents**.

A Next.js 16 web application, a FastAPI service and PostgreSQL 17 with real
health probes, structured logging, a standard error contract, a typed OpenAPI
pipeline, Argon2id authentication, server-side sessions, four roles, row level
security and the complete quotation-to-delivery chain: deals, RFQs, supplier
quotes, landed-cost pricing, sales quotes, documented customer acceptance,
sales orders, supplier purchase orders, partial shipments, delivery evidence and
a private trade-document register.

> Stage 4 contains **no accounting, payments, external integrations or AI
> agents**. `WON` happens only when an order is created, dispatch and delivery
> require recorded evidence, and drafts are labelled DRAFT. Nothing is
> fabricated.

---

## Status

| Area | State |
| ---- | ----- |
| Frontend shell + auth UI + trade screens (`localhost:3000`) | ✅ verified |
| API (`127.0.0.1:8000`) incl. CRM, catalogue, deals, dashboard | ✅ verified |
| Sourcing API + screens (RFQs, supplier quotes, pricing, sales quotes, FX) | ✅ verified at API/integration level |
| Execution API + screens (orders, purchase orders, shipments, documents) | ✅ verified at API/integration/SSR level |
| PostgreSQL 17 + migrations `0001_foundation` … `0009_reconciliation` | ✅ verified |
| `/api/v1/health/live` · `/api/v1/health/ready` | ✅ 200 |
| Backend tests (unit + live DB incl. RLS matrix) | ✅ 317 passed |
| Frontend tests / lint / typecheck / build | ✅ 88 passed, clean |
| Finance read-only connector (`/api/v1/finance/*`) | ✅ Stage 5C; isolated HTTP PASS |
| Live identity verification (`scripts\verify-identity.ps1`) | ✅ 31 checks passed |
| Live trade workflow (`scripts\verify-trade.ps1`) | ✅ 39 checks passed |
| Live sourcing workflow (`scripts\verify-sourcing.ps1`) | ✅ 53 checks passed |
| Live operations workflow (`scripts\verify-operations.ps1`) | ✅ 45 checks passed |
| Docker Compose path | ⚠️ not executed — Docker is not installed on this workstation |
| GitHub Actions run | ⚠️ workflow authored, no remote run performed |
| Browser automation | ⚠️ unavailable — verified at HTTP/integration/SSR level only |

Details, commands and raw results: **`docs/PROGRESS.md`**.

---

## Repository layout

```
frontend/     Next.js App Router shell, auth screens, same-origin API proxy, typed client
backend/      FastAPI app, security primitives, services, models, migrations, tests
infra/        docker-compose.yml, PostgreSQL init hook, local runtime (git-ignored)
scripts/      setup / migrate / dev / verify / bootstrap / test-database (PowerShell + bash)
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

# 4. Create the first administrator + company (interactive, no default password)
scripts\bootstrap-admin.ps1

# 5. Run (two terminals)
scripts\dev-backend.ps1      # http://127.0.0.1:8000  (docs: /docs)
scripts\dev-frontend.ps1     # http://localhost:3000

# 6. Verify everything (automated checks)
scripts\verify.ps1
scripts\verify-identity.ps1 -Email you@company.example   # live auth/session checks
```

Additional companies and memberships are managed with the privileged CLI:

```powershell
cd backend
.\.venv\Scripts\python -m app.cli create-company --name "Meridian Commodities" --country AE --currency USD
.\.venv\Scripts\python -m app.cli membership grant --email a@b.example --company "Meridian Commodities" --role approver
.\.venv\Scripts\python -m app.cli membership revoke --email a@b.example --company "Meridian Commodities"
.\.venv\Scripts\python -m app.cli list memberships --company "Meridian Commodities"
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

`http://localhost:3000` requires a session. The flow is:

1. **`/login`** — email + password, inline validation, generic failure messages,
   rate-limit feedback, no token stored in the browser.
2. **`/select-company`** — shown when the account holds more than one membership;
   each switch rotates the session token.
3. **`/`** (Command Center) — signed-in user, active company, role, permissions,
   session timestamps and the three live infrastructure probes.
4. **`/account`** — profile, memberships, permissions and the session policy.
5. **`/status`** — public, read-only probe page (no session required) so operators
   can see infrastructure health when nobody can sign in.

Unauthenticated requests to any authenticated route redirect to
`/login?next=<path>`. If the API is unreachable the shell renders an explicit
"session unavailable" screen instead of guessing.

| Scenario | Rendered state |
| -------- | -------------- |
| Everything up | "All probes nominal" |
| API stopped | "Unreachable", "API unreachable", remediation command |
| PostgreSQL stopped | "Degraded", "Database not ready", `DATABASE_UNAVAILABLE` |
| No session | redirect to `/login` with the requested path preserved |
| Membership revoked | next request returns 401; sign in again to see the remaining companies |

No status is hardcoded: every value comes from an HTTP request made during that
server render (`force-dynamic`).

---

## API

| Method | Path | Purpose |
| ------ | ---- | ------- |
| `GET` | `/` | Service descriptor |
| `GET` | `/api/v1/health/live` | Liveness — never touches PostgreSQL |
| `GET` | `/api/v1/health/ready` | Readiness — verifies PostgreSQL via the runtime role |
| `POST` | `/api/v1/auth/login` | Sign in (rate limited, Origin validated) |
| `GET` | `/api/v1/auth/me` | Current user, active company, memberships, CSRF token |
| `POST` | `/api/v1/auth/logout` | Revoke the current session (CSRF required) |
| `GET` | `/api/v1/companies` | Companies the caller may access, with roles |
| `POST` | `/api/v1/session/company` | Switch active company and rotate the session token |
| `GET/POST` | `/api/v1/counterparties` | CRM list (cursor pagination) and create |
| `GET/PATCH` | `/api/v1/counterparties/{id}` | Read / update (`If-Match`) |
| `GET/POST` | `/api/v1/products` | Catalogue list and create |
| `GET/PATCH` | `/api/v1/products/{id}` | Read / update (`If-Match`) |
| `GET/POST` | `/api/v1/deals` | Deal list and create (lines included) |
| `GET/PATCH` | `/api/v1/deals/{id}` | Detail with history / header update (`If-Match`) |
| `POST` | `/api/v1/deals/{id}/transitions` | Validated status change (`Idempotency-Key` required) |
| `GET` | `/api/v1/dashboard/summary` | KPIs, pipeline and recent activity |
| `GET` | `/api/v1/openapi.json` | OpenAPI 3.1 document |
| `GET` | `/docs` | Interactive documentation (disabled in production) |

Every mutating request must carry a trusted `Origin` **and** (once authenticated)
an `X-CSRF-Token` header. Deal transitions also require an `Idempotency-Key`;
versioned updates require `If-Match`. Contracts and error codes:
`docs/API_CONTRACTS.md`.

---

## Security model (implemented)

* **Passwords** — Argon2id with per-hash salt; policy enforced when a password is
  set; unknown accounts receive equivalent hashing work so response time does not
  reveal existence.
* **Sessions** — random 256-bit tokens, stored only as SHA-256 digests; the
  browser holds an `HttpOnly`, `SameSite=Lax` cookie (`Secure` + `__Host-` prefix
  outside local development); 30-minute idle and 12-hour absolute expiry enforced
  server-side; token and CSRF token rotate on company switch.
* **Revocation** — logout, expiry and membership revocation revoke the row
  immediately; a revoked cookie is useless even before the browser drops it.
* **Tenant isolation** — PostgreSQL RLS on `company_settings`,
  `company_setting_entry`, `idempotency_record`, `company`, `membership` and
  `audit_record`, driven by transaction-scoped `touche.company_id` /
  `touche.actor_id`; the runtime role is `NOBYPASSRLS`; composite foreign keys
  prevent cross-tenant child rows.
* **Audit** — append-only `touche.audit_record` (grants + trigger), redacted JSON
  details, `request_id` correlation, no credentials or tokens.
* **Failure disclosure** — login errors are identical for unknown, disabled and
  wrong-password accounts; switching to a non-member company returns `403`
  without confirming whether the company exists.

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
| `TOUCHE_CORS_ALLOWED_ORIGINS` | JSON array of allowed browser origins (also the trusted `Origin` list) |
| `TOUCHE_SESSION_IDLE_TIMEOUT_SECONDS` / `..._ABSOLUTE_...` | 1800 s / 43 200 s |
| `TOUCHE_SESSION_COOKIE_SECURE` / `..._SAMESITE` / `..._NAME` | Cookie hardening; `__Host-` prefix is applied outside local development |
| `TOUCHE_PASSWORD_MIN_LENGTH` | Minimum policy length for new passwords (12) |
| `TOUCHE_ARGON2_TIME_COST` / `..._MEMORY_COST_KIB` / `..._PARALLELISM` | Argon2id cost (2 / 19 456 KiB / 1) |
| `TOUCHE_LOGIN_RATE_LIMIT_ATTEMPTS` / `..._WINDOW_SECONDS` / `..._IP_ATTEMPTS` | 10 per account / 300 s, 30 per source |
| `TOUCHE_IDEMPOTENCY_TTL_HOURS` | Idempotency retention (24) |
| `TOUCHE_PAGINATION_DEFAULT_LIMIT` / `..._MAX_LIMIT` | 25 / 100 |
| `TOUCHE_TEST_DATABASE_NAME` | Isolated database used by the integration suite |
| `TOUCHE_FINANCE_INTEGRATION_ENABLED` | `true` enables the loopback-only Finance connector (default `false`; no network I/O while disabled) |
| `TOUCHE_FINANCE_INTEGRATION_BASE_URL` | Literal loopback origin, default `http://127.0.0.1:8765`; DNS, HTTPS, credentials, paths, queries and fragments are rejected |
| `TOUCHE_FINANCE_INTEGRATION_KEY_ID` | Finance integration key id (`key_` + 16 hex); server-side only |
| `TOUCHE_FINANCE_INTEGRATION_SECRET` | Finance integration secret (32+ characters); server-side only, never `NEXT_PUBLIC_*` |
| `TOUCHE_FINANCE_INTEGRATION_TIMEOUT_SECONDS` | Request budget, 0.1–10 s (default 2) |
| `TOUCHE_FINANCE_INTEGRATION_MAX_RESPONSE_BYTES` | Bounded Finance response, default 1 MiB |
| `NEXT_PUBLIC_API_BASE_URL` | API origin used by server components |
| `API_INTERNAL_BASE_URL` | Optional internal proxy target (defaults to the public base URL) |
| `NEXT_PUBLIC_API_TIMEOUT_MS` | Client/SSR request budget (10 s) |

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
scripts\verify-identity.ps1 -Email you@company.example   # live auth/session/CSRF/proxy checks
scripts\verify-trade.ps1              # live 15-step CRM/catalogue/deal workflow
scripts\verify-sourcing.ps1           # live RFQ → quote → pricing → sales-quote workflow
scripts\verify-operations.ps1         # live acceptance → order → PO → shipment → document workflow
scripts\verify-finance-readonly.ps1   # read-only Finance DB/workbook hashes + health probe (never starts Finance)

scripts\db\setup-test-database.ps1    # (re)create the isolated integration database
backend\.venv\Scripts\python -m pytest -m integration   # live database only
```

`verify-trade.ps1` needs the passwords of the two local verification accounts in
the environment (never on the command line):

```powershell
$env:TOUCHE_VERIFY_TRADER_PASSWORD = '…'
$env:TOUCHE_VERIFY_ADMIN_PASSWORD  = '…'
scripts\verify-trade.ps1
```

`verify-operations.ps1` needs three accounts (trader + approver in one company,
viewer in another) and their passwords in the environment:

```powershell
$env:TOUCHE_VERIFY_STAGE4_TRADER_PASSWORD   = '…'
$env:TOUCHE_VERIFY_STAGE4_APPROVER_PASSWORD = '…'
$env:TOUCHE_VERIFY_STAGE4_OUTSIDER_PASSWORD = '…'
scripts\verify-operations.ps1
```

Optional, explicitly requested demo data (local/test/ci only):

```powershell
backend\.venv\Scripts\python -m app.cli seed-demo --company "TOUCHE Trading"
```

```bash
bash scripts/verify.sh
```

The generated API artefacts must stay in sync:

```powershell
scripts\generate-api-types.ps1 -Check   # fails on drift
```

The integration suite uses `touche_commerce_test` only: the DSN is derived from
the configured URLs by swapping the database name, and every test resets that
database. A development database cannot be truncated by a test run.

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
| Login returns 403 `ORIGIN_REJECTED` | Send a trusted `Origin` (the browser does automatically); update `TOUCHE_CORS_ALLOWED_ORIGINS` for other hosts |
| Login returns 429 | The account or source hit the rate limit; wait for `Retry-After` seconds |
| "Session unavailable" screen | The API is down or the session check failed; start the API and reload (no state was changed) |
| Pages redirect to `/login` in a loop | The API rejects the cookie (expired/revoked): sign in again; the redirect preserves `?next=` |
| Integration tests fail with "test database does not exist" | Run `scripts\db\setup-test-database.ps1` |
| Frontend shows a stale status | The page is `force-dynamic`; use "Re-check status" or reload |
| Windows: `pg_ctl start` appears to hang | Fixed in the scripts by redirecting pg_ctl output to files; pull the latest scripts |

---

## Documentation

* `docs/ARCHITECTURE.md` — system structure, data model, tenancy, RLS, sessions.
* `docs/API_CONTRACTS.md` — envelopes, auth/session contracts, error codes.
* `docs/DECISIONS.md` — 37 binding ADRs with verification evidence.
* `docs/ROADMAP.md` — Stage 0 → Stage 6 with exit criteria.
* `docs/PROGRESS.md` — executed commands, real test results, blockers, next task.

---

## Stage 1A acceptance

| # | Criterion | Result |
| - | --------- | ------ |
| 1 | Login works | PASS |
| 2 | Logout works | PASS |
| 3 | Sessions persist securely (HttpOnly cookie, hashed token) | PASS |
| 4 | Company selection works | PASS |
| 5 | Unauthorized company access is blocked | PASS |
| 6 | PostgreSQL RLS isolation tests pass | PASS (16 tests) |
| 7 | Membership revocation takes effect immediately | PASS (live + integration) |
| 8 | Audit logs record security actions | PASS (7 action types observed) |
| 9 | Frontend and backend work together | PASS (`scripts\verify-identity.ps1`) |
| 10 | All Stage 0 tests still pass | PASS |
| 11 | New tests pass | PASS (backend 120 total, frontend 45) |
| 12 | `PROGRESS.md` reports actual results | PASS |

Blocked / unverified: Docker Compose execution, remote GitHub Actions, browser
automation and POSIX shell execution (environment limitations, not code failures).
See `docs/PROGRESS.md` §11.

---

## Stage 1B acceptance

| # | Criterion | Result |
| - | --------- | ------ |
| 1 | Migration `0003_trade` applies, reverses and re-applies | PASS |
| 2 | CRM and catalogue CRUD with per-company uniqueness | PASS |
| 3 | Deal creation writes lines, history and audit atomically | PASS |
| 4 | Status only changes through the transition endpoint | PASS (422 on `PATCH status`) |
| 5 | Transition graph enforced (`INVALID_TRANSITION` with allowed targets) | PASS |
| 6 | `WON` disabled until orders exist | PASS (409 `TRANSITION_DISABLED`) |
| 7 | `LOST`/`CANCELLED` require a reason | PASS (422 `REASON_REQUIRED`) |
| 8 | Replays are idempotent; conflicting bodies rejected | PASS (`Idempotent-Replay`, 409) |
| 9 | Stale writes rejected (`428`/`409` + ETag) | PASS |
| 10 | Cross-tenant reads and writes blocked (API + RLS + composite FK) | PASS |
| 11 | Admin/viewer can read but not write trade data | PASS (403) |
| 12 | Dashboard reflects the database only | PASS (live workflow) |
| 13 | Frontend renders real API data on every trade page | PASS (build + SSR checks) |
| 14 | All earlier tests still pass | PASS (backend 191, frontend 60) |
| 15 | Documentation reports actual results | PASS (`docs/PROGRESS.md` §20) |

Stage 2 (dashboard expansion) and Stage 3 (sourcing, pricing and sales quotes)
are delivered. The sales *order* was deliberately deferred to Stage 4, so a won
deal could not claim an order that did not exist.


## Stage 3 acceptance

| # | Criterion | Result |
| - | --------- | ------ |
| 1 | Migration `0004_sourcing` applies, reverses and re-applies; no model drift | PASS |
| 2 | One RFQ per supplier, created atomically; buyer cannot be addressed | PASS |
| 3 | `PREPARED` writes an immutable revision; `SENT` needs channel, time and evidence | PASS |
| 4 | Editing a prepared RFQ returns it to DRAFT and opens the next revision | PASS |
| 5 | Supplier quotes are bound to the RFQ's supplier and line descriptions | PASS |
| 6 | Revisions supersede by new row; withdrawals keep history and require a reason | PASS |
| 7 | Cross-currency pricing needs an explicit, matching FX snapshot | PASS |
| 8 | ORDER costs allocate cent-exactly; LINE costs land on their product | PASS |
| 9 | Margin and markup are mutually exclusive and produce the documented prices | PASS |
| 10 | Scenario results are stored with their inputs and a calculation version | PASS |
| 11 | Recalculation requires a current `If-Match` and bumps the version | PASS |
| 12 | Sales quote submission requires `VERIFIED_INPUTS` | PASS |
| 13 | Approval requires `finance.approve` and a different person from the submitter | PASS |
| 14 | Rejection requires a reason; approved quotes are revised, not withdrawn | PASS |
| 15 | Cross-tenant reads blocked by RLS and composite FKs; audit rows written | PASS |
| 16 | Generated OpenAPI/TypeScript contract regenerated and builds | PASS |
| 17 | All earlier tests still pass | PASS (backend 236, frontend 71) |
| 18 | Documentation reports actual results | PASS (`docs/PROGRESS.md` §21) |

Stage 3 delivered sourcing, pricing and sales quotes. The logistics, shipment and
document parts of its original list were delivered in Stage 4, together with the
sales-order aggregate.

---

## Stage 4 acceptance

| # | Criterion | Result |
| - | --------- | ------ |
| 1 | Approved quote + documented customer acceptance produce a real order | PASS (acceptance gate + conversion) |
| 2 | `WON` and order creation are atomic | PASS (one transaction; live check 11-12) |
| 3 | Duplicate orders are prevented | PASS (unique index, replay, `ALREADY_WON`, concurrency test) |
| 4 | Accepted commercial terms are preserved | PASS (`accepted_terms` snapshot after quote revision/catalogue change) |
| 5 | Supplier purchase orders work | PASS (draft → approved → sent → confirmed, with evidence) |
| 6 | Shipments and partial quantities work | PASS (40/100 delivered, over-allocation refused) |
| 7 | Delivery events are traceable | PASS (timeline, actor, timestamps, evidence) |
| 8 | Trade document upload/download is secure | PASS (checksum, size/type limits, tenant + entity authorization) |
| 9 | Draft invoice/packing-list previews are honest | PASS (`is_draft`, legal notice, no issued claims) |
| 10 | Tenant isolation remains intact | PASS (RLS + composite FKs + cross-tenant 404s) |
| 11 | Frontend uses real backend APIs | PASS (8 SSR pages rendered in the live run) |
| 12 | All previous regressions pass | PASS (284 backend, 88 frontend) |
| 13 | New tests pass | PASS (48 backend, 17 frontend) |
| 14 | Production build passes | PASS (`next build`) |
| 15 | Documentation is current | PASS (`docs/PROGRESS.md` §22) |
| 16 | No accounting entries are fabricated | PASS (no invoice/payment endpoints or postings) |

Not implemented, by design: accounting ledger and postings, payments, Touche
Finance synchronisation, e-YAY, automated email/WhatsApp sending, AI agents and
live carrier tracking.

---

## Stage 5A acceptance

| # | Criterion | Result |
| - | --------- | ------ |
| 1 | Real Finance worktree and revision identified | PASS (`C:\ai-excel`, `main`, `8dce8245`; remote HEAD identical) |
| 2 | Finance API, auth, models, engine, Excel and SQLite inspected read-only | PASS (`docs/STAGE5_FINANCE_DISCOVERY.md`) |
| 3 | Commerce → Finance mapping is concrete | PASS (companies, counterparties, orders, POs, shipments, costs, documents, reports) |
| 4 | Missing interfaces are named, not invented | PASS (§8.1–§8.3 proposals; no fake client) |
| 5 | No second accounting engine in Commerce | PASS (no ledger/invoice/payment tables or endpoints) |
| 6 | Read-only integration verified before any write proposal | PASS (DB/workbook hashes unchanged; Finance not started) |
| 7 | Connector cannot impersonate Finance's local `OWNER` session | PASS (no cookie/bearer/Tailscale header; health only) |
| 8 | Connector is safe by default | PASS (disabled; loopback-only; 8 KiB cap; no redirects) |
| 9 | Status endpoint requires a Commerce session | PASS (`401` without a session) |
| 10 | Status cannot claim an accounting capability | PASS (`scope=health_only`, `accounting_writes_enabled=false`) |
| 11 | Finance remains financial source of truth | PASS (ADR-038; no postings) |
| 12 | Documentation and contracts current | PASS (`PROGRESS.md` §23, ADR-038/039/040, OpenAPI regenerated) |

Not implemented, by design: invoices, payments, ledger postings, outbox delivery
to Finance, counterparty auto-matching and reconciliation writes. The Stage 5B
read-only Finance contract has since been implemented and is consumed by the
Stage 5C connector below; Stage 5D reconciliation is still not started.

Reproduce the read-only proof:

```powershell
scripts\verify-finance-readonly.ps1
```


---

## Stage 5C acceptance — real read-only Finance connector

**Finance revision verified:** `feat/finance-integration-v1` /
`107c30e2ae4b5e4c22891f01ca730d3284994de5`.

**Commerce migration:** `0008_finance_mapping`.

The connector reads only
`GET /api/integration/v1/{health,capabilities,companies,companies/{id}/summary,companies/{id}/accounts,companies/{id}/aging}`.
It uses dedicated server-side key/secret headers, an explicit tenant mapping
(configured by an active company admin through `python -m app.cli finance-map`),
one explicit currency per request and no accounting writes.

Commerce endpoints:

```text
GET /api/v1/finance/status
GET /api/v1/finance/capabilities
GET /api/v1/finance/summary?currency=TL
GET /api/v1/finance/accounts?currency=TL&from=...&to=...
GET /api/v1/finance/aging?type=receivable|payable&currency=TL
```

The `/finance` page provides Overview, Accounts, Receivables and Payables views
with connection state, mapped company, currencies, data-through, source balances
and FIFO aging. Invoice and payment data is explicitly “Not available”.

**Verification:** `ISOLATED_HTTP_VERIFIED` using a disposable Finance runtime,
synthetic ledger, temporary credentials, real Commerce API/Next.js HTTP requests,
cross-tenant refusal and unchanged Finance hashes. No live Finance server was
started. Full evidence and limitations are in
`docs/FINANCE_INTEGRATION_CONTRACT.md` and `docs/PROGRESS.md` §24.

**Not implemented:** invoices, payments, bank transfers, ledger/journal writes,
automatic reconciliation, AI Trade Director, Gmail/WhatsApp automation and
E-YAY integration.

---

## Stage 5D acceptance — evidence-based financial reconciliation

**Commerce migration:** `0009_reconciliation`.

Stage 5D keeps Finance read-only and records **evidence**, not accounting entries.
It snapshots one accepted order against Finance's supported per-currency summary
and aging surface, stores stable Finance source ids, requires explicit operator
links, produces deterministic discrepancies and permits `VERIFIED` only through a
separate `finance.reconcile` reviewer.

New screens:

```text
GET /finance/reconciliation
GET /finance/reconciliation/[id]
GET /finance/discrepancies
GET /finance/orders/[id]
```

New API surface:

```text
GET/POST /api/v1/finance/reconciliation[/runs]
GET/POST /api/v1/finance/evidence-links
GET/POST /api/v1/finance/discrepancies[/{id}/resolve]
POST     /api/v1/finance/reviews
GET      /api/v1/finance/orders/{id}
```

**Verification:** backend `379 passed`; frontend `102 passed` across 18 files;
`ISOLATED_HTTP_VERIFIED` with a real accepted order, exact USD evidence,
unauthorized-review refusal, reviewer verification, unlinked-run refusal,
cross-tenant isolation, all four screens and unchanged Finance hashes. See
`docs/STAGE5D_RECONCILIATION.md`.

**Not implemented:** Finance writes, invoices, payments, bank transfers,
journals, actual-profit calculation, document-supported margin, AI Trade
Director, Gmail/WhatsApp automation and E-YAY integration.


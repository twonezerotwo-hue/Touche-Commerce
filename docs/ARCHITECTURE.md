# TOUCHE COMMERCE — Architecture

**Status:** Stages 0–6 are implemented with local verification recorded in PROGRESS.
Stage 6 is mock-provider verified, not live-provider verified. Stage 7A is in
progress on a feature branch and has not completed local regressions.
**Audience:** engineers and reviewers working on Stage 2 and later.
**Companion documents:** `docs/DECISIONS.md` (binding ADRs), `docs/API_CONTRACTS.md`,
`docs/ROADMAP.md`, `docs/PROGRESS.md`, `docs/FINANCE_INTEGRATION_CONTRACT.md`.

---

## 1. Purpose and scope

TOUCHE COMMERCE is an independent, premium international trade management
application. It will eventually integrate with E-YAY, Touche Finance, Gmail,
WhatsApp Business and TOUCHE ONE.

Stage 0 delivered **infrastructure only**: a running web shell, a running API, a
migrated PostgreSQL database, health probes, the error/logging/correlation
foundation, the contract-generation pipeline and the documentation that binds
later stages. Stage 1A added identity, server-side sessions, multi-company
membership, RLS and the audit trail. Stage 1B adds the first business workflow:
counterparties, products, deals with a validated state machine, and a dashboard.
Quotations, orders, logistics, finance and AI remain out of scope and are not
rendered as if they existed.

---

## 2. System context

```
┌──────────────────────┐      HTTP / JSON       ┌──────────────────────┐
│  Next.js 16 (App)    │ ─────────────────────► │  FastAPI (API v1)    │
│  localhost:3000      │ ◄───────────────────── │  127.0.0.1:8000      │
│  React 19, Tailwind  │   X-Request-ID, ETag   │  SQLAlchemy 2        │
└──────────────────────┘                        └──────────┬───────────┘
                                                           │ psycopg 3
                                                           │ role: touche_app
                                                ┌──────────▼───────────┐
                                                │ PostgreSQL 17        │
                                                │ schema: touche       │
                                                │ RLS-ready            │
                                                └──────────────────────┘

Future (Stage 2+): transactional outbox → relay worker → E-YAY, Touche Finance,
Gmail, WhatsApp Business, TOUCHE ONE.
```

| Service  | Local address | Notes |
| -------- | ------------- | ----- |
| Frontend | `http://localhost:3000` | Next.js App Router, server components |
| Backend  | `http://127.0.0.1:8000` | FastAPI, OpenAPI at `/api/v1/openapi.json`, docs at `/docs` |
| Database | `127.0.0.1:5432` | PostgreSQL 17, database `touche_commerce` |

---

## 3. Modular monolith

One deployable frontend and one deployable API, with a single PostgreSQL
database (ADR-001). Modules are separated by package boundaries, not by network
calls. No microservices, Redis, Kubernetes or Kafka are introduced without a
demonstrated need.

### 3.1 Repository layout

```
touche-commerce/
├── frontend/                 Next.js App Router shell + generated API types
│   ├── src/app/              routes: /, /crm, /products, /deals, /deals/new, /deals/[id]
│   ├── src/components/       shell, system-status, trade forms/tables, ui primitives
│   ├── src/lib/api/          typed client, server reader, generated schema.d.ts
│   ├── src/lib/trade/        trade DTO aliases, formatting helpers, browser client
│   └── openapi/openapi.json  exported from FastAPI (committed, drift-checked)
├── backend/                  FastAPI service
│   ├── app/core/             configuration, logging, errors, middleware, context
│   ├── app/db/               engine/session, tenant context, ORM models (incl. trade)
│   ├── app/api/v1/           versioned routers, schemas (source of TS types), etag helpers
│   ├── app/services/         auth, audit, crm, catalog, trade, deal_state, idempotency
│   ├── alembic/              migration environment + versions (0001–0003)
│   ├── scripts/              export_openapi.py, verify_trade_workflow.py
│   └── tests/                unit + live-database integration tests
├── infra/                    docker-compose.yml, Postgres init hooks, local runtime
├── scripts/                  setup / migrate / dev / verify (PowerShell + bash)
├── docs/                     architecture, contracts, roadmap, progress, ADRs
└── .github/workflows/ci.yml  lint → typecheck → test → build
```

### 3.2 Backend layering

```
app/api/v1/routes        ← HTTP only: validation, status codes, dependency wiring
app/api/v1/schemas       ← Pydantic contracts (single source for OpenAPI/TS)
app/api/security.py      ← session resolution, CSRF, permission dependencies
app/services             ← auth/session service, audit writer, admin (CLI)
app/security             ← Argon2id, opaque tokens, role→permission matrix
app/db                   ← SQLAlchemy models, engine, transaction/tenant scope
PostgreSQL               ← constraints, RLS, composite FKs
```

Rules:

* Dependencies point downward only; routes never issue ad-hoc SQL.
* Services own their transaction boundaries. Login/revocation deliberately commit
  the failure audit row *before* raising, so a refused attempt is still recorded.
* Authorization is decided server-side, never in the browser and never by an AI
  tool (ADR-018).
* Tenant-scoped transactions set `touche.company_id` / `touche.actor_id` with
  `SET LOCAL` inside the same transaction that queries the data.

### 3.3 Module status

Implemented: `identity` (`app/services/auth.py`, `admin.py`), `audit`
(`app/services/audit.py`), `security` (`app/security/*`), `tenancy`
(`app/db/tenant.py`, RLS policies), `crm` (`app/services/crm.py`), `catalog`
(`app/services/catalog.py`) and `trade` (`app/services/trade.py`,
`deal_state.py`, `idempotency.py`).

Planned (not implemented, no partial screens): `quoting` (RFQ, quotes), `orders`,
`logistics`, `finance`, `documents`, `settings`, `integrations` (outbox relay),
`ai` (assistants restricted to authorized tools). Each becomes a package under
`app/services` with its own router under `app/api/v1/routes/`.

---

## 4. Configuration

All runtime configuration is environment-driven with the `TOUCHE_` prefix and is
validated by `app/core/config.py` at start-up:

* Required DSNs: `TOUCHE_DATABASE_URL` (runtime role) and
  `TOUCHE_DATABASE_MIGRATION_URL` (migration role).
* Secrets are `SecretStr` values; `repr()` and logs never contain them.
* Non-local environments (`staging`, `production`) additionally require
  `session_cookie_secure=true`, `debug=false`, JSON logging and HTTPS,
  non-loopback CORS origins. The process refuses to start otherwise.
* Policy values are centralised (session idle 1800 s, absolute 43 200 s,
  pagination 25/100, idempotency TTL 24 h, login rate limit 10/300 s).
* Identity policy values are configuration, not constants: cookie name/secure/
  SameSite/domain, Argon2id cost (time 2, memory 19 MiB, parallelism 1), password
  minimum length 12, per-account and per-source login limits. Tests use a cheap
  Argon2 profile; production can raise the cost without a code change.
* The FastAPI app is created through the `create_app()` factory
  (`uvicorn app.main:create_app --factory`) so importing the module has no
  configuration side effects.

`.env.example` documents every variable with development-only credentials.
Real secrets must come from the platform secret store; `.env` is git-ignored.

---

## 5. Observability and request correlation

Implemented in `app/core/{middleware,logging,context,errors}.py`.

* **Request id** — `X-Request-ID` is accepted when it matches
  `[A-Za-z0-9._:-]{8,128}`, otherwise a fresh UUID4 hex is generated. It is
  bound to a `contextvars` value, echoed on every response (including errors)
  and injected into every log line emitted while handling the request.
* **Access log** — one structured line per request with method, path, status and
  duration. Query strings, bodies, cookies and headers are never logged.
* **Structured JSON logging** — single-line JSON with `timestamp`, `level`,
  `logger`, `message`, `service`, `environment`, `version`, `request_id` and
  explicit `extra` fields. Field names that look sensitive (`password`,
  `token`, `secret`, `authorization`, `cookie`, `session_id`, `api_key`,
  `document_body`, `request_body`, `response_body`, …) are redacted
  defensively; the formatter never serialises request or response bodies.
* **Error envelope** — every non-2xx response shares one shape (see
  `docs/API_CONTRACTS.md`). Unexpected exceptions are logged with a stack trace
  and returned as an opaque `INTERNAL_ERROR`; driver messages are sanitised to
  remove DSN credentials and truncated.
* **Uvicorn** loggers are re-routed through the same JSON sink, so the process
  emits one log format.

Health semantics:

| Endpoint | Purpose | Dependencies |
| -------- | ------- | ------------ |
| `GET /api/v1/health/live` | The process serves HTTP | **none** (never touches PostgreSQL) |
| `GET /api/v1/health/ready` | Required dependencies usable | PostgreSQL via the runtime role |

Readiness runs a real `SELECT current_setting('server_version'), current_user`
plus `SELECT 1`, bounded by the connection timeout (3 s) and
`statement_timeout` (5 s). Failures return `503` with `NOT_READY` and a
`checks[]` array. The frontend probe timeout (10 s) is deliberately larger than
the backend readiness budget so a database outage renders as **Degraded**, not
as a client-side timeout.

---

## 6. Database architecture

* **One database**, schema `touche` for application tables (created by migration
  `0001_foundation`), `public` for the Alembic version table.
* **Two roles** (ADR-004):
  * `touche_migrator` — owns the database/schema, runs Alembic, has DDL rights.
  * `touche_app` — runtime role: `NOSUPERUSER`, `NOCREATEDB`, `NOCREATEROLE`,
    `NOREPLICATION`, `NOBYPASSRLS`, no `CREATE` on schema `touche`, DML only.
  * `touche_admin` — local cluster superuser, used only for bootstrap.
* **Migrations** — Alembic with `target_metadata = Base.metadata`,
  `include_schemas=True`, `compare_type`, `compare_server_default`.
  Environment: `backend/alembic`. The DSN comes from
  `TOUCHE_DATABASE_MIGRATION_URL`; credentials never live in `alembic.ini`.
* **Session/transaction foundation** — `app/db/engine.py` provides a pooled
  engine (`pool_pre_ping`, bounded pool, `statement_timeout`,
  `idle_in_transaction_session_timeout`), a `session()` context manager that
  always closes and rolls back on error, and a `transaction()` scope.
* **Integration verification** — `backend/tests/test_database_foundation.py`
  proves on a live database that the migration is applied, the runtime role is
  not a superuser, cannot bypass RLS, cannot create objects, can write the
  outbox table, and that `SET LOCAL` does not survive its transaction.

### 6.1 Table inventory

| Table | Purpose | Tenant column | RLS |
| ----- | ------- | ------------- | --- |
| `app_user` | Global identities, Argon2id hash, status, timestamps | — | no (login bootstrap) |
| `company` | Tenant root: name, country, default currency, status | `id` | yes (membership required) |
| `membership` | `(user, company)` + role + active/revoked | `company_id` | yes |
| `auth_session` | Server-side session; hashed token, CSRF token, expiry, revocation, IP/UA | `company_id` (nullable) | no (token lookup precedes context) |
| `login_attempt` | Rate-limit counters and forensics | — | no (no API exposure) |
| `audit_record` | Append-only audit trail | `company_id` (nullable) | yes (tenant reads, insert-only) |
| `idempotency_record` | Durable replay records (implemented in 1B) | `company_id` | yes |
| `company_settings` | Per-company settings container | `company_id` | yes |
| `company_setting_entry` | Key/value children with a composite FK | `company_id` | yes |
| `counterparty` | Customers/suppliers: name, type, country, contact, version | `company_id` | yes |
| `product` | Catalogue: SKU, unit, currency, unit price, version | `company_id` | yes |
| `deal` | Deal header: reference, status, counterparty, currency, version | `company_id` | yes |
| `deal_item` | Deal lines; composite FKs to `deal` and `product` | `company_id` | yes |
| `deal_transition` | Append-only status history (no UPDATE/DELETE grant) | `company_id` | yes |
| `outbox_event` | Transactional outbox for later integrations | `company_id` (nullable) | no (Stage 2 relay) |

Naming rationale (`app_user`, `auth_session`) is recorded in ADR-019. The scope of
RLS and the reason three identity tables are not policy-protected is ADR-023.

Owner bypass: `touche_migrator` owns the tables and therefore bypasses RLS (no
`FORCE ROW LEVEL SECURITY`, which would break migrations and seed scripts). That
role is never used by the API; the runtime DSN is a separate secret. The
privileged CLI (`python -m app.cli`) uses the migration role deliberately, because
bootstrapping the first company/user happens before any tenant context can exist.

### 6.2 Transactional outbox (foundation only)

`touche.outbox_event` exists with: `id`, `company_id`, `event_type`,
`aggregate_type`, `aggregate_id`, `payload` (JSONB), `occurred_at`,
`available_at`, `attempts`, `last_error`, `processed_at`, `created_at`, a
partial index on pending rows and a `(company_id, occurred_at)` index.

Stage 0 creates the durable table and ORM mapping only. Producers and the relay
worker arrive with the first business module (Stage 2), written in the same
transaction as the business change. No external system is contacted today.

---

## 7. Multi-company isolation (implemented in Stage 1A)

* Every tenant-owned table carries `company_id uuid NOT NULL` referencing
  `touche.company(id)` (`idempotency_record` and `audit_record` allow `NULL` only
  for system-level events).
* The runtime role never has `BYPASSRLS`. Policies compare `company_id` with
  `touche.current_company_id()`, a `STABLE` SQL function wrapping
  `current_setting('touche.company_id', true)`; a missing setting yields `NULL`,
  so the predicate matches **no rows** (fail closed).
* `membership` additionally allows a user to read their own rows
  (`user_id = touche.current_actor_id()`), and `company` is readable only when an
  active membership exists for the actor — so `GET /companies` cannot leak other
  tenants even without an explicit `WHERE`.
* Context is applied with `SET LOCAL` (`set_config(..., true)`) inside the same
  transaction that reads or writes the data, so a pooled connection cannot leak a
  tenant to the next request. `app/db/tenant.py` refuses to apply context outside
  a transaction.
* The active company lives in the **server-side session row** (never in a client
  value). `POST /api/v1/session/company` verifies an active membership first,
  rotates the session token, then writes the audit row.
* Every authenticated request re-verifies that the session's company still has an
  active membership; if not, the session is revoked and `401` is returned.
* Removing a membership revokes all sessions bound to that company in the same
  transaction (`membership_revoked`), leaving other memberships untouched.

### 7.1 Composite foreign keys

Tenant-owned children reference parents by `(id, company_id)` so a row can never
point at another company's parent — even if a policy is missing. This is
implemented today for `company_setting_entry → company_settings`:

```sql
ALTER TABLE touche.company_settings
    ADD CONSTRAINT uq_company_settings_id_company_id UNIQUE (id, company_id);

ALTER TABLE touche.company_setting_entry
    ADD CONSTRAINT fk_company_setting_entry_settings
        FOREIGN KEY (settings_id, company_id)
        REFERENCES touche.company_settings (id, company_id)
        ON DELETE CASCADE;
```

Future business tables follow the same pattern, e.g.:

```sql
CREATE TABLE touche.trade_deal (
    id          uuid PRIMARY KEY DEFAULT gen_random_uuid(),
    company_id  uuid NOT NULL REFERENCES touche.company (id),
    status      text NOT NULL,
    CONSTRAINT uq_trade_deal_id_company UNIQUE (id, company_id)   -- referenced key
);

CREATE TABLE touche.sales_order (
    id          uuid PRIMARY KEY DEFAULT gen_random_uuid(),
    company_id  uuid NOT NULL REFERENCES touche.company (id),
    deal_id     uuid NOT NULL,
    status      text NOT NULL,
    CONSTRAINT fk_sales_order_deal_same_company
        FOREIGN KEY (deal_id, company_id)
        REFERENCES touche.trade_deal (id, company_id)
);
```

### 7.2 RLS isolation matrix (executed)

`backend/tests/test_rls_isolation.py` runs 16 tests with the **runtime** role on
the isolated test database:

| Requirement | Test | Verified behaviour |
| ----------- | ---- | ------------------ |
| Runtime role is least privilege | `test_runtime_role_is_least_privileged` | `rolbypassrls=false`, `rolsuper=false` |
| Cannot disable RLS | `test_runtime_role_cannot_switch_rls_off` | `SET row_security = off` + query raises |
| No DDL | `test_runtime_role_has_no_ddl_rights` | `CREATE TABLE` denied |
| Missing context fails closed | `test_missing_tenant_context_returns_no_rows` | 0 rows from company/membership/settings/audit |
| Transaction pooling cannot leak | `test_context_is_cleared_after_commit` | after `COMMIT`, setting empty and reads return 0 |
| No cross-connection leakage | `test_two_connections_never_share_context` | each connection sees only its own tenant |
| Reads are scoped | `test_settings_are_scoped_to_the_active_company` | only the active company's entries |
| Company visibility needs membership | `test_company_rows_require_a_membership` | companies A+B visible, C hidden |
| Membership rows are actor-scoped | `test_user_b_sees_only_their_own_membership` | 1 row for user B |
| Audit reads are tenant-scoped | `test_audit_rows_are_scoped_to_the_active_company` | only company A rows |
| Cross-tenant insert rejected | `test_cross_tenant_insert_is_rejected` | RLS violation |
| Cross-tenant update/delete no-op | `test_cross_tenant_update_changes_nothing`, `..._delete_...` | 0 rows, data intact |
| Composite FK blocks cross-tenant child | `test_composite_foreign_key_blocks_a_cross_tenant_child` | FK violation |
| Audit is append-only | `test_runtime_role_cannot_update_or_delete_audit_rows`, `test_trigger_also_protects_the_table_from_the_owner` | permission denied / trigger raises |

### 7.3 Scope boundaries (deliberate)

`app_user`, `auth_session` and `login_attempt` are **not** protected by RLS:
authentication must read a user by email and a session by token hash *before* any
actor or tenant is known. Their protection is the absence of any direct API
exposure plus least-privilege grants; every access goes through
`AuthService`/`AdminService`. Any future exposure of these tables must go through
a `SECURITY DEFINER` function, not a loosened policy. See ADR-023.

The composite foreign key makes cross-company references structurally
impossible; RLS then prevents cross-company *reads*.

### 7.2 RLS test strategy (Stage 1A)

1. Seed two companies with a member in each and one child row per company.
2. Connect as `touche_app`, open a transaction, `SET LOCAL` company A, and
   assert only A's rows are visible for every tenant-owned table.
3. Attempt to read/update B's row by id → zero rows / policy violation.
4. Attempt to insert a child row referencing B's parent while scoped to A →
   composite FK or policy rejection.
5. Commit and run the same query in a new transaction **without** context →
   zero rows (fail closed), proving `SET LOCAL` did not leak through the pool.
6. Attempt a schema change as `touche_app` → permission denied.
7. Query `pg_roles` to prove `rolbypassrls = false` for the runtime role.

---

## 8. Identity, sessions and authorization (Stage 1A)

Stage 0 intentionally ships **no authentication**. The following is the binding
design; it is not implemented and the UI says so.

* **Sessions** are server-side rows in PostgreSQL. The browser holds a random
  256-bit token in an `HttpOnly`, `Secure`, `SameSite=Lax` cookie
  (`__Host-touche_session` outside local development). Only a SHA-256 hash of the
  token is stored.
* **Policies** — 30-minute idle timeout, 12-hour absolute timeout, session
  rotation on login, privilege change and company switch.
* **CSRF** — double-submit token in `X-CSRF-Token` for state-changing requests,
  validated against the session; `SameSite=Lax` is defence in depth, not a
  replacement.
* **Login rate limiting** — 10 attempts / 300 s per account+source, recorded in
  PostgreSQL (no Redis).
* **Roles** — `viewer`, `trader`, `approver`, `admin`. Financial approval is a
  separate permission (`finance.approve`) that `admin` does **not** imply.
* **Verified memberships** — `membership(company_id, user_id, role, status,
  verified_at)`; only `active` memberships grant access.
* **Revocation** — membership removal revokes sessions bound to that company;
  role changes rotate the session and force re-evaluation.

UI consequence: every screen must present the *server-verified* actor, company
and permissions; the frontend never infers authority from local state.

---

## 9. Financial data

* Money and quantities use `Decimal` in Python, `NUMERIC` in PostgreSQL and
  decimal strings in JSON. Floats are forbidden end-to-end.
* Every amount carries an explicit ISO 4217 currency code (three letters).
* Currency conversion always persists `fx_rate`, `fx_effective_date` and
  `fx_source` alongside the converted amount, so historical documents remain
  reproducible after rates change.
* The frontend formats decimals for display only; it never performs arithmetic
  that affects persisted values.

---

## 10. Audit

Append-only table `touche.audit_record` with exactly these columns:
`event_id`, `company_id`, `actor_type`, `actor_id`, `action`, `entity_type`,
`entity_id`, `before` (JSONB, redacted), `after` (JSONB, redacted), `request_id`,
`occurred_at`.

* Written in the same transaction as the change it describes.
* No `UPDATE`/`DELETE` grants for the runtime role; a trigger rejects
  modifications (defence in depth).
* Redaction happens before serialisation (secrets, tokens, document bodies and
  payment data are replaced with `[redacted]`).
* Audit is not a business log: it records who changed what, on which company,
  correlated by `request_id`.

---

## 11. Document storage

Interface (implemented in Stage 1B/2, designed now):

```python
class DocumentStorage(Protocol):
    def put(self, *, key: str, data: BinaryIO, content_type: str) -> StoredDocument: ...
    def get(self, key: str) -> tuple[BinaryIO, str]: ...
    def delete(self, key: str) -> None: ...
    def presigned_url(self, key: str, *, expires_in_seconds: int = 300) -> str | None: ...
```

* Keys are **server-generated**: `companies/{company_id}/{category}/{uuid4}{ext}`
  with a whitelisted extension. Client filenames are metadata only and never
  used as paths (no traversal, no collisions).
* A local filesystem implementation comes first (directory outside the
  repository or a configured volume), S3-compatible storage later; callers
  depend only on the interface.
* `presigned_url` returns `None` for backends that do not support it, and the
  API then streams through `get()`.

---

## 12. Idempotency, concurrency and pagination (implemented in Stage 1B)

* `Idempotency-Key` is scoped by `(company_id, actor_id, endpoint, key)`, TTL
  24 h, stored in `touche.idempotency_record` with the request fingerprint and the
  original response (ADR-012, ADR-026).
* The idempotency row and the business change commit in **one** transaction. A
  unique constraint serialises concurrent duplicates: the loser replays the
  committed response or receives `409 IDEMPOTENCY_IN_PROGRESS` with
  `Retry-After: 1`. A reused key with a different fingerprint returns
  `409 IDEMPOTENCY_CONFLICT`. Replays return the stored body with
  `Idempotent-Replay: true`.
* Deal transitions require a key; other writes accept one. A failed request rolls
  the record back, so a retry is safe.
* Optimistic concurrency uses a monotonically increasing `version` and an
  `ETag: "v{version}"`. Mutations require `If-Match` (`428
  PRECONDITION_REQUIRED` when absent, `409 VERSION_CONFLICT` when stale, with the
  current ETag in the response). Transitions additionally lock the row.
* Pagination: `limit` default 25, maximum 100, opaque cursors bound to the filter
  set (a cursor from another filter combination is `422`), stable order
  `created_at DESC, id DESC`.

---

## 13. Frontend architecture

* Next.js 16 App Router, React 19, TypeScript strict, Tailwind CSS 4, shadcn/ui
  style primitives (owned in-repo, not an external dependency), Lucide icons.
* Server components perform the status probes; status pages are `force-dynamic`
  so a build can never embed a stale "online" label.
* All DTO types come from `src/lib/api/schema.d.ts`, generated by
  `openapi-typescript` from `frontend/openapi/openapi.json`, which is exported
  from FastAPI. Drift is a build failure (`scripts/generate-api-types.ps1 -Check`,
  CI job `api-contract`).
* The client is transport-only: it reports the exact backend answer, including
  the error envelope, and never invents success.
* Navigation placeholders are disabled buttons labelled with the stage in which
  they become available — no dead links, no fake screens, no fabricated KPIs.
* Presentation helpers (`src/lib/status.ts`) are pure and unit tested.

### 13.1 Routes (Stage 1B)

| Route | Group | Access | Purpose |
| ----- | ----- | ------ | ------- |
| `/login` | `(auth)` | public | Sign in; redirects an authenticated visitor onward |
| `/select-company` | `(auth)` | session | Choose the active company (multi-membership accounts) |
| `/` | `(app)` | session + company | Command Center: KPIs, pipeline, recent deals, audit activity, probe strip |
| `/crm` | `(app)` | session + company | Counterparty list, filter, create (trader only) |
| `/products` | `(app)` | session + company | Catalogue list, filter, create (trader only) |
| `/deals` | `(app)` | session + company | Deal list with status filters; read-only for non-traders |
| `/deals/new` | `(app)` | session + company + `trade.write` | Create a deal with one or more lines |
| `/deals/[id]` | `(app)` | session + company | Lines, history, transition controls, header edit (`If-Match`) |
| `/account` | `(app)` | session + company | Profile, memberships, permissions, session policy |
| `/status` | root | public | Read-only infrastructure status (no session data) |
| `/api/v1/[...path]` | root | — | Same-origin proxy to FastAPI |

Pages are server components that call the API with the incoming cookie via
`src/lib/api/server.ts`; a failure is rendered as an explicit error with the
request id, never as an empty state. Mutations run in client components against
the same-origin proxy with CSRF, `Idempotency-Key` and `If-Match`.

`(app)/layout.tsx` loads the session on the server, applies `resolveRoute()`
(pure, unit tested) and redirects anonymous visitors to
`/login?next=<pathname>`; accounts without an active company go to
`/select-company`. The pathname reaches the layout through `src/proxy.ts`
(formerly `middleware.ts`), which only copies it into an `x-pathname` request
header.

### 13.2 Session handling in the browser

* The session cookie is `HttpOnly`; no JavaScript reads it.
* Browser mutations go through the same-origin proxy, so the cookie is
  first-party on `localhost:3000` and `Origin`/CSRF validation behave exactly as
  in production.
* The CSRF token is delivered in the session payload (server-rendered prop) and
  sent back as `X-CSRF-Token`; it is never persisted in `localStorage` or
  `sessionStorage`.
* `loadSession()` is wrapped in React `cache()` so a layout and a page share one
  `/auth/me` call per request.
* When the API is unreachable the shell renders an explicit "session unavailable"
  screen and performs no redirect, rather than guessing authentication state.

### 13.3 Status and health screens

`/status` is public and read-only (liveness, readiness, contract count, and
explicit `Unreachable`/`Degraded` states). The authenticated Command Center shows
the same probes next to the signed-in identity and active company — no fabricated
KPI, deal or financial figure is rendered anywhere.


---

## 14. AI boundary

AI tools will call the same authenticated API as humans, with a service actor
identity recorded in the audit log (`actor_type='agent'`). They may not read the
database directly, bypass permission checks, approve financial documents, or
write audit records outside the normal service path. Prompt input/output is not
persisted in logs; document bodies are never logged.

---

## 15. Scheduled maintenance (contract only — not executed in 1A)

| Job | Purpose | Status |
| --- | ------- | ------ |
| `sessions.expire` | delete sessions past idle/absolute expiry | contract; rows are already rejected and revoked on use |
| `idempotency.expire` | delete idempotency records older than TTL (24 h) | table exists; middleware and job in Stage 1B/2 |
| `audit.retention` | enforce the documented audit retention window | contract only — requires the trigger to be disabled by the owner, deliberately auditable |
| `outbox.relay` | deliver pending outbox events, exponential backoff | Stage 2 |
| `outbox.prune` | delete delivered events after retention | Stage 2 |

No background worker exists yet, so nothing above is scheduled. Expiry is
enforced *synchronously*: an expired session is rejected and revoked on use, so
correctness does not depend on a job. When jobs arrive they will be idempotent,
single-writer guarded (advisory lock) and observable through the same structured
logs.

---

## 16. Environments and non-goals

Local development is the only environment that exists today. The API refuses to
start with unsafe production settings (insecure cookie, non-HTTPS CORS,
non-JSON logging, debug enabled, a cookie `Domain` combined with the `__Host-`
prefix), and CORS/Origin validation is restricted to the configured frontend
origins.

Explicit non-goals for Stage 1A: business modules, CRM, deals, quotations,
logistics, financial postings/approvals, integrations (E-YAY, Touche Finance,
Gmail, WhatsApp Business, TOUCHE ONE), AI agents, idempotency middleware,
scheduled cleanup jobs, membership/audit HTTP APIs, invitations, password reset
and MFA.

Deferred infrastructure (requires a new ADR and a demonstrated need): Kubernetes,
Redis, Kafka, a separate worker platform, microservices.

Known environment limitation: this workstation has **no Docker/WSL**, so
`infra/docker-compose.yml` was authored but not executed here. Stages 0 and 1A
were verified against a native portable PostgreSQL 17.6 cluster started by
`scripts/db/bootstrap-local-postgres.ps1`. Both paths share the same role
bootstrap SQL (`scripts/db/01-roles-and-database.sql`,
`scripts/db/02-schema-grants.sql`).

---

## 17. Authentication and session security (implemented)

### 17.1 Password storage

* Argon2id (`argon2-cffi`) with a per-hash random salt, encoded hash stored in
  `app_user.password_hash`. Parameters are configuration (time 2, memory 19 MiB,
  parallelism 1 by default; a cheaper profile is used by tests).
* Password policy (minimum 12 characters, three character classes, no leading or
  trailing whitespace, maximum 512 characters) is enforced when a password is
  **set** (CLI now, reset flows later), never when it is verified.
* Verification failures are indistinguishable: `PasswordService.verify_dummy()`
  performs an equivalent hash comparison for unknown accounts.
* Hashes are re-computed on login when cost parameters change (`needs_rehash`).
* No password, hash or token is ever placed in a response body, an audit row or
  a log line.

### 17.2 Session mechanics

| Aspect | Implementation |
| ------ | -------------- |
| Token | `secrets.token_urlsafe(32)` (256 bits), returned once in `Set-Cookie` |
| Storage | `auth_session.token_hash` = SHA-256 hex; plaintext token never stored |
| CSRF | separate 256-bit token stored on the session row; sent as `X-CSRF-Token`; compared in constant time |
| Cookie | `HttpOnly`, `SameSite=Lax`, `Path=/`, `Max-Age=idle`, `Secure` outside local dev, `__Host-` prefix outside local dev |
| Idle timeout | `now - last_activity_at >= 30 min` → revoke + `SESSION_EXPIRED` |
| Absolute timeout | `now >= expires_at` (12 h from login, never extended) → revoke + `SESSION_EXPIRED` |
| Rotation | new token **and** new CSRF token on company switch; the old token stops working immediately |
| Revocation | `revoked_at` + `revoked_reason` (`logout`, `idle_timeout`, `absolute_timeout`, `membership_revoked`, `user_disabled`) |
| Concurrency | one session per login; multiple sessions per user are allowed (separate devices) |

### 17.3 Request protection order

```
CORS → X-Request-ID correlation → Origin validation → route
     → session resolution (cookie → hashed lookup → expiry → membership)
     → CSRF validation (mutations) → permission check → service
```

* **Origin validation** (ASGI middleware) rejects *every* non-GET request whose
  `Origin` is missing or not in `TOUCHE_CORS_ALLOWED_ORIGINS`, before routing.
  Browsers always send `Origin` on non-GET requests, so "missing" means a
  non-browser client or a stripped header; both fail closed.
* **CSRF** is validated against the presented session, not merely against a
  second cookie: a token from another session is rejected.
* **Rate limiting** runs before credential verification (10 failures per account
  and 30 per source per 300 s), backed by `login_attempt`, returning `429` with
  `Retry-After`.

### 17.4 Failure disclosure

| Situation | Client sees |
| --------- | ----------- |
| Unknown email | `401` "Email or password is incorrect." |
| Wrong password | `401` "Email or password is incorrect." |
| Disabled account | `401` "Email or password is incorrect." |
| Rate limited | `429` + `Retry-After` (no account information) |
| Company the user cannot access | `403` "You are not authorised to access that company." |
| Revoked/expired session | `401` (`SESSION_EXPIRED` when it existed and timed out) |

The internal reason (`unknown_user`, `invalid_password`, `user_disabled`,
`login_rate_limited`, `company_switch_without_membership`,
`membership_revoked`) is recorded in `login_attempt`/`audit_record` for operators
and never returned.

### 17.5 Audit events

| Action value | When | Actor | Company |
| ------------ | ---- | ----- | ------- |
| `auth.login.success` | credentials accepted, session created | user | active company when auto-selected |
| `auth.login.failure` | any credential failure | user (if known) or system | null |
| `auth.logout` | session revoked by the user | user | active company |
| `session.company.switch` | company changed | user | target company |
| `session.revoked` | expiry, disablement, membership revocation | user/system | company (when bound) |
| `membership.changed` | grant/reactivate/revoke via CLI | system | affected company |
| `access.denied` | forbidden switch, revoked membership, login rate limit | user/system | null (the denial itself proves no access) |
| `identity.bootstrap` | first admin/company created by the CLI | system | new company |

Details are redacted (`password`, `token`, `csrf`, `cookie`, `authorization`,
`api_key`, `secret`, `credential` → `[redacted]`), strings are bounded to 512
characters, and inserts use a Core `INSERT` without `RETURNING` so the
tenant-scoped read policy can stay strict (ADR-021).

### 17.6 Trusted administration (CLI)

`python -m app.cli` (wrapped by `scripts/bootstrap-admin.ps1` /
`bootstrap-admin.sh`) is the only supported way to create users, companies and
memberships in Stage 1A. It:

* connects with the **migration** role (documented privilege, never used by the
  API process);
* reads passwords from a hidden interactive prompt or `--password-stdin`, never
  from argv, and never prints them;
* validates email/country/currency/role and refuses duplicates instead of
  silently overwriting;
* writes `membership.changed` / `identity.bootstrap` audit rows.

---

## 18. Verification of Stage 1A

* Backend: `python -m pytest` — 120 tests (38 Stage 0 + 82 Stage 1A), including
  live PostgreSQL RLS isolation and session/CSRF/rate-limit flows.
* Frontend: `npm test` — 45 tests (22 Stage 0 + 23 Stage 1A), plus
  `format:check`, `eslint`, `typecheck` and a production `build`.
* Live: `scripts\verify-identity.ps1` — 31 HTTP-level checks against the running
  API and web shell (cookie flags, rotation, CSRF/Origin rejection, rate limit,
  company isolation, proxy behaviour, redirects).
* Membership revocation was also verified live: revoking a membership revoked the
  bound session (1 row) and the next request returned `401`, while a colleague's
  session on the same company continued to work.






---

## 19. Trade workspace (Stage 1B)

### 19.1 Model

```
company 1 ── * counterparty
        1 ── * product
        1 ── * deal ── * deal_item ── 1 product
                    └─ * deal_transition (append-only)
```

Each child references its parent by `(id, company_id)`, so a line item cannot be
attached to another company's deal even if a bug supplies the wrong pair of ids
(ADR-024). `deal.reference` is unique per company; `product.sku` is unique per
company and stored upper case; `counterparty.name` is unique per company.

### 19.2 State machine

`app/services/deal_state.py` holds the graph as data; `app/services/trade.py`
enforces it inside the transaction that locks the deal row:

| From | Allowed targets |
| ---- | --------------- |
| `DRAFT` | `OPEN`, `CANCELLED` |
| `OPEN` | `NEGOTIATION`, `LOST`, `CANCELLED` |
| `NEGOTIATION` | `OPEN`, `LOST`, `CANCELLED` |
| `WON`, `LOST`, `CANCELLED` | terminal |

* `WON` is not an edge: the endpoint returns `409 TRANSITION_DISABLED`
  (ADR-025). `ALREADY_WON` is retained defensively.
* `LOST`/`CANCELLED` require a 3–500 character reason (`422 REASON_REQUIRED`).
* An impossible edge returns `409 INVALID_TRANSITION` with `details.allowed`.
* `PATCH` forbids unknown fields, so `status` cannot bypass the endpoint; closed
  deals reject header edits.
* Every accepted transition writes the deal update, the `deal_transition` row and
  the audit row in one transaction; concurrent attempts serialise on
  `SELECT … FOR UPDATE`.

### 19.3 API surface

All endpoints are namespaced under `/api/v1`, require an active company, and
check `company.view` (reads) or `trade.write` (writes) server-side:

| Method | Path | Notes |
| ------ | ---- | ----- |
| `GET` | `/counterparties`, `/products`, `/deals` | cursor pagination, filters, stable sort |
| `POST` | `/counterparties`, `/products`, `/deals` | optional `Idempotency-Key` |
| `GET` | `/counterparties/{id}`, `/products/{id}`, `/deals/{id}` | detail + `ETag` |
| `PATCH` | same ids | `If-Match` required; header fields only |
| `POST` | `/deals/{id}/transitions` | **required** `Idempotency-Key`, optional `If-Match` |
| `GET` | `/dashboard/summary` | KPIs, per-currency pipeline, recent deals and audit |

Money and quantities are `Decimal` end to end and serialise as strings, so no
binary floating point ever touches a price. `allowed_transitions` is returned on
every deal so the UI renders exactly the permitted controls.

### 19.4 Frontend

Server components read through `src/lib/api/server.ts` (cookie-forwarding,
`no-store`), and client components mutate through `src/lib/trade/client.ts`
(CSRF, idempotency key, `If-Match`). `DealStatusBadge`, `DealForm`,
`TransitionPanel` and `DealEditForm` contain no business rules of their own:
they render the API's `allowed_transitions` and surface the API's error codes
(including a refresh affordance for `VERSION_CONFLICT`).

### 19.5 Demo data

`python -m app.cli seed-demo --company "…"` inserts a clearly labelled demo set
(three counterparties, three products, three deals: draft, open and cancelled).
It refuses to run outside `local`/`test`/`ci`, refuses to touch a company that
already has trade data unless `--force` is given (which adds a suffixed set
rather than deleting anything), and never runs from application code.

### 19.6 Verification

`scripts\verify-trade.ps1` → `backend/scripts/verify_trade_workflow.py` runs the
15-step workflow (sign-in, master data, deal creation, concurrency, blocked
status bypass, transitions, disabled WON, mandatory reason, replay, cross-tenant
isolation, dashboard) and then checks that the rendered deal page contains the
deal reference. Results are recorded in `docs/PROGRESS.md` §20.



---

## 20. Sourcing, pricing and sales quotes (Stage 3)

### 20.1 Data model

Twelve tables in migration `0004_sourcing`, all tenant-scoped, RLS-protected, and
linked to parents through composite `(id, company_id)` foreign keys:

| Group | Tables |
| ----- | ------ |
| FX | `fx_rate_snapshot` (unique pair + effective time, immutable) |
| RFQ | `supplier_rfq`, `supplier_rfq_item`, `supplier_rfq_revision` (append-only) |
| Quote | `supplier_quote`, `supplier_quote_item`, `supplier_quote_revision` (append-only) |
| Pricing | `pricing_scenario` (inputs + results JSONB), `pricing_cost_component` |
| Sales | `sales_quote`, `sales_quote_item`, `sales_quote_revision` (append-only) |

Revision tables receive `SELECT, INSERT` only. Money is `numeric`; quantities are
`numeric(18,3)`; unit prices `numeric(18,4)`; line totals and component amounts
`numeric(18,2)`. CHECK constraints encode the invariants: ISO-4217 currency,
Incoterms 2020, allowed units, positive quantities, `revision >= 1`, a sent RFQ
must carry `sent_at`, a LINE cost must name a product, and
`(status = 'APPROVED') = (approved_by IS NOT NULL AND approved_at IS NOT NULL)`.

### 20.2 Pricing engine

`app/services/pricing_engine.py` is a pure module: no session, no clock, no rate
lookup. It converts quote lines with an explicit `FxInput`, allocates ORDER costs
pro-rata by purchase value using largest-remainder rounding, applies LINE costs to
their product, and derives the selling price from exactly one of margin or markup.
It returns the rounded line figures, totals, a completeness document and a derived
status (`INCOMPLETE`, `ESTIMATED`, `VERIFIED_INPUTS`).

The scenario service is the only writer: it resolves FX snapshots and components
from the database, runs the engine once, and persists `pricing_inputs`,
`calculated_results`, `completeness` and `calculation_version`. Reads return the
stored calculation, so an approved price cannot drift.

### 20.3 Workflows

| Document | States | Notes |
| -------- | ------ | ----- |
| RFQ | `DRAFT � PREPARED � SENT � RESPONDED � CLOSED`, `CANCELLED` | Preparing snapshots; sending needs channel + evidence + timestamp |
| Supplier quote | `RECEIVED � WITHDRAWN` | A revision is a new row that supersedes the old one |
| Sales quote | `DRAFT � PENDING_APPROVAL � APPROVED / REJECTED`, `WITHDRAWN` | Submit needs `VERIFIED_INPUTS`; approve needs `finance.approve` and a second person |

Every transition writes an audit row in the same transaction; mutable headers carry
`version` for `ETag`/`If-Match`; every mutation is replay-safe through
`Idempotency-Key`.

### 20.4 Frontend

Server components read through `src/lib/api/server.ts`; client components mutate
through `src/lib/sourcing/client.ts` (CSRF, idempotency, `If-Match`). Pages:
`/rfq`, `/rfq/new`, `/rfq/[id]`, `/quotes`, `/quotes/[id]`, `/pricing`,
`/pricing/[id]`, `/sales-quotes`, `/sales-quotes/[id]`, `/fx-rates`. Panels render
the API's `allowed_transitions`/`can_submit` facts rather than re-deriving rules,
and show the stable error codes (including reload guidance for
`VERSION_CONFLICT`).

### 20.5 Verification

Backend: 24 engine unit tests plus 24 sourcing API integration tests covering
batch RFQ creation, the prepare/send gate, quote revisions and withdrawal, FX pair
validation, allocation and totals, recalculation concurrency, approval separation
of duties, revision superseding, RLS isolation and audit rows. Frontend: a unit
test file for sourcing formatting and a component test for the RFQ action panel
(evidence gate, ETag, replay/conflict messaging). Contract artefacts are
regenerated from OpenAPI.

---

## 21. Stage 4 — the execution chain

Stage 4 turns a commercial agreement into operational evidence. It adds one
chain of tenant-scoped aggregates and three pure state machines, and it keeps
four boundaries visible in the code:

1. **A win is not a status edit.** `WON` exists only as the outcome of the order
   conversion transaction (ADR-032).
2. **An order is not a live view of the quote.** Commercial facts are copied into
   the order and its JSONB snapshot (ADR-033).
3. **A plan is not an event.** Dispatch, arrival and delivery each need their own
   recorded evidence; procurement is optional and never auto-sent (ADR-034).
4. **A delivery is the only fulfilment fact.** Order status is derived from
   delivered shipment quantities, not typed by a user (ADR-035).

### 21.1 Data model (`0005_orders`)

| Group | Tables | Notes |
| ----- | ------ | ----- |
| Acceptance | `customer_acceptance_evidence` | Append-only; channel, timestamp, evidence reference, quote revision |
| Orders | `sales_order`, `sales_order_item`, `sales_order_transition`, `order_amendment` | Frozen lines, one `accepted_terms` JSONB snapshot, append-only history |
| Procurement | `purchase_order`, `purchase_order_item`, `purchase_order_transition` | Dispatch evidence columns; transition history |
| Logistics | `shipment`, `shipment_item`, `shipment_event`, `shipment_reference`, `shipment_cost` | Partial allocations, milestone events, provenance, staged costs |
| Documents | `trade_document` | Metadata + server key + SHA-256 + version + verification status |

Every child row carries `company_id` and references its parent with a composite
`(parent_id, company_id)` foreign key, so a cross-tenant link is impossible even
before RLS is considered. RLS is enabled on all 14 tables. History tables
(`*_transition`, `order_amendment`, `customer_acceptance_evidence`,
`shipment_event`) grant `SELECT, INSERT` only to the runtime role. CHECK
constraints encode the commercial invariants: ISO currencies, Incoterms 2020,
allowed units and modes, positive quantities, `version >= 1`, a delivered
shipment has evidence, a cancelled row explains itself, and fulfilment/status
pairs cannot contradict each other.

Two constraints were corrected after the integration suite proved them wrong
(`0006_shipment_dispatch`, `0007_purchase_order_dispatch`): an actual dispatch may
precede the *planned* date, and a recorded dispatch timestamp must survive later
procurement statuses.

### 21.2 The conversion transaction (`SalesOrderService.convert`)

```
BEGIN
  SELECT deal ... FOR UPDATE                    -- serialises concurrent attempts
  verify status in (OPEN, NEGOTIATION)
  SELECT quote ... FOR UPDATE
  verify quote.deal_id = deal.id, status = APPROVED, customer = deal counterparty
  verify/snapshot acceptance evidence for the exact quote revision
  INSERT sales_order (+ items, + accepted_terms JSONB, + first transition)
      unique (deal_id) where initial → DB-level "one initial order"
  UPDATE deal → WON (+ deal_transition)
  INSERT audit rows (order created, deal won, acceptance recorded)
COMMIT
```

Every refusal happens before the first write. The order number generator is
server-side; `expected_total` (when supplied) must match the accepted revision;
the idempotency row, order, transition, deal update and audit rows share one
transaction. A retry with the same key returns the stored response; a different
key on a won deal returns `409 ALREADY_WON`; the unique index is the final guard
even if two transactions race.

### 21.3 State machines (`app/services/order_state.py`)

| Aggregate | Edges (terminal states have none) |
| --------- | --------------------------------- |
| Sales order | `CONFIRMED → IN_FULFILLMENT → FULFILLED → CLOSED`; `CANCELLED` from confirmed/in-fulfilment |
| Purchase order | `DRAFT → APPROVED → RECORDED_SENT → SUPPLIER_CONFIRMED → IN_FULFILLMENT → RECEIVED`; `CANCELLED` from any non-terminal |
| Shipment | `PLANNED → BOOKED → DISPATCHED → IN_TRANSIT → ARRIVED → DELIVERED`; `CANCELLED` from any non-terminal |

`FULFILLED` has no manual edge: `validate_sales_order_transition` refuses it and
only the shipment service may promote an order after delivery. Evidence rules
live beside the graphs, are pure, and are tested without a database:
`RECORDED_SENT` requires channel + timestamp + reference, `SUPPLIER_CONFIRMED`
requires a supplier reference, `DISPATCHED` requires a tracking/booking
reference, `ARRIVED` requires an actual arrival timestamp, `DELIVERED` requires a
delivery-evidence reference, and every cancellation requires a written reason.

### 21.4 Allocation and derived fulfilment

`shipment_item` rows allocate decimal quantities against a `sales_order_item`.

* Units must match the order line exactly; the API schema refuses an extra
  `unit` field on a shipment line, and the service re-validates unit equality.
* `validate_allocation` refuses non-positive quantities and any allocation above
  `ordered − already_allocated`, using `Decimal` arithmetic throughout.
* Cancelled shipments do not count towards `allocated` or `delivered`, so a
  cancellation releases the quantity for replanning.
* `GET /sales-orders/{id}/fulfilment` returns per line `ordered`, `allocated`,
  `delivered`, `remaining` and a `completion_ratio`.
* `fully_delivered` (every line delivered) promotes the order to `FULFILLED`;
  partial delivery moves it to `IN_FULFILLMENT`. A 5-tonne delivery against a
  20-tonne line can therefore never mark the order delivered.
* An ETA never sets `delivered_at`; `is_delayed` is computed only from a
  documented ETA that has passed on a shipment that is neither delivered nor
  cancelled.

### 21.5 Logistics costs

`shipment_cost` keeps one row per fact, each with an explicit stage:
`ESTIMATED`, `QUOTED`, `INCURRED` or `DOCUMENTED`, plus a reference. Recording an
incurred freight invoice adds a row; it never rewrites the Stage 3 pricing
assumption or an earlier estimate. Comparing the two is a read-side concern and
full reconciliation is deliberately left to Stage 5.

### 21.6 Document storage and authorisation

`app/services/documents.py` owns the only filesystem access.

* The client never supplies a path. The storage key is
  `{company_id}/{document_id}/v{version}-{sha256[:16]}{suffix}`, generated on the
  server, validated against a strict regex, and resolved with
  `Path.is_relative_to(root)` to defeat traversal.
* Uploads are streamed in chunks with a hard byte ceiling; the SHA-256 is
  computed twice (while spooling for the idempotency fingerprint, and again while
  writing to storage) and verified before every download. A mismatch is a 409,
  not a silent read.
* MIME types come from an allow-list with magic-prefix checks; filenames are
  sanitised and re-sanitised for `Content-Disposition`; storage lives under the
  ignored `backend/var/documents` tree, outside every served directory.
* Authorisation is layered: RLS scopes the row to the active company, and
  `_assert_entity` proves the linked entity exists in that company. Uploads may
  only link to `DEAL`, `SALES_ORDER`, `PURCHASE_ORDER`, `SHIPMENT` or
  `CUSTOMER_ACCEPTANCE`.
* A new upload for the same entity + type becomes the next version and archives
  the previous one. Deletion is archival; the version history stays readable.
* Draft previews are generated from the accepted order snapshot and always carry
  `is_draft: true`, a `DRAFT-…` number and a legal notice that they are not
  issued invoices, customs declarations, certificates or carrier documents.
  The preview query also binds the actor because the seller row is protected by a
  membership policy.

Malware scanning is **not** implemented and is documented as a remaining
control (PROGRESS.md §22.11).

### 21.7 Frontend

The eight execution pages are server components reading through
`src/lib/api/server.ts`; mutations use `src/lib/operations/client.ts` with the
same CSRF/idempotency/`If-Match` conventions as Stage 3. The conversion panel
lives on the deal page and shows the acceptance warning before offering the
action. Order, purchase-order and shipment panels render `allowed_transitions`
from the API instead of re-deriving the rules, and explain `VERSION_CONFLICT`,
`ALREADY_WON`, `IDEMPOTENCY_CONFLICT`, `REASON_REQUIRED` and evidence failures.
Draft previews and tracking provenance are labelled in the UI exactly as the API
describes them (`MANUAL` / `DOCUMENT_EVIDENCE`); there is no live map or carrier
feed.

### 21.8 Verification

29 API integration tests, 19 pure state-machine tests and 17 frontend tests
cover the boundaries above, including concurrent conversion, immutable
snapshots, over-allocation, cancellation effects, document corruption,
cross-tenant access and permission separation. The live workflow
(`45/45` checks) adds evidence from the running API and SSR. See PROGRESS.md
§22.6–22.7 for exact counts and the issues found.



---

## 22. Stage 5A — the TOUCHE FINANCE boundary (read-only)

```
COMMERCE (commercial operational source of truth)
  sales order / purchase order / shipment / shipment_cost / trade document
        |
        |  Stage 5A: GET /api/health only (no auth, no business data, no write)
        v
  app/integrations/finance  ->  FinanceHealthClient  ->  127.0.0.1:8765
        |
        |  Stage 5B/5C: proposed /api/integration/v1 (HMAC, not implemented)
        v
FINANCE (financial source of truth)
  faaliyet / hesap / fis / fis_satiri / cari / AR-AP aging / reports
```

### 22.1 Source-of-truth split

| Fact | Owner | Commerce stores | Finance stores |
| ---- | ----- | --------------- | -------------- |
| Customer acceptance, order terms, allocations, dispatch/delivery evidence | Commerce | Yes | No |
| Chart of accounts, journal, receivables/payables, payments, reconciliation | Finance | No | Yes |
| Invoice as a legal posting | Finance | Only a `DRAFT` preview / uploaded document metadata | Yes |
| Shipment cost estimate / incurred amount | Commerce (provenance) | Yes, staged | Only if Finance approves an expense/payable |

Commerce must never infer a Finance balance from its own operational data, and
Finance must never treat a Commerce operational state as a posting.

### 22.2 Verified Finance interface

Finance is a local stdlib HTTP server with a same-origin UI API. Only
`GET /api/health` is unauthenticated; it is read-only. All business endpoints
require a loopback/Tailscale session, and loopback requests become `OWNER`.
There is no API key, HMAC contract, webhook receiver or remote-write endpoint.
`docs/STAGE5_FINANCE_DISCOVERY.md` records the exact inventory and the missing
interfaces.

### 22.3 Stage 5A connector rules

* Disabled by default; a disabled integration performs no network I/O.
* Base URL must be a literal loopback `http://` origin. No DNS, HTTPS,
  credentials, path, query or fragment.
* The request carries only `Accept: application/json` and a dedicated
  `User-Agent`; no cookie, bearer token or Tailscale identity header.
* Response is capped at 8 KiB; redirects are not followed; a non-200, invalid
  JSON, unknown `durum` or non-boolean `yerel` is `incompatible`.
* States: `disabled`, `healthy`, `degraded`, `unreachable`, `incompatible`.
* `GET /api/v1/integrations/finance/status` requires a Commerce session and
  always reports `scope="health_only"` and `accounting_writes_enabled=false`.

### 22.4 Why no direct SQLite adapter

The live ledger schema is readable (`fisler`, `fis_satirlari`, `hesaplar`,
`faaliyetler`), but it is an internal persistence contract, not a supported
integration interface. Coupling Commerce to it would bypass Finance's
authorisation, audit, recovery and schema evolution. The offline probe
(`scripts/finance_readonly_probe.py`) uses `mode=ro` only to prove discovery and
non-modification; it is not imported by the running API.

### 22.5 Future contract

Stage 5B/5C require Finance to implement the HMAC-authenticated
`/api/integration/v1` read endpoints and a draft-only event endpoint
(ADR-040). Commerce will then add read-only snapshots and outbox producers.
Until that interface exists and is verified, Commerce must not fake it, poll a
session endpoint, or write an outbox event that nobody can consume.


---

## 23. Stage 5C — real read-only Finance connector

### 23.1 Boundary and data flow

```text
Browser
  │ Commerce session cookie + X-CSRF-Token (mutations only)
  ▼
Next.js /finance (server component)
  │ serverGet() with the session cookie, no Finance credential in browser
  ▼
Commerce FastAPI /api/v1/finance/*
  │ active membership + company.view + explicit mapping
  ▼
FinanceIntegrationClient (http.client, loopback only, headers)
  │ X-Touche-Integration-Key / X-Touche-Integration-Secret
  ▼
Finance /api/integration/v1/* (separate auth boundary, mode=ro SQLite)
```

Commerce never imports Finance code or opens Finance SQLite at runtime.

### 23.2 Mapping and isolation

`touche.finance_company_mapping` (migration `0008_finance_mapping`) is a
tenant-owned table with one row per Commerce company and a unique
`company_id`. It records the explicit Finance `faaliyet_key`, verification
status, configuring admin, timestamps and non-secret verification details.
The runtime role has `SELECT` only; RLS uses `touche.current_company_id()`.

The mapping is created/changed only by an active company admin through
`python -m app.cli finance-map set`, which verifies the Finance company against
`/capabilities` and `/companies` before writing. No name matching is performed.
A missing, disabled or unverified map refuses data reads.

### 23.3 API and currency behavior

The five Stage 5C endpoints are `GET /api/v1/finance/status`, `/capabilities`,
`/summary`, `/accounts` and `/aging`. A caller can never submit a Finance
company id, Finance URL or credential. A multi-currency company must select one
currency explicitly; Finance amounts are preserved; there is no conversion or
cross-currency aggregation.

All calls are GET. POST/PUT/PATCH/DELETE have no business handler; the API
returns `405` and no accounting write path exists. Every successful read writes
an audit record with the Commerce actor/company, Finance company, endpoint,
currency/date context and request id. Secrets and headers are never recorded.

### 23.4 UI

`/finance` has an Overview, Accounts, Receivables and Payables view. It renders
the connection state (`NOT_CONFIGURED`, `CONNECTED`, `DEGRADED`, `UNAVAILABLE`,
`AUTH_ERROR`), mapped company, currencies, data-through watermark, source
balances, account table and FIFO aging with open Finance `fis_id` source items.
Invoice/payment data is explicitly marked “Not available” because Finance has
no structured objects. No operational cost/pricing logic changed.

### 23.5 Configuration and deployment limits

The connector is disabled by default and loopback-only. Key id/secret are
server-side `SecretStr` values. Responses are capped, redirects are not
followed, and the client rejects non-Finance server identification or an
unsupported contract. TLS/mTLS, remote exposure, Windows ACL enforcement and
HSM/KMS are deployment prerequisites, not verified here.

### 23.6 Verification

The isolated HTTP acceptance harness
`backend/scripts/verify_finance_http.py` creates a disposable Finance runtime,
synthetic ledger and key, starts Finance on port 8877, configures the Commerce
mapping through the CLI, starts Commerce/Next.js, drives login and all Finance
views, and confirms cross-tenant refusal and unchanged Finance hashes. Result:
`ISOLATED_HTTP_VERIFIED`. The live Finance application was never started and
the live database/workbook hashes remained unchanged.

---

## 24. Stage 5D — evidence-based financial reconciliation

### 24.1 Separation of facts

Commerce commercial execution and Finance accounting remain separate:

```text
accepted sales order ─┐
committed purchase ───┼─ Commerce facts (DOCUMENTED / COMMITTED)
estimated landed ─────┤
recorded costs ───────┘
                        explicit evidence link (operator decision)
Finance aging source id ┘─ Finance observation (FINANCE_OBSERVED)
                        ↓
                  human review
                        ↓
                 VERIFIED evidence — not an accounting entry
```

No company-wide Finance balance is attributed to an order and no transaction is
matched by a counterparty name. Only Finance's exposed aging source ids are
eligible for evidence links.

### 24.2 Persistence and state

Migration `0009_reconciliation` creates `finance_reconciliation_run`,
`finance_source_reference`, `finance_reconciliation_evidence`,
`finance_discrepancy` and `finance_reconciliation_review`. All are tenant-owned,
RLS-protected, composite-FK linked and have no runtime `DELETE` grant. Evidence
is append-only except the reviewer verification columns.

States are `INCOMPLETE`, `UNMATCHED`, `POTENTIAL_MATCH`, `MATCHED_EVIDENCE`,
`VERIFIED`, `DISPUTED`. New runs never start above `UNMATCHED`. Exact evidence on
a complete run reaches `MATCHED_EVIDENCE`; `VERIFIED` requires an authorised
`finance.reconcile` reviewer who is not the creator, no open blocking
discrepancy, and a sales-order evidence link. A mismatch stays
`POTENTIAL_MATCH`. A verified run is immutable; later source data needs a new
run.

### 24.3 Calculations and currencies

The pure engine (`reconciliation_calculations.py`) keeps accepted value,
commitments, estimate, recorded costs and margin separate. `None` means
unavailable, never zero. `TRY`/`TL` is a label alias; no amount conversion or
cross-currency aggregation exists. Mixed currencies create a blocking
`CURRENCY_MISMATCH`. Document-supported margin and actual profit are deliberately
`UNAVAILABLE`.

Discrepancies are deterministic (`MISSING_EVIDENCE`,
`MISSING_FINANCE_REFERENCE`, `AMOUNT_MISMATCH`, `CURRENCY_MISMATCH`,
`DUPLICATE_REFERENCE`, `INCOMPLETE_COSTS`, `UNMATCHED_FINANCE_ITEM`,
`SOURCE_STALE`, `COMPANY_MAPPING_INVALID`, `MANUAL_REVIEW_REQUIRED`). A missing
order-level Finance reference is described as an unavailable capability, not
proof that an invoice is missing.

### 24.4 API and UI

Ten versioned endpoints under `/api/v1/finance` cover runs, evidence, reviews,
discrepancies and order finance. Reads need `company.view`, operational creation
needs `trade.write`, and review/resolution need the separate
`finance.reconcile`. CSRF, `Idempotency-Key`, `If-Match`, ETag, audit and
`no-store` apply. No route writes to Finance.

The premium UI adds `/finance/reconciliation`,
`/finance/reconciliation/[id]`, `/finance/discrepancies` and
`/finance/orders/[id]`. Unavailable metrics are labelled “Not available”;
invoice, payment, recognized revenue and actual profit are never fabricated.

### 24.5 Verification

Backend `379 passed`; frontend `102 passed / 18 files`; ruff, mypy, ESLint,
Prettier, typecheck and `next build` pass. The extended isolated harness builds a
real accepted order through the Stage 3/4 HTTP APIs, snapshots Finance, links
`F-USD-AR-1` for exactly `250.00`, refuses an unauthorized review, verifies with
an approver, proves an unlinked run cannot verify, renders all four screens,
rejects cross-tenant access and leaves the Finance hashes unchanged. Level:
`ISOLATED_HTTP_VERIFIED`; live Finance was not started.

See `docs/STAGE5D_RECONCILIATION.md` for the complete model and limitations.

---

## 25. Stage 5E — read-only financial intelligence

### 25.1 Data flow and boundary

Stage 5E is a pure read model. It adds no table, no migration and no Finance call:

```text
sales order ── accepted quote ── pricing scenario ── FX snapshots
     │               (Stage 3/4 facts, tenant-scoped, RLS)
     ├── purchase orders ── shipment costs (with provenance stage)
     └── Stage 5D runs ── evidence ── discrepancies
                    │
                    ▼
   intelligence_calculations.py   pure, no I/O, stage5e-1.0.0
                    ▼
   intelligence.py (service)      loads facts, applies filters, aggregates per currency
                    ▼
   presenters_intelligence.py → /api/v1/finance/intelligence/*   (GET, company.view)
                    ▼
   Next.js server components      /finance/intelligence, …/orders, …/orders/[id], …/exceptions
```

Finance reaches the analysis only through the evidence and discrepancies Stage 5D
already stored. Finance remains the financial source of truth (ADR-038).

### 25.2 Two bases, never blended

| Basis | Formula | Classification |
| ----- | ------- | -------------- |
| Estimated | accepted value − Stage 3 landed-cost scenario (recoverable `VAT_CASHFLOW` excluded) | `ESTIMATED` |
| Committed / documented | accepted value − committed purchase orders − shipment costs at `INCURRED`/`DOCUMENTED` | `COMMITTED` / `DOCUMENTED` |

Committed purchase orders are approved-or-later (`APPROVED`, `RECORDED_SENT`,
`SUPPLIER_CONFIRMED`, `IN_FULFILLMENT`, `RECEIVED`); a draft purchase order blocks
the committed basis and a cancelled one is ignored. `QUOTED`/`ESTIMATED` shipment
costs and the pricing scenario never enter the documented basis. A part-shipped
order withholds its committed profit. A cost in another currency is used only
through a stored FX snapshot; without one the figure is unavailable. There is
intentionally no `actual_profit`.

### 25.3 Currencies, limits and unavailable values

All totals are grouped by currency; there is no cross-currency amount. `None` means
unavailable and is never rendered or exported as zero. One analysis is bounded to
5000 orders and 731 days so a request cannot load an unbounded fact set; beyond that
the API refuses with `400 BAD_REQUEST`. Nothing is cached or persisted, so each
request reflects the current facts. The orders screen asks for the summary as well
as the list (the list endpoints do not return filter options), which doubles the
analysis per page view.

### 25.4 API and UI

Seven `GET` endpoints, all behind `company.view`, all `no-store`; see
API_CONTRACTS §12. The CSV export is audited (`finance.read`) and escapes formula
prefixes in text columns only. The UI follows the Stage 5C/5D conventions
(server-rendered pages through `serverGet`, GET filter forms, generated OpenAPI
types). Charts are CSS/SVG with no new dependency: one scale per currency, a legend
for two series, a table view and a keyboard/hover tooltip. The two series colours
(`#3987e5`, `#d95926`) were validated against the real panel surface because the
theme's accent/cyan pair fails the normal-vision separation floor. Status colours
are used only for completeness states and always carry a label. The export button
fetches the file so a refusal is shown on the page, and the same-origin proxy
forwards `content-disposition` and `x-content-type-options` for it.

### 25.5 Verification

Backend `402 passed`; frontend `160 passed / 22 files`; ruff, mypy, ESLint,
Prettier, typecheck and `next build` pass. The isolated harness reuses the real
Stage 5D order and checks the figures against values derived from its inputs
(estimated profit `50.00` at `20.00%`, committed profit withheld while part-shipped),
the exception queue and its permission, the CSV through the API and the proxy, the
rendered screens, tenant isolation and unchanged Finance hashes. Level:
`ISOLATED_HTTP_VERIFIED`, plus a real-browser review at four widths whose defects
were fixed; no live Finance (PROGRESS §26).

## 26. Stage 6 — the AI Trade Director

Stage 6 adds an assistant that analyses the company's real records, explains them,
cites its sources and proposes drafts and tasks for a person to approve. It is a
consumer of the services that already exist: it has no data of its own beyond
conversation history, usage metadata and proposals, and no path that changes a deal,
an order, a shipment, a document or the accounting. ADRs 048–053 record the decisions.

### 26.1 Components

```
 browser ──► /ai (Next.js) ──► /api/v1/ai/* (FastAPI)
                                   │
                 AIRuntime (one per process)
   ┌───────────────┬───────────────┼────────────────┬──────────────────┐
   │ AiOfficeService│  AIGateway    │ ToolExecutor   │ Evidence registry │
   │ conversations, │ provider call │ registry of 16 │ + response        │
   │ runs, tool log,│ retry, timeout│ READ_ONLY tools│ validator         │
   │ usage, proposals│ budget, cancel│ authz, schema │ (ADR-050)         │
   └───────┬────────┴──────┬────────┴───────┬────────┴──────────────────┘
           │               │                │
      PostgreSQL     ModelProvider      existing services (same RLS,
   (RLS, audit)   mock │ OpenAI-compatible │ Anthropic     permissions, rules)
```

* `app/ai/providers` — the `ModelProvider` protocol and three adapters. HTTP uses the
  standard library only (no new dependency); redirects are never followed; responses
  are capped at 2 MiB; every failure maps to a provider error without a body or a
  credential. The OpenAI-compatible adapter speaks `POST {base}/chat/completions` with
  `tools[].function`; the Anthropic adapter speaks `POST {base}/v1/messages` with
  `input_schema` and `tool_use`/`tool_result` blocks. Both were written against the
  providers' public documentation and are exercised against a local stub server; a live
  call needs a credential and is reported separately (`REAL_PROVIDER_BLOCKED`).
* `app/ai/gateway.py` — bounded retries with `Retry-After`, per-request budgets
  (tokens, steps, tool calls), a non-blocking concurrency limiter, a cancellable run
  registry, usage estimation when a provider omits it, and logging of sizes only.
* `app/ai/prompts.py` — versioned prompt (`trade_director@1.0.0`) stored with every run.
* `app/ai/tools` — the registry, the executor and the 16 read-only handlers.
* `app/ai/evidence.py`, `safety.py`, `proposals.py` — evidence registry and validator,
  untrusted-text handling, and the only two executable approval actions.
* `app/ai/director.py` — `AIRuntime` (admission checks, run lifecycle) and the bounded
  loop.
* `app/services/ai_office.py` — persistence and the human-approval rules.
* `app/api/v1/routes/ai.py` — the HTTP surface (API_CONTRACTS §13).

### 26.2 One request, end to end

1. `POST /ai/conversations/{id}/messages` — the route checks the session, the active
   company and `company.view`; the runtime checks that the AI Office is enabled, the
   message size, the per-user rate, the daily budget and a free concurrency slot; it
   records the run (`RUNNING`) and the user message in one transaction and answers `202`.
2. A background task builds the context (versioned system prompt, a server-written
   context block naming the company, the last messages) and loops: call the model →
   for each requested tool, execute it (§26.3) → append the bounded result → repeat,
   until the model answers or a limit is reached. Cancellation and the deadline are
   checked before every step.
3. The final text is parsed and validated against the run's evidence (ADR-050). The
   assistant message (summary, validated answer, cited evidence) and any proposals are
   stored together with the run's counters and the audit row.
4. The client polls `GET /ai/runs/{id}`; tool progress appears as soon as each call is
   logged.

### 26.3 What the executor guarantees for every tool call

Refuse unknown/blocked names → refuse invalid arguments → re-read the *current*
membership → validate against a closed schema → run the handler with the
server-chosen company → withhold instruction-like text → bound the size → register
evidence → log the call → audit it. The model cannot choose, change or see a company id.

### 26.4 Data model (migration `0010_ai_office`)

`ai_conversation`, `ai_run`, `ai_message`, `ai_tool_call`, `ai_proposal` — all with
`company_id`, composite `(id, company_id)` foreign keys and row level security on
`touche.current_company_id()`. Runtime grants are narrow: `ai_message` and
`ai_tool_call` are append-only (`SELECT, INSERT`); conversation, run and proposal can
be updated only in the columns the application changes; nothing can be deleted. The
audit CHECK gains eleven `ai.*` actions. Nothing stores a prompt sent to a provider, a
credential, a raw tool result or a document body. Downgrade removes the tables and is
refused while `ai.*` audit rows exist (the audit trail is append-only).

### 26.5 Security properties

* **Authority.** Read-only tools; two proposal actions that record a decision; a CHECK
  constraint and an executor registry that cannot express anything else.
* **Tenancy.** Company from the session only; every service call runs in the company's
  RLS context; another user's conversation is `404`; a revoked membership loses tool
  access on the next call.
* **Untrusted input.** Stored text is sanitised and instruction-like text is withheld
  (ADR-052); tool arguments are validated; tool results are size-bounded.
* **Traceability.** Every claim is labelled with a basis and cites evidence the tools
  returned; the server computes links and rejects invented citations and figures.
* **Secrets.** The provider credential is a `SecretStr`, never returned, never logged;
  errors and audit rows hold no prompt, result or credential.
* **Resource limits.** ADR-053.
* **Known limits.** Cancellation, the concurrency limiter and the per-user rate are
  per process or per database window; a multi-process deployment needs a shared limiter
  and a job runner (not needed for a single local process).

### 26.6 Frontend

`/ai` is a server component that loads status, tools, suggestions, conversations,
proposals and activity, then renders a client workspace **keyed by the company id**, so
switching company discards every conversation, draft and proposal. Panels: provider
status and budget; history; the thread with validated answers (basis badge per claim,
figures, links to the cited records, server-side warnings in plain language, a sources
list); live tool progress with cancel; proposed actions (draft preview stating nothing
is sent, edit, approve/reject only for `trade.write`); activity history; the tool
registry with the actions that are never available. Hrefs are only followed when they
are application-internal paths.


---

## 27. Stage 7A communications discovery (in progress)

Stage 7A deliberately has no outbound transport. The new route `/communications`
uses an active session and `company.view` to expose existing Stage 6 AI Office
DRAFT proposals, constrained by PostgreSQL company RLS. No company id is accepted
from query/body. The displayed approval state is a **human review**, never delivery.
A separate `communications.send` permission exists without any role assignment:
future delivery requires explicit authorization, provider configuration, idempotent
outbox, audit, consent and per-channel execution rules. The channel status endpoint
reports `NOT_CONFIGURED` until a real connector is implemented and verified.

No message dispatch, credential handling, external access or Finance write is
implemented in this slice. Regression and browser acceptance are still pending.


---

## 28. Stage 7C1 — CRM provenance, not delivery (GitHub CI verified)

The Stage 7B no-send preflight optionally accepts an explicit CRM counterparty
ID. A read-only service applies the session's tenant context and PostgreSQL
RLS and compares a validated email/E.164 address to one active CRM record.
Missing, wrong-company and archived records fail closed. No address is returned,
persisted by preflight or sent to any provider. Even a CRM match never supplies
communication consent; `CONSENT_UNDOCUMENTED` is unconditional.
`sendable=false` and the unassigned `communications.send` permission remain.

CI run `40021727161` passed 561 backend / 192 frontend tests and generated
API client drift checks; PR #3 merged at `7624c33`. This is not a provider
OAuth implementation, customer consent ledger, browser acceptance or live
sending verification. All provider connections still report NOT_CONFIGURED.

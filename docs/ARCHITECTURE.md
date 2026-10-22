# TOUCHE COMMERCE — Architecture

**Status:** Stages 0, 1A (identity, sessions, tenancy, audit) and 1B (CRM,
catalogue, deals) implemented and verified locally.
**Audience:** engineers and reviewers working on Stage 2 and later.
**Companion documents:** `docs/DECISIONS.md` (binding ADRs), `docs/API_CONTRACTS.md`,
`docs/ROADMAP.md`, `docs/PROGRESS.md`.

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



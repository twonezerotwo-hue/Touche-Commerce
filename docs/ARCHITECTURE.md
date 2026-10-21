# TOUCHE COMMERCE — Architecture

**Status:** Stage 0 (foundation) implemented and verified locally.
**Audience:** engineers and reviewers working on Stage 1A and later.
**Companion documents:** `docs/DECISIONS.md` (binding ADRs), `docs/API_CONTRACTS.md`,
`docs/ROADMAP.md`, `docs/PROGRESS.md`.

---

## 1. Purpose and scope

TOUCHE COMMERCE is an independent, premium international trade management
application. It will eventually integrate with E-YAY, Touche Finance, Gmail,
WhatsApp Business and TOUCHE ONE.

Stage 0 delivers **infrastructure only**: a running web shell, a running API, a
migrated PostgreSQL database, health probes, the error/logging/correlation
foundation, the contract-generation pipeline and the documentation that binds
later stages. It contains **no business features, no AI agents, no CRM, no
quotation workflow and no external integration**. Nothing in the UI claims a
capability that is not implemented.

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
│   ├── src/app/              routes (only "/" exists in Stage 0)
│   ├── src/components/       shell, system-status, ui primitives (shadcn/ui style)
│   ├── src/lib/api/          typed client + generated schema.d.ts
│   └── openapi/openapi.json  exported from FastAPI (committed, drift-checked)
├── backend/                  FastAPI service
│   ├── app/core/             configuration, logging, errors, middleware, context
│   ├── app/db/               engine/session, tenant context, ORM models
│   ├── app/api/v1/           versioned routers, schemas (source of TS types)
│   ├── alembic/              migration environment + versions
│   ├── scripts/              export_openapi.py
│   └── tests/                unit + live-database integration tests
├── infra/                    docker-compose.yml, Postgres init hooks, local runtime
├── scripts/                  setup / migrate / dev / verify (PowerShell + bash)
├── docs/                     architecture, contracts, roadmap, progress, ADRs
└── .github/workflows/ci.yml  lint → typecheck → test → build
```

### 3.2 Backend layering

```
app/api/v1/routes   ← HTTP only: validation, status codes, dependency wiring
        │
app/api/v1/schemas  ← Pydantic contracts (single source for OpenAPI/TS)
        │
app/domain (1A+)    ← business rules, state machines, authorization decisions
        │
app/db              ← SQLAlchemy models, repositories, transaction/tenant scope
        │
PostgreSQL          ← constraints, RLS, composite FKs
```

Rules:

* Dependencies point downward only; routes never issue ad-hoc SQL.
* Every mutation runs inside one transaction that also writes audit and outbox
  rows (Stage 1A+).
* Authorization is decided server-side, never in the browser and never by an AI
  tool (ADR-018).

### 3.3 Planned modules (not implemented)

`identity` (users, sessions, companies, memberships, invitations), `audit`,
`trade` (deals, sales orders), `crm`, `quoting` (RFQ, quotes), `catalog`
(products), `logistics`, `finance`, `documents`, `integrations` (outbox relay),
`ai` (assistants restricted to authorized tools). Each becomes a package under
`app/domain/<module>` with its own router under `app/api/v1/routes/<module>.py`.

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

### 6.1 Transactional outbox (foundation only)

`touche.outbox_event` exists with: `id`, `company_id`, `event_type`,
`aggregate_type`, `aggregate_id`, `payload` (JSONB), `occurred_at`,
`available_at`, `attempts`, `last_error`, `processed_at`, `created_at`, a
partial index on pending rows and a `(company_id, occurred_at)` index.

Stage 0 creates the durable table and ORM mapping only. Producers and the relay
worker arrive with the first business module (Stage 2), written in the same
transaction as the business change. No external system is contacted today.

---

## 7. Multi-company isolation (design, enforced from Stage 1A)

* Every tenant-owned table carries `company_id uuid NOT NULL` referencing
  `touche.company(id)`.
* The runtime role never has `BYPASSRLS`; policies compare `company_id` with
  `current_setting('touche.company_id', true)`.
* The request transaction sets the value with `SET LOCAL`
  (`set_config('touche.company_id', ?, true)`), which is automatically reset at
  `COMMIT`/`ROLLBACK`. `app/db/tenant.py` exposes `apply_company_context()`,
  which refuses to run outside a transaction and is verified by an integration
  test.
* The active company lives in the **server-side session row** (not in a client
  cookie). `POST /api/v1/session/company` verifies an active membership before
  switching, rotates the session token, and writes an audit record.
* Every relevant request re-verifies that the session's company still has an
  active membership for the actor.
* When a membership is removed, all sessions referencing that company are
  revoked in the same transaction.

### 7.1 Composite foreign keys

Tenant-owned children reference parents by `(id, company_id)` so a row can never
point at another company's parent — even if a policy is missing:

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

## 12. Idempotency, concurrency and pagination

* `Idempotency-Key` is scoped by `(company_id, actor_id, endpoint, key)`, TTL
  24 h, stored in PostgreSQL with the request fingerprint and the original
  response.
* Concurrent duplicates are serialised with a unique constraint: the first
  request inserts an `in_flight` record, duplicates receive `409` with
  `IDEMPOTENCY_IN_PROGRESS` and `Retry-After: 1`. A reused key with a different
  fingerprint returns `409 IDEMPOTENCY_CONFLICT`. Completed keys replay the
  stored response (`Idempotent-Replay: true`).
* Optimistic concurrency uses a monotonically increasing `version` and an
  `ETag: "v{version}"`. Mutations require `If-Match` (`428
  PRECONDITION_REQUIRED` when absent, `409 VERSION_CONFLICT` when stale).
* Pagination: `limit` default 25, maximum 100, cursors rather than page numbers
  so results stay stable while rows mutate.

---

## 13. Frontend architecture

* Next.js 16 App Router, React 19, TypeScript strict, Tailwind CSS 4, shadcn/ui
  style primitives (owned in-repo, not an external dependency), Lucide icons.
* Server components perform the status probes; the page is `force-dynamic` so a
  build can never embed a stale "online" label.
* All DTO types come from `src/lib/api/schema.d.ts`, generated by
  `openapi-typescript` from `frontend/openapi/openapi.json`, which is exported
  from FastAPI. Drift is a build failure (`scripts/generate-api-types.ps1 -Check`,
  CI job `api-contract`).
* The client is transport-only: it reports the exact backend answer, including
  the error envelope, and never invents success.
* Navigation placeholders are disabled buttons labelled with the stage in which
  they become available — no dead links, no fake screens, no fabricated KPIs.
* Presentation helpers (`src/lib/status.ts`) are pure and unit tested.

---

## 14. AI boundary

AI tools will call the same authenticated API as humans, with a service actor
identity recorded in the audit log (`actor_type='agent'`). They may not read the
database directly, bypass permission checks, approve financial documents, or
write audit records outside the normal service path. Prompt input/output is not
persisted in logs; document bodies are never logged.

---

## 15. Scheduled maintenance (planned)

| Job | Purpose | Planned stage |
| --- | ------- | ------------- |
| `sessions.expire` | delete sessions past idle/absolute expiry | 1A |
| `idempotency.expire` | delete idempotency records older than TTL (24 h) | 1A |
| `audit.retention` | enforce the documented audit retention window | 1A |
| `outbox.relay` | deliver pending outbox events, exponential backoff | 2 |
| `outbox.prune` | delete delivered events after retention | 2 |

Stage 0 does not run background workers. Jobs will be idempotent, single-writer
guarded (advisory lock), and observable through the same structured logs.

---

## 16. Environments and non-goals

Local development is the only environment that exists today. The API refuses to
start with unsafe production settings (insecure cookie, non-HTTPS CORS,
non-JSON logging, debug enabled), and CORS is restricted to the local frontend
origins.

Explicit non-goals for Stage 0: authentication, sessions, companies,
memberships, RLS policies, audit table, idempotency storage, business modules,
AI agents, Gmail/WhatsApp/E-YAY/Touche Finance/TOUCHE ONE clients, Kubernetes,
Redis, Kafka and any additional infrastructure.

Known environment limitation: this workstation has **no Docker/WSL**, so
`infra/docker-compose.yml` was authored but not executed here. Stage 0 was
verified against a native portable PostgreSQL 17.6 cluster started by
`scripts/db/bootstrap-local-postgres.ps1`. Both paths share the same role
bootstrap SQL (`scripts/db/01-roles-and-database.sql`,
`scripts/db/02-schema-grants.sql`).





# TOUCHE COMMERCE — Roadmap

Stages are sequential: a stage starts only when the previous stage's acceptance
criteria are met and verified. Nothing is marked complete without executed
evidence (see `docs/PROGRESS.md`).

---

## Stage 0 — Foundation ✅ (implemented and verified locally)

**Goal:** a running, observable, migrated skeleton with binding architecture.

Delivered:

* Next.js 16 dark application shell with premium navigation placeholders.
* FastAPI service with configuration, JSON logging, request correlation,
  standard error envelope, CORS, database layer and health endpoints.
* PostgreSQL 17 with `touche` schema, transactional outbox table, migration
  `0001_foundation`, and two least-privilege roles (`touche_migrator`,
  `touche_app`, `NOBYPASSRLS`).
* OpenAPI → TypeScript pipeline and a real status screen driven by live probes.
* Backend unit + live-database integration tests, frontend unit/component tests,
  lint, typecheck, production build.
* Documentation set and CI workflow.

**Exit criteria:** all ten Stage 0 acceptance checks verified (see
`docs/PROGRESS.md`).

Not in scope, deliberately: authentication, companies, memberships, RLS
policies, audit table, idempotency storage, business data, integrations, AI.

---

## Stage 1A — Identity, sessions, tenancy, audit ✅ (implemented and verified locally)

**Goal:** a trustworthy security and data-isolation core.

Delivered:

1. **Schema** (`0002_identity`): `app_user`, `company`, `membership`,
   `auth_session`, `login_attempt`, `audit_record`, `idempotency_record`,
   `company_settings`, `company_setting_entry`; composite unique keys, the
   composite-FK child rule, CHECK constraints for every enum-like column.
2. **Sessions**: Argon2id passwords; 256-bit opaque tokens stored as SHA-256;
   rotation on company switch; 30-minute idle / 12-hour absolute expiry enforced
   server-side; CSRF token bound to the session; logout and revocation.
3. **Companies**: `GET /api/v1/companies` (memberships only) and
   `POST /api/v1/session/company` with membership re-validation and token
   rotation. Membership administration (grant/revoke) via the privileged CLI.
4. **Roles/permissions**: `viewer`, `trader`, `approver`, `admin`;
   `finance.approve` is approver-only and never granted to `admin`.
5. **Audit writer** with redaction, append-only grants plus a trigger; observed
   actions: login success/failure, logout, company switch, session revoked,
   membership changed, access denied.
6. **PostgreSQL RLS** on `company`, `membership`, `company_settings`,
   `company_setting_entry`, `idempotency_record` and `audit_record`, driven by
   transaction-scoped `SET LOCAL`; the runtime role is `NOBYPASSRLS` and cannot
   disable row security; missing tenant context fails closed.
7. **Rate limiting**: 10 failed logins per account and 30 per source per 300 s,
   database-backed, with `Retry-After`.
8. **Tests**: 82 new backend tests (security primitives, auth/session flows,
   RLS isolation matrix) and 23 new frontend tests, all green alongside the
   Stage 0 suite.

**Exit criteria:** met — a non-member cannot read or write another company's data
(proven by direct SQL, not just API filtering); sessions cannot be replayed after
revocation or timeout; audit rows are immutable; `admin` cannot approve financial
documents; the whole suite passes on the isolated test database.

**Deferred deliberately (recorded so nothing is implied as done):**

| Item | Why | Target |
| ---- | --- | ------ |
| Idempotency middleware | No mutating business endpoint exists yet; the table and cleanup contract are in place | Stage 1B/2 |
| Session/idempotency cleanup jobs | Requires a scheduler/worker; ADR-016 keeps the contract but execution is deferred | Stage 1B |
| Membership/audit HTTP APIs and admin UI | The task scoped Stage 1A to selection + CLI; endpoints are reserved and return 404 | Stage 1B |
| Invitations, password reset, MFA | Out of the Stage 1A brief; no partial UI is exposed | Stage 1B+ |

**Guardrail (kept):** no endpoint is marked done while its authorization path is
untested.

---

## Stage 1B — Trade workspace (CRM, catalogue, deals) ✅ (implemented and verified locally)

**Goal:** the first real business workflow, end to end, on top of the Stage 1A
security core.

Delivered:

1. **Schema** (`0003_trade`): `counterparty`, `product`, `deal`, `deal_item`,
   `deal_transition`; composite foreign keys that include `company_id`, a
   `version` column on every mutable row, CHECK constraints for every status and
   money rule, row level security on all five tables and append-only grants on
   the deal history.
2. **Deal state machine**: explicit transition graph
   (`DRAFT → OPEN → NEGOTIATION`, terminal `LOST`/`CANCELLED` with a mandatory
   reason). `WON` is deliberately **disabled** (`409 TRANSITION_DISABLED`) until
   sales orders exist. Impossible edges return `409 INVALID_TRANSITION` with the
   allowed targets; history and audit rows are written in the same transaction.
3. **APIs**: `/counterparties`, `/products`, `/deals`, `/deals/{id}`,
   `/deals/{id}/transitions` and `/dashboard/summary` with active-company
   scoping, `company.view` / `trade.write` permissions, cursor pagination bound
   to the filter set, `ETag`/`If-Match` optimistic concurrency, required
   `Idempotency-Key` on transitions, request-id correlation and audit.
4. **Frontend**: `/crm`, `/products`, `/deals`, `/deals/new`, `/deals/[id]` and
   a live command center, all server-rendered from the API through the
   session-forwarding layer; mutations use the same-origin proxy with CSRF,
   idempotency keys and `If-Match`. Read-only roles see no write affordances.
5. **Operations**: `python -m app.cli seed-demo --company "…"` for explicitly
   requested, clearly labelled demo data (local/test/ci only) and
   `scripts\verify-trade.ps1` for the 15-step workflow.

**Exit criteria:** met — the executed workflow proves a trader can create CRM,
catalogue and deal data, that status can only change through the validated
endpoint, that WON is unreachable, that reasons are mandatory for terminal
states, that replays are idempotent, that a foreign company sees nothing, and
that the rendered pages show exactly the API data (`docs/PROGRESS.md` §20).

**Deferred deliberately (recorded so nothing is implied as done):**

| Item | Why | Target |
| ---- | --- | ------ |
| `WON` transition and sales orders | Needs the order aggregate; a win without an order is a lie | Stage 2 |
| Deal line editing after creation | Financial lines should not change silently; replacement needs an amendment workflow | Stage 2 |
| Quotations, logistics, documents | Separate modules with their own state machines | Stage 2–3 |
| Membership/audit admin UI and `company_settings` screens | Still CLI/API-only; no partial screens are exposed | Stage 2 |
| Invitations, password reset, MFA | Identity extension, not trade functionality | Stage 2 |
| Idempotency/session cleanup scheduler | Records are bounded by TTL but nothing purges them yet | Stage 2 |

**Guardrail (kept):** no endpoint is marked done while its authorization path is
untested; no screen renders data the API did not return.

---

## Stage 2 — Trade workspace

**Goal:** deals and orders with correct commercial state transitions.

Work: `trade_deal` and `sales_order` state machines, transition endpoint with
atomic `WON` + single order creation, idempotent replay and `ALREADY_WON`,
optimistic concurrency, attachments, comments, audit integration, first outbox
producers and relay worker with retries.

**Exit criteria:** concurrent `WON` attempts create exactly one order; repeated
keys replay identical responses; outbox events are delivered at least once and
retried with backoff; no orphaned order/deal states exist.

---

## Stage 3 — CRM, RFQ, quotes, products, logistics

**Goal:** the day-to-day trading workflow.

Work: accounts/contacts, RFQ intake, quotation versioning, product catalogue,
price lists, shipments and milestones, document generation. Quotes and orders
reuse the Decimal/currency/FX rules and the audit/idempotency conventions.

**Exit criteria:** quote → order traceability with immutable revisions; every
state change audited; list endpoints paginated and permission-filtered.

---

## Stage 4 — Finance and integrations

**Goal:** money movements and the first external systems.

Work: invoices, payments, approvals (`finance.approve`), FX snapshots,
reconciliation; E-YAY and Touche Finance adapters driven by the outbox; webhook
receivers with signature verification and idempotent processing.

**Exit criteria:** no financial posting without the approval permission; every
conversion stores rate/date/source; duplicate webhooks do not duplicate entries;
failed deliveries recover from the outbox.

---

## Stage 5 — AI Office and messaging

**Goal:** assistants that operate strictly inside the rules.

Work: Gmail and WhatsApp Business connectors, AI Office tooling, agent identities
with scoped permissions, prompt/response privacy controls, audit of every tool
invocation, human-in-the-loop for approvals and outbound messages.

**Exit criteria:** negative tests prove an agent cannot approve finance, read
another company's data, or bypass audit; all outbound messages are logged with
actor and request id; no secret ever appears in a prompt log.

---

## Deferred / explicitly avoided

Microservices, Redis, Kubernetes, Kafka, event sourcing, CQRS and a separate
worker platform. Each requires a demonstrated need, a new ADR and a migration
plan. Infrastructure additions must pay for their operational cost in
reliability or product capability.

---

## Dependency direction rule

Each stage may depend on earlier stages only. Business modules never reach
around the API layer into another module's tables; they call services. AI and
integration adapters call the same services as the UI, with the same
permission checks and the same audit trail.

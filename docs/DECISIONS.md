# TOUCHE COMMERCE — Architecture Decision Records

These decisions are **binding** for Stage 1A and later. Each record states the
decision, the reasoning and how compliance is verified. Changing one requires a
new ADR that supersedes it, never a silent edit.

Status legend: `ACCEPTED` (binding), `IMPLEMENTED` (code exists and is tested).

---

## ADR-001 — Modular monolith (Next.js + FastAPI + PostgreSQL)

**Status:** ACCEPTED · IMPLEMENTED (Stage 0)

**Decision.** One Next.js frontend, one FastAPI backend, one PostgreSQL database.
Modules are packages inside the backend and route groups inside the frontend.
No microservices, Redis, Kubernetes or Kafka.

**Reasoning.** The domain is cohesive (trade deals, quotations, orders, finance)
and the team is small. Distributed transactions and extra infrastructure would
add failure modes before any product value exists.

**Consequences.** Clear module boundaries and dependency direction are enforced
by review and package layout. Scaling is vertical first; a module can be
extracted later only with a demonstrated need.

**Verification.** Repository layout (`backend/app`, `frontend/src`), no service
mesh or queue in `infra/`.

---

## ADR-002 — Server-side sessions in PostgreSQL

**Status:** ACCEPTED · IMPLEMENTED (Stage 1A)

**Decision.** Sessions are rows in PostgreSQL. The browser receives a random
256-bit token in an `HttpOnly`, `Secure`, `SameSite=Lax` cookie
(`__Host-touche_session` outside local dev). Only a SHA-256 hash of the token is
stored server-side. Rotation occurs on login, privilege change and company
switch. Initial policies: **30-minute idle timeout**, **12-hour absolute
timeout**, both configurable. CSRF protection uses a double-submit
`X-CSRF-Token` validated against the session. Login attempts are rate limited
(10 attempts / 300 s per account+source) using database counters.

**Reasoning.** Revocation and multi-company switching need server state;
PostgreSQL is already a hard dependency, so no Redis is introduced.

**Consequences.** Every authenticated request performs one indexed lookup
(hashed token). Session rows are purged by a scheduled job.

**Verification (Stage 1A).** Tests for: expired idle session rejected, expired
absolute session rejected, rotated token invalidates the old one, CSRF header
required for mutations, rate limiter blocks the 11th attempt, cookie flags
asserted on the Set-Cookie header.

---

## ADR-003 — Four roles; approval is a separate permission

**Status:** ACCEPTED · IMPLEMENTED (Stage 1A)

**Decision.** Roles: `viewer`, `trader`, `approver`, `admin`. Financial approval
is the distinct permission `finance.approve`. Being `admin` does **not** grant
`finance.approve`.

**Reasoning.** Separation of duties: administering users and infrastructure is
not the same as authorising money. A single admin role that can approve
financial documents would collapse that control.

**Consequences.** Permission checks are explicit (`require_permission(...)`), not
role comparisons spread through code. `admin` gets management permissions only.

**Verification (Stage 1A).** Matrix tests: admin without the approval permission
receives `403 FORBIDDEN` on approval endpoints; approver can approve but cannot
manage memberships.

---

## ADR-004 — Multi-company model with PostgreSQL RLS

**Status:** ACCEPTED · IMPLEMENTED (Stage 1A)

**Decision.** Tenant data is scoped by `company_id`. Membership must be verified.
Row level security is enabled on tenant-owned tables and reads
`current_setting('touche.company_id', true)`, set with `SET LOCAL` inside the
request transaction. Two database roles exist: `touche_migrator` (DDL, owns the
schema) and `touche_app` (runtime DML only). The runtime role is created with
`NOBYPASSRLS`, `NOSUPERUSER`, `NOCREATEDB`, `NOCREATEROLE` and has no `CREATE`
privilege on schema `touche`.

**Reasoning.** Application-level filtering alone fails open when a query is
forgotten. RLS fails closed. Separate roles contain the blast radius of a SQL
injection or a compromised runtime credential.

**Consequences.** Every request transaction must set the company context before
tenant queries; queries without context see nothing. Migrations always run as
the migration role.

**Verification.** Stage 0 integration tests assert `rolbypassrls = false`,
`rolsuper = false`, no schema `CREATE`, working DML grants, and that `SET LOCAL`
does not survive its transaction. Stage 1A adds the RLS isolation matrix
described in `ARCHITECTURE.md §7.2`.

---

## ADR-005 — Active company stored in the session

**Status:** ACCEPTED (implemented in Stage 1A)

**Decision.** The active company lives in the server-side session row, never in
a client-controlled cookie or header. `POST /api/v1/session/company` switches it:
the server verifies an **active, verified membership** for the actor, updates the
session, rotates the session token and writes an audit record. Every relevant
request re-verifies the membership. Removing a membership revokes **all**
sessions referencing that company in the same transaction.

**Reasoning.** A client-selected tenant identifier is an authorization input and
must be validated server-side every time; stale sessions must not retain access
after removal.

**Consequences.** Switching company invalidates the previous token (the browser
receives the new cookie in the response). A revoked membership produces `403`
immediately, not at the next login.

**Verification (Stage 1A).** Tests for: switch to a non-member company → `403`;
switch rotates the token; request after membership removal → `403` and session
row revoked; audit record written with `action='session.company.switch'`.

---

## ADR-006 — Composite foreign keys for tenant-owned children

**Status:** ACCEPTED (applied to every tenant-owned table from Stage 1A)

**Decision.** Parents expose `UNIQUE (id, company_id)`. Children reference
`FOREIGN KEY (parent_id, company_id) REFERENCES parent (id, company_id)`.

**Reasoning.** Even a missing RLS policy cannot create a cross-company
relationship; the database rejects it.

**Consequences.** Slightly wider indexes and explicit composite constraints in
every child table; `company_id` is never nullable on tenant data.

**Verification (Stage 1A).** Test inserting a child that references another
company's parent → foreign key violation. Concrete example in
`ARCHITECTURE.md §7.1`.

---

## ADR-007 — Separate state machines for trade deals and sales orders

**Status:** ACCEPTED (implemented in Stage 2; WON disabled until then)

**Decision.** `trade_deal` and `sales_order` have independent state machines.
Transitioning a deal to `WON` and creating its single sales order happen in one
transaction: either both exist or neither does. Until the orders module exists,
the `WON` transition is **disabled** in the API (no partial feature). Mutations
use an `Idempotency-Key`: a repeated key replays the original result; a
different key after `WON` returns `409 ALREADY_WON`.

**Reasoning.** A won deal without an order (or an order without a won deal) is
corrupt commercial data. Idempotent transitions make retries safe for unreliable
networks and automation.

**Consequences.** The transition endpoint owns the transaction boundary; order
creation is an internal service call, not a second HTTP request.

**Verification (Stage 2).** Tests: concurrent `WON` requests produce one order;
repeated key returns the identical response body and status; a second distinct
key returns `ALREADY_WON`; a failed order insert rolls the deal status back.

---

## ADR-008 — Decimal money and ISO currency with FX provenance

**Status:** ACCEPTED (enforced from Stage 2)

**Decision.** Amounts and quantities are `Decimal`/`NUMERIC`/JSON decimal
strings. Every amount has an ISO 4217 currency code. Any conversion persists
`fx_rate`, `fx_effective_date` and `fx_source` on the record that holds the
converted amount.

**Reasoning.** Binary floating point silently loses cents; historical documents
must be reproducible after exchange rates change.

**Consequences.** No `float` in schemas, services or database columns. The
frontend renders strings; it never recomputes money.

**Verification (Stage 2).** Schema tests assert decimal serialisation and
currency validation; an FX conversion test asserts the persisted provenance
fields.

---

## ADR-009 — Append-only audit with redacted snapshots

**Status:** ACCEPTED (implemented in Stage 1A)

**Decision.** `touche.audit_record` contains exactly: `event_id`, `company_id`,
`actor_type`, `actor_id`, `action`, `entity_type`, `entity_id`, `before`,
`after`, `request_id`, `occurred_at`. `before`/`after` are JSONB redacted before
serialisation. The table is append-only: the runtime role has `INSERT`/`SELECT`
only and a trigger rejects `UPDATE`/`DELETE`.

**Reasoning.** Disputes in international trade require a trustworthy history of
who changed what. Mutable audit rows are worthless as evidence.

**Consequences.** Corrections are new audit events, never edits. Audit writes
share the business transaction, so a rolled-back change leaves no audit entry.

**Verification (Stage 1A).** Tests: update/delete attempts fail; sensitive keys
are redacted; `request_id` matches the response header; audit row exists only
when the business transaction committed.

---

## ADR-010 — DocumentStorage interface with server-generated keys

**Status:** ACCEPTED (implemented in Stage 1B/2)

**Decision.** Storage is behind an interface with `put`, `get`, `delete` and an
optional `presigned_url`. Keys are generated by the server
(`companies/{company_id}/{category}/{uuid4}{ext}`), never derived from client
input. Local filesystem first; S3-compatible storage later.

**Reasoning.** Storage backends change; path traversal and collisions are
prevented by construction rather than validation.

**Consequences.** Business code depends only on the protocol. Local storage must
live outside the repository (or in a git-ignored volume) and be excluded from
backups of source code.

**Verification (Stage 1B).** Tests: stored key contains a UUID and whitelisted
extension; client filename `../../etc/passwd` never appears in the key;
`presigned_url` returns `None` for local storage.

---

## ADR-011 — API contract conventions

**Status:** ACCEPTED · foundation IMPLEMENTED (Stage 0)

**Decision.** All endpoints live under `/api/v1`. Every response carries
`X-Request-ID`. Errors use one envelope (`{"error": {code, message, request_id,
timestamp, details}}`). Lists use cursor pagination with `limit` default **25**
and maximum **100**. Mutating endpoints accept `Idempotency-Key` and require
`If-Match` for optimistic concurrency.

**Reasoning.** A stable, machine-readable contract lets the frontend, future
integrations and AI tools share one implementation without guessing.

**Consequences.** Codes — not messages — are the contract. Unknown codes must be
treated as generic failures by clients. Breaking changes require `/api/v2`.

**Verification.** Stage 0 tests pin the envelope for 404/405/422/500, the
request-id echo, CORS headers, and the `no-store` cache policy; pagination and
idempotency conventions are enforced by contract tests in Stage 1B.

---

## ADR-012 — Idempotency scoped by company, actor, endpoint and key

**Status:** ACCEPTED · IMPLEMENTED (Stage 1B, see ADR-026)

**Decision.** Identity of an idempotent operation is
`(company_id, actor_id, endpoint, key)`. Records store the request fingerprint,
state (`in_flight` / `completed`), the response snapshot and an expiry
(**24 hours** default). The unique constraint serialises concurrent requests:
the loser receives `409 IDEMPOTENCY_IN_PROGRESS` with `Retry-After: 1`; a
completed record replays the original response with `Idempotent-Replay: true`; a
different fingerprint for the same key returns `409 IDEMPOTENCY_CONFLICT`.

**Reasoning.** Keys generated by different tenants or actors must never collide;
retries after a network failure must not duplicate business effects.

**Consequences.** The idempotency row is written in the same transaction as the
business change when possible, and finalised immediately after commit. Expired
rows are purged by a scheduled job.

**Verification (Stage 1B).** Tests: same key replays; different body → conflict;
same key in another company is treated as new; concurrent duplicate gets the
in-progress response; expired row is treated as unused.

---

## ADR-013 — Concurrency error semantics

**Status:** ACCEPTED · IMPLEMENTED (codes exist in Stage 0)

**Decision.** Missing `If-Match` where required → **428
`PRECONDITION_REQUIRED`**. Stale version → **409 `VERSION_CONFLICT`**. Reused
idempotency key with a different payload → **409 `IDEMPOTENCY_CONFLICT`**.

**Reasoning.** Clients need to distinguish "you forgot the precondition" from
"someone else changed the row" without parsing prose.

**Consequences.** `ETag` is returned on every versioned resource; `412` is not
used for missing preconditions. The frontend surfaces a refresh-and-retry
affordance for `VERSION_CONFLICT`.

**Verification (Stage 1B).** Endpoint tests for each code, including the
`ETag`/`If-Match` round trip.

---

## ADR-014 — OpenAPI-generated TypeScript types

**Status:** ACCEPTED · IMPLEMENTED (Stage 0)

**Decision.** Backend Pydantic schemas are the single source of truth. FastAPI
exports `frontend/openapi/openapi.json`; `openapi-typescript` generates
`frontend/src/lib/api/schema.d.ts`. Hand-written duplicate DTOs are forbidden.

**Reasoning.** Duplicated types drift silently; generated types fail the build
at the exact place that broke.

**Consequences.** Contract changes require regenerating and committing both
artefacts (`scripts/generate-api-types.ps1`). CI fails on drift.

**Verification.** Stage 0 generated types drive the real status page;
`scripts/generate-api-types.ps1 -Check` passes; the `api-contract` CI job
regenerates and diffs.

---

## ADR-015 — Structured logging without secrets

**Status:** ACCEPTED · IMPLEMENTED (Stage 0)

**Decision.** Logs are single-line JSON with service/environment/version,
request id and explicit fields. Credentials, session tokens, cookies,
authorization headers, document bodies and request/response bodies are never
logged; sensitive field names are redacted defensively.

**Reasoning.** Logs are copied, shipped and retained; they are the easiest way
to leak a secret or a customer document.

**Consequences.** Debugging relies on request ids and explicit contextual fields
rather than dumping payloads. Driver errors are sanitised and truncated.

**Verification.** Stage 0 smoke tests parse emitted JSON, assert redaction of
sensitive keys and confirm request-id correlation.

---

## ADR-016 — Cleanup jobs for ephemeral data

**Status:** ACCEPTED (contract defined; jobs deliberately deferred to Stage 1B)

**Decision.** Scheduled, idempotent jobs delete expired sessions, expired
idempotency records (default 24 h), and (from Stage 2) delivered outbox events.
Each job runs under a PostgreSQL advisory lock so only one instance executes it.

**Reasoning.** Unbounded session/idempotency tables degrade performance and
retain sensitive state longer than needed.

**Consequences.** No external scheduler is introduced; a `maintenance` command is
invoked by the platform scheduler (or a Stage 2 worker loop). Retention windows
are configuration, not hardcoded.

**Verification (Stage 1A).** Tests assert only expired rows are removed and the
job is safe to run twice.

---

## ADR-017 — Transactional outbox for future integrations

**Status:** ACCEPTED · foundation IMPLEMENTED (Stage 0)

**Decision.** External integration events are written to `touche.outbox_event`
in the same transaction as the business change. A relay worker (Stage 2)
delivers them with retries, exponential backoff, attempt counting and
`last_error` capture. Stage 0 ships only the table, ORM model and indexes.

**Reasoning.** Publishing after commit loses events on crash; publishing inside
the transaction without a broker duplicates or loses state. The outbox is the
smallest reliable primitive, and it needs no new infrastructure.

**Consequences.** Consumers must be idempotent (at-least-once delivery). Event
payloads are versioned and never contain secrets.

**Verification.** Stage 0 integration test writes an outbox row as the runtime
role and rolls it back. Stage 2 adds relay tests with a fake consumer.

---

## ADR-018 — AI cannot bypass authorization, approval or audit

**Status:** ACCEPTED (binding from Stage 1A)

**Decision.** AI tools act through the same authenticated API with a service
actor identity (`actor_type='agent'`). They cannot read the database directly,
escalate permissions, approve financial documents, suppress audit records or
call internal services that skip permission checks.

**Reasoning.** An agent with side-channel access would silently invalidate the
approval and audit controls the business depends on.

**Consequences.** Every AI capability is a thin wrapper over an existing,
permission-checked endpoint. Tool invocations are audited with the same
`request_id` chain.

**Verification (Stage 5).** Negative tests: agent token without `finance.approve`
receives `403`; audit row records `actor_type='agent'`; no endpoint accepts an
actor identity from the request body.

---
## ADR-019 — Table names that avoid SQL reserved words

**Status:** ACCEPTED · IMPLEMENTED (Stage 1A)

**Decision.** The identity tables are `touche.app_user` and
`touche.auth_session`; domain vocabulary (user, session) is preserved in code,
API and docs. Every other table uses a plain singular noun (`company`,
`membership`, `audit_record`, `login_attempt`, `idempotency_record`,
`company_settings`, `company_setting_entry`).

**Reasoning.** `USER` is fully reserved in SQL and cannot be used unquoted, and
`session` collides with both SQLAlchemy's `Session` and PostgreSQL terminology.
Quoting identifiers everywhere creates a class of bugs that only appear in raw
SQL, and a mis-quoted identifier silently resolves to a different case.

**Consequences.** One documented deviation from the original naming; no path,
schema or ORM class ever needs manual quoting. Applied by migration
`0002_identity`.

**Verification.** Migration + live schema inspection; all queries run without
quoted identifiers.

---

## ADR-020 — Argon2id with configurable cost and a set-time password policy

**Status:** ACCEPTED · IMPLEMENTED (Stage 1A)

**Decision.** Passwords are hashed with Argon2id (`argon2-cffi`), default cost
`time=2`, `memory=19 456 KiB`, `parallelism=1`, 32-byte hash, 16-byte salt.
Parameters come from configuration so production can raise them and tests can
lower them. The policy (minimum 12 characters, at least three of lower/upper/
digit/symbol, no surrounding whitespace, maximum 512) is enforced when a password
is set, never on login. Unknown accounts still incur a dummy Argon2 verification.

**Reasoning.** Argon2id is the current OWASP first choice for password storage and
resists GPU cracking; the policy belongs at set time because rejecting a login for
"too short" would confirm which inputs are plausible passwords for an account.
Uniform work for unknown accounts removes a timing oracle.

**Consequences.** Login latency is dominated by hashing (~50 ms at the default
cost). `needs_rehash()` transparently upgrades hashes when the cost changes.
Operators never see plaintext; the CLI reads passwords from a hidden prompt or
stdin.

**Verification.** Unit tests: hash prefix `$argon2id$`, wrong/garbage hash
rejection, distinct hashes for identical passwords, policy rejections, dummy
verification, plus integration tests asserting no hash or password appears in
responses or audit details.

---

## ADR-021 — Login-attempt data minimisation

**Status:** ACCEPTED · IMPLEMENTED (Stage 1A)

**Decision.** `login_attempt` stores `email_normalized`, source IP, success flag,
reason and timestamp — and nothing else. The audit trail records the *reason*
(`unknown_user`, `invalid_password`, `user_disabled`) but never the attempted
email, the password or any hash. The table has no API exposure.

**Reasoning.** Rate limiting needs to count failures per account and per source,
which requires the identifier; the audit trail needs to explain *why* an access
was refused. Splitting the two keeps the durable, widely-visible audit log free of
raw identifiers while retaining operational forensics in a table nobody can query
through the API.

**Consequences.** Investigations join `login_attempt` (short retention, future
cleanup job) with `audit_record` by time and actor, not by email.

**Verification.** Integration tests assert `audit_record.details` for a failed
login contains only the reason and never the email/password; the rate-limit test
asserts behaviour without inspecting identifiers.

---

## ADR-022 — Origin validation for every mutation; CSRF bound to the session

**Status:** ACCEPTED · IMPLEMENTED (Stage 1A)

**Decision.** (1) An ASGI middleware rejects any non-GET request whose `Origin`
header is missing or not in the configured trusted origin list — before routing,
including `/auth/login`. (2) Every authenticated mutation must also send
`X-CSRF-Token`, compared in constant time against the token stored on the session
row it was issued for. Login is CSRF-exempt because no session exists yet, but it
is still Origin-validated. (3) The CSRF token is stored on the session row in clear
text; the session token is stored only as a SHA-256 digest.

**Reasoning.** Double-submit cookies alone can be defeated when subdomains are in
play; binding the CSRF token to the server-side session makes a token from another
session useless. Requiring `Origin` on every mutation (rather than only when
present) closes the "strip the header" bypass. Storing the CSRF token in clear is
acceptable because it is not a credential on its own: it is worthless without the
`HttpOnly` session cookie, and it must survive a page reload so the client can
receive it again from `/auth/me`.

**Consequences.** Non-browser clients (CLI, curl, tests) must send `Origin` on
mutating requests; the verification script and tests do so explicitly. The
frontend proxy forwards `Origin` unchanged. Swagger UI mutations are rejected in
local development.

**Verification.** Integration tests: mutation without `Origin` → `403
ORIGIN_REJECTED`; foreign origin → `403` and no session created; logout/switch
without or with a foreign CSRF token → `403 CSRF_REJECTED`; the token rotates on
switch and the old token stops working.

---

## ADR-023 — RLS covers tenant data, not the authentication bootstrap

**Status:** ACCEPTED · IMPLEMENTED (Stage 1A)

**Decision.** Row level security is enabled on `company`, `membership`,
`company_settings`, `company_setting_entry`, `idempotency_record` and
`audit_record`. It is **not** enabled on `app_user`, `auth_session`,
`login_attempt` or `outbox_event`. Those tables are protected by least-privilege
grants (DML only, no DDL, no `TRUNCATE`) and by having no direct API exposure;
every access goes through `AuthService`/`AdminService`. The runtime role has
`NOBYPASSRLS`; any future exposure of those tables must use a `SECURITY DEFINER`
function rather than a relaxed policy.

**Reasoning.** Authentication must read a user by email and a session by token
hash before an actor or tenant is known. An actor-scoped policy on `auth_session`
would make login impossible without a privileged function; a `company_id`-scoped
policy would hide the session before the user has chosen a company.

**Consequences.** Tenant isolation is enforced where tenant data lives. The
`audit_record` policy still permits system-level inserts (`company_id IS NULL`) but
only tenant reads. `company` and `membership` policies are actor-aware, so the API
cannot list companies or memberships the caller has no membership for, even if a
query forgets a filter.

**Verification.** 16 live tests in `test_rls_isolation.py` (cross-tenant read,
write, update, delete, missing context, `row_security=off`, pooled-connection
reset, composite-FK violation, append-only audit) plus role/privilege assertions.

---

## ADR-024 — Same-origin API proxy in the frontend

**Status:** ACCEPTED · IMPLEMENTED (Stage 1A)

**Decision.** The browser calls `/api/v1/*` on the Next.js origin. A route handler
(`src/app/api/v1/[...path]/route.ts`) forwards an explicit allow-list of headers,
the body and `Set-Cookie` to FastAPI, using `API_INTERNAL_BASE_URL` when set.
Server components call FastAPI directly with the incoming cookie header. No token
is ever stored in `localStorage` or `sessionStorage`.

**Reasoning.** A cross-origin cookie would need `SameSite=None`, weakening CSRF
protection, and would require CORS to allow credentials on every request. A
first-party proxy keeps `HttpOnly` + `SameSite=Lax` meaningful, lets Origin
validation behave exactly as in production and hides the internal API address.
Server-side rendering needs the raw cookie, which only the server can read.

**Consequences.** The proxy is a security boundary: it forwards only named headers
and response headers, never arbitrary traffic, and returns a JSON error envelope
(`502 UPSTREAM_UNAVAILABLE`) instead of an HTML error page. `Cache-Control:
no-store` is forced on every proxied response.

**Verification.** Live verification proves login/logout/switch through the proxy,
cookie attributes, CSRF rejection propagation, the `/select-company` redirect and
that an unauthenticated page redirects to `/login?next=…`.

---



## Environment notes (this workstation)

* Detected: Windows 11 (10.0.26200), Python 3.12.10, Node 24.18.0, npm 11.16.0,
  Git 2.55.0. **Docker, Docker Compose and WSL are not installed.**
* Consequence: `infra/docker-compose.yml` is the documented team path but was not
  executed here. Verification used a portable PostgreSQL 17.6 cluster
  (`infra/.local`, git-ignored) started by
  `scripts/db/bootstrap-local-postgres.ps1`.
* `starlette.testclient` in this dependency set requires `httpx2`; the backend
  dev extras install `httpx2` (not `httpx`).
* Python support is pinned to `>=3.12,<3.14`; dependency ranges are bounded to
  the current major/minor line and resolved versions are recorded in
  `docs/PROGRESS.md`.




---

## ADR-024 — Trade schema: composite foreign keys, versions and append-only history

**Status:** ACCEPTED · IMPLEMENTED (Stage 1B)

**Decision.** `counterparty`, `product`, `deal`, `deal_item` and
`deal_transition` are tenant-owned tables in schema `touche`, each carrying
`company_id` and protected by row level security. Every reference from a child
row to a parent includes `company_id` in a composite foreign key
(`deal_item → deal`, `deal_item → product`, `deal → counterparty`,
`deal_transition → deal`), and every parent exposes a redundant
`UNIQUE (id, company_id)` key to make that possible. Mutable rows carry
`version INTEGER NOT NULL DEFAULT 1` with `CHECK (version >= 1)`; the deal
history is insert-only for the runtime role (`GRANT SELECT, INSERT`, no UPDATE or
DELETE).

**Reasoning.** Application code can forget a `WHERE company_id = …` clause; a
composite foreign key cannot. The same mechanism makes a cross-tenant line item
impossible even if a bug supplies a valid id from another company. Versions are
required for `If-Match`; an append-only history table is required for a state
machine that can be audited.

**Consequences.** Ids are globally unique but relationships are still enforced
per tenant. Correcting a line requires a new deal (or a future amendment
workflow), not an in-place edit.

**Verification.** `tests/test_trade_api.py::TestTenantIsolation` proves RLS
filters even for direct SQL, that a missing tenant context returns zero rows, that
the composite FK rejects a cross-tenant deal at the database level, and that the
runtime role cannot update history.

---

## ADR-025 — Deal state machine: explicit graph, disabled WON, mandatory reasons

**Status:** ACCEPTED · IMPLEMENTED (Stage 1B)

**Decision.** The deal lifecycle is an explicit graph in
`app/services/deal_state.py`:

```
DRAFT → OPEN | CANCELLED
OPEN  → NEGOTIATION | LOST | CANCELLED
NEGOTIATION → OPEN | LOST | CANCELLED
WON, LOST, CANCELLED = terminal
```

`LOST` and `CANCELLED` require a 3–500 character reason. `WON` is not reachable:
the endpoint returns `409 TRANSITION_DISABLED` until the sales-order module
exists. Status is never accepted by `PATCH`: the update schema forbids unknown
fields, so `{"status": "WON"}` is a `422 VALIDATION_ERROR`, and closed deals
reject header edits with `409 CONFLICT`. A transition locks the deal row
(`SELECT … FOR UPDATE`), re-reads the status, then writes the deal, the
`deal_transition` row and the audit row in one transaction.

**Reasoning.** A win that creates no order would be a false business record, and
a status field editable through `PATCH` would bypass the transition endpoint,
its history and its reasons. Row locking makes concurrent transitions serialise
instead of racing.

**Consequences.** The API exposes `allowed_transitions` on every deal, and the UI
renders exactly those buttons plus a disabled "Won" control with an explanation.
Re-opening a lost deal requires a new deal.

**Verification.** `tests/test_deal_state.py` exhaustively checks the graph;
`tests/test_trade_api.py::TestTransitions` proves disabled WON, required reasons,
terminal protection, stale `If-Match`, and the blocked `PATCH status` bypass.

---

## ADR-026 — Idempotency implemented as one transaction, scoped per endpoint

**Status:** ACCEPTED · IMPLEMENTED (Stage 1B) — supersedes the implementation note of ADR-012

**Decision.** `idempotency_record` gains `endpoint` and its uniqueness becomes
`(actor_id, company_id, endpoint, key)`. A helper opens a single transaction that
(a) inserts the row `in_flight` with `ON CONFLICT DO NOTHING`, (b) runs the
business change with the same session, (c) stamps the row `completed` with the
serialised response, then commits. Concurrent duplicates block on the unique
index; the loser either replays the committed response or receives
`409 IDEMPOTENCY_IN_PROGRESS` with `Retry-After: 1`. A failure rolls the row back,
so a retry simply runs again. Replays answer with `Idempotent-Replay: true`.
Deal transitions require a key; other writes accept one.

**Reasoning.** Writing the idempotency record *after* the business change loses
the guarantee on a crash between the two commits; writing it in a separate
transaction before the change can leave a permanent "in progress" row. One
transaction removes both failure modes without new infrastructure. Including the
endpoint means the same key used against another endpoint is a different
operation rather than a false conflict.

**Consequences.** A replay is byte-identical to the original response (the JSON
was captured server-side). Expired records are treated as unused and rewritten.
Purging remains a Stage 2 maintenance job.

**Verification.** `tests/test_trade_api.py::TestIdempotency` covers replay, key
reuse with a different body, the same key on another endpoint, and the stored
record; the 15-step workflow replays a transition live.

---

## ADR-027 — Read-only roles see no write affordances; the API is the only authority

**Status:** ACCEPTED · IMPLEMENTED (Stage 1B)

**Decision.** Trade reads require `company.view`; writes require `trade.write`
inside an active company (`require_company_permission`). The UI derives
affordances from the server-rendered `permissions` list, but the API re-checks
every request independently. An administrator (who deliberately lacks
`trade.write`) sees the CRM, catalogue and deals as read-only; a viewer sees the
same.

**Reasoning.** Hiding a button is not authorization. Deriving the UI from the
same permission list keeps the two consistent without moving the decision into
the browser (ADR-018).

**Consequences.** `admin` cannot create or transition deals, by design; granting a
trader role is required to trade.

**Verification.** `tests/test_trade_api.py::TestCounterparties` asserts 403 for
admin and viewer writes; the workflow asserts a real administrator gets 403 and
cannot see another company's deal.



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



---

## ADR-028 - One RFQ per supplier; PREPARED is not SENT

**Status:** ACCEPTED / IMPLEMENTED (Stage 3)

**Decision.** An RFQ addresses exactly one supplier and one deal. Selecting several
suppliers creates one RFQ per supplier in a single transaction. Preparing writes an
append-only revision snapshot; sending additionally requires a channel, a timestamp
and recorded evidence, and cancelling requires a reason. Editing a prepared RFQ
returns it to DRAFT and opens the next revision number.

**Reasoning.** A quote that could belong to two requests, or an RFQ marked sent
without proof of dispatch, destroys the audit chain that the rest of the sourcing
workflow depends on. Splitting prepare and send makes the moment of dispatch a
recorded event rather than a status flip, and makes a prepared snapshot immune to
later edits.

**Consequences.** Comparing offers happens *across* RFQs of a deal, not inside one
row. The UI creates several RFQs at once. A supplier cannot be re-quoted on the
same RFQ without a new quote row or revision.

**Verification.** `tests/test_sourcing_api.py::TestRfqCreation` (batch creation,
buyer rejection, duplicate supplier), `TestRfqLifecycle` (SENT requires PREPARED,
evidence gate, revision snapshot, edit reopens revision, sent RFQ not editable),
`test_pricing_engine.py` and the migration CHECK constraints.

---

## ADR-029 - Pricing is a pure engine; results are stored with their inputs

**Status:** ACCEPTED / IMPLEMENTED (Stage 3)

**Decision.** `app.services.pricing_engine.calculate()` is a pure function of
explicit inputs (lines, an optional FX snapshot, cost components, margin or markup).
The scenario service resolves database rows into those inputs, runs the engine once,
and stores `pricing_inputs`, `calculated_results` and `completeness` together with a
`calculation_version`. Reads never recompute; recalculation is an audited `PUT`
guarded by `If-Match`.

**Reasoning.** A landed cost must be reproducible after prices, invoices and rates
change. Recomputing on read would silently rewrite an already-approved price.
Keeping the engine pure makes it unit-testable without a database and keeps
rounding rules in one place.

**Consequences.** Money rounds to cents (`ROUND_HALF_UP`), unit prices to four
decimals; ORDER costs use largest-remainder pro-rata allocation so allocated cents
always sum to the component exactly. Margin and markup are mutually exclusive
because they produce different prices for the same percentage. A scenario is bound
to one supplier quote and cannot be repointed.

**Verification.** 24 engine unit tests (allocation, margin vs markup, FX pair
checks, LINE-product binding, status derivation, rounding) and the pricing API
tests that assert stored totals, component replacement and version conflicts.

---

## ADR-030 - FX is an explicit, sourced snapshot; never inferred

**Status:** ACCEPTED / IMPLEMENTED (Stage 3)

**Decision.** Conversions use a stored `fx_rate_snapshot` row with base currency,
quote currency, rate, effective timestamp and source. Cross-currency pricing
requires a snapshot whose pair is exactly quote -> target; a component in another
currency requires its own snapshot. There is no update endpoint and no "latest
rate" lookup by the engine.

**Reasoning.** An inferred rate makes a price unreproducible and hides the moment
and source of the assumption. Explicit snapshots turn that assumption into
reviewable data and let a reviewer see which rate produced which quote.

**Consequences.** A user must record a rate before pricing across currencies; the
UI links to the FX page. Recording the same pair and effective time twice is a
`409` instead of a silently duplicated observation. A correction is a new row.

**Verification.** `test_pricing_engine.py` (missing rate, wrong pair) and
`tests/test_sourcing_api.py::TestPricingScenarios::test_cross_currency_needs_a_matching_explicit_fx_snapshot`
(missing snapshot, wrong direction, correct pair, converted totals).

---

## ADR-031 - Sales quote approval: verified inputs, separation of duties, revisions over withdrawal

**Status:** ACCEPTED / IMPLEMENTED (Stage 3)

**Decision.** A sales quote may only be submitted when its pricing scenario is
`VERIFIED_INPUTS`. Approval requires the `finance.approve` permission *and* an
actor different from the submitter. Rejection requires a stored reason. An
approved quote cannot be withdrawn or rejected; a new revision supersedes it and
starts in `DRAFT`, leaving the approved row intact. Status and the approval pair
are held consistent by a database CHECK.

**Reasoning.** A quote is a financial commitment: approving an estimate or letting
one person submit and approve removes the second pair of eyes the permission model
exists to provide. Keeping the approved row immutable preserves the evidence of
what was approved and by whom.

**Consequences.** Admins and traders cannot approve (they do not hold
`finance.approve`). A rejected or withdrawn quote is also revised, not edited. The
UI hides actions the session cannot perform, and the API rejects them anyway.

**Verification.** `tests/test_sourcing_api.py::TestSalesQuotes` covers the
ESTIMATED submission block, trader 403 on approve, approver success, self-approval
refusal, rejection reason, terminal states and revision superseding.

---

## ADR-032 - WON only through the atomic order-conversion service

**Status:** ACCEPTED / IMPLEMENTED (Stage 4)

**Decision.** `WON` is not an edge in the deal state machine. The only path is
`POST /deals/{id}/sales-order`, which locks the deal, verifies the approved quote
revision and the customer acceptance evidence, creates the order and its lines,
writes the transition and audit rows, and sets `WON` in one transaction. A
database unique index enforces at most one initial order per deal. Direct
transitions to `WON` return `409 TRANSITION_DISABLED`; a second conversion key
returns `409 ALREADY_WON`.

**Reasoning.** A won deal without an order is a claim with no operational
consequence, and two orders for one deal are a commercial defect no UI can
repair. Making the state change a side effect of the order insert means the two
facts can never disagree, even under concurrent requests.

**Consequences.** The conversion requires an `Idempotency-Key`; retries replay
the stored response. Clients must create the acceptance evidence first (or inline
it). The generic deal transition endpoint can never produce a false win.

**Verification.** `tests/test_operations_api.py::TestOrderConversionGate`,
`TestOrderConversion` (replay, payload conflict, `ALREADY_WON`, concurrency,
direct-WON refusal) and live checks 6-16.

---

## ADR-033 - Accepted commercial terms are an immutable snapshot

**Status:** ACCEPTED / IMPLEMENTED (Stage 4)

**Decision.** The order copies product, description, quantity, unit, unit price,
line totals, currency, Incoterm, delivery place and payment terms at conversion,
into `sales_order_item` plus one `accepted_terms` JSONB document (quote id,
revision, approval, acceptance channel/timestamp/reference and the lines).
Reconstructing an order never reads the catalogue or the quote.

**Reasoning.** Catalogue prices and quote revisions are mutable by design. An
order that silently followed them would change what the customer agreed to. The
snapshot is the commercial fact; later amendments are appended, never written
over it.

**Consequences.** `PATCH` on a product or a new quote revision has no effect on
an existing order. Amendments record from/to values and leave the snapshot
intact; cancellation preserves it.

**Verification.**
`tests/test_operations_api.py::TestOrderConversion::test_terms_stay_frozen_after_quote_revision_and_catalogue_change`
and
`TestOrderLifecycle::test_amendment_is_recorded_without_rewriting_the_accepted_terms`.

---

## ADR-034 - Procurement is optional, evidence-based and never auto-sent

**Status:** ACCEPTED / IMPLEMENTED (Stage 4)

**Decision.** A purchase order is created explicitly against a sales order and is
refused for `BROKERAGE` deals where TOUCHE is not the buyer. Approval requires
`finance.approve` and a different person from the creator. `RECORDED_SENT`
requires a channel, a timestamp and an external reference; `SUPPLIER_CONFIRMED`
requires the supplier's confirmation reference. The platform sends nothing.

**Reasoning.** Domestic resale and brokerage have different cost structures; a
mandatory purchase order would fabricate a relationship that does not exist. A
"sent" status without evidence is indistinguishable from a draft, and automated
sending would make the platform the author of a communication it cannot verify.

**Consequences.** Purchase orders are a separate, optional workflow. The UI asks
for the evidence fields; the API refuses the transition without them. The
approval route is split from operational transitions so an approver does not need
`trade.write`.

**Verification.** `tests/test_operations_api.py::TestProcurement` (approval
segregation, missing dispatch evidence, supplier confirmation, tenant isolation)
and `tests/test_operations_state.py::TestPurchaseOrderStateMachine`; live checks
17-22.

## ADR-035 - Fulfilment is derived from delivered shipments

**Status:** ACCEPTED / IMPLEMENTED (Stage 4)

**Decision.** Shipments allocate decimal quantities against order lines. A
shipment cannot exceed the unallocated quantity and must use the order line unit.
Cancelled shipments release their allocation. Order status is promoted by the
shipment service: partial delivery → `IN_FULFILLMENT`, every line delivered →
`FULFILLED`. `FULFILLED` has no manual transition.

**Reasoning.** Operators type statuses optimistically; quantities and evidence
are harder to fake. Deriving fulfilment from delivery records makes "delivered"
mean something specific and keeps partial shipments honest (40 of 100 tonnes does
not complete the order).

**Consequences.** Multiple shipments per order are normal. A shortage is visible
as `remaining` rather than hidden. Closing an order remains a separate
administrative step and does not imply payment.

**Verification.** `tests/test_operations_api.py::TestShipments` (partial delivery,
over-allocation, cancellation release, invalid transitions, delivery evidence),
`tests/test_operations_state.py::TestAllocation`, live checks 23-31.

---

## ADR-036 - Logistics costs keep their provenance stage

**Status:** ACCEPTED / IMPLEMENTED (Stage 4)

**Decision.** Each logistics cost row is `ESTIMATED`, `QUOTED`, `INCURRED` or
`DOCUMENTED`, with its own amount, currency and reference. Recording an incurred
invoice adds a row and never edits an estimate or the Stage 3 pricing scenario.

**Reasoning.** Estimated and confirmed costs answer different questions
("what did we plan?" vs "what did we owe?"). Overwriting one with the other
destroys the comparison and quietly changes margin analysis.

**Consequences.** The UI shows the stages separately; reconciliation is a Stage 5
concern. The shipment detail page presents the rows without pretending they are
accounting entries.

**Verification.**
`tests/test_operations_api.py::TestShipments::test_cost_provenance_references_and_documented_delay`
and live check 31.

---

## ADR-037 - Private document storage with two-layer authorisation and DRAFT previews

**Status:** ACCEPTED / IMPLEMENTED (Stage 4)

**Decision.** Files are stored on local disk outside every served directory,
under server-generated keys, with streaming size limits, magic-prefix checks,
SHA-256 verification before download, and versioning that archives rather than
deletes. Authorisation requires the active company *and* an existing linked entity
in that company. Generated invoice/packing-list previews are always labelled
DRAFT with an explicit legal notice and are never stored as issued documents.

**Reasoning.** Bills of lading and certificates are legally significant. Letting
a client choose a path or trusting a MIME header invites traversal, type spoofing
and cross-tenant reads; generating "certificates" or "customs declarations" would
be fabricating documents the platform has no authority to issue.

**Consequences.** Only real external documents may be uploaded for carrier or
customs paperwork. Malware scanning remains an outstanding control. Object
storage/signed URLs would be a deployment change behind the same adapter
interface.

**Verification.** `tests/test_operations_api.py::TestDocuments` (checksum,
versions, archive, MIME/size limits, traversal-safe storage keys, corruption,
cross-tenant 404, draft previews) and live checks 32-42.



---

## ADR-038 - TOUCHE FINANCE remains the only financial source of truth

**Status:** ACCEPTED / IMPLEMENTED as a boundary (Stage 5A)

**Decision.** Commerce owns commercial operational facts (deals, quotes, sales
orders, purchase orders, shipments, documents). Finance owns the chart of
accounts, journal, invoices as postings, receivables, payables, payments,
reconciliation and financial reports. Commerce never creates a ledger entry,
invoice posting or payment, and it does not build a second accounting engine.

**Reasoning.** Stage 4 deliberately stopped at "no accounting". Running two
ledgers would make every balance ambiguous and every reconciliation a guess.
Finance already has double-entry mapping, FIFO aging, recovery journal and
audit evidence; duplicating any of it in Commerce would be strictly worse.

**Consequences.** The original Stage 5 roadmap line "invoices and payments in
Commerce" is superseded. Stage 5 becomes an integration programme: read Finance
first, then send draft commercial events only after Finance exposes a supported
ingest. Commerce's `CLOSED` remains an administrative state, not payment.

**Verification.** No `/invoices`, `/payments`, ledger or journal table exists in
Commerce; Stage 4 tests remain green. The new endpoint reports
`accounting_writes_enabled: false`.

---

## ADR-039 - Read-only-first Finance connector on literal loopback

**Status:** ACCEPTED / IMPLEMENTED (Stage 5A)

**Decision.** The first Commerce→Finance connector may call only Finance's
public `GET /api/health`. It is disabled by default, accepts only
`http://127.0.0.1[:port]` or `http://[::1][:port]`, sends no cookie, bearer token
or Tailscale identity header, requires Finance's `Server: ToucheFinans/...`
identity and a JSON content type, caps the response at 8 KiB, does not follow
redirects, and reports failures as data rather than crashing Commerce.

**Reasoning.** Finance has no service credential. Its business endpoints treat a
loopback request as `OWNER`, so reusing that path would grant a connector
membership, approval and recovery powers it must never have. A health-only
probe is the largest capability that is both verified and safe today.

**Consequences.** Commerce can show whether Finance is reachable and consistent,
but cannot display Finance balances yet. Remote/Tailscale access, business reads
and writes require ADR-040's authenticated interface. Enabling the connector
outside a loopback host is rejected at configuration time.

**Verification.** `tests/test_finance_integration.py` (33 tests: URL rejection,
healthy/degraded/incompatible/unreachable/timeout, Finance identity headers, no
auth headers, disabled default, authenticated endpoint, OpenAPI wiring);
`scripts/verify-finance-readonly.ps1` PASS with unchanged DB/workbook hashes.

---

## ADR-040 - Proposed Finance integration contract (draft-only, not implemented)

**Status:** PROPOSED - NOT IMPLEMENTED (blocked on Finance work)

**Decision.** If Finance integration proceeds, it must use a dedicated,
versioned `/api/integration/v1` surface with HMAC-SHA256 service authentication,
timestamp/nonce replay protection, idempotency keys and an audit record per call.
Read endpoints are added first. Any commercial-event write creates **drafts
only**; Finance's existing human approval/password flow remains the only path to
a posting. A mapping table links Commerce source ids to Finance entities; names
are never used as keys.

**Reasoning.** The current session model authenticates a *network position* or a
Tailscale person, not a service. It cannot scope a connector to read-only or
attribute its actions distinctly. Unsigned JSON over loopback would be
indistinguishable from the local owner. Draft-only ingestion preserves Finance's
approval and recovery guarantees.

**Consequences.** No endpoint in this ADR may be called by Commerce yet; no fake
client or outbox producer is added. Finance must implement and verify §8.1 of
`docs/STAGE5_FINANCE_DISCOVERY.md` before Stage 5B. The exact proposed storage is
additive (`entegrasyon_anahtarlari`, `entegrasyon_istek_kayitlari`,
`entegrasyon_eslesmeleri`, `entegrasyon_olaylari`).

**Verification.** None yet, by design. The proposal is reviewed against the live
Finance source at `8dce8245`; no Finance file, database or workbook was changed.


---

## ADR-041 — Explicit tenant-scoped Finance company mapping

**Status:** ACCEPTED · IMPLEMENTED (Stage 5C)

**Decision.** A Commerce company reads Finance only through one explicit row in
`touche.finance_company_mapping`: `company_id` (unique) → Finance
`faaliyet_key`, verification status, configuring admin and timestamps. The row is
created/changed only by an active company admin through the privileged
`finance-map` CLI after live Finance verification against `/capabilities` and
`/companies`.

**Reasoning.** Company names, currencies and free-text `fisler.cari` values are
not stable identities. Matching by name would silently connect one legal entity's
accounting data to another. A unique, audited mapping makes the relationship
reviewable and revocable.

**Consequences.** Missing, pending, invalid or disabled maps refuse data reads.
The runtime role has `SELECT` only on the mapping; RLS prevents cross-tenant
reads. A future multi-entity mapping requires a new ADR and migration.

**Verification.** `test_finance_api.py` mapping/RLS/cross-tenant tests; CLI set
and isolated HTTP acceptance; migration `0008_finance_mapping`.

---

## ADR-042 — Finance reads are one-currency, read-only and fail closed

**Status:** ACCEPTED · IMPLEMENTED (Stage 5C)

**Decision.** Every Commerce Finance data read requires an authenticated
Commerce session, active company, `company.view` and a verified mapping. When
Finance reports more than one currency, the caller must select exactly one.
Amounts are passed through as Finance decimal strings; no conversion or
aggregation is performed. Only GET endpoints exist. Credentials remain
server-side. Finance error categories are preserved in
`details.finance_code`. An unauditable read is not served.

**Reasoning.** Summing TL, EUR and USD would produce a meaningless number. A
conversion rate invented by Commerce would be a second financial calculation.
A write path would duplicate Finance's accounting authority and recovery
guarantees.

**Consequences.** The UI exposes a currency selector and explicit
NOT_CONFIGURED / CONNECTED / DEGRADED / UNAVAILABLE / AUTH_ERROR states. Invoice
and payment views are marked “Not available”. Finance owns approval, posting,
reconciliation and recovery.

**Verification.** `test_finance_connector.py` (currency/error/read-only),
`test_finance_api.py` (permission/RLS/audit/405), isolated HTTP acceptance with
unchanged Finance database and workbook hashes.

---

## ADR-043 — Reconciliation is evidence, review and append-only history

**Status:** ACCEPTED · IMPLEMENTED (Stage 5D)

**Decision.** Commerce reconciliation stores a reproducible snapshot of Commerce
commercial facts and Finance observations, explicit operator evidence links,
deterministic discrepancies and append-only human reviews. A Finance source id
is the only transaction-level matching key. Exact amount and currency checks are
required. `MATCHED_EVIDENCE` is reachable automatically from an explicit link;
`VERIFIED` is reachable only through an authorised review with no open blocking
discrepancy. A verified run is immutable.

**Reasoning.** Free-text counterparties, company-wide balances and approximate
amounts cannot prove an order-level relationship. Automatically promoting a
match would create a second financial truth. A human decision with identity,
timestamp and notes is auditable and reversible only by a new run.

**Consequences.** Missing or unsupported evidence leaves a run `UNMATCHED` or
`INCOMPLETE`; it is never called reconciled. Company summary/account balances
are non-matchable. A mismatch stays `POTENTIAL_MATCH` until the underlying facts
change in a new run. No accounting entry is created.

**Verification.** `test_reconciliation_calculations.py` (Decimal/currency/
unavailable classifications), `test_reconciliation_api.py` (evidence, duplicate,
amount mismatch, review refusal, verification, audit), isolated HTTP acceptance.

---

## ADR-044 — Financial review uses a separate capability and immutable evidence

**Status:** ACCEPTED · IMPLEMENTED (Stage 5D)

**Decision.** Add `finance.reconcile` as a capability granted to `approver` only;
`admin` does not inherit it. Run creation/evidence linking requires `trade.write`.
Reviewers cannot review a run they created. Evidence/source/review records have no
runtime `DELETE`; evidence exposes only reviewer verification columns for update.
Discrepancy resolution requires `finance.reconcile` and a note.

**Reasoning.** Operational preparation and financial approval are different
duties. An admin who can manage people/settings must not automatically approve
money. Append-only evidence prevents silent rewriting of the basis for a
verification.

**Consequences.** A trader can prepare runs and links but cannot verify them. An
approver can approve a sales quote, approve a purchase order and review
reconciliation. A new financial role requires a new ADR/matrix change.

**Verification.** Permission assertion and API negative tests; runtime grant and
RLS tests; `has_table_privilege(...,'DELETE') = false` on all five tables.

---

## ADR-045 — Profitability is reported on separate bases and there is no actual profit

**Status:** ACCEPTED · IMPLEMENTED (Stage 5E)

**Decision.** The analysis keeps two bases apart and never blends them. `ESTIMATED`:
accepted order value minus the Stage 3 landed-cost scenario, with recoverable
`VAT_CASHFLOW` excluded because it is not an expense. `COMMITTED`/`DOCUMENTED`:
accepted value minus committed purchase orders (approved or later) and shipment costs
recorded as `INCURRED` or `DOCUMENTED`. `QUOTED`/`ESTIMATED` shipment costs and the
pricing scenario are forecasts and never enter the documented basis. A part-shipped
order withholds its committed profit. Currencies are never summed and a cost in
another currency is used only through a stored FX snapshot. No `actual_profit` field
exists; its classification is always `UNAVAILABLE`. Every response carries the
`calculation_version` (`stage5e-1.0.0`).

**Reasoning.** An estimate, a commitment and a recognised result answer different
questions; adding them would produce a number nobody can audit. Actual profit needs
transaction-level invoices and payments, and Finance exposes none (ADR-038). Showing
a committed profit for an order that has shipped 10% would claim a result that has
not happened.

**Consequences.** Many orders show “Not available” for the committed basis until they
are fully shipped and costed. Changing a rule requires a new calculation version, not a
silent edit. If Finance later exposes invoices and payments, an actual-profit basis
needs its own ADR.

**Verification.** `test_intelligence_calculations.py` (VAT exclusion, quoted costs,
partial fulfilment, multiple purchase orders, currency mismatch, missing or exact FX,
zero and negative margins, cancelled orders, currency totals never mixed);
isolated HTTP acceptance (estimated `50.00` at `20.00%`, committed profit withheld
while part-shipped, no actual-profit field or column).

---

## ADR-046 — The profitability export is an audited, formula-safe operational file

**Status:** ACCEPTED · IMPLEMENTED (Stage 5E) · permission scope open for review

**Decision.** `GET /api/v1/finance/intelligence/export` returns a CSV under the same
`company.view` permission as every other financial read. Every row carries its
currency, completeness, reconciliation status and calculation version, and every file
carries an analysis label and a notice that it is not a statutory statement. Each
export writes one `finance.read` audit row. Text columns beginning with `=`, `+`,
`-`, `@`, a tab or a carriage return are prefixed with `'`; numeric columns are never
prefixed. The browser downloads the file with `fetch` so a refusal (for example more
than 5000 orders) is shown on the page, and the same-origin proxy forwards
`content-disposition` and `x-content-type-options` so the file keeps its name and
`nosniff`.

**Reasoning.** Spreadsheet formula injection is a real risk for user-controlled text
such as customer names, but escaping a number turns a loss (`-50.00`) into text and
silently corrupts the figure that matters most. A plain link would save an error
response as a file. Using the existing read permission avoids inventing a role
during this stage.

**Consequences.** A viewer can export all profitability for the company. That is
consistent with what the same role can already read on screen but is a product
decision worth revisiting; a narrower capability needs a new ADR and a permission
matrix change. The 5000-order cap makes a very broad export a refusal, not a truncated
file.

**Verification.** `test_export_is_operational_authorised_and_formula_safe` (headers,
notice, audit row, other-company export empty, escaping), the pure regression
`test_csv_export_keeps_a_loss_numeric_and_escapes_only_text`, the proxy header test,
the frontend export tests (success, refusal, unreachable API) and the isolated CSV
through the API and the proxy.

---

## ADR-047 — “Unavailable” is a state in the contract and on the screen

**Status:** ACCEPTED · IMPLEMENTED (Stage 5E)

**Decision.** In the API, a missing figure is `null` or `available=false`, never zero,
and a summary metric's `classification` names the metric's kind (it stays, for example,
`COMMITTED` even when there is no figure); `available` and the value lists are the
authority. On the screens, money and percentages are listed one line per currency, a
metric with nothing to show reads “Not available” and wears the `UNAVAILABLE` badge,
and “Actual profit” is always shown as unavailable. Chart series colours are chosen
with the dataviz validator against the real surface, status colours are reserved for
completeness states and always carry a label, and each chart offers a table view.

**Reasoning.** A kind label beside “Not available” reads as a claim the data does not
support; the isolated run on a part-shipped order exposed exactly that. The API label
is useful metadata and changing it is a contract change, so the presentation layer is
the right place to be conservative.

**Consequences.** Clients must read `available`, not the kind label, before showing a
figure. If the API later reports `UNAVAILABLE` itself, the screens need no change.

**Verification.** `intelligence.test.ts` (`metricLines` per currency, unavailable →
no lines), `intelligence.test.tsx` (per-currency card, “Not available” without zero,
no kind badge on a figure-less metric, chart legend and table view), and the isolated
HTTP run on the part-shipped order.

## ADR-048 — A real AI provider is external data processing and must be acknowledged

**Status:** ACCEPTED · IMPLEMENTED (Stage 6)

**Decision.** The AI Office is disabled by default (`TOUCHE_AI_ENABLED=false`). The
only provider that works without any configuration is the offline `mock` provider,
which is deterministic, makes no network call and is refused in `staging` and
`production`. A real provider (`openai_compatible` or `anthropic`) is accepted only
when all of these are set: `TOUCHE_AI_API_KEY` (a `SecretStr`), a base URL (`https`,
or `http` on loopback for a local stub; no embedded credentials, no query string) and
`TOUCHE_AI_EXTERNAL_PROCESSING_ACKNOWLEDGED=true`. The credential lives only in the
server environment; no endpoint returns it, the provider URL or a prompt, and the
status screen says plainly whether answers come from the mock, a live provider or
nothing.

**What leaves the host.** With a real provider, the operator's question, the system
prompt and the *tool results* the model asked for (names, references, amounts and
dates of records the operator may already read) are sent to the provider. Personal
contact data (e-mail, phone, contact name) is not included in any tool result, no
document body or storage key is ever sent, and Finance is never queried by the AI.
What the provider does with the data is governed by the contract the company has with
that provider; Commerce cannot enforce it. The acknowledgement flag exists so an
administrator makes that decision consciously, once, in configuration — not a user
in a browser.

**Reasoning.** Sending commercial data to a third party is a business and legal
decision. Making it an explicit, auditable configuration step (and failing start-up
without it) is cheaper and safer than discovering it later.

**Consequences.** Switching provider needs a restart. A deployment that must keep all
data on premises simply leaves the AI Office disabled or points `openai_compatible`
at a self-hosted endpoint on a trusted network.

**Verification.** `test_ai_providers.py` (`test_unsafe_ai_configuration_is_refused`,
`test_mock_provider_is_refused_in_production`, `test_credentials_never_appear_in_settings_repr`)
and `test_ai_api.py::test_status_never_reveals_a_configured_credential`.

## ADR-049 — The model gets read-only tools that mirror existing reads

**Status:** ACCEPTED · IMPLEMENTED (Stage 6)

**Decision.** The model never touches a service. It names a tool and arguments; a
single executor runs the call. Sixteen tools exist, all `READ_ONLY`, each a thin
wrapper over a service that an existing REST read already uses and requiring the same
permission (`company.view`). The executor, for every call and in this order: refuses
an unknown or blocked name; refuses arguments the provider sent as invalid JSON;
re-reads the caller's **current** membership and refuses a tool the caller no longer
holds; validates arguments against a closed schema (`additionalProperties: false`, so
a `company_id` argument is rejected and flagged, never honoured); runs the handler
with the server-chosen company and user; sanitises untrusted text; bounds the result
size; registers the evidence; and writes a tool-call row and an audit row.

**Reasoning.** Re-using the services keeps one implementation of every rule (RLS, the
company filter, pagination, deterministic pricing and profitability). A closed schema
and a server-chosen company make a prompt-injected "switch to another company" a
no-op by construction. Re-checking the membership per call means a revoked member
loses access in the middle of a conversation.

**Consequences.** A new tool is a code change with a test, not a configuration. There
is deliberately no free-form query tool, no write tool, no network or file tool.
`BLOCKED_ACTIONS` lists what a misbehaving model is most likely to ask for
(`send_email`, `post_journal_entry`, `mark_deal_won`, `approve_payment`,
`execute_sql`, …); such a request is denied, audited as `ai.action.blocked` and shows
as a safety flag on the run.

**Verification.** `test_ai_units.py` (registry, validation, executor refusals),
`test_ai_api.py` (blocked actions change nothing, company id rejected, other-company
ids → `NOT_FOUND`, revoked membership → `PERMISSION_DENIED`).

## ADR-050 — Every claim is checked against evidence the tools returned

**Status:** ACCEPTED · IMPLEMENTED (Stage 6)

**Decision.** Tools return *evidence items* (entity, human reference, timestamp,
completeness and the exact key facts as strings). The server assigns the ids
(`E1`, `E2` …) and computes every link; the model only cites ids. The model's answer
is one JSON object that the server parses and validates:

* an unknown evidence id is removed;
* a claim can never be stronger than its weakest cited source (`CONFIRMED_SOURCE` →
  `ESTIMATED` → `INCOMPLETE`), and a claim with no real source becomes `AI_INFERENCE`;
* a figure survives only if its exact value is among the cited evidence's facts;
* a number in prose or in a draft that appears in no tool result of the run marks the
  text `UNVERIFIED_NUMBER` (small counts and years are exempt);
* a task target must be a record a tool returned.

The five bases are `CONFIRMED_SOURCE`, `ESTIMATED`, `INCOMPLETE`, `AI_INFERENCE` and
`NOT_AVAILABLE`. Profitability is never `CONFIRMED_SOURCE`: it is `ESTIMATED` when the
analysis is complete and `INCOMPLETE` otherwise, because Commerce has no actual profit
(ADR-045). A reply that is not valid JSON is kept but labelled
`RESPONSE_NOT_STRUCTURED`, with no citations.

**Reasoning.** A model may hallucinate a number or a citation whatever the prompt
says. Validating on the server makes traceability a property of the system, not of
the provider, and it works the same for the mock and any real model.

**Consequences.** The checker can be too strict: a correct number written in a unit
the tool did not use (for example a percentage the model derived) is flagged, which is
the intended bias. Language is not constrained; numbers are.

**Verification.** `test_ai_units.py` (basis downgrade, unknown citations, figures,
prose numbers, task targets) and `test_ai_api.py::test_invented_evidence_and_numbers_are_removed_or_downgraded`.

## ADR-051 — The AI proposes; only a person approves, and approval executes nothing risky

**Status:** ACCEPTED · IMPLEMENTED (Stage 6)

**Decision.** Four classes: `READ_ONLY` (the tools), `DRAFT_PROPOSAL` (a written draft),
`REQUIRES_HUMAN_APPROVAL` (a suggested operator task) and `BLOCKED` (never available:
accounting postings, bank payments, contract signature, financial approval,
unapproved customer communication, arbitrary deletion, marking a deal WON, accepting a
customer quote). Only two executors exist. Approving a draft records that a person
reviewed the wording (`sent=false`); approving a task records the follow-up for the
team. Neither sends, signs, pays, posts, accepts or changes a deal, order or
shipment. The database CHECK constraint on `action_type` allows only those two values.

Editing and deciding need `trade.write` (a role without it can read proposals and
cannot edit, approve or reject). At approval the backend re-validates: the live
membership and permission, that the proposal is still pending, the `If-Match` version,
and that the target record still exists in the company. A proposal whose text carries
`UNVERIFIED_NUMBER` additionally needs an explicit `acknowledge_warnings`. Edits change
wording only; the target and the cited evidence cannot be redirected.

**Reasoning.** The value of the AI is analysis and drafting. The first risky action it
could take should still be a human's click, and the system should make a wrong click
low-impact. Separating "a person approved this wording" from "a message was sent" keeps
the audit trail honest until a real, separately-reviewed send integration exists.

**Consequences.** There is no outbound channel in Stage 6; a draft must be copied by a
person. A later stage that adds one needs its own ADR, its own permission and its own
executor — it cannot be reached by editing a proposal.

**Verification.** `test_ai_api.py` (edit/approve flow with `If-Match`, viewer cannot
decide, second person can review, target revalidation, unsupported action,
business-table row counts unchanged) and the isolated HTTP acceptance.

## ADR-052 — Stored text is untrusted data

**Status:** ACCEPTED · IMPLEMENTED (Stage 6)

**Decision.** Free text from the database (names, notes, descriptions, delay reasons,
document titles) reaches the model only through a sanitiser: control, zero-width and
bidirectional-override characters are removed, the length is bounded, and text that
reads like an instruction to an AI (override/ignore-instructions phrasing, role or
chat-template markers, tool or `company_id` directives, requests for secrets, data
exfiltration URLs) is **withheld** and replaced by a neutral marker; the run records
`INJECTION:<kind>` safety flags. An action word near a business noun ("send the
invoice") is flagged but kept, because it is ordinary in trade notes and the model
cannot act on it anyway. The system prompt repeats the rule, but nothing depends on
the model obeying it: the tool set, the server-chosen company, the permission
re-check and the response validator are the controls.

**Reasoning.** Anyone who can write a note, a counterparty name or an uploaded document
title can try to steer an assistant that reads it. Withholding the text costs the
operator one click to the record and removes the attack surface.

**Consequences.** A legitimate note that happens to read like an instruction is
withheld from the assistant (the record itself is unchanged and linked). Detection is
pattern-based and will miss a novel phrasing; that is why it is only one layer.

**Verification.** `test_ai_units.py` (parametrised hostile and ordinary text, hidden
characters), `test_ai_api.py::test_instructions_stored_in_records_are_withheld_and_cannot_widen_authority`
and the isolated acceptance (hostile deal note).

## ADR-053 — Runs are bounded, asynchronous and cancellable

**Status:** ACCEPTED · IMPLEMENTED (Stage 6)

**Decision.** A question returns `202` with a run id; the model loop runs in a
background task and the client polls `GET /ai/runs/{id}` for tool progress and the
validated answer. Limits (all configurable, all reported by `/ai/status`): model steps
(6), tool calls per request (10; once spent the model is called without tools and must
answer), output tokens, total tokens per request (cumulative across steps), wall-clock
deadline (120 s), tool-result size, user-message size, concurrent runs (4), runs per
user per minute (6), and a daily token and cost budget per company. Provider calls
have a timeout and at most two retries with backoff, only for retryable errors
(unavailable, timeout, rate limit — honouring `Retry-After`, capped). Cancellation is
cooperative and checked before every model call, tool call and backoff wait. Usage is
recorded per run; when a provider omits it, the gateway estimates and flags the run
`estimated_usage`. Prompts, tool results and credentials are never logged; the run row
holds counters, the prompt version, validation warnings and safety flags only.

**Reasoning.** A model loop is the one place a request can run away, cost money or hold
a worker. Every dimension needs a hard ceiling that does not depend on the model.

**Consequences.** The cancellation registry and the concurrency limiter are
per-process; with more than one API process a cancel request must reach the process
running the job (a run that never finishes is marked failed after the deadline plus a
minute). Cost uses configured per-million-token prices, which default to zero, so a
cost budget is only meaningful once prices are set.

**Verification.** `test_ai_providers.py` (retry bounds, `Retry-After`, cancel during
backoff, budget before any data leaves) and `test_ai_api.py` (tool-call, step, token,
size, daily, rate and concurrency limits; outage, auth failure, timeout; deadline;
cancellation).

---

## ADR-054 — Communications permission and draft-only boundary

**Status:** ACCEPTED · PARTIALLY IMPLEMENTED (Stage 7A; regression pending)

**Decision.** A dedicated `communications.send` permission is introduced and is
not granted to any current role. Stage 7A exposes only `GET` endpoints for
channel status and existing AI Office draft proposals, using the signed-in
active company and RLS. Both EMAIL and WHATSAPP_BUSINESS report
`NOT_CONFIGURED`. No outbound transport or send route exists.

**Reason.** Stage 6 draft approval means a human reviewed content; it is not
consent to dispatch. An AI agent must never acquire outbound rights by being
able to suggest or approve a proposal. Keeping delivery unavailable removes
the risk of accidental customer commitments while the later provider-specific
authorization and audit model is designed.

**Future preconditions.** Explicit recipient and channel verification,
separate reviewer and sender permissions, a bounded idempotent outbox,
operator-approved send intent tied to a draft version, webhook authenticity,
delivery status reconciliation, rate limits, data minimization, and per-tenant
provider credentials. Every actual send must be audited and tested with an
isolated provider stub before any real destination is enabled.

**Verification.** Stage 7A GitHub Actions run 40016540897 passed: 555 backend,
192 frontend and OpenAPI drift checks. PR #1 merged at 1db9b73. Isolated Windows
browser acceptance remains open.


---

## ADR-055 — Preflight is not authority to deliver

**Status:** ACCEPTED · IMPLEMENTED AND CI VERIFIED (Stage 7B)

**Decision.** Recipient readiness checking must be a bounded, authenticated
and CSRF-protected request. The active company comes only from the server
session. It references an existing AI DRAFT proposal by ID and version,
validates approval and recipient format, and returns reason codes only.
No recipient, provider credentials or message body is emitted in the response,
written to the ledger, attached to audit events or sent to an external network.

**Hard safety rule.** All preflight results have `sendable=false`. No role
currently receives `communications.send`; provider channels remain
`NOT_CONFIGURED`. An AI draft review or a preflight result alone never gives
delivery rights. A later send executor requires a separate ADR and migration.

**Verification.** GitHub Actions run `40019149502` passed 558 backend and
192 frontend tests with clean OpenAPI. A missing CSRF dependency was found
by the new negative test and corrected in `e160815`. PR #2 merged at
`1140b06`. No live provider or Windows browser verification was performed.


---

## ADR-056 — CRM provenance must not be treated as consent

**Status:** ACCEPTED · STAGE 7C1 IMPLEMENTED / CI VERIFIED

**Decision:** A communication preflight can reference an existing CRM
counterparty ID, but the server obtains its company from the authenticated
session and applies tenant RLS before reading the contact point. A casefolded
email or exact E.164 phone match only establishes **CRM source consistency**.
A missing, archived, cross-company, or mismatched record is reported through
a generic blocker, not through the recipient address or record details.

**No consent claim:** CRM existence and an AI draft approval do not prove the
recipient has agreed to communication or controls that contact point.
`CONSENT_UNDOCUMENTED` is always returned while no separately auditable
channel-specific consent system exists. Independent opt-outs, provider auth,
approved send intent and delivery remain unimplemented.

**Safety:** No recipient address stored, logged, or echoed by preflight.
No transport, token, webhooks, sending or financial writes. No changes to
`communications.send` role assignments.

**Verification:** GitHub CI run `40021727161` PASSED (561 backend,
192 frontend, OpenAPI). Regex regression fixed in `ac3c4ad`; PR #3 merged
at `7624c33`. Local Windows browser, provider and real consent verification
remain outstanding.


---

## ADR-057 — Contact suppression is append-only and independent of consent

**Status:** ACCEPTED / Stage 7C2 CI VERIFIED

Outbound communication risk must be reducible independently of any future
approval or provider connection. Commerce stores a permanent per-company CRM
contact/channel block in `communication_suppression`, without addresses,
message bodies or provider tokens. Its RLS and composite FK prevent tenant
cross-linking. The application grants INSERT+SELECT only and cannot lift a
suppression; duplicate commands preserve the first row. All successful
new blocks are audited within the same idempotent transaction, including the
actor and reason but no direct contact data.

`communications.suppress` is available to an authenticated company admin
only; `communications.send` stays unassigned. A suppressed contact produces
an additional preflight blocker. CRM provenance and suppression never assert
opt-in, independent ownership or legal basis; explicit consent evidence and
compliant suppression lifting require separate ADRs, tests and controls.
Real provider connections and live sending remain disabled.

**Validation:** GitHub Actions `40025166931` PASSED (565 backend,
192 frontend and OpenAPI drift). PR #4 merged into main at `5bc7bdc`.
No browser, live provider, legal consent or outbound delivery was verified.


---

## ADR-058 — E-YAY context cannot cross execution boundaries

**Status:** ACCEPTED · STAGE 8 DEVELOPMENT IN PROGRESS.

E-YAY's canonical source OpenAPI exposes health and regime-context views.
Commerce may read only two concrete GET endpoints over numeric loopback;
never scrape, proxy paper positions, trade execution, news body, or internal
provider credentials. Reject untrusted hosts, redirect responses, unsafe source
mode, stale timestamps and malformed numeric data. Display explicit snapshot
provenance. Server-side disabled by default. No automatic trading, actual P&L,
financial posts, user positions, RFQ/order changes, or AI action rights result.

The E-YAY connector's existence is not proof of a running source or accurate
forecasts. CI fixture tests and an isolated real-HTTP check are distinct gates.

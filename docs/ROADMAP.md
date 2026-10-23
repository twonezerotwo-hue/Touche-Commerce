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

**Status: sourcing, pricing and sales quotes delivered (2026-10-22); logistics
and document generation remain.**

**Goal:** the day-to-day trading workflow.

Work: accounts/contacts, RFQ intake, quotation versioning, product catalogue,
price lists, shipments and milestones, document generation. Quotes and orders
reuse the Decimal/currency/FX rules and the audit/idempotency conventions.

**Delivered in this stage:**
RFQ per supplier with prepared snapshots and dispatch evidence; supplier quote
recording, superseding revisions and withdrawals; explicit FX snapshots; a
deterministic landed-cost engine (pro-rata/line allocation, margin or markup) whose
inputs and results are stored; sales quotes with a submit → approve/reject
workflow, segregation of duties and immutable revisions.

**Exit criteria:** quote → order traceability with immutable revisions; every
state change audited; list endpoints paginated and permission-filtered.

Traceability now holds end to end: RFQ → supplier quote → pricing scenario →
sales quote revision → customer acceptance → sales order → purchase order →
shipment → delivery evidence → trade documents.

**Remaining from the original Stage 3 list that Stage 4 absorbed:** shipments
and milestones, trade document storage/versions, and honest draft previews —
delivered in Stage 4 (§22 of PROGRESS.md). Contact-level CRM and price lists
remain deferred.


---

## Stage 4 — Sales orders, procurement, logistics and documents ✅ (implemented and verified locally)

**Status: delivered 2026-10-22.** Evidence is in PROGRESS.md §22.

**Goal:** turn an approved quote and a documented customer acceptance into real
order execution.

**Delivered:**

* **4A** customer acceptance evidence; the only `WON` path is a single atomic
  conversion transaction that creates the order and its frozen lines; idempotent
  replay; `ALREADY_WON`; one initial order per deal enforced in the database;
  cancellation and amendments preserve the accepted snapshot.
* **4B** supplier purchase orders that are optional for brokerage, approved with
  `finance.approve` by a second person, and never treated as sent without a
  recorded channel, timestamp and external reference; supplier confirmation
  carries its own evidence.
* **4C** multiple shipments per order, partial allocation with decimal
  quantities, over-allocation refusal, evidence-gated dispatch/arrival/delivery,
  timeline events, references, logistics costs with explicit provenance and
  fulfilment derived from delivered quantities.
* **4D** private document storage with server-generated keys, SHA-256, streaming
  size limits, version history, archive-not-delete, two-layer authorisation, and
  DRAFT-labelled invoice/packing-list previews.
* **4E** the eight execution screens, the deal conversion panel, real dashboard
  counters, execution navigation and OpenAPI-generated types.

**Explicitly out of scope and not implemented:** accounting entries, invoices as
postings, payments, Touche Finance synchronisation, e-YAY, automated
email/WhatsApp sending and live carrier tracking.

**Exit criteria:** met — see PROGRESS.md §22.6 (284 backend tests, 88 frontend
tests, production build) and §22.7 (45/45 live checks). The flow never invents
a dispatch, arrival or delivery; every one requires recorded evidence.

---

## Stage 5 — Finance integration (read-only first) 🟡

**Goal:** connect Commerce's commercial execution to TOUCHE FINANCE without
creating a second accounting engine. Finance remains the financial source of
truth; Commerce remains the commercial operational source of truth (ADR-038).

### Stage 5A — discovery and read-only boundary ✅ (implemented 2026-10-22)

**Delivered:**

* Read-only inspection of the live Finance tree (`C:\ai-excel`, `main`,
  `8dce8245`), SQLite ledger and Excel workbook, with unchanged hashes.
* Concrete Commerce → Finance mapping and exact missing-interface list
  (`docs/STAGE5_FINANCE_DISCOVERY.md`).
* Loopback-only, disabled-by-default `GET /api/health` probe.
* `GET /api/v1/integrations/finance/status` with
  `scope="health_only"` and `accounting_writes_enabled=false`.
* `scripts/verify-finance-readonly.ps1` executable evidence; no Finance process
  was started and no DB/workbook byte changed.
* ADR-038/039/040.

### Stage 5B — Finance read-only data contract ✅ (implemented in Finance 2026-10-22)

Finance branch `feat/finance-integration-v1` at
`107c30e2ae4b5e4c22891f01ca730d3284994de5` exposes authenticated read-only
`/api/integration/v1/health`, `/capabilities`, `/companies`,
`/companies/{id}/summary`, `/companies/{id}/accounts` and
`/companies/{id}/aging`. Dedicated key/secret authentication, explicit company
allow-lists, per-currency reads, append-only audit and `mode=ro` SQLite were
verified in Finance. Invoices, payments, counterparty/project masters and report
allow-lists are not implemented.

### Stage 5C — real read-only Commerce connector ✅ (implemented 2026-10-22)

**Delivered:** tenant-scoped explicit mapping (migration `0008_finance_mapping`),
server-side service credentials, loopback HTTP client with bounded responses and
no redirects, normalized error categories, `finance.read` audit rows, five
`/api/v1/finance/*` endpoints and a premium `/finance` Overview/Accounts/AR/AP
workspace. The connector is disabled by default and has no write path.

**Verification:** backend `355 passed` (including 20 connector tests and 18 API
tests); frontend `96 passed` across 17 files; real isolated HTTP acceptance
`ISOLATED_HTTP_VERIFIED` with synthetic Finance data, temporary credentials,
cross-tenant refusal and unchanged Finance hashes. See
`docs/FINANCE_INTEGRATION_CONTRACT.md` and `docs/PROGRESS.md` §23.

**Explicitly not implemented:** invoices, payments, bank transfers, journal
writes, draft commercial events, AI Trade Director, Gmail/WhatsApp automation and
E-YAY integration. Finance remains the financial source of truth.

### Stage 5D — evidence-based financial reconciliation ✅ (implemented 2026-10-22)

**Delivered:** migration `0009_reconciliation` with tenant-scoped runs, Finance
source references, explicit evidence links, deterministic discrepancies and
append-only reviews; Decimal analysis of accepted value, purchase commitments,
estimated landed cost, recorded operational costs, variance and
commitment-based margin; `finance.reconcile` reviewer permission; ten versioned
reconciliation/evidence/review/order-finance endpoints; and premium
`/finance/reconciliation`, `/finance/discrepancies` and
`/finance/orders/[id]` screens.

**Verification:** backend `379 passed`, frontend `102 passed` across 18 files,
isolated HTTP `ISOLATED_HTTP_VERIFIED` with a real accepted Stage 3/4 order,
exact USD evidence `F-USD-AR-1`, unauthorized-review refusal, reviewer
verification, unlinked-run refusal, cross-tenant isolation and unchanged Finance
hashes. See `docs/STAGE5D_RECONCILIATION.md`.

**Explicitly not implemented:** Finance writes, invoices, payments, bank
transfers, automatic journals, AI Trade Director, Gmail/WhatsApp automation and
E-YAY integration.

### Stage 5E — read-only financial intelligence ✅ (implemented 2026-10-23)

**Delivered:** a pure profitability engine (`stage5e-1.0.0`) that keeps an
`ESTIMATED` basis (accepted value minus the Stage 3 landed-cost scenario, recoverable
VAT excluded) apart from a `COMMITTED`/`DOCUMENTED` basis (committed purchase orders
plus `INCURRED`/`DOCUMENTED` shipment costs); seven read-only
`/api/v1/finance/intelligence/*` endpoints (summary, orders, order drill-down, cost
variance, coverage, exceptions, CSV export) behind `company.view`; and four premium
screens — `/finance/intelligence`, `/finance/intelligence/orders`,
`/finance/intelligence/orders/[id]`, `/finance/intelligence/exceptions` — with five
per-currency charts and an audited, formula-safe CSV export. No migration, no
Finance call and no `actual_profit` field exist.

**Verification:** backend `402 passed`, frontend `160 passed` across 22 files,
`ISOLATED_HTTP_VERIFIED` over a real accepted order (estimated profit `50.00` at
`20.00%`, committed profit withheld while the order is part-shipped, exception
resolution gated by `finance.reconcile`, CSV through the proxy, cross-tenant
isolation, unchanged live Finance hashes). See `docs/PROGRESS.md` §26.

**Explicitly not implemented:** actual profit, document-supported margin, saved or
scheduled reports, Finance writes, invoices, payments, journals, AI Trade Director,
Gmail/WhatsApp automation and E-YAY integration. A real-browser review at four widths
found and fixed layout, label and cosmetic defects (PROGRESS §26.5); a few minor items
remain (§26.6) and tablet width and a full accessibility audit were not run.

### Next safe milestone (not started)

Any further work must remain read-only unless separately authorised. A live
Finance read verification requires an approved startup plan that accepts or
isolates Finance's startup-recovery writes. Remote deployment needs a TLS reverse
proxy, Windows ACL review and key distribution (new ADR).

---

## Stage 6 — AI Trade Director ✅ (implemented 2026-10-23)

**Goal:** an assistant that works strictly inside the rules — it reads, explains,
cites and proposes; a person decides.

**Delivered (branch `stage-6`, migration `0010_ai_office`):**

* **6A — AI architecture.** A provider-independent gateway (`mock`, OpenAI-compatible,
  Anthropic) with server-side credentials, structured tool calling, validated structured
  answers, timeouts, bounded retries, token/step/tool budgets, concurrency and rate
  limits, cancellation, versioned prompts and usage logging. External data processing
  needs an explicit acknowledgement (ADR-048).
* **6B — Safe business tools.** Sixteen `READ_ONLY` tools over the existing services
  (deals, counterparties, products, supplier quotes and comparison, pricing scenarios,
  orders, purchase commitments, shipments, document metadata, profitability, Finance
  reconciliation view, discrepancies). Each re-checks the live membership and
  permission, validates a closed schema, bounds its result and is audited (ADR-049).
* **6C — Trade Director.** A bounded loop whose answers are validated against the
  evidence the tools returned: five bases, server-computed links, no invented
  citations or figures (ADR-050).
* **6D — Human approval.** `READ_ONLY` / `DRAFT_PROPOSAL` / `REQUIRES_HUMAN_APPROVAL` /
  `BLOCKED`. Only a draft review and a suggested task can be approved; approval records
  a decision and nothing else (ADR-051).
* **6E — AI Office UI** at `/ai`.
* **6F — Security and reliability.** Stored text is untrusted (ADR-052); resource
  limits, cancellation and failure handling (ADR-053); no prompt, result or credential
  in a log or audit row.
* **6G/6H — Tests and acceptance.** See `docs/PROGRESS.md` §27.
* **6I — Interface debt.** AA muted text, single navigation highlight, current footer,
  no box-in-box empty tables, no horizontal overflow at 768 px.

**Provider status:** `MOCK_PROVIDER_VERIFIED`; `REAL_PROVIDER_BLOCKED` — no AI credential
is configured for Commerce, so no live provider call has been made. The OpenAI-compatible
and Anthropic adapters are verified against local stubs of their documented wire
formats.

**Explicitly not implemented:** Gmail and WhatsApp connectors, e-mail or message
sending, E-YAY, web crawling, accounting writes, bank payments, contract signature and
any commitment made on a person's behalf.

**Exit criteria met:** negative tests prove the assistant cannot approve finance, read
another company's data, widen its authority from text stored in a record, or bypass the
audit trail; no prompt text or secret appears in a log.

### Next safe milestone (not started)

Any real-provider rollout starts with an explicit credential and data-processing
decision (ADR-048) and a live provider check. Outbound messaging (Gmail/WhatsApp) is a
separate stage with its own permission, ADR and executor; it must not be reachable by
editing an AI proposal.

---

## Stage 7 — Messaging and external connectors (Stage 7A/7B/7C1 merged; providers not connected)

**Stage 7A (initial GitHub code, verification pending):** a company-scoped
communications view of existing AI drafts, a status API that reports unconfigured
email/WhatsApp channels, and an unassigned `communications.send` permission.
There is no outbound transport or credential and no claim of verified delivery.

**Next after validation:** real provider authentication, webhook verification,
distinct operator send authorization, explicit human approval, auditable idempotent
outbox, delivery status callbacks and tenant-safe message threading. Gmail/WhatsApp
connections must each be tested independently. No AI proposal may dispatch by itself.

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


### Stage 7B — Safe recipient preflight (CI verified)

A bounded POST endpoint checks an operator-entered recipient, the latest reviewed
AI draft and selected channel, without retaining the address. It returns exact
blockers and can **never** authorize or perform sending. User interface shows
preflight status but no send button. Full delivery remains a separately-approved
future milestone and requires provider accounts and secure token provisioning.


### Stage 7C — Provider authentication and consent (7C1 CI verified; provider work pending)

Per-company Gmail and WhatsApp Business account connections, secure secret
storage, recipient provenance and consent, scoped send approval distinct from
AI draft review, explicit outbound transport with idempotent outbox and audited
delivery evidence. No provider is configured and sending stays disabled.


#### Stage 7C1 — CRM recipient matching (CI verified, PR #3 merged)

Preflight requires a current active-company CRM counterparty match to identify
the **source record** for the operator-entered address/number. This is not proof
of contact ownership or permission to send. Both channels still report
NOT_CONFIGURED, `CONSENT_UNDOCUMENTED` is unavoidable, and sending is disabled.
Provider authorization and structured consent history belong to later Stage
7C milestones, each requiring independent security/production validation.


#### Stage 7C2 — Suppression ledger (CI verified, PR #4 merged)

Introduce an immutable, audited do-not-contact ledger: an administrator can
block an existing company's CRM contact on either channel without adding
recipient PII. Existing preflight always refuses delivery and now also
reports an explicit suppression blocker. Opt-in evidence, suppression
lifting procedures, provider auth, transport, webhooks and human-approved
outbound messages are **not** implemented in Stage 7C2.


### Stage 7C3 — provider prerequisites contract (CI pending)
The authenticated `GET /api/v1/communications/provider-requirements` exposes
Gmail API and Meta WhatsApp Cloud API prerequisites, explicit need for verified
consent and independent send approval, and an unconfigured status. There is no
credential store or OAuth flow in Stage 7C3; channel transport stays disabled.

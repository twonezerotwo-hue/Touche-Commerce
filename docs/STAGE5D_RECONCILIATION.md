# Stage 5D — evidence-based financial reconciliation

**Status:** implemented and verified locally on branch `stage-5d`
**Base:** `stage-5c` HEAD `3e35ef112b8486fee8e34218cd7a4fdd3aa5d8d4`
**Commerce migration:** `0009_reconciliation`
**Verified Finance revision:** `feat/finance-integration-v1` at `107c30e08375c132bad90a9f5dcf867550c38c37`
**Verification level:** `ISOLATED_HTTP_VERIFIED`
**Accounting writes:** none, in either direction.

---

## 1. Boundary

Stage 5D does **not** turn Commerce into an accounting system. It compares:

* Commerce commercial facts: accepted sales order, committed purchase orders,
  Stage 3 landed-cost estimate, Stage 4 shipment costs;
* Finance observations: per-currency summary and FIFO aging source ids read
  through the Stage 5C connector.

Finance remains the only source of journals, invoices, payments, account
balances and ledger aging. Commerce never converts currencies, posts a journal,
creates an invoice or records a payment. Reconciliation records are evidence,
not accounting entries.

Finance still exposes no structured invoice, payment, project-master,
counterparty-master or report endpoints. Commerce does not invent them.

---

## 2. Domain model

| Table | Purpose | Runtime privilege |
| ----- | ------- | ----------------- |
| `finance_reconciliation_run` | reproducible per-order snapshot | SELECT, INSERT, UPDATE |
| `finance_source_reference` | stable Finance source ids/observations | SELECT, INSERT |
| `finance_reconciliation_evidence` | explicit Commerce → Finance links | SELECT, INSERT, UPDATE only verification columns |
| `finance_discrepancy` | deterministic exceptions, resolution | SELECT, INSERT, UPDATE |
| `finance_reconciliation_review` | append-only human decisions | SELECT, INSERT |

All five tables carry `company_id`, use RLS with
`touche.current_company_id()`, and use composite `(id, company_id)` foreign keys.
No runtime role receives `DELETE`. The migration explicitly revokes broad
default privileges before granting the least-privilege set.

A run stores Commerce order/currency/as-of, Finance mapping/currency/watermark,
commercial facts and classifications, calculation version `stage5d-1.0.0`, a
content hash per Finance source reference, and evidence/discrepancies/reviews as
child records. One Finance company mapping still applies per Commerce company.
A new run may be created for later source data; a verified run is immutable.

---

## 3. Reconciliation state model

| State | Meaning |
| ----- | ------- |
| `INCOMPLETE` | required Commerce evidence is missing, stale or inconsistent |
| `UNMATCHED` | Commerce evidence is complete but no explicit Finance source is linked |
| `POTENTIAL_MATCH` | an explicit link exists but a blocking amount/currency check fails |
| `MATCHED_EVIDENCE` | a supported Finance source id is linked and amount/currency checks pass |
| `VERIFIED` | an authorised reviewer confirmed the evidence |
| `DISPUTED` | a reviewer disputed the run or its evidence |

* New run → `INCOMPLETE` or `UNMATCHED` only.
* Exact evidence on a complete run → `MATCHED_EVIDENCE`.
* Mismatched evidence → `POTENTIAL_MATCH`.
* `CONFIRM` only from `MATCHED_EVIDENCE`, with a sales-order link, no open
  blocking discrepancy and a reviewer different from the creator.
* `CONFIRM` → `VERIFIED`, marking evidence verified.
* `DISPUTE` → `DISPUTED`; `REQUEST_CHANGES` keeps the current status.
* `VERIFIED` is immutable in the API; a later review needs a new run.
* `INCOMPLETE`, `UNMATCHED` and `POTENTIAL_MATCH` can never be verified.

The separate permission `finance.reconcile` is required for reviews and
discrepancy resolution. It is granted to `approver` only; `admin` never inherits
it.

---

## 4. Deterministic analysis

Values are `Decimal` end to end and serialized as decimal strings.

| Figure | Classification | Rule |
| ------ | -------------- | ---- |
| Accepted sales order value | `DOCUMENTED` | frozen `sales_order.order_total` |
| Purchase commitments | `COMMITTED` | approved/recorded/confirmed/in-fulfilment/received POs; drafts excluded |
| Estimated landed cost | `ESTIMATED` | same-currency Stage 3 `landed_total` |
| Recorded operational costs | `DOCUMENTED` | same-currency shipment costs; missing costs make the total unavailable |
| Estimate vs recorded variance | `ESTIMATED` | estimate − recorded costs, only when both exist |
| Commitment-based margin | `COMMITTED` | accepted − commitments − recorded costs; never actual profit |
| Document-supported margin | `UNAVAILABLE` | no transaction-level Finance invoice/payment/cost source |
| Actual profit | `UNAVAILABLE` | deliberately not modelled |
| Finance company summary | `FINANCE_OBSERVED` | company-wide, never attributed to an order |

`TRY`/`TL` is a **code alias only**. No amount is converted. Other currency
codes must match exactly. Mixed currencies produce `CURRENCY_MISMATCH` and the
affected total becomes unavailable rather than a partial sum.

Completeness checks are explicit: accepted order, same-currency pricing
estimate, purchase commitment (unless brokerage), operational costs and currency
consistency. A score below 100 keeps the run `INCOMPLETE`. Analysis covers
partial shipments, multiple purchase orders, missing freight, brokerage,
cancellations and incomplete cost allocation. VAT is not assumed to be an
expense. No historical FX conversion is invented.

---

## 5. Evidence rules

Only stable Finance aging source ids are linkable: `AGING_RECEIVABLE` and
`AGING_PAYABLE`. `SUMMARY` and `ACCOUNT` observations are company-wide and are
explicitly non-matchable. Counterparty names (`ledger.cari`) are display context
only and are never matching keys.

An evidence link must belong to the same tenant/run, target a transaction-level
source id, use the run currency, take its amount from Finance (never the request
body), be unique per source id in the run, compare exactly with the Commerce
source amount, and record provenance/expected/observed values/operator.

A mismatch remains `POTENTIAL_MATCH` with a blocking `AMOUNT_MISMATCH` and cannot
be verified. Resolving a discrepancy does not rewrite Finance and does not
auto-promote a run.

---

## 6. Discrepancy categories

`MISSING_EVIDENCE`, `MISSING_FINANCE_REFERENCE`, `AMOUNT_MISMATCH`,
`CURRENCY_MISMATCH`, `DUPLICATE_REFERENCE`, `INCOMPLETE_COSTS`,
`UNMATCHED_FINANCE_ITEM`, `SOURCE_STALE`, `COMPANY_MAPPING_INVALID`,
`MANUAL_REVIEW_REQUIRED`.

A missing order-level Finance reference is described as an unavailable
capability, not proof that a real invoice is missing. Company-wide aging items
are never declared unmatched to a specific order.

---

## 7. API contract

All endpoints require an authenticated Commerce session and active company.
Reads require `company.view`; run/evidence creation requires `trade.write`;
review and resolution require `finance.reconcile`. Mutating calls require CSRF,
`Idempotency-Key`, and `If-Match` where they change an existing run or
discrepancy.

| Method | Path | Purpose |
| ------ | ---- | ------- |
| `GET` | `/api/v1/finance/reconciliation` | runs, status counts, open/blocking counts |
| `POST` | `/api/v1/finance/reconciliation/runs` | create snapshot |
| `GET` | `/api/v1/finance/reconciliation/runs/{id}` | run with evidence, findings and reviews |
| `GET` | `/api/v1/finance/evidence-links?run_id=` | explicit links |
| `POST` | `/api/v1/finance/evidence-links` | link source id to Commerce entity |
| `GET` | `/api/v1/finance/discrepancies` | filterable exception queue |
| `GET` | `/api/v1/finance/discrepancies/{id}` | one discrepancy |
| `POST` | `/api/v1/finance/discrepancies/{id}/resolve` | reviewer resolution note |
| `POST` | `/api/v1/finance/reviews` | CONFIRM / DISPUTE / REQUEST_CHANGES |
| `GET` | `/api/v1/finance/orders/{id}` | order finance view |

New error codes: `RECONCILIATION_CURRENCY_MISMATCH`,
`RECONCILIATION_EVIDENCE_INVALID`, `RECONCILIATION_EVIDENCE_DUPLICATE`,
`RECONCILIATION_SOURCE_NOT_MATCHABLE`, `RECONCILIATION_NOT_VERIFIABLE`,
`RECONCILIATION_STATE_INVALID`.

Every response declares `read_only=true` and
`accounting_writes_enabled=false`. No endpoint writes to Finance.

---

## 8. Frontend

Premium dark screens:

* `/finance/reconciliation` — financial overview, connection state, data-through,
  completeness, open discrepancies, runs, explicit currency selector, create-run
  form.
* `/finance/reconciliation/[id]` — snapshot metrics, classifications, Finance
  observations, source references, evidence links, discrepancy resolution,
  review form and review timeline.
* `/finance/discrepancies` — deterministic exception queue with filters and
  reviewer-only resolution.
* `/finance/orders/[id]` — accepted order, purchase commitments, Stage 4 costs,
  estimate, margins, evidence gaps and latest run.

The UI reuses existing design tokens/components and generated OpenAPI types.
Unavailable metrics are labelled **Not available**; no invoice, payment,
recognized revenue, actual profit or net profit is shown.

---

## 9. Migration and security

Migration `0009_reconciliation`:

* creates the five tables and indexes;
* enables RLS and tenant policies;
* grants only the intended runtime operations;
* revokes broad default grants on these tables;
* widens the audit-action allow-list with
  `finance.reconciliation_run.created`, `finance.evidence.linked`,
  `finance.discrepancy.resolved`, `finance.reconciliation.reviewed`.

Audit rows record actor, company, resource, status, amount match and Finance
request ids but never credentials. `finance.read` is also written when a run
snapshots Finance.

`alembic check` shows only the pre-existing unrelated drift
(`public.alembic_version`, comments on three Stage 1 tenant tables); the Stage 5D
tables themselves have no drift.

---

## 10. Verification

**Backend:** `379 passed` / 0 failed / 0 skipped. This includes 12 pure Decimal
calculation tests and 12 API integration tests for missing mapping, currency,
RLS, evidence, review permissions, amount mismatch, duplicate references,
idempotency, optimistic concurrency, cross-tenant invisibility, audit and
runtime grants.

**Frontend:** `102 passed` / 18 files, including 6 Stage 5D component tests.
`typecheck`, ESLint, Prettier and `next build` pass.

**Isolated HTTP acceptance:** `ISOLATED_HTTP_VERIFIED`.

The extended `backend/scripts/verify_finance_http.py` creates a synthetic Finance
ledger including a USD receivable of `250.00`, starts Finance on `127.0.0.1:8877`,
seeds isolated Commerce users (admin, trader, approver), and builds a real
accepted order through the Stage 3/4 HTTP APIs. It verified:

* accepted order value `250.00`, PO commitment, estimate and recorded cost;
* Finance source id `F-USD-AR-1`, amount `250.00`, currency `USD`;
* new run `UNMATCHED`;
* exact evidence link → `MATCHED_EVIDENCE`;
* unauthorized review → `FORBIDDEN`;
* authorised reviewer → `VERIFIED`;
* unlinked run cannot verify (`RECONCILIATION_NOT_VERIFIABLE`);
* all four Stage 5D frontend routes render;
* cross-tenant run access returns `404` and list is empty;
* Finance ledger write-shaped route returns `405`;
* no credentials in responses;
* synthetic Finance DB and workbook hashes unchanged.

The live Finance application was not started. Live source hashes remain:

```text
C:\ai-excel\veri\finans.db
C9BA0EB7EC82F1DE50105F1E0019CA695B48843319B7E1D2184296632EF52BE1

C:\Users\twone\OneDrive\Desktop\Touche\Touche Holding - AI Ready Finans Yönetim Sistemi.xlsx
E03740DA624522EA9AC4869D3ADDDFB008C96DC7D2A78759CE760D810B0FA51E
```

---

## 11. Honest limitations

* Verification is **isolated**, not live. No live Finance server or live
  credential was used.
* Finance exposes no invoice/payment/counterparty/project/report objects.
* Document-supported margin and actual profit remain unavailable.
* One Finance company per Commerce company.
* Remote/TLS/mTLS, Windows ACL proof and HSM/KMS are not verified.
* There is no automatic journal, invoice, payment or settlement.
* No real production mapping has been configured in this environment.
* `alembic check` retains the pre-existing drift noted above.
* Migration downgrade after Stage 5D audit rows exist requires an explicit audit
  cleanup, consistent with the existing audit append-only policy.

---

## 12. Git

Branch `stage-5d`, created from `3e35ef1`:

* `0e9a1af` — evidence reconciliation backend
* `0ce2658` — premium reconciliation workspace
* documentation commit containing this page

Nothing was pushed, merged or deployed; the Finance repository was not modified.

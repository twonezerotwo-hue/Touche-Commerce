# TOUCHE COMMERCE ↔ TOUCHE FINANCE — Stage 5C integration contract

**Status:** implemented and verified locally on branch `stage-5c`
**Commerce baseline:** `6381f59` (`stage-5`, Stage 5A complete)
**Verified Finance branch:** `feat/finance-integration-v1`
**Verified Finance HEAD:** `107c30e2ae4b5e4c22891f01ca730d3284994de5`
**Finance base:** `main` at `8dce8245c013ec74b81cf93927a067a4cc334c78`
**HTTP verification level:** `ISOLATED_HTTP_VERIFIED`
**Accounting writes:** none, in either direction.

---

## 1. Boundary

Finance owns the ledger, account balances, receivables, payables and aging.
Commerce owns trade operations. Commerce reads Finance through a dedicated
service credential and never receives a Finance browser session, cookie,
Tailscale identity or implicit loopback `OWNER` identity.

The connector is **disabled by default**. Disabled means zero network I/O and no
Finance data. No automated invoice, payment, journal or settlement is generated.

---

## 2. Finance endpoints used

Only these six Finance v1 operations are callable:

| Method | Finance path | Commerce use |
| ------ | ------------ | ------------ |
| `GET` | `/api/integration/v1/health` | Connection/watermark/recovery state |
| `GET` | `/api/integration/v1/capabilities` | Verify scope and authorized company |
| `GET` | `/api/integration/v1/companies` | Verify mapping, currencies, data-through |
| `GET` | `/api/integration/v1/companies/{id}/summary` | One-currency ledger summary |
| `GET` | `/api/integration/v1/companies/{id}/accounts` | Account debit/credit/balance |
| `GET` | `/api/integration/v1/companies/{id}/aging?type=receivable\|payable` | FIFO AR/AP aging |

Authentication headers:

```text
X-Touche-Integration-Key: key_<16 hex>
X-Touche-Integration-Secret: <server-side secret>
```

No other Finance endpoint is called. `/counterparties`, `/projects`,
`/reports/*`, invoices and payments are **not implemented by Finance** and are
not called by Commerce.

Finance response envelope:

```json
{
  "data": { "...": "..." },
  "meta": {
    "request_id": "…",
    "contract_version": "1",
    "generated_at": "2026-10-22T18:00:00+00:00",
    "source": "finance_ledger",
    "read_only": true
  }
}
```

Finance error envelope:

```json
{"error": {"code": "COMPANY_DENIED", "message": "…", "request_id": "…"}}
```

Commerce preserves the original category in
`error.details.finance_code`, and also forwards `finance_request_id` when
present.

---

## 3. Commerce endpoints

All require an authenticated Commerce session, an active company, active
membership and `company.view`:

| Method | Commerce path | Purpose |
| ------ | ------------- | ------- |
| `GET` | `/api/v1/finance/status` | `NOT_CONFIGURED`, `DISABLED`, `CONNECTED`, `DEGRADED`, `UNAVAILABLE`, `AUTH_ERROR` |
| `GET` | `/api/v1/finance/capabilities` | Verified capabilities for the mapped company only |
| `GET` | `/api/v1/finance/summary` | `currency` required for a multi-currency company |
| `GET` | `/api/v1/finance/accounts` | `currency`, `from`, `to`/`as_of`, `limit`, `offset` |
| `GET` | `/api/v1/finance/aging` | `type=receivable\|payable`, `currency`, `as_of`, `limit`, `offset` |

The old Stage 5A `GET /api/v1/integrations/finance/status` remains available and
still reports `scope="health_only"`; it is not the Stage 5C data connector.

Normalized Commerce error codes:

`FINANCE_NOT_CONFIGURED`, `FINANCE_MAPPING_UNVERIFIED`,
`FINANCE_MAPPING_DISABLED`, `FINANCE_INTEGRATION_DISABLED`,
`FINANCE_AUTH_ERROR`, `FINANCE_COMPANY_DENIED`,
`FINANCE_CURRENCY_REQUIRED`, `FINANCE_INVALID_CURRENCY`,
`FINANCE_UNAVAILABLE`, `FINANCE_PROTOCOL_ERROR`,
`FINANCE_AUDIT_UNAVAILABLE`.

Every successful data read writes a `finance.read` audit row containing actor,
company, Finance company, endpoint, currency/date context and request id. It
never contains the key id, secret, cookies or headers.

---

## 4. Explicit company mapping

Migration `0008_finance_mapping` creates
`touche.finance_company_mapping`:

| Column | Meaning |
| ------ | ------- |
| `company_id` | Commerce company; unique, so one mapping per tenant |
| `finance_company_id` | Explicit Finance `faaliyet_key` |
| `finance_company_name` | Display name returned by Finance |
| `status` | `pending`, `verified`, `disabled`, `invalid` |
| `configured_by` | Authorized Commerce admin user |
| `configured_at`, `last_verified_at` | Lifecycle timestamps |
| `last_verification_error`, `verification_details` | Non-secret verification context |

The runtime role receives `SELECT` only. The table has RLS using
`touche.current_company_id()`. Configuration is performed by the privileged CLI,
which requires an active **admin** membership in the Commerce company and live
verification against Finance:

```powershell
python -m app.cli finance-map set `
  --company "TOUCHE Trading" `
  --finance-company gursar_mimarlik `
  --actor admin@example.com

python -m app.cli finance-map list
python -m app.cli finance-map disable --company "TOUCHE Trading" --actor admin@example.com
```

`set` is the only way to create or change a map. Names are never matched, and
free-text `fisler.cari` counterparties are never mapped to Commerce records.

---

## 5. Currency semantics

Finance uses per-ledger currencies (`TL`, `EUR`, `USD` in the verified ledger).
Commerce passes exactly one explicit currency per request when Finance reports
more than one.

* Missing currency for a multi-currency company → `409 FINANCE_CURRENCY_REQUIRED`
  with `details.available_currencies`.
* Unknown currency → `400 FINANCE_INVALID_CURRENCY`.
* No conversion, no cross-currency aggregation and no hidden rounding.
* Amounts remain Finance decimal strings plus integer `amount_kurus`.
* `data_through` is Finance's ledger watermark, not Commerce's clock.

The UI renders `NOT_CONFIGURED`, `CONNECTED`, `DEGRADED`, `UNAVAILABLE` and
`AUTH_ERROR` explicitly.

---

## 6. Configuration

Server-side Commerce variables (never `NEXT_PUBLIC_*`):

```text
TOUCHE_FINANCE_INTEGRATION_ENABLED=false
TOUCHE_FINANCE_INTEGRATION_BASE_URL=http://127.0.0.1:8765
TOUCHE_FINANCE_INTEGRATION_KEY_ID=key_<16 hex>
TOUCHE_FINANCE_INTEGRATION_SECRET=<32+ characters>
TOUCHE_FINANCE_INTEGRATION_TIMEOUT_SECONDS=2
TOUCHE_FINANCE_INTEGRATION_MAX_RESPONSE_BYTES=1048576
```

The base URL remains a literal loopback `http://127.0.0.1`/`::1` endpoint.
Secrets live only on the server. No secret is accepted from an API request, and
no caller can supply a Finance company id or URL.

Finance-side prerequisites are the Stage 5B variables documented in
`C:\ai-excel\INTEGRATION_API_V1.md`: `TOUCHE_INTEGRATION_ENABLED`,
`TOUCHE_INTEGRATION_KEYS_FILE`, `TOUCHE_INTEGRATION_AUDIT_LOG` and
`TOUCHE_INTEGRATION_MAX_PAGE`. Create the key with
`py -3.12 scripts\integration_keys.py create --label touche-commerce --companies <ids>`.

---

## 7. Verification evidence

**Automated:** 20 connector/client unit tests and 18 Commerce API integration
tests. Frontend: 96 tests across 17 files including Finance component tests.

**HTTP acceptance:** `ISOLATED_HTTP_VERIFIED` using a temporary Finance base
directory and synthetic ledger, temporary key, isolated Finance server on
`127.0.0.1:8877`, Commerce test PostgreSQL database, Commerce CLI mapping,
Commerce API and Next.js server. All six Finance operations, four Finance UI
views, missing-currency handling, cross-tenant refusal and credential redaction
passed. Finance source hashes were unchanged. No live Finance server was started.

The acceptance harness is
`backend/scripts/verify_finance_http.py`; it refuses occupied ports and deletes
its temporary runtime on exit unless `--keep-isolated` is supplied.

**Live read-only source check:** Finance DB
`C9BA0EB7EC82F1DE50105F1E0019CA695B48843319B7E1D2184296632EF52BE1`;
workbook `E03740DA624522EA9AC4869D3ADDDFB008C96DC7D2A78759CE760D810B0FA51E`.
Both were unchanged before and after Stage 5C work.

---

## 8. Not available

* Invoice objects, payment objects, bank transfers and settlement status.
* Counterparty master, project master and report allow-list endpoints.
* Any Finance write, journal posting, reconciliation write or Excel write.
* Remote/TLS/mTLS deployment; the connector is loopback-only pending a separate
  security review.
* Live Finance connection: the acceptance test used an isolated Finance runtime,
  not the live Finance application.

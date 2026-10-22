# Stage 5A — TOUCHE FINANCE discovery and read-only boundary

**Executed:** 2026-10-22
**Commerce branch:** `stage-4` (Stage 5A changes are uncommitted)
**Finance revision inspected:** `8dce8245c013ec74b81cf93927a067a4cc334c78` (`main`)
**Stop point:** read-only. No invoice, payment or ledger write path exists in
Commerce or was added to Finance.

---

## 1. Executive summary

TOUCHE FINANCE is a **local, single-host application**. It has no service-to-
service API, no API key, no HMAC/webhook contract and no remote-write endpoint.
Its HTTP surface is a same-origin UI API protected by a loopback/Tailscale
session; the only unauthenticated business-adjacent endpoint is
`GET /api/health`, which is explicitly read-only.

Consequences for Stage 5:

1. Commerce can verify that Finance is reachable and reports a consistent ledger.
2. Commerce **cannot** read companies, counterparties, receivables, payables,
   invoices or reports through a supported machine interface today.
3. Commerce **must not** post accounting entries, invoices or payments. Finance
   remains the financial source of truth (ADR-038).
4. Any business-data connector requires a new, additive Finance interface,
   specified below and implemented in Finance first (ADR-040). Commerce must not
   impersonate Finance's loopback `OWNER` session or read its SQLite schema in
   production.

Stage 5A therefore implements the smallest honest slice: a disabled-by-default,
loopback-only health probe, an authenticated status endpoint, and an executable
read-only verification script. It creates no second accounting engine.

---

## 2. Verified project locations and revisions

| Item | Verified value | How verified |
| ---- | -------------- | ------------ |
| Real Finance Git worktree | `C:\ai-excel` | `.git` directory, `git rev-parse --is-inside-work-tree` → `true` |
| Finance branch | `main` | `git --no-optional-locks branch --show-current` |
| Finance HEAD | `8dce8245c013ec74b81cf93927a067a4cc334c78` | `git rev-parse HEAD` |
| GitHub remote HEAD | same commit | `git ls-remote origin HEAD` |
| Isolated review directory | `C:\Users\twone\OneDrive\Belgeler\ChatGPT\Smart Holding Finance\isolated_review` | Not the live tree: a container of linked worktrees at `18024fe [chore/pr-01-ci-isolation]` |
| SQLite ledger | `C:\ai-excel\veri\finans.db` | exists; opened with `mode=ro` |
| Excel master | `C:\Users\twone\OneDrive\Desktop\Touche\Touche Holding - AI Ready Finans Yönetim Sistemi.xlsx` | 227,137 bytes; mtime 2026-10-21 19:18:19 |
| Finance server | not listening on `127.0.0.1:8765` during discovery | `Get-NetTCPConnection` returned no listener; it was **not started** |

`git status` in Finance shows one untracked local item (`.claude/`); no tracked
file is modified. The isolation directory contains `pr02_worktree` … `pr19_worktree`
and must not be mistaken for the live application.

### Method

* Git inspection used `--no-optional-locks` so even the index was not refreshed.
* SQLite was opened with `file:…?mode=ro`, `PRAGMA query_only=ON`; no DDL/DML.
* The workbook was read as a ZIP archive (`xl/workbook.xml`); Excel was not opened.
* Finance code was read statically. No Finance module was imported and the Finance
  server was not started, because startup calls `recover_pending_transactions()`,
  which can legitimately write.
* SHA-256 and mtime were captured before and after the read. See §8.

---

## 3. Finance architecture (verified from source)

| Layer | Verified implementation |
| ----- | ----------------------- |
| HTTP server | Python 3.12 stdlib `ThreadingHTTPServer`, `127.0.0.1:8765` (`FINANS_UI_PORT`) |
| UI | Vanilla JS (`ui/index.html`, `app.js`, `cfo.js`), same-origin |
| Persistence | SQLite `veri/finans.db` + one ANA Excel + one YEDEK Excel |
| Excel library | `openpyxl`, single controlled writer `excel_deposu.guvenli_degistir` |
| Financial engine | `finans_cekirdegi`, `finans_motoru`, `proje_finansi`, `ticari`, `kurumsal_finans`, `raporlar` |
| Recovery journal | `finans_islemleri` / `finans_islem_olaylari`, states `PREPARED → EXCEL_WRITTEN → DB_POSTED → COMMITTED` plus `PENDING_RECOVERY`, `NEEDS_REVIEW`, `ABORTED` |
| Audit | hash-chained `loglar/audit.jsonl` + `audit_log` |
| Auth | `ui_yetki.oturum`: loopback admin or Tailscale identity; roles OWNER/CFO/FINANCE_MANAGER/ACCOUNTANT/PROJECT_MANAGER/VIEWER |

Finance does **not** claim Excel + SQLite are one ACID transaction.
`FINANCIAL_COMMIT_RECOVERY.md` documents the durable journal: Excel is written
first, SQLite is posted second, and a crash leaves `PENDING_RECOVERY` or
`NEEDS_REVIEW` rather than a fabricated success. `/api/health` reports
`degraded` when recovery or audit repair is pending; `recovery_health()` never
initialises the schema or writes.

---

## 4. Verified interface inventory

### 4.1 Unauthenticated endpoints

| Method | Path | Behaviour |
| ------ | ---- | --------- |
| `GET` | `/api/health` | Calls read-only `recovery_health()`; returns `{durum: "ok"|"degraded", yerel: bool}` (extra recovery counters when `yerel`) |
| `GET` | `/api/demo/status` | Returns demo flags only when `DEMO_MODE=1`; otherwise `{demo: false}` |
| `GET` | `/api/session` | Returns the current session descriptor; no business data |
| `POST` | `/api/session/pair` | Tailscale-only pairing code, 10-minute expiry |

### 4.2 Session-gated endpoints (selection)

`/api/faaliyetler`, `/api/excel/*`, `/api/belgeler`, `/api/kurumsal`,
`/api/cari-yaslandirma`, `/api/konsolide-mizan`, `/api/ticari/alacak`,
`/api/ticari/borc`, `/api/ticari/yaklasan`, `/api/nakit/13hafta`,
`/api/rapor`, `/api/raporlar`, `/api/kpi`, `/api/dashboard`, `/api/audit`,
`/api/yetki/roller`, `/api/fx/cevir`, `/api/senaryolar`, `/api/recovery/*`,
plus `POST /api/chat`, `POST /api/cfo/adim`, document upload/approval and
recovery-authorisation routes.

Every one of these calls `_yetki_gerekli()` and `_origin_gecerli()`; none accepts
an API key, bearer token or signed service request. There are no webhook
receivers.

### 4.3 Authentication model (exact)

1. `_oturum()` calls `ui_yetki.oturum(headers, Host, client_ip)`.
2. A request is `yerel=True` only when the client IP is exactly `127.0.0.1` or
   `::1`, the peer is in `TOUCHE_TRUSTED_PROXY_IPS` (default loopback), and the
   `Host` is in `TOUCHE_LOCAL_ADMIN_HOSTS` (default `127.0.0.1,localhost,::1`).
   Such a request becomes `OWNER`.
3. Tailscale identity comes only from `Tailscale-User-Login` when the peer is a
   trusted proxy. The identity must be paired in `veri/ui_yetkililer.json`.
4. Roles and permissions are enforced server-side (`yetki.py`).
5. `_origin_gecerli()` requires same-origin for non-local sessions.

**This is network-position authentication, not a service credential.** A
connector that relies on it would silently become `OWNER`. Stage 5A therefore
does not use it, and a future business-data API must introduce its own
authenticated principal.


---

## 5. Data model and financial semantics

### 5.1 Entities

| Finance table | Meaning | Live rows |
| ------------- | ------- | --------- |
| `faaliyetler` | Company / activity (`faaliyet_key`) | 3: `gursar_mimarlik`, `touche_enerji`, `touche_holding` |
| `faaliyet_alanlari` | Activity-area hierarchy under the holding | not counted |
| `hesaplar` | Chart of accounts | 22 |
| `fisler` | Journal header: `faaliyet_key`, `tarih`, `vade`, `proje`, `cari`, `aciklama`, `para_birimi`, `kur_mikro`, `belge_id` | 24 |
| `fis_satirlari` | Journal lines: `hesap_kodu`, `borc_kurus`, `alacak_kurus` | 48 |
| `karsi_taraflar` | Structured counterparties (`taraf_id`, `ad`, `tip`, `vergi_no`) | **0 (empty)** |
| `sozlesmeler` / `hakedisler` / `is_kalemleri` | Contract, progress billing, work items | 0 / 0 / not counted |
| `finans_islemleri` | Durable write journal | 1 |
| `butceler`, `banka_hareketleri`, `kurlar`, `donemler`, `onay_*` | Budget, bank matching, FX, periods, approvals | present |

### 5.2 Semantics that must not be re-implemented in Commerce

* **Revenue** = net credit on 600/646/649, not collections.
* **Cost** = net debit on 740/770/780/799, not payments.
* **Receivables** = net debit on 120/131/159; **payables** = net credit on
  300/320/331/335/336.
* **Collections** = cash accounts 100/101/102 closing 120/131/159.
* **Payments** = Dr 320 / Cr cash.
* **AR/AP aging** = FIFO open-item matching in `kurumsal_finans.cari_yaslandirma`,
  buckets 0–30/31–60/61–90/90+; exposed by `ticari.alacaklar/borclar`.
* **Invoices** are not a separate structured table. A posted document is a
  `fisler` header (`belge_id`) plus lines; uploaded documents live in
  `belge_kuyrugu` / `belge_butunlugu`.
* **Counterparties** are primarily free-text `fisler.cari`; the structured
  `karsi_taraflar` table is empty in the live ledger.
* **Projects** are free-text `fisler.proje` / `is_kalemleri.proje`; there is no
  standalone project master.
* **Reports** available: holding overview, cash flow, 13-week forecast,
  receivables/payables aging, budget vs actual, project/company/business-unit
  profitability, intercompany balances, scenario comparison, trial balance,
  P&L, balance sheet. Some return `Accounting mapping incomplete` when the chart
  of accounts/mappings is insufficient.

Commerce's Stage 4 `shipment_cost` stages (`ESTIMATED`, `QUOTED`, `INCURRED`,
`DOCUMENTED`) are **not** ledger entries. Only Finance may decide when an
incurred cost becomes an expense or payable.

---

## 6. Live read-only snapshot

Verified with `scripts/finance_readonly_probe.py`:

```text
table_count = 31
counts = {faaliyetler: 3, hesaplar: 22, fisler: 24,
          fis_satirlari: 48, finans_islemleri: 1, karsi_taraflar: 0}
missing_tables = []
missing_columns = {}
companies = gursar_mimarlik, touche_enerji, touche_holding
```

Workbook sheets (XML metadata; Excel was not opened):

```text
00_Touche Holding, 01_Faaliyetler, 02_Faaliyet Detayı, 03_Kayıt Merkezi,
04_Kredi & Vade, 05_AI Belge Inbox, 99_Ayarlar, 06_Proje İş Kalemleri
```

No row-level customer, invoice or payment data is copied into this document.


---

## 7. Mapping: Commerce → Finance

The mapping is deliberately **not automatic**. Names alone are not stable keys,
and Finance has no external-reference column yet.

| Commerce entity | Finance target | Key / mapping | Direction | Status |
| --------------- | -------------- | ------------- | --------- | ------ |
| `company` (`id`, `name`, `country`, `default_currency`) | `faaliyetler` (`faaliyet_key`, `ad`, `aktif`) | Explicit per-company registry; legal entity ≠ holding | read | **Blocked:** no API. Manual mapping only. |
| `counterparty` (buyer/supplier, `id`, `name`, `country`) | `karsi_taraflar` (`taraf_id`, `ad`, `tip`, `vergi_no`) or `fisler.cari` | No tax/VKN in Commerce; normalized name + country + manual confirmation | read/write | **Blocked:** table empty; no API. |
| `sales_order` (`order_number`, `currency`, `order_total`, `status`, `accepted_terms`) | No direct entity. Future draft receivable / `hakedis` (120/600) after delivery | `order_number` as `source_id`; one event per accepted order | write (draft) | **Blocked:** no ingestion API; no invoice table. |
| `sales_order_item` (`sku`, `name`, `quantity`, `unit_price`, `line_total`) | `hakedis` has header totals only; `fis_satirlari` is ledger, not invoice lines | Line-level source id + SKU; Finance must add draft line storage | write (draft) | **Blocked:** no line table / API. |
| `purchase_order` (`po_number`, `supplier_id`, `total_cost`, `status`, dispatch evidence) | No PO table. Future draft payable (320/740) | `po_number` as `source_id` | write (draft) | **Blocked:** no API. |
| `purchase_order_item` | Ledger line / draft payable line | SKU + quantity + unit cost | write (draft) | **Blocked:** no API. |
| `shipment` (`shipment_number`, delivery evidence, dates) | No shipment entity. Delivery is the trigger for revenue/COGS recognition | `shipment_number` as `source_id`; event only on `DELIVERED` with evidence | write (draft) | **Blocked:** no API. |
| `shipment_cost` (`cost_type`, `stage`, `amount`, `currency`, `reference`) | Expense (740/770/780/799) + payable if unpaid | Only `INCURRED`/`DOCUMENTED` are candidates; estimates never post | write (draft) | **Blocked:** no API. |
| `trade_document` (`document_type`, `sha256`, versions, linked entity) | `belge_butunlugu` (hash) / `belge_kuyrugu` (queue) | SHA-256 + source document id; no file transfer interface | metadata write | **Blocked:** no API; do not copy files into Finance. |
| Operational cost / budget | Expense + cost center (`masraf_merkezi_id` nullable) | Category mapping + project/cost-center registry | write (draft) | **Blocked:** no cost-center master in Commerce. |
| Payments / collections | Finance-only, accounts 100/101/102 | Read-only reporting; Commerce never records payments | read | **Blocked:** no read API. |
| Financial reports (AR/AP aging, trial balance, P&L, cash) | Finance report service | Read-only snapshots with `data_through` | read | **Blocked:** no read API. |


---

## 8. Missing interfaces (exact) and smallest safe implementation

These endpoints **do not exist**. They are a specification for Finance, not a
claim that Commerce can call them. Commerce must not add a fake client for them.

### 8.1 Read-only contract (required before any write discussion)

| Proposed method/path | Returns | Reuses |
| -------------------- | ------- | ------ |
| `GET /api/integration/v1/health` | `contract_version`, `status`, `ledger_readable`, `pending_recovery`, `needs_review`, `data_through` | `recovery_health()` + read-only ledger probe |
| `GET /api/integration/v1/companies` | `faaliyet_key`, `name`, `holding_key`, `active`, `external_ref` | `faaliyetler`, `faaliyet_alanlari` |
| `GET /api/integration/v1/counterparties?company_key=` | `taraf_id`, `name`, `type`, `tax_no`, `external_ref` | `karsi_taraflar` |
| `GET /api/integration/v1/projects?company_key=` | Distinct projects plus contract/work-item totals | `fisler.proje`, `is_kalemleri`, `sozlesmeler` |
| `GET /api/integration/v1/receivables?company_key=&as_of=` | Aging rows: `cari`, `vade`, `remaining`, `currency`, `source_fis_id`, buckets | `ticari.alacaklar` |
| `GET /api/integration/v1/payables?company_key=&as_of=` | Aging rows: `cari`, `vade`, `remaining`, `currency`, `source_fis_id`, buckets | `ticari.borclar` |
| `GET /api/integration/v1/trial-balance?company_key=&from=&to=` | Account balances with `data_through` | `kurumsal_finans.konsolide_mizan` |
| `GET /api/integration/v1/reports/{report}` | The existing report payload plus `data_through` and `mapping_status` | `raporlar.RAPORLAR` |

Rules: no new financial calculations; every number comes from the existing
engine. Each response carries `data_through` and `source`. Unknown company keys
return `404`; missing data returns an explicit `DATA_NOT_AVAILABLE`, never `0`.

### 8.2 Draft-only write contract (only after 8.1 is verified)

```text
POST /api/integration/v1/commercial-events
Headers:
  X-Touche-Key-Id: <key id>
  X-Touche-Timestamp: <unix seconds, ±300 s>
  X-Touche-Nonce: <unique>
  X-Touche-Signature: hex(HMAC-SHA256(secret,
      METHOD \n PATH \n TIMESTAMP \n NONCE \n SHA256(body)))
  Idempotency-Key: <source event id>
Body:
  { contract_version: "1", source_system: "touche-commerce",
    source_company_id, source_event_id, event_type,
    aggregate_type, aggregate_id, occurred_at, currency, amount,
    counterparty: { source_id, name, country, tax_no? },
    lines: [ { sku, description, quantity, unit, unit_price, line_total } ],
    evidence: { type, reference, sha256? } }
Response 202:
  { event_id, status: "DRAFT_CREATED" | "DUPLICATE",
    draft_refs: [...], data_through }
```

The endpoint may create **drafts only**. It must never post a ledger entry,
approve a document, record a payment or send a message. Approval stays inside
Finance's existing UI/password flow. A source event is unique on
`(source_system, source_event_id)`; replay returns the original result.

### 8.3 Storage additions in Finance (additive, no renames)

* `entegrasyon_anahtarlari` — key id, hashed secret, scopes, active, created/rotated.
* `entegrasyon_istek_kayitlari` — nonce, timestamp, body hash, response status,
  unique `(key_id, nonce)`; replay window cleanup.
* `entegrasyon_eslesmeleri` — `source_system`, `source_id`, `target_type`,
  `target_id`, `company_key`; unique source key.
* `entegrasyon_olaylari` — source event id, event type, payload hash, draft refs,
  status, `data_through`, timestamps; unique `(source_system, source_event_id)`.

### 8.4 Smallest safe sequence

1. Add the read-only endpoints (8.1) behind HMAC auth; bind to loopback first.
2. Run Commerce read-only reconciliation against them; prove no writes.
3. Add `entegrasyon_eslesmeleri` and a manual mapping UI in Finance.
4. Add draft-only event ingestion (8.2), still without auto-posting.
5. Only then discuss approval/payment automation, as a separate ADR.

### 8.5 Why not reuse the existing UI session?

`127.0.0.1` requests are treated as `OWNER`. A Commerce connector using that
would inherit membership administration, document approval and recovery
authorisation. It would also be impossible to audit as a distinct principal or
to scope to read-only. Reusing the session is therefore rejected.


---

## 9. Stage 5A implemented in Commerce

| Component | File | Behaviour |
| --------- | ---- | --------- |
| Config | `backend/app/core/config.py` | `TOUCHE_FINANCE_INTEGRATION_ENABLED=false` by default; loopback-only URL; 0.1–10 s timeout |
| Client | `backend/app/integrations/finance/client.py` | `GET /api/health` only; no cookies/auth headers; requires `Server: ToucheFinans/...` + JSON; no redirects; 8 KiB cap |
| Service | `backend/app/integrations/finance/service.py` | Disabled performs **zero** network I/O; otherwise returns one observation |
| API | `GET /api/v1/integrations/finance/status` | Requires a Commerce session; returns `state`, `latency_ms`, `detail`, `scope="health_only"`, `accounting_writes_enabled=false` |
| Probe | `scripts/finance_readonly_probe.py` | `mode=ro` SQLite + ZIP workbook metadata + before/after hashes |
| Verifier | `scripts/verify-finance-readonly.ps1` | Git revision, schema, hash equality; probes health only if Finance is already listening |

State machine: `disabled` → `healthy` / `degraded` / `unreachable` /
`incompatible`. Protocol mismatches (non-200, invalid JSON, unknown `durum`,
non-boolean `yerel`, oversized body) are `incompatible`, never silently healthy.

Deliberate properties:

* The connector never opens Finance's SQLite database in production; the probe
  is an offline verification tool.
* It never sends `Tailscale-User-Login`, a cookie or a bearer token.
* It never calls `/api/session`, `/api/faaliyetler`, `/api/ticari/*` or any
  write endpoint.
* It does not add invoices, payments, ledger tables or a second accounting
  engine to Commerce.

---

## 10. Read-only verification evidence

Executed 2026-10-22 with Finance **not running**:

```text
Finance worktree : C:\ai-excel [main] 8dce8245c013ec74b81cf93927a067a4cc334c78
Remote HEAD      : 8dce8245c013ec74b81cf93927a067a4cc334c78
Dirty files      : 1 (untracked .claude/ only)
Database         : C:\ai-excel\veri\finans.db
DB SHA-256       : C9BA0EB7EC82F1DE50105F1E0019CA695B48843319B7E1D2184296632EF52BE1
DB unchanged     : True
Workbook         : ...\Touche Holding - AI Ready Finans Yönetim Sistemi.xlsx
WB unchanged     : True
Schema ok        : True
Health           : skipped — Finance was not listening; it was not started
PASSED           : True
```

Probe-internal `unchanged` was `{database: true, database_wal: true,
workbook: true}`. Independent `Get-FileHash` before/after matched. The workbook
SHA-256 was `E03740DA624522EA9AC4869D3ADDDFB008C96DC7D2A78759CE760D810B0FA51E`.

Why health was skipped: starting Finance runs `recover_pending_transactions()` at
startup, which may legitimately write. Verification must not cause the write it
is trying to exclude.

Reproduce:

```powershell
scripts\verify-finance-readonly.ps1
scripts\verify-finance-readonly.ps1 -Json
```

If Finance is already running, the script probes `GET /api/health` and reports
`{status: "observed", durum, yerel}`. It still does not start or stop Finance.

---

## 11. Explicitly not implemented

* No business-data read (companies, counterparties, AR/AP, invoices, reports).
* No outbox producer/relay for Finance events; the existing `outbox_event` table
  remains empty until a Finance ingestion contract exists.
* No invoice, payment, ledger, journal or reconciliation write in Commerce.
* No direct SQLite coupling in the running connector.
* No UI screen; the status endpoint is for operators and tests.
* No automatic matching of Commerce counterparties to Finance `cari` names.

Stage 5B may start only when Finance exposes and verifies the §8.1 read-only
contract. Stage 5C (draft-only events) additionally requires §8.2/§8.3 and a
Finance-side approval design.


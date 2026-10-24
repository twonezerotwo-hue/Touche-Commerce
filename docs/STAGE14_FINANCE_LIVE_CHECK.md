# Stage 14 — live read-only check of the Finance integration (2026-10-24)

Status: **FINANCE_LIVE_VERIFIED for the real Finance application code reading a byte-for-byte
snapshot of the real ledger.** It is *not* a check of Finance running inside `C:\ai-excel`, and
that was deliberate (see "Why a snapshot"). Your instruction was to read only and not modify
`C:\ai-excel`; that was kept and proven.

## What was run

1. Recorded a manifest of every file under `C:\ai-excel` (4,173 files: path, size, modified time)
   and the SHA-256 of `finans.db`, `finans.db-wal`, `finans.db-shm` and the master workbook.
2. Copied `finans.db` (its WAL was empty), and the workbook, into a throw-away folder in
   `%TEMP%`. Finance's own configuration (`TOUCHE_BASE_DIR`) was pointed at that folder; Finance
   resolved its database, workbook and log paths inside it (checked before starting).
3. Created an integration key with Finance's own `scripts\integration_keys.py`, stored only in
   the snapshot folder, authorised for the three real company ids in the ledger.
4. Started Finance's real server (`scripts\finans_asistani_sunucu.py`) from `C:\ai-excel` with
   `PYTHONDONTWRITEBYTECODE=1` on `127.0.0.1:8765`, integration enabled.
5. `scripts\finance_live_check.py` called the six read-only endpoints for every authorised
   company and probed refusals.
6. Mapped the acceptance Commerce company to the real Finance company with the real CLI
   (`backend\scripts\acceptance_finance_map.py` → `app.cli finance-map set`, which verifies the
   company against Finance before storing the mapping), started the isolated acceptance stack with
   the connector enabled and ran `e2e/tests/finance-live.spec.ts` in Chromium and WebKit.
7. Stopped every process I started, compared the manifest and hashes again, and deleted the
   snapshot folder (it contained a copy of the real ledger).

## Results

| Check | Result |
|---|---|
| Finance health | `ok`, ledger readable, no missing tables, no journal in recovery, data through 2026-10-20 (3 activities, 22 accounts, 24 journals, 48 lines) |
| Scope and companies | single `finance.read` scope; 3 authorised company ids; list matches the key |
| Summary, accounts, receivable and payable aging | HTTP 200 for all three companies |
| Write attempt (`POST`) | refused `405 READ_ONLY` |
| Wrong secret | refused `401` |
| Company not on the key | refused `403` |
| Finance's own audit log | 96 requests recorded: 94 allowed, 2 denied |
| Commerce → Finance mapping | verified live (company name, currencies EUR/TL/USD) |
| Commerce status / capabilities | `connected`, mapping `verified`, `read_only: true` |
| Several currencies | summary without a currency → `409 FINANCE_CURRENCY_REQUIRED`; unknown currency → `400`; with a currency → `200`; nothing is converted or summed across currencies |
| `/finance` page | renders the live data, asks for a currency first, states it never posts an invoice, payment or journal |
| Company without a mapping | `not_configured`, `409 FINANCE_NOT_CONFIGURED`; no Finance data crosses the tenant boundary |
| Commerce write path to Finance | none exists (`POST` on the Finance routes → 404/405/403) |
| **`C:\ai-excel` afterwards** | **4,173 files, 0 differences (path, size, modified time); SHA-256 of database, WAL, shm and workbook identical** |

Only one of the three Finance companies has postings (`gursar_mimarlik`: 22 documents in TL and a
small number in EUR and USD); the other two are empty.

## Why a snapshot and not the live folder

Finance's server runs a **recovery scan when it starts** (`recover_pending_transactions`), writes
its own audit rows, keeps the integration key file under `veri\` and the integration audit log under
`loglar\`, and Python would write `.pyc` files next to the sources. Starting it inside
`C:\ai-excel` would therefore have changed that folder even if no request ever wrote a ledger row.
Using a snapshot keeps every one of those writes in the throw-away copy while still exercising the
real Finance code on real data. The cost: this proves the integration works, not that Finance's
normal runtime behaves identically when started from its own folder.

## Repeat it

```powershell
# 1. snapshot + key + server (see the steps above; keep all paths outside C:\ai-excel)
# 2. check the Finance API directly
$env:TOUCHE_FINANCE_INTEGRATION_KEY_ID = '<key id>'; $env:TOUCHE_FINANCE_INTEGRATION_SECRET = '<secret>'
backend\.venv\Scripts\python.exe scripts\finance_live_check.py
# 3. map the acceptance company and run the browser spec against the isolated stack
cd backend; .\.venv\Scripts\python.exe -m scripts.acceptance_finance_map gursar_mimarlik
cd ..\e2e; $env:E2E_FINANCE_LIVE = '1'; npx playwright test finance-live
```

## What this does not cover

* Mapping a real Commerce company in the development database (only the acceptance company on the
  test database was mapped). Do that with `python -m app.cli finance-map set` once you decide which
  company is which.
* Running Finance's normal runtime from `C:\ai-excel` side by side with Commerce; that needs the
  owner to accept Finance's startup recovery scan on the live files.
* Reconciliation runs and profitability against real Finance data (Stage 5D/5E logic exists and is
  tested on fixtures; no real orders exist to reconcile).

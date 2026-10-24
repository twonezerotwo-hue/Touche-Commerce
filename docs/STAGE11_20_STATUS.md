# Stages 11–20 — what is real, what is not (2026-10-24)

Rule used throughout: a stage is only called *done* for the part that was run and observed. Nothing
is marked `COMPLETED`, `LOCAL_ACCEPTED` or `PRODUCTION_APPROVED`. The most this release claims is
**LOCAL_OPERATIONAL candidate** for the part listed as "running locally".

Legend: **Coded** = code merged · **Tested** = automated tests pass · **Local** = observed running on
this Windows PC · **Live** = proven against the real external system · **Blocker** = what only the
owner can unblock.

| Stage | Coded | Tested | Local | Live | Blocker / honest gap |
|---|---|---|---|---|---|
| 11 Windows workspace, backup/restore | ✅ launcher with port-collision handling, `backup-local`, `restore-test`, acceptance stack | ✅ contract tests, `verify.ps1`, restore drill | ✅ started on moved ports, health OK; restore of plain **and** encrypted backup into a scratch DB = `RESTORE_VERIFIED` | n/a | **MacBook / LAN over HTTPS not built and not tested.** Firefox does not start on this PC (Playwright build, side-by-side error). |
| 12 Bilingual UI | ✅ cookie-based server-rendered TR/EN, typed catalogues | ✅ parity tests, EN+TR component tests, Playwright | ✅ | n/a | **Partial:** shell, sign-in, Command Center, import, company profile, document panel, CRM, products, deal status words. Deals, sourcing, orders, shipments, finance, AI, communications and the public status page are English only (`STAGE12B_BILINGUAL_SCREENS.md`). Timestamps still show English month names. |
| 13 Trade operations | ✅ CRM, catalogue, CSV/XLSX import wizard, RFQ → quote → pricing → sales quote → order → PO → shipment (Stages 3–4), 8 TR/EN document kinds in PDF/DOCX/XLSX/CSV, company profile | ✅ 705 backend + 226 frontend tests incl. API, RLS and concurrency tests | ✅ real-browser journeys (import, documents, concurrent users) | n/a | **Not built:** supplier price lists with validity and revision history, product attachments, a separate contacts table (one contact per counterparty today), a "supplier quotation" document sheet, import of other record types. A Commerce invoice is always a **DRAFT**; it posts nothing. |
| 14 Finance (read-only) | ✅ connector, reconciliation, intelligence (Stage 5) | ✅ fixtures, plus `finance-live.spec.ts` (6 specs, Chromium + WebKit) | ✅ real Finance server on `127.0.0.1:8765`; Commerce → Finance read the real ledger end to end | ✅ **FINANCE_LIVE_VERIFIED on a snapshot of the real ledger** (`STAGE14_FINANCE_LIVE_CHECK.md`) | Run against a throw-away **snapshot**, not inside `C:\ai-excel`, because Finance's startup recovery scan and its key/audit files would have written there. `C:\ai-excel` proven unchanged (4,173 files, 0 differences, hashes equal). Only the acceptance company was mapped; which real Commerce company maps to which Finance company is your decision. Only 1 of 3 Finance companies has postings. |
| 15 E-YAY (read-only, paper-safe) | ✅ read-only adapter (Stage 8), loopback only | ✅ against a stub | — | ❌ service not running | Owner must start it. `D:\Clean E-yAy` was never touched; no trading or portfolio function is called. |
| 16 AI Trade Director | ✅ DeepSeek-compatible primary, local Ollama fallback, monthly cost reservation, human-approved proposals | ✅ provider, fallback and budget tests | ✅ **real local `qwen3:8b` fallback verified** (answered "evet", flagged `LOCAL_FALLBACK_USED`, 16.6 s) | ❌ DeepSeek: no API key, prepaid balance and spend limit not checked | Needs your key and a look at the DeepSeek dashboard. Per-user and per-company consumption *views* were not verified. |
| 17 Communications | ✅ draft-only preflight, suppression list (opt-out) | ✅ API tests | ✅ | ❌ | **No Gmail, WhatsApp, Instagram or LinkedIn connector exists.** Each needs an account, OAuth authorization or a key from you, plus opt-in/templates/webhook design. Nothing was sent anywhere. |
| 18 Security and operations | ✅ Argon2id, server-side sessions, CSRF/Origin checks, RLS, append-only audit, encrypted backups (AES-256-GCM) | ✅ 15 crypto tests, restore drill | ✅ | ❌ no offsite copy | **MFA/TOTP not implemented.** No offsite or key management. Dependency scan run: `npm audit` 0 vulnerabilities (web app production packages and the E2E tools); `pip-audit` found advisories on `cryptography` 47.0.0, fixed by requiring 50.x, and on the virtualenv's own `pip` 25.0.1 (build tool, not shipped; upgrade with `python -m pip install --upgrade pip`). Admin cannot trade (ADR-003) — see the owner decision in `STAGE11_LOCAL_ACCEPTANCE.md`. |
| 19 Real-browser acceptance | ✅ Playwright suite (`e2e/`) on an isolated acceptance database | ✅ **64 specs pass: 32 on Chromium and 32 on WebKit** | ✅ | n/a | Firefox blocked on this PC. 5+ concurrent users covered (6 browse together; 3 import at once; 2 identical imports). Not covered: the 20 mission scenarios end to end (RFQ → shipment → profitability in a browser), tablet breakpoints, screen-reader checks. |
| 20 Local release | ✅ `LOCAL_RELEASE.md`, `verify.ps1`, backup/restore, release docs | ✅ | ✅ | n/a | Hosting budget is $0: no paid service was enabled; `canwetouche.com` is expired; this is a **local pilot, not production**. |

## Integrations at a glance

| Integration | Implemented | Tested | Connected live | Why not connected |
|---|---|---|---|---|
| Finance (`C:\ai-excel`) | yes, read-only | stub, real-ledger probe, live HTTP specs | **yes, on a snapshot of the real ledger** | not run inside `C:\ai-excel` (it would write there); no real Commerce company mapped yet |
| E-YAY (`C:\dev\clean-e-yay`) | yes, read-only | stub | no | service not running; owner decision |
| DeepSeek API | yes | stub | no | no API key; prepaid balance unverified |
| Ollama / Qwen3 8B | yes | yes | **yes (local)** | — |
| Gmail | no | — | no | needs OAuth authorization + connector |
| WhatsApp Cloud API | no (channel and suppression model only) | — | no | needs Meta account, templates, webhooks |
| Instagram / LinkedIn | no | — | no | needs accounts and official API approval |

## Defects found and fixed during this work

* **P1** (since Stage 1B): the "New counterparty" form could never open (unreachable `return`). Fixed; a browser journey covers it.
* **P2**: `scripts\migrate.ps1` aborted on Alembic's stderr under Windows PowerShell 5.1; a stale temp folder made 18 tests fail with `PermissionError`; a 2 MB parametrize id overflowed the 32,767-character environment limit; CRLF checkouts failed Prettier on 158 files. All fixed.
* **CI**: the encrypted-backup branch failed CI because `cryptography` was installed locally but not declared; caught by CI, fixed.

## Owner decisions that block progress

1. Should the owner role also be able to trade? (Today `admin` cannot, by design.)
2. May E-YAY be started for a read-only live check? (Finance is done on a snapshot. Running it inside `C:\ai-excel` means accepting its startup recovery scan on the live files, and you must choose which Commerce company maps to which Finance company.)
3. Provide the DeepSeek key (and check the prepaid balance), or keep the local model only?
4. Which messaging channels matter first, and will you create the accounts?
5. Is an offsite backup location available, and who holds the backup passphrase?

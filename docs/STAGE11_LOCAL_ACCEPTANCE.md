# Stage 11B — Windows local acceptance (evidence, not a claim)

Status: **LOCAL_OPERATIONAL candidate, not LOCAL_ACCEPTED.** The Windows workspace, the real
PostgreSQL database, backup + scratch-database restore and a real-browser role journey are
evidenced below. The MacBook/LAN path and Firefox are **not** tested; see "Not proven".

Date of the runs below: 2026-10-24, Windows 11, PostgreSQL 17 (portable cluster, port 5432).

## What was run, and what it showed

| Check | Command | Result |
|---|---|---|
| Local launcher with port collision | `scripts\start-local.ps1 -AutoPorts` | Ports 3000/8000 were held by an unrelated project; the launcher refused to attach to them, picked 3010/8010, set loopback-only CORS for the moved port, health checks passed. Nothing bound to `0.0.0.0`. |
| Migrations | `scripts\migrate.ps1` | Dev database moved 0010 → 0013 after a verified backup. `migrate.ps1` previously aborted on Alembic's stderr under Windows PowerShell 5.1; it now goes through `Invoke-Native`. |
| Backup | `scripts\backup-local.ps1` | `backups\touche_commerce-20261024-054056.dump` (477.3 KiB), revision `0013_import_batch`, 54 tables, SHA-256 recorded in the manifest. Never overwrites an existing backup. |
| Restore rehearsal | `scripts\restore-test.ps1 -BackupFile <that dump>` | `RESTORE_VERIFIED`: checksum and size match, restored into scratch database `touche_restore_check` (dropped afterwards), 54 tables compared, 50 with row level security, audit trigger present. The development database is never the restore target. |
| Backend tests | `pytest` in `backend` | Run with the repo-local base directory (see below); the Stage 13 import suite adds 14 API tests. |
| Real-browser acceptance | `e2e` (Playwright 1.63.0) | **44 passed, 0 failed** on Chromium and WebKit 26.6 (22 specs per engine). |

### Real-browser suite (`e2e/`)

It runs against an **isolated acceptance stack**, never the development database:

```powershell
cd backend
.\.venv\Scripts\python.exe -m scripts.seed_acceptance        # *_test database only; random passwords
cd ..
backend\.venv\Scripts\python.exe scripts\acceptance_stack.py  # API + web on free loopback ports
cd e2e
npx playwright test                                           # chromium + webkit
```

The seed refuses to run unless the target database name ends in `_test`, writes the generated
passwords to the git-ignored `backend/var/acceptance/credentials.json` and never prints them. The
company name is plainly synthetic ("Touche Acceptance Trading"); the real company's legal title,
tax number and address are unverified and are not invented anywhere.

What the 22 specs per engine prove:

* **Authentication** — wrong password gives one generic message; every private route redirects an
  anonymous visitor to `/login`; the session cookie is `HttpOnly; SameSite=lax`; sign-out ends the
  session; the login form works with the keyboard alone.
* **Roles** — `sales`, `purchasing`, `operations` (trader) get the import wizard; `owner` (admin),
  `finance` (approver) and `viewer` get the history only; a forged import request from a viewer is
  refused by the API; each role shows its own badge.
* **Import wizard end to end** — preview → column match → review → explicit confirmation → atomic
  save; the identical file cannot be imported twice; existing records must be skipped explicitly;
  invalid rows block the import and write nothing; Turkish column headings are recognised;
  customers/suppliers import.
* **Language** — switching to Turkish stores a cookie, survives reload and does not leak to
  another user's session.
* **Company isolation** — a user of another company sees none of this company's records and gets an
  empty list from the API.
* **Concurrency** — six signed-in users browse seven screens at once without an error page; three
  traders import three different files at the same moment and every file lands exactly once; two
  traders submitting the *identical* file together create it exactly once.
* **Responsive** — no horizontal overflow at 390 px on five screens; the mobile menu opens.

### Findings from the run

1. **Admin cannot trade (by design, ADR-003).** The owner role maps to `admin`, which has no
   `trade.write`, so an owner who also wants to import products or create deals cannot. This is the
   intended separation of duties (and `admin` must never gain finance approval), but a small company
   will expect its owner to trade as well. Decision needed from the owner: give people who need both
   *two memberships*? (the schema allows one row per user and company, so this needs a design
   change), or add an explicit `owner` role that includes `trade.write` but still excludes finance
   approval. Not changed here because it alters a security boundary.
2. **The dashboard's recent-activity feed is visible to every member** (documented in
   `routes/dashboard.py`). It lists action names and entity ids only (never values), but it is
   wider than the admin-only `audit.view`. Left as designed; worth a conscious decision.
3. **Hydration race on first paint (test finding, not a product bug).** Typing into the login form
   before React hydrates is dropped on WebKit. The E2E helpers wait for hydration before
   interacting.
4. Windows-specific defects found and fixed earlier in this stage: PowerShell 5.1 turns native
   stderr into terminating errors; a stale `pytest-of-<user>` temp folder caused `PermissionError`
   in 18 tests (pytest now uses `backend\var\pytest-tmp`); a 2 MB parametrize id overflowed the
   32,767-character environment limit; CRLF checkouts failed Prettier on 158 files (`.gitattributes`
   now forces LF).

## Not proven (honest list)

* **MacBook / LAN access over HTTPS: not built and not tested.** The launcher binds loopback only.
  A LAN or tunnelled path needs a TLS design (reverse proxy or tunnel, `__Host-` cookies,
  CORS/CSRF origin policy) and a MacBook to test with. Do not expose dev ports to the internet.
* **Firefox: BLOCKED on this machine.** Playwright's Firefox 155 build fails to start
  (`spawn UNKNOWN`; Windows side-by-side error, dependent assembly `mozglue` not found). The project
  is opt-in (`E2E_FIREFOX=1`) so the suite stays green and honest. WebKit and Chromium were run.
* The acceptance data is synthetic and lives in the `*_test` database; the development database has
  no users I could sign in with, and none were added to it.
* The 20 mission scenarios beyond the ones above (RFQ → sales order → shipment → documents →
  profitability, finance/E-YAY live reads, AI, communications) are not yet exercised in a browser.

## Decision log

* Acceptance stack on the `*_test` database instead of seeding the development database: the test
  database is already truncated by the test-suite, so synthetic users cannot pollute real data.
* Playwright lives in its own `e2e/` package so the frontend build and CI stay unchanged.

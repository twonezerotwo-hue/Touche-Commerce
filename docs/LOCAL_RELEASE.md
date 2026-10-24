# TOUCHE COMMERCE — running it on your Windows PC

This is the operator's guide for the **local, single-machine** release. It is not a production
deployment: nothing here is reachable from the internet, and no paid service is used or required.
Everything below is a command you run in PowerShell from the repository folder.

## 1. First time only

```powershell
.\scripts\setup.ps1            # .env from the example, Python virtualenv, npm packages
.\scripts\migrate.ps1          # creates/updates the database tables (needs PostgreSQL running)
.\scripts\bootstrap-admin.ps1  # first administrator and company; asks for the password (hidden)
```

`setup.ps1` writes `.env` with **local development credentials**. `.env` never leaves your
machine (it is git-ignored). PostgreSQL 17 must already be running on port 5432 (the repository's
portable cluster under `infra\.local` is what the scripts expect).

## 2. Open it

```powershell
.\scripts\start-local.ps1
```

It opens two windows (API and web app), waits until both answer, and prints the addresses:
**http://localhost:3000** (web) and http://127.0.0.1:8000 (API, `/docs` for the API reference).
It refuses to start if another program already uses those ports and never touches that program.
If 3000/8000 are taken, run `.\scripts\start-local.ps1 -AutoPorts` and use the addresses it prints.

Everything listens on this computer only. To use it from another device (for example a MacBook) you
need an HTTPS reverse proxy or a private tunnel — **that is not built or tested**; do not simply
expose the ports.

## 3. Close it

Close the two PowerShell windows the launcher opened (or press Ctrl+C in each). Nothing else runs
in the background. Your data stays in PostgreSQL.

## 4. Language

The switcher in the top bar (and on the sign-in page) changes the interface between English and
Turkish; the choice is remembered in this browser. Stored data (names, notes, product
descriptions) is never translated. See `docs/STAGE12B_BILINGUAL_SCREENS.md` for which screens are
translated so far.

## 5. Add a person

```powershell
cd backend
.\.venv\Scripts\python.exe -m app.cli create-user --email ayse@example.com --name "Ayşe Yılmaz"
.\.venv\Scripts\python.exe -m app.cli membership grant --email ayse@example.com --company "Your Company" --role trader
.\.venv\Scripts\python.exe -m app.cli list memberships
```

Roles: `viewer` (read only), `trader` (create and edit trade records, import files, generate
documents), `approver` (finance review and approval; no trading), `admin` (people, settings, company
profile; **cannot** trade or approve money — separation of duties). The password is asked for with a
hidden prompt; there is no default password. Revoke with `membership revoke`; reset with `set-password`.

Mapping of the roles you described: owner/manager → `admin`; sales, purchasing and
operations/logistics → `trader`; finance review and finance approval → `approver`; read-only →
`viewer`. An owner who also trades needs a second account today (see the open decision in
`docs/STAGE11_LOCAL_ACCEPTANCE.md`).

## 6. Fill in your company details

Sign in as the administrator and open **Company profile**. Legal name, tax number, address and bank
details are printed on quotations, orders and invoice drafts. Nothing is invented: until you fill
them in, each document says what is missing.

## 7. Back up and prove the backup

```powershell
$env:TOUCHE_BACKUP_PASSPHRASE = '<at least 16 characters, kept in your password manager>'
.\scripts\backup-local.ps1 -Encrypt
.\scripts\restore-test.ps1 -BackupFile .\backups\<name>.dump.enc
```

The first command writes the dump, a manifest and an encrypted copy that it has already decrypted
once to prove it works. The second restores the encrypted copy into a throw-away scratch database
and checks tables, row counts, row level security and the audit trigger; it prints
`RESTORE_VERIFIED` only when everything matches and never touches your live database. Only the
`.enc` file should ever be copied off this PC. A lost passphrase means an unreadable backup. Details:
`docs/STAGE18_ENCRYPTED_BACKUP.md`.

## 8. Update to a newer version

```powershell
git pull --ff-only
.\scripts\setup.ps1
.\scripts\backup-local.ps1 -Encrypt    # always back up before changing the database
.\scripts\migrate.ps1
.\scripts\verify.ps1                   # lint, types, all tests, production build
.\scripts\start-local.ps1
```

## 9. Check that everything works

```powershell
.\scripts\verify.ps1                   # backend + frontend checks and tests (about 3 minutes)
```

Real-browser tests run against a **separate test database**, never your data:

```powershell
cd backend; .\.venv\Scripts\python.exe -m scripts.seed_acceptance; cd ..
backend\.venv\Scripts\python.exe scripts\acceptance_stack.py    # leave running
cd e2e; npx playwright test                                      # Chromium and WebKit
```

## 10. What is and is not connected

See `docs/STAGE11_20_STATUS.md`. In short: the trade workflow, documents, imports, Turkish/English
interface (partial), backup/restore and the local AI fallback run on this PC. Finance, E-YAY,
DeepSeek, Gmail, WhatsApp, Instagram and LinkedIn are **not live**; each needs something only you
can provide (a running service, an account, a key or an authorization), and nothing was faked.

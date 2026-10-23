# Stage 10 — Release readiness, not automatic production authorisation

**Status:** CI verification pending. Stage 9 local launcher was merged at
`40a69d8`; no remote access to the owner's Windows desktop was used.

## What Stage 10 can prove in GitHub Actions

The non-invasive command `python scripts/release-gate.py --target ci` verifies
the presence of required source, schema, startup and operational artifacts.
It runs without accounts, real credentials, Windows local services, DNS or
external APIs. Automated unit tests verify that missing prerequisites fail
closed and that a successful source check **never** claims production readiness.

Full CI must additionally pass PostgreSQL migrations, backend pytest, Ruff,
mypy app, frontend lint/format/typecheck/Vitest/build, OpenAPI drift and Windows
PowerShell syntax parsing before Stage 10's **CI milestone** can close.

## Running locally

1. Download/pull the merged `main` repository on the target Windows machine.
2. Follow `scripts/setup.ps1` and create a dedicated local database using the
   documented migration/role process. Back up and verify a restore first.
3. Run `python scripts/release-gate.py --target local`. A `BLOCKED` result is
   **expected**: static inspection cannot attest Windows services, database
   state or interactive browser behavior.
4. Run `scripts/verify.ps1` against the documented isolated test database.
5. Start `scripts/start-local.ps1` in two visible consoles, then verify login,
   company switching, CRM, RFQ, quotes, order, procurement, shipment, finance,
   AI mock, communications and E-YAY disabled state in a real browser.
6. Record a dated test log, screenshots only when privacy-safe, backup/restore
   evidence, accepted known defects and operational owner sign-off.

## Release exclusions

The application can be used **locally in a supported development/demo capacity**
after successfully completing actual setup and Windows browser/DB checks.
It is **not** yet verified as a deployed production trading platform.

- No outbound Gmail/WhatsApp send integration, webhooks, provider auth, or
  recipient opt-in verification exists in the shipped code.
- No live read-only Finance or E-YAY run was verified; both are explicitly
  disabled/fail-closed absent approved external source verification.
- AI real provider use requires separately configured credentials and data
  processing acknowledgement; mock mode remains the verified development path.
- Ledger writes, actual invoices/payments/bank transfers and live trading
  executor must not be fabricated or enabled.
- No TLS reverse proxy, offsite encrypted backups, restore drill, live
  incident monitoring, complete accessibility audit or deployment hardening
  has been demonstrated in this CI environment.

## Release truth states

- `CI_VERIFIED`: all repository CI jobs and static gate pass. **Not production**.
- `LOCAL_ACCEPTED`: manually documented Windows, PostgreSQL and browser
  acceptance, including a tested backup/restore path.
- `EXTERNAL_CONNECTORS_ACCEPTED`: provider-specific security approvals and
  explicit service ownership, verified per connector.
- `PRODUCTION_APPROVED`: deployment/operational security and human acceptance
  recorded separately. No source-code-only script may assert this automatically.

Run `python scripts/release-gate.py --target production` to enumerate blockers
until the separate real-world evidence and authorisations exist. It returns a
non-zero status deliberately; environment flags cannot turn missing evidence
into a green production report.

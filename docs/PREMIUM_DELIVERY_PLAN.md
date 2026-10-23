# TOUCHE COMMERCE — Premium completion plan (Stages 11–20)

**Planning document only.** Created after Stage 10 PR #8 merged as `4ff5518`. This is a proposed implementation and acceptance contract, **not** evidence that any new stage was executed. Stage 10 is `CI_VERIFIED` (GitHub Actions `40030032968`: 585 backend tests, 192 frontend tests; 4/4 CI jobs). `LOCAL_ACCEPTED`, live provider acceptance and `PRODUCTION_APPROVED` have **not** been demonstrated.

## Outcome and scope

Deliver a polished, secure, bilingual (TR/EN) multi-user trade platform accessible from Windows and macOS browsers over a centrally hosted, hardened HTTPS service; retain safe local-development operation; integrate read-only TOUCHE FINANCE and E-YAY, a primary API AI with conditional local-model fallback, and authorization-gated Gmail / WhatsApp Business / social publishing. Do not redesign or duplicate working Stages 0–10. Preserve PostgreSQL tenant isolation, role permissions, auditable immutable evidence, Decimal/currency invariants and financial source-of-truth boundaries.

**Owner requirements and technical decisions (2026-10-24):** [PREMIUM_PLATFORM_DECISIONS.md](PREMIUM_PLATFORM_DECISIONS.md) is the requirements baseline for Stages 11–20. Cloud-first EU hosting; shared PostgreSQL; 5+ users; one operator company with many counterparties; TRY/USD/EUR; manual + CSV/XLSX import; dark TR/EN; professional trade documents; encrypted offsite + local backup. \n\n**Three distinct milestones:**
- **M1: LOCAL_OPERATIONAL** — Stage 11 and critical Stage 12–13 workflows run and pass real Windows/browser/DB tests. Standalone Commerce must work with all external connectors disabled; this is not the shared internet deployment.
- **M2: CONNECTED_OPERATIONAL** — Stage 14–17 connectors and AI each accepted individually; connectors are independently optional and fail closed.
- **M3: PRODUCTION_APPROVED** — Stage 18–20 security, recovery, UAT and deployment evidence accepted by designated operator. This designation cannot be achieved by static CI checks alone.

## Non-negotiable engineering rules

1. One stage = one isolated branch, focused PR, tests, docs/ADR updates, review and merge only after green CI. Maintain a dated, reproducible acceptance record and known defects.
2. For destructive operations (migrations on real DB, data import, cleanup, restore, provider send, financial posting, real orders) require a tested backup and explicit operator authorization. Never overwrite local `.env`, databases or Finance workbooks.
3. Never put credentials, OAuth tokens, personal messages, customer data or actual addresses in GitHub issues, commits, CI logs, screenshots, or user-facing chat. Provide setup steps for local secret entry or secret manager.
4. No Commerce accounting writes, invented actual profit, auto payments, live market order execution, customer commitments, or unauthorized outreach. If these are ever desired, scope and authorize a separate project with its own controls and safety cases.
5. FINANCE is accounting source of truth; Commerce is commercial execution source; E-YAY is paper-safe market context, **not** a command bridge.
6. If a provider is unavailable, keep local Commerce usable, show explicit `NOT_CONFIGURED` / `DEGRADED` state, and never silently simulate successful send, booking, financial reconciliation or an external signal.
7. No unsubstantiated “production ready” claims. Passing code tests does not demonstrate Windows/browser runtime, remote TLS, backed-up storage or live external credentials.

## Stages and evidence requirements

### Stage 11 — Windows local launch and acceptance (P0)
- Establish current workstation/repository baseline, synchronize main safely, check Python 3.12, Node, PowerShell and local PostgreSQL; inspect existing ports/processes without killing them.
- Safely back up and restore an isolated copy before any real migration. Use existing `scripts/setup.ps1`, `scripts/verify.ps1`, `scripts/start-local.ps1`; fix genuine Windows differences.
- Execute real browser login, session rotation, company switching, CRM, catalogue, RFQ, quote, sales order, procurement, partial shipment, documents, Finance-disabled, E-YAY-disabled, mock AI and communications-disabled journeys.
- **Exit:** dated LOCAL_ACCEPTED evidence: environment versions, test outputs, sanitized screenshots, DB role/RLS proof, backup/restore test, operator sign-off. Do not modify live Finance/e-yay state.

### Stage 12 — Premium UI system and accessibility (P0)
- Audit all routes and common patterns. Implement a consistent design system (tokens, typography, spacing, navigation, tables, details, modals, forms, feedback, empty/error/loading states, dashboard).
- Test responsive desktop/tablet/mobile, keyboard-only usage, focus visibility, validation, meaningful accessibility checks; no overflow or hidden essential actions.
- **Exit:** agreed reference screens and visual checklist, real-browser journeys at agreed viewports, frontend tests/build, documented a11y findings and closure of P0/P1 defects.

### Stage 13 — Core trade operational completeness (P0)
- Gap-audit the existing CRM/RFQ/quote/pricing/order/procurement/shipment/document paths before adding anything. Prioritize contact-level CRM, price lists and commercially useful document exports only where genuinely missing.
- Enforce immutable quote revisions, clear approval separation, complete provenance, explicit prices/currencies/incoterms where relevant, evidence-gated fulfilment and operator-visible audit history. No formal posted invoice or payment is created in Commerce.
- **Exit:** operator executes a realistic non-demo RFQ → supplier comparison → quote approval → customer acceptance → order → purchase commitment → partial dispatch/delivery → document register → profitability interpretation without fabricated events, with repeatable tests.

### Stage 14 — Live FINANCE read-only acceptance (P0)
- Use `docs/FINANCE_INTEGRATION_CONTRACT.md`; confirm Finance startup behavior and snapshot strategy; approve company-to-company mappings.
- Configure per-company credentials only in server-side secret storage; use documented loopback authenticated reads. Run read-only permission, negative, currency, freshness, error, cross-tenant and unchanged-source-hash checks against the actual Finance service **only once separately approved**.
- **Exit:** dated authenticated LIVE_READ_ONLY_ACCEPTED record and operator sign-off; no Finance writes, invoice/payment or accounting journal access added.

### Stage 15 — Live E-YAY paper-safe acceptance (P1)
- Verify actual published source endpoints and data semantics, E-YAY `paper_safe`/`no_execution` flags, timestamps, 15-minute freshness guard, whitelist and bounded response. Preserve source provenance.
- Present market context in readable Commerce dashboard/AI tools without importing portfolios, secrets or trading commands.
- **Exit:** LIVE_PAPER_SAFE_READ_ACCEPTED, with stale/unsafe/unavailable fail-closed tests; no automatic trading.

### Stage 16 — AI Trade Director real-provider quality (P1)
- Select provider and data transfer policy; explicitly acknowledge external processing where applicable. Use existing provider-agnostic AI gateway and tool allowlists.
- Implement scenario tests for evidence-backed answers, hallucinated numbers/citations, cross-tenant and prompt-injection attempts, budgets, token spend, timeouts, retries and human-approved proposals.
- **Exit:** real provider smoke test with authorized account, quality/safety evaluation, spend limit, degraded fallback; no AI financial posting, autonomous outreach or trading.

### Stage 17 — Communications provider and consent (P1)
- Determine Gmail workspace/account and Meta WhatsApp Business/Cloud API availability and intended inbound/outbound scope.
- Implement OAuth/key lifecycle and revocation, minimal scopes, scoped secrets, consent evidence and opt-out/suppression checks, human review + explicit send approval, transactional outbox/idempotency and delivery status/webhooks; do not send just because AI approved a draft.
- **Exit:** sandbox/real approved recipient end-to-end send/receive test for each enabled channel; consent and authorization evidence, replay prevention, disabled behavior and incident/rollback plan. Neither channel should block core Commerce availability.

### Stage 18 — Security, backup and operations (P0 for production)
- Threat model, secrets/keys/rotation, MFA and account recovery as specified, Windows ACL and DB hardening, TLS/mTLS where relevant, audit retention, vulnerability and dependency scan, monitoring, alerts, encrypted offsite backup and verified restore, recovery procedures.
- **Exit:** redacted evidence of restore rehearsal, least-privilege review, security tests and an owned incident/runbook. Document targeted RPO/RTO and actual achieved times.

### Stage 19 — End-to-end UAT and performance (P0)
- Representative data set, user/role matrix, cross-company isolation, approvals, correct currency/FX calculations, full trade traceability, finance reconciliation interpretation, optional integrations, export integrity, browser/a11y coverage and stress/failure recovery tests.
- **Exit:** signed UAT checklist, no open P0/P1 defects, measured baseline for agreed performance thresholds, change log and rollback candidate.

### Stage 20 — Release and handover (P0)
- Owner selected **both local operation and shared internet/cloud production** for Windows + macOS browsers. Use an EU-region hosted HTTPS deployment, centrally managed PostgreSQL and private document storage. Keep local Finance/E-YAY/Ollama behind an outbound-authenticated allowlisted connector rather than exposing localhost. Requires domain/hosting, certificates, DNS, secret management, production pipeline, monitored DB and restore-tested cloud + local backups. Do not expose development scripts/services to the public internet.
- Release from a CI-green versioned commit, migrate only with verified backup, execute smoke tests, rollback drill and hand over operator/admin guides.
- **Exit:** operator-approved release manifest, dated production acceptance evidence and operational owner. Default classification remains `NOT_PRODUCTION_APPROVED` until proved.

## Required operator input (non-secret answers only)

Record values as **provided / undecided / not applicable**, never infer missing provider rights:
- **Runtime:** Confirm Windows workstation and repository path (previously `C:\Users\twone\OneDrive\Desktop\touche-commerce`), availability of local PostgreSQL 17, and whether real Commerce data already exists.
- **First rollout:** Local-only, office LAN, VPN/private access, or public internet? Expected users, locations, concurrency and which device/browser profiles matter.
- **Business scope:** Legal company or companies, country, operating currencies, supported languages, staff roles/approvers, and target trade scenarios / required documents.
- **Finance:** Confirm repository/runtime path (previously `C:\ai-excel`), Finance version/start command, permitted read-only mapping and which company IDs should be paired. No passwords/API secrets in chat.
- **E-YAY:** Confirm repository/runtime path, actual installed build/version and whether paper-safe published endpoints are active and accessible.
- **AI:** Choose OpenAI-compatible local/API, Anthropic or other; data residency/preferences and monthly spend cap; configure keys privately.
- **Communications:** Which Gmail/Google Workspace identity? Meta Business Manager, verified WhatsApp Business number and Cloud API configuration status? Desired receive/draft/send scope, consent evidence ownership and sender approver.
- **Premium UX:** Reference brand/style, logo/assets, default language, light/dark preference and must-have dashboards.
- **Production operations:** Domain/hosting decision (if public), responsible operator, encryption/backup location, acceptable data-loss and outage thresholds and whether real customer data will be used in first pilot.

## Work queue and dependencies

1. Stage 11 starts with **no external provider credentials**; offline core operation must be proven first.
2. Stage 12 and 13 can be developed in parallel after the Stage 11 baseline, but their acceptance requires a single real browser validation.
3. Stage 14–17 need approved provider access and explicit non-secret configuration decisions; each remains optional and independently blocked until accepted.
4. Stage 18 and 19 follow the established target deployment model, with operations/security gaps prioritized ahead of release.
5. Stage 20 is last and cannot be waived by green CI. Record blockers rather than upgrading status by changing environment flags.

**Plan status: PROPOSED — operator requirements pending.**

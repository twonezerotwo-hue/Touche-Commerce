# Premium platform decisions — owner answers recorded 2026-10-24

**Status:** DECISIONS_CAPTURED / implementation pending. This document is user-provided requirements and a recommended design, not deployed infrastructure or evidence of live integration. See [PREMIUM_DELIVERY_PLAN.md](PREMIUM_DELIVERY_PLAN.md).

## 1. Confirmed user requirements

| ID | Requirement | Decision / constraint |
| --- | --- | --- |
| R-01 | Device and access | Windows AND MacBook, shared live data, accessible over internet; first 5 users, no fixed upper bound |
| R-02 | Business domain | One primary company as operating business; manage unlimited customer/supplier companies and their offers, product catalogs, quoted and historical prices. Do **not** infer each trading counterparty is a tenant |
| R-03 | Currency | TRY, USD, EUR; per-transaction ISO currency + source/effective-date FX snapshots, no silent netting across currencies |
| R-04 | Users | Distinct people with role-based permissions and approval separation |
| R-05 | Inputs | Both manually entered records and imported Excel files (CSV/XLSX), with validated mappings |
| R-06 | Finance runtime | Existing Windows installation at `C:\ai-excel`; live read-only integration needed, mapped by explicit IDs |
| R-07 | E-YAY runtime | Production source `C:\dev\clean-e-yay`; brief: `packages\agent\llm\premium_brief.py`; world report: `packages\agent\llm\world_report.py`. `D:\Clean E-yAy` is backup, do not touch |
| R-08 | AI | API primary. On quota/rate-limit/outage or provider unavailability, immediately fail over to locally hosted LLM if safe and reachable; no fake “local answered” state |
| R-09 | Communications | Gmail, business WhatsApp and social publishing requested; workflow should be feature-complete subject to provider onboarding, consent, roles and approval |
| R-10 | UI | Premium dark mode, fully supported Turkish + English language selection; design delegated to implementation team |
| R-11 | Documents | No existing templates. Provide professional templates and import/export for commercial artifacts, with review for unstructured inputs |
| R-12 | Backup/deployment | Internet access plus local use; maintain both encrypted cloud backups and verified local copies |

## 2. Approved technical direction for design (requires real deployment acceptance)

### Cloud-first application / multi-device access
- Recommended: EU-region centrally hosted HTTPS web application with stateless Next.js frontend and FastAPI backend, centrally managed PostgreSQL 17 and encrypted private object storage for documents.
- Windows and macOS access the same tenant from browser. No duplicated authoritative local database or per-device sync conflict.
- Initial capacity target: five named users, test to a configurable capacity; do not claim unlimited concurrency. Scale stateless app and database based on measured load. Mobile responsive UI is included even though native app is not required.
- Offer a private initial pilot URL; public availability requires chosen domain/organization ownership, TLS, production operations and legal/privacy acceptance. Do not publish Windows development ports 3000/8000/5432 or localhost secrets to the internet.
- Existing company row(s) are operating tenants. Customer/supplier companies belong to active business's CRM with counterparty contacts and historical prices; maintain the established PostgreSQL row level security for operating-tenant isolation.

### Local source connector gateway (new contract required)
- Live Finance, E-YAY and Ollama stay on authorized local Windows infrastructure. No inbound public network port to them.
- Proposed **outbound-initiated authenticated on-prem connector agent** reads only allowlisted local endpoints; agent pushes signed, bounded, provenance/freshness-marked snapshots or executes precisely authorized read requests through a mutually authenticated protected channel. Separate tenant-scoped keys, rotation, scope allowlist, audit, no generic remote command execution.
- Finance remains authoritative accounting. Cloud stores only permitted read-only derived snapshots/reconciliation references. For finance data: approval on classes/retention/encryption required; no writeback.
- E-YAY remains paper-safe reporting only: read published health/regime outputs, provenance and freshness guards, **never** invoke the brief/report Python files remotely as arbitrary commands or expose portfolio positions/trade executor. Those paths describe source locations for contract validation, not APIs to call.
- The connector service and local AI fallback need an **always-on** office machine/host. If offline, show `CONNECTOR_UNAVAILABLE` or `LOCAL_MODEL_UNAVAILABLE`; global Commerce stays available.
- New design must honor existing Finance/E-YAY loopback restrictions; do not weaken SSRF host validation to enable cloud requests.

### Product modules / data correctness
- Company-specific counterparty/contacts, SKU/product catalogs, supplier- and customer-specific prices, effective dates, tiers/currencies, quote versions, RFQs, source evidence, audit and permissions.
- CSV/XLSX import with preview, column mapping, duplicate detection, data validation, per-row error report, idempotent safe commit, downloadable failure report and rollback strategy. Never overwrite price history or send messages by import alone.
- Existing trade state machines and customer acceptance remain source of truth. Distinguish draft commercial invoice/document from posted accounting invoice owned by Finance.

### Document center
- Templates: Request for Quotation, supplier quotation, sales quotation, proforma invoice, commercial invoice **draft only**, packing list, purchase order, order confirmation and relevant shipping/document register exports; branded versions in TR/EN.
- PDF generation and download; structured CSV/XLSX export; editable DOCX or XLSX when justified by format. Existing PDF/Office files can be uploaded, stored, versioned, attached and metadata extracted with human validation; importing arbitrary PDF documents is not equivalent to guaranteed correct transactional data extraction.
- Currency, Incoterms (per chosen ICC revision), company identity and shipment trade data must be validated before document finalization. No fabricated signatures, customs validation, payments or legal invoice postings.

### User roles and identity
- Preserve existing viewer/trader/approver/admin role rules and finance segregation. Future business-role UI profiles (Owner/Admin, Sales, Procurement, Logistics, Finance Reviewer, Approver, Read-only) must map to explicit tested permissions, not introduce implicit privileged aliases.
- MFA, invite/revoke, session rotation, immutable audit, scoped company/record access, dual approval for commitments above policy thresholds, delegated access and action logs.

### AI execution policy
- Primary configurable API: provider to be chosen; local Ollama on approved always-on host. Select fallback on verified timeout/429/quota or service errors, not on arbitrary hallucination. Bound retries, time-to-first-response, workload concurrency, budget and user privacy.
- For each answer show source/provenance and which provider actually answered. Local fallback is conditional on its availability; otherwise return accurate actionable degradation. Protect trade secrets; user approval for external AI processing is a separate setting.
- AI may read, classify, draft, propose offers/tasks/social posts, prepare commercial messages; **cannot unilaterally issue binding offers, approve its own proposals, post accounting entries, transfer funds or place market orders.**
- All externally visible send/publish actions must follow channel consent, role-based scopes, administrator-controlled policy and logged approvals. Individual low-risk rule-based automatic replies may be added in a separately scoped post-review capability, never free-form unsupervised bulk outreach.

### Communications and marketing
- Gmail: OAuth 2.0 minimal scopes per feature (read, draft, send) with scope verification/security assessment *where applicable*; provider connection per authorized account and secure revocation. Incoming mail, threading, case/RFQ linking, draft generation, explicit outbound approval and delivery/error status.
- WhatsApp Business: Meta Business/Cloud API onboarding, number, webhooks, verified consent/opt-out, suppression list, channel rules, approved templates and messaging windows. Never bypass provider policies or imply a personal WhatsApp account is Cloud API-capable.
- Social: choose actual platforms (e.g. LinkedIn/Instagram/Facebook) after provider inventory. Editorial calendar, generated drafts, human review, post scheduling/publishing via official APIs, audit and post metrics only with authorized scopes.
- Per-account policies separate reply vs marketing, send vs draft and company owner vs operator; no cross-company contact mixing.

### Appearance and internationalization
- Premium dark-first visual system with typographic hierarchy, dense but legible B2B tables, reusable dashboards, command bar, search, global filters, approval inbox, consistent states and responsive desktop/tablet.
- Complete `tr-TR` and `en` localization: navigation, fields, errors, data formats, templates and screen-reader labels. Store stable currency codes and UTC timestamps; render locale-specific dates/number formats. Keep underlying quoted text in original language unless translated on request.

### Security, resilience, and release
- EU data location preferred with documented DPA/processor/access policies and GDPR review for customer/contact/communications data.
- Managed database backup + encrypted remote object storage + separate encrypted local backup copies; rotate, alert on failure and **test restore**. Record RPO/RTO after operator agrees. A backup copy is not sufficient without a successful restoration.
- Cloud secret management, key rotation, audited admin controls, network ACL/WAF/rate-limit, penetration/security testing proportional to exposed surface, logging/alerts and incident on-call owner.
- Release states: `CI_VERIFIED` → `LOCAL_ACCEPTED` → `CONNECTED_ACCEPTED` per source → `PRODUCTION_APPROVED` (human evidence-based). No automatic promotion.

## 3. Work sequencing after these answers

1. Stage 11: verify real local Windows baseline and backup/restore; make local existing app usable without any remote provider first.
2. Stage 12–13: implement final dark TR/EN UX, CRM price-history and controlled Excel/document workflows; real-browser UAT.
3. In parallel plan and provision EU cloud environment/central DB; migrate *only after backup, migration rehearsal and access review*.
4. Stage 14–16: introduce outbound private Windows bridge and independently accept live Finance/E-YAY read contracts and API→Ollama failover.
5. Stage 17: official Gmail/WhatsApp/social provider onboarding, safe consent and authorized delivery.
6. Stage 18–20: harden infrastructure, recovery, performance, operator UAT, release sign-off.

## 4. Remaining decisions / owner inputs (non-secret)

| Priority | Question | Why it is needed | Default until answered |
| --- | --- | --- | --- |
| REQUIRED | Official legal name of operating company, country of registration and logo? | Document headers, legal terms, tenancy profile | Placeholder; no real legal documents issued |
| REQUIRED | Domain name: existing domain or purchase one, and who controls DNS? | HTTPS identity, Gmail OAuth consent, WhatsApp/social callbacks | Private staging address only |
| REQUIRED | Monthly target hosting + storage budget range? | Select appropriately managed EU hosting and backups | No provider charges/provisioning |
| REQUIRED | What is the primary Gmail account type (personal Gmail vs Google Workspace) and who can authorize OAuth? | Correct authentication/verification procedure | Gmail disabled; UI can be developed |
| REQUIRED | Meta WhatsApp Business Platform/Cloud API: available or not yet? | Live channel onboarding | WhatsApp disabled; prereq workflow developed |
| REQUIRED | Social platforms to support initially? | Scope official APIs and permissions | Draft-only calendar; platform connectors optional |
| REQUIRED | Which AI API provider to use first, and accepted cloud-processing categories/budget? | Implement real provider adapter and cost controls | Existing mock mode; plan fallback |
| REQUIRED | Is one Windows machine/mini-server permitted to stay on as the secure connector/local AI host? | Finance/E-YAY/local model availability to remote users | Connector not active |
| REQUIRED | Expected backup restoration time and permitted data-loss window? | RTO/RPO and monitoring | No production claims; conservative interim backup defaults |

**Secrets, OAuth refresh tokens, passwords, bank details, raw client lists and customer data must never be copied into GitHub or chat.**

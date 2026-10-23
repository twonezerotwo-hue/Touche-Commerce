# $0 hosting pilot decision — Stage 11/18 infrastructure gate

**Decision state:** PROPOSED, NOT PROVISIONED, NOT PRODUCTION APPROVED. Owner explicitly confirmed **company in Türkiye**, **$0 recurring hosting cost**, **no payment card supplied**, >=5 Windows/macOS browser users and a long-term aspiration for cloud-primary availability without an always-on personal PC. This combination cannot guarantee 24/7 availability today. Oracle signup is **blocked by card verification**. First milestone is local Windows + MacBook LAN acceptance; optional internet preview uses only synthetic records and cardless free-tier evaluation, never real customer trade data.

## Deployment candidates and selection

| Option | Pilot fit | Business-use and financial risk |
| --- | --- | --- |
| Oracle Cloud Always Free ARM VM (Linux) | **BLOCKED**. Oracle explicitly requires credit/debit-card payment verification. Owner has not added a card. | No attempt to bypass verification; no credentials or payment method requested in chat. Not the current recommended path. |
| Existing Windows PC hosting | **Immediate $0/no-card starting path**. Existing FastAPI+Next.js+PostgreSQL can run, and Windows/MacBook browsers use the same test database on the LAN only after secure host-binding, Windows firewall, network ACL, auth/session/cookie/CSRF and browser verification. | Only available while PC is on; not automatically internet-accessible. Existing loopback-only launcher does **not** provide LAN access, so a separate security-reviewed LAN mode is required; never expose existing development listeners blindly. |
| Tailscale Personal / ZeroTier Personal | Not selected for commercial access. | Personal free plans have **non-commercial/personal-use restrictions**; do not use them as a disguised free business VPN. |
| Cloudflare Zero Trust free access | Optional access control layer to evaluate after origin and DNS arrangement. | Free tier of Access is not a replacement for paid compute, an owned domain, authoritative storage, on-prem connectivity or backup/restore. |
| Render Free web service + Neon Free PostgreSQL | **Candidate for disposable/synthetic remote demonstration** if sign-up without a card and account/plan terms are confirmed. Render supports Node and Python web services; Neon retains PostgreSQL dialect but free storage/compute and backup safeguards are constrained. | Render sleeps after ~15 min idle and explicitly disclaims production readiness. Combined quotas and deployment of both backend/frontend must be tested; not a live business-data system. No cost or uptime guarantee. |
| Prisma Compute/Postgres Free | Cardless candidate for **frontend/TypeScript app portions**, NOT a direct replacement for the present FastAPI Python backend. | Compute supports Node/Bun/Next.js, not a drop-in Python API host; avoid unnecessary replatforming just to fit a trial. |

Sources verified 2026-10-24:
- Oracle payment verification: https://docs.oracle.com/en-us/iaas/Content/GSG/Tasks/signingup_topic-Sign_Up_for_Free_Oracle_Cloud_Promotion.htm
- Render free + payment limits: https://render.com/docs/free and https://render.com/docs/faq
- Neon free: https://neon.com/pricing
- Prisma Compute runtime restrictions: https://www.prisma.io/docs/compute
- Cloudflare access tier: https://www.cloudflare.com/plans/
- Tailscale personal-use constraints: https://tailscale.com/pricing
- ZeroTier personal-use constraints: https://www.zerotier.com/pricing/

## Architecture (zero forced local host uptime)

- **Two gated profiles**: (1) local-only LAN UAT on Windows + MacBook with one test PostgreSQL, and (2) synthetic-only no-card hosted preview if third-party accounts/quota can be verified. Ultimate business production remains separately blocked until funded/reliable hosting, encryption, compliant storage, backups and internet access are in place. The free remote preview may not be durable.
- Use managed HTTPS with validated hostname once a domain is controlled; `canwetouche.com` has expired and **may not be available**. Temporary pilot access address with valid HTTPS is acceptable only after ownership/security check; never issue customer-facing document links on an unverified hostname.
- Finance (`C:\ai-excel`), E-YAY (`C:\dev\clean-e-yay`) and Ollama run on Windows and connect to the cloud **outbound only** via strongly authenticated allowlisted connector after security review. Windows offline -> source data stale/unavailable; no raw public localhost ports. Commerce remains usable without the connectors.
- DeepSeek API is primary; **USD 10/month combined cap**. Plan a backend reservation-based, concurrency-safe budget mechanism and fallback for 402/429/timeout/5xx. Provider prepaid spend controls, if supported, are a second layer. No guarantee spending cannot exceed exactly $10 solely from application counters without accounting for billing lag. Expose provider and real cost per request.
- Keep a manual fallback channel for data entry and exports if any external provider is blocked.
- Handle customer records only within authorized company; no externally public databases or object buckets.

## Backups under $0

- Daily encrypted database and document backups with tested restore; retention and actual available free external quota must be checked.
- Local offline encrypted copy **and an independent cloud copy** (not simply a second folder on the same Oracle VM). Existing personal cloud storage may be evaluated if owner approves sharing terms, quota and data-protection implications. Never upload unencrypted contracts, customer lists, API keys or accounting files.
- A successful backup job is NOT proof of restore; require a dated isolated restore drill. Choose conservative RPO/RTO for pilot and disclose the limits. Do not claim disaster recovery until a second failure domain is verified.
- Do not sacrifice least privilege, MFA, TLS or proper credential rotation to meet zero budget.

## Operational acceptance checklist

- [ ] Record `ORACLE_BLOCKED_CARD_VERIFICATION`; do not request owner's card.
- [ ] Local Windows/MacBook LAN test succeeds with no unapproved public port exposure.
- [ ] If hosted preview selected, verify Render + Neon signup without a card, acceptable commercial terms and disposable synthetic-only records.
- [ ] For any provider, verify allowed region and runtime compatibility with exact FastAPI/Next.js dependency locks.
- [ ] Provision and protect central VM, private PostgreSQL, host firewall, minimal ports, HTTPS and secrets.
- [ ] Five distinct role-based user accounts, login/CSRF/session/membership isolation, key admin recovery.
- [ ] Real MacBook and Windows browser UAT; no direct public DB listener.
- [ ] Simultaneous edits/approvals and document round trips tested.
- [ ] Encrypted remote+local backup and isolated restore evidence; response to VM loss rehearsed.
- [ ] Finance/E-YAY on-prem sources offline during core Commerce workflow; core remains functional.
- [ ] Cost dashboard/alerts demonstrate actual recurring infrastructure spend is $0, or release is blocked.
- [ ] Human acceptance and sign-off. Until then: `PILOT_PLANNED`.

## Dependencies requiring owner action

1. **Do not ask for Oracle card setup.** The onboarding route was attempted and blocked by mandatory card verification. For optional remote preview, the owner may authorize a no-card free service signup, and development proceeds without it in local-only mode.
2. For an eventual branded domain, renew/re-register or buy available hostname separately; under a $0 domain budget do not assume `canwetouche.com` is owned.
3. Confirm official company registration details and a separate business contact identity before live external account setup.
4. OAuth/Meta/DeepSeek onboarding with credentials entered through a trusted secret store, never GitHub.

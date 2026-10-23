# $0 hosting pilot decision — Stage 11/18 infrastructure gate

**Decision state:** PROPOSED, NOT PROVISIONED, NOT PRODUCTION APPROVED. Owner has explicitly selected **$0 recurring hosting cost**, >=5 Windows/macOS browser users, a cloud-primary shared database, no always-on dependence on their Windows desktop. The real onboarding of cloud, domain, IAM, providers and billable resources requires separate operator authorization.

## Deployment candidates and selection

| Option | Pilot fit | Business-use and financial risk |
| --- | --- | --- |
| Oracle Cloud Always Free ARM VM (Linux) | **Preferred test candidate** for FastAPI + Next.js + PostgreSQL with limited initial users, if free Arm capacity, approved region and quotas are actually available. | Cannot guarantee placement, continuity, resources or 24/7 SLA; underutilized free instances may be reclaimed. Protect data with **independent** backups. Never upgrade/pay automatically. |
| Existing Windows PC hosting | Local fallback only for testing; browser devices on same private network or via separately approved private gateway. | Host power, updates and availability depend on Windows; owner says continuous operation is undesirable. Not the default shared production architecture. |
| Tailscale Personal / ZeroTier Personal | Not selected for commercial access. | Personal free plans have **non-commercial/personal-use restrictions**; do not use them as a disguised free business VPN. |
| Cloudflare Zero Trust free access | Optional access control layer to evaluate after origin and DNS arrangement. | Free tier of Access is not a replacement for paid compute, an owned domain, authoritative storage, on-prem connectivity or backup/restore. |
| Free PaaS plans | Only if another candidate is objectively supportable and terms allow business use. | Sleep/expiry/storage/CPU/request limits often conflict with an operational trade system; no production approval on assumptions. |

Sources verified 2026-10-24:
- Oracle: https://docs.oracle.com/en-us/iaas/Content/FreeTier/freetier_topic-Always_Free_Resources.htm
- Cloudflare access tier: https://www.cloudflare.com/plans/
- Tailscale personal-use constraints: https://tailscale.com/pricing
- ZeroTier personal-use constraints: https://www.zerotier.com/pricing/

## Architecture (zero forced local host uptime)

- Browser TR/EN premium Next.js app -> private FastAPI backend -> centrally hosted PostgreSQL + encrypted private document files. The server's **free allocation is unproven** until resources are provisioned and load tested.
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

- [ ] Owner has verified a no-charge OCI account and accepted free-usage restrictions; no paid upgrade.
- [ ] Choose available allowed region and host architecture; ARM compatibility verified for exact dependency locks.
- [ ] Provision and protect central VM, private PostgreSQL, host firewall, minimal ports, HTTPS and secrets.
- [ ] Five distinct role-based user accounts, login/CSRF/session/membership isolation, key admin recovery.
- [ ] Real MacBook and Windows browser UAT; no direct public DB listener.
- [ ] Simultaneous edits/approvals and document round trips tested.
- [ ] Encrypted remote+local backup and isolated restore evidence; response to VM loss rehearsed.
- [ ] Finance/E-YAY on-prem sources offline during core Commerce workflow; core remains functional.
- [ ] Cost dashboard/alerts demonstrate actual recurring infrastructure spend is $0, or release is blocked.
- [ ] Human acceptance and sign-off. Until then: `PILOT_PLANNED`.

## Dependencies requiring owner action

1. OCI account signup and payment-authorization handling if requested by provider. This is performed **by the owner in Oracle directly**, not by supplying card details in chat.
2. For an eventual branded domain, renew/re-register or buy available hostname separately; under a $0 domain budget do not assume `canwetouche.com` is owned.
3. Confirm official company registration details and a separate business contact identity before live external account setup.
4. OAuth/Meta/DeepSeek onboarding with credentials entered through a trusted secret store, never GitHub.

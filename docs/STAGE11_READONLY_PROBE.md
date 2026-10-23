# Stage 11A — Cross-platform, read-only acceptance probes

**Status:** Implemented as a repository-side diagnostic. It has **not** been run
against the owner's Windows 11 or MacBook. This is a small, safe part of Stage 11,
not a claim that the trade application, LAN deployment or any cloud production is
ready. Stage 11 remains open.

## Purpose

`scripts/acceptance_probe.py` is Python 3.12 standard-library-only and can run
on Windows or macOS. It checks whether the public, unauthenticated login,
status, liveness and readiness pages return HTTP 200. It never logs in, sends
customer messages, reads business data, runs a database migration, changes
system configuration, writes backups or contacts external providers.

The CLI always reports `local_accepted=false` and
`production_approved=false` even when every probe passes.

### 1. Windows, local runtime

First start PostgreSQL and Touche's existing local backend/frontend using
the current documented scripts. From the repository root:

```powershell
py -3.12 scripts\acceptance_probe.py --mode local
```

The defaults are `http://localhost:3000` and
`http://127.0.0.1:8000`. All four checks must return HTTP 200 for a green
`PROBES_PASS`; 503, 302, network failures and timeouts remain blocked.
A passing result does **not** prove that users can log in or work with orders.

### 2. MacBook / private LAN, only after separately deploying verified TLS

```bash
python3 scripts/acceptance_probe.py --mode lan --frontend https://192.168.1.23:8443
```

LAN mode intentionally rejects plaintext HTTP, DNS hostnames, public IPs,
loopback IPs and credentials in URLs. The browser frontend must be served over
**trusted HTTPS** with an appropriate certificate containing the private IP
address and restricted to the private LAN. This command does **not** set that
up and the existing `scripts/start-local.ps1` remains deliberately bound to
localhost. Do not change its bind address to `0.0.0.0` or forward ports on
the home router as a shortcut. Configuring safe LAN TLS, proper session
cookies, CSRF/origin handling, host firewall, cross-device browser testing and
rollback is a **future Stage 11 task**.

The MacBook check without `--backend` probes only the frontend login/status
routes. It says nothing about backend DB or trading readiness. Supply a
separately authorized backend HTTPS origin if the LAN topology supports
read-only backend checks; **never** expose PostgreSQL.

The probe disables proxy environment forwarding and HTTP redirects. It logs
only a whitelisted check name, status and HTTP code, never HTML, response bodies
or credentials.

## Separate required acceptance evidence

- [ ] Actual Windows startup and `scripts/verify.ps1` on isolated test DB
- [ ] RLS and actor/company role matrix in a real browser
- [ ] Real quote/order/procurement/shipment/document workflows
- [ ] Windows and MacBook sessions with verified HTTPS and CSRF protections
- [ ] Backup made, restore rehearsed on separate test DB
- [ ] Error handling and service restart/recovery
- [ ] Date, environment versions, known defects and operator sign-off

**Do not** merge a security-weakened LAN listener solely to pass this diagnostic.
No provider keys are needed and none should be pasted into GitHub or chat.

# TOUCHE COMMERCE — API contracts

**Version:** v1 · Stages 0–6 documented as implemented. Stage 7A communications
discovery is in progress; local validation and client regeneration remain pending.
**Source of truth:** `backend/app/api/v1/schemas/*` → `/api/v1/openapi.json` →
`frontend/src/lib/api/schema.d.ts`.

---

## 1. General conventions

| Item | Contract |
| ---- | -------- |
| Base URL (local) | `http://127.0.0.1:8000` (browser calls `http://localhost:3000/api/v1/*`, proxied same-origin) |
| Namespace | `/api/v1` (breaking changes require `/api/v2`) |
| Content type | `application/json; charset=utf-8` |
| Authentication | `touche_session` cookie (`__Host-touche_session` outside local dev), `HttpOnly`, `SameSite=Lax`, `Secure` outside local dev |
| CSRF | `X-CSRF-Token` header required on every authenticated non-GET request |
| Origin validation | Every non-GET request must carry a trusted `Origin` header, including `/auth/login` |
| Request correlation | `X-Request-ID` header, echoed on every response |
| Idempotency | `Idempotency-Key` header on mutating requests (required for deal transitions) |
| Concurrency | `ETag` response header + `If-Match` request header on versioned resources |
| CORS | Local origins only (`http://localhost:3000`, `http://127.0.0.1:3000`) |
| Caching | Session-bearing responses are `Cache-Control: no-store`; status pages are `force-dynamic` |


### 1.1 Request id

`X-Request-ID` is accepted from the caller only when it matches
`^[A-Za-z0-9._:-]{8,128}$`. Otherwise the server generates a 32-character hex id.
The value is returned in the response header and in `error.request_id`, and it
appears on every log line for that request.

### 1.2 Error envelope

Every non-2xx response has this shape (and only this shape):

```json
{
  "error": {
    "code": "NOT_READY",
    "message": "The service is not ready to handle requests.",
    "request_id": "5ec658eba7774b3081c5ca2ee62bbca3",
    "timestamp": "2026-10-22T22:37:17.631330+00:00",
    "details": {
      "status": "not_ready",
      "checks": [
        {
          "name": "database",
          "status": "error",
          "latency_ms": 3012.47,
          "detail": "connection timeout expired",
          "error_code": "DATABASE_UNAVAILABLE"
        }
      ]
    }
  }
}
```

* `code` is the contract; `message` is for humans and may change wording.
* `details` is `null` or a structured object/list; its shape depends on `code`.
* `timestamp` is UTC ISO-8601. `request_id` is never omitted.

### 1.3 Error codes

| Code | HTTP | Meaning |
| ---- | ---- | ------- |
| `BAD_REQUEST` | 400 | Malformed request that is not a validation error |
| `VALIDATION_ERROR` | 422 | Field-level validation failed; `details` lists `field`, `message`, `type` |
| `UNAUTHORIZED` | 401 | Missing, expired or revoked session |
| `SESSION_EXPIRED` | 401 | Session existed but reached its idle or absolute timeout |
| `ORIGIN_REJECTED` | 403 | `Origin` missing or not trusted on a state-changing request |
| `CSRF_REJECTED` | 403 | `X-CSRF-Token` missing or not bound to the presented session |
| `FORBIDDEN` | 403 | Authenticated but not permitted, or no active membership |
| `NOT_FOUND` | 404 | Unknown route or resource |
| `METHOD_NOT_ALLOWED` | 405 | Wrong HTTP method |
| `CONFLICT` | 409 | Generic state conflict (duplicate name/SKU, closed deal) |
| `VERSION_CONFLICT` | 409 | Stale `If-Match` version; response carries the current `ETag` |
| `IDEMPOTENCY_CONFLICT` | 409 | Reused key with a different payload |
| `IDEMPOTENCY_IN_PROGRESS` | 409 | Duplicate in-flight request; honour `Retry-After` |
| `IDEMPOTENCY_KEY_REQUIRED` | 400 | The endpoint requires an `Idempotency-Key` header |
| `ALREADY_WON` | 409 | Deal already WON; no second order is created |
| `INVALID_TRANSITION` | 409 | The state machine has no such edge; `details.allowed` lists targets |
| `TRANSITION_DISABLED` | 409 | The edge exists in the domain but is not implemented (WON until orders) |
| `REASON_REQUIRED` | 422 | LOST/CANCELLED without a 3–500 character reason; `details` lists the field |
| `PRECONDITION_REQUIRED` | 428 | `If-Match` is required for this mutation |
| `PAYLOAD_TOO_LARGE` | 413 | Body exceeds the configured limit |
| `RATE_LIMITED` | 429 | Login or request rate limit exceeded |
| `NOT_READY` | 503 | A required dependency is unavailable (readiness) |
| `SERVICE_UNAVAILABLE` | 503 | Temporary unavailability not tied to readiness |
| `INTERNAL_ERROR` | 500 | Unexpected server error (opaque; correlate via `request_id`) |
| `HTTP_ERROR` | 4xx/5xx | Mapping fallback for framework-level errors |

Clients must treat unknown codes as generic failures and display `message` plus
`request_id` for support.

### 1.4 Validation error details

FastAPI/Pydantic errors are normalised to:

```json
{
  "error": {
    "code": "VALIDATION_ERROR",
    "message": "Request validation failed.",
    "request_id": "…",
    "timestamp": "…",
    "details": [
      { "field": "query.limit", "message": "Input should be less than or equal to 100", "type": "less_than_equal" }
    ]
  }
}
```

---

## 2. Health endpoints (implemented)

### 2.1 `GET /api/v1/health/live`

Liveness. Proves the process can serve HTTP. **Never** touches PostgreSQL,
caches or the network. A dependency outage must not cause an orchestrator to
restart a healthy process.

**Response 200**

```json
{
  "status": "ok",
  "service": "touche-commerce-api",
  "version": "0.1.0",
  "environment": "local",
  "checked_at": "2026-10-22T22:28:53.886659Z"
}
```

| Field | Type | Notes |
| ----- | ---- | ----- |
| `status` | `"ok"` | Literal; anything else is a contract break |
| `service` | string | `touche-commerce-api` |
| `version` | string | Application version from configuration |
| `environment` | string | `local` / `test` / `ci` / `staging` / `production` |
| `checked_at` | datetime | Server UTC, ISO-8601 |

### 2.2 `GET /api/v1/health/ready`

Readiness. Verifies required dependencies — currently PostgreSQL via the
least-privilege runtime role (`SELECT current_setting('server_version'),
current_user` and `SELECT 1`).

**Response 200**

```json
{
  "status": "ready",
  "service": "touche-commerce-api",
  "version": "0.1.0",
  "environment": "local",
  "checked_at": "2026-10-22T22:28:53.868819Z",
  "checks": [
    {
      "name": "database",
      "status": "ok",
      "latency_ms": 1.61,
      "detail": "PostgreSQL 17.6 reachable as role 'touche_app'.",
      "error_code": null
    }
  ]
}
```

**Response 503 — dependency unavailable**

```json
{
  "error": {
    "code": "NOT_READY",
    "message": "The service is not ready to handle requests.",
    "request_id": "9f1c2b7d4a8e4c1b9d0e5f6a7b8c9d0e",
    "timestamp": "2026-10-22T22:37:17.631330+00:00",
    "details": {
      "status": "not_ready",
      "checks": [
        {
          "name": "database",
          "status": "error",
          "latency_ms": 3012.47,
          "detail": "connection timeout expired",
          "error_code": "DATABASE_UNAVAILABLE"
        }
      ]
    }
  }
}
```

Readiness never raises: driver failures are converted into `DATABASE_UNAVAILABLE`
with a sanitised message (no DSN, no credentials) and a bounded length.

**Other readiness error codes:** `DATABASE_NOT_CONFIGURED` (no DSN supplied in the
test harness), `DATABASE_UNAVAILABLE` (connection/query failure).

**Client guidance:** probe liveness every 10–30 s with a timeout above the
readiness budget (the frontend uses 10 s because the backend connect timeout is
3 s). Treat 503 as "degraded, do not route traffic", not as a crash.

### 2.3 Service descriptor `GET /`

```json
{
  "service": "touche-commerce-api",
  "version": "0.1.0",
  "environment": "local",
  "api": "/api/v1",
  "docs": "/docs",
  "liveness": "/api/v1/health/live",
  "readiness": "/api/v1/health/ready"
}
```

Not versioned; used for discovery only.

### 2.4 OpenAPI document

`GET /api/v1/openapi.json` returns OpenAPI 3.1. Interactive docs at `/docs`
(disabled in production). The document is exported to
`frontend/openapi/openapi.json` and converted to TypeScript.

---

## 3. Pagination (implemented in Stage 1B)

List endpoints accept `limit` (default **25**, max **100**) and an opaque
`cursor`. Offset/page-number pagination is not used because trade data mutates
while users browse.

```http
GET /api/v1/trade-deals?limit=25&cursor=eyJpZCI6...
```

```json
{
  "items": [],
  "next_cursor": "eyJpZCI6...",
  "has_more": true
}
```

* `next_cursor` is `null` on the last page.
* `limit > 100` → `422 VALIDATION_ERROR`.
* Cursors are opaque, encoded server-side and bound to the filter set; a cursor
  from another filter combination is rejected with `422`.

---

## 4. Idempotency (implemented in Stage 1B)

Mutating endpoints accept `Idempotency-Key` (client-generated, 8–128 chars).

| Situation | Behaviour |
| --------- | --------- |
| First use | Operation executes; key + fingerprint + response recorded (TTL 24 h) |
| Same key, same fingerprint, completed | Original status/body replayed, header `Idempotent-Replay: true` |
| Same key, same fingerprint, still running | `409 IDEMPOTENCY_IN_PROGRESS`, `Retry-After: 1` |
| Same key, different fingerprint | `409 IDEMPOTENCY_CONFLICT` |
| No key on a mutating endpoint | Allowed for non-critical writes; required where the contract says so (deal transitions, order creation, approvals, finance postings) |

Scope: `(company_id, actor_id, endpoint, key)`. The same key in another company
is a different operation. Records are stored in PostgreSQL with a unique
constraint, so concurrent duplicates are serialised by the database rather than
by application locks.

---

## 5. Optimistic concurrency (implemented in Stage 1B)

Versioned resources return `ETag: "v{version}"` and a `version` field.

```http
PATCH /api/v1/deals/{id}
If-Match: "v7"
Content-Type: application/json

{ "title": "Updated" }
```

| Condition | Response |
| --------- | -------- |
| `If-Match` missing where required | `428 PRECONDITION_REQUIRED` |
| `If-Match` stale | `409 VERSION_CONFLICT` (includes current `ETag`) |
| Match | `200` with the new `ETag` |

`412 Precondition Failed` is not used; the contract standardises on `428` and
`409` as described in ADR-013.

---

## 6. Authentication, sessions and company selection (implemented)

### 6.0 Common session payload

`POST /auth/login`, `GET /auth/me` and `POST /session/company` return the same
shape:

```json
{
  "user": {
    "user_id": "5f0c1d0e-2f8f-4c55-9a64-2a5f3d7b8c11",
    "email": "amina@touche.example",
    "display_name": "Amina Haddad",
    "status": "active"
  },
  "session": {
    "session_id": "a8c9e0f1-1b2c-4d3e-8f90-1234567890ab",
    "company": {
      "company_id": "8f14e45f-ceea-4b7b-9d0b-9d1f0f2b7c11",
      "name": "TOUCHE Trading",
      "country": "GB",
      "default_currency": "GBP",
      "status": "active",
      "role": "admin",
      "permissions": ["audit.view", "company.view", "membership.manage", "settings.manage", "settings.view"]
    },
    "created_at": "2026-10-22T08:00:00Z",
    "last_activity_at": "2026-10-22T08:12:31Z",
    "idle_expires_at": "2026-10-22T08:42:31Z",
    "expires_at": "2026-10-22T20:00:00Z",
    "csrf_token": "sD3…43chars",
    "ip_address": "127.0.0.1",
    "user_agent": "Mozilla/5.0 …"
  },
  "memberships": [
    {
      "company_id": "8f14e45f-ceea-4b7b-9d0b-9d1f0f2b7c11",
      "name": "TOUCHE Trading",
      "country": "GB",
      "default_currency": "GBP",
      "status": "active",
      "role": "admin",
      "permissions": ["audit.view", "company.view", "membership.manage", "settings.manage", "settings.view"]
    }
  ]
}
```

Rules:

* The session token is **never** in the body — only in the `Set-Cookie` header.
* `session.company` is `null` until a company is chosen. It is auto-selected only
  when the user has exactly one active membership.
* `permissions` is derived server-side from the role (`viewer`, `trader`,
  `approver`, `admin`). `finance.approve` belongs to `approver` only — `admin`
  never receives it (ADR-003).
* Session-bearing responses carry `Cache-Control: no-store` and `Vary: Cookie`.

### 6.1 `POST /api/v1/auth/login`

```http
POST /api/v1/auth/login
Origin: http://localhost:3000
Content-Type: application/json

{ "email": "amina@touche.example", "password": "…" }
```

Behaviour:

1. **Rate limit first** — 10 failed attempts per account and 30 per source IP per
   300 s (configurable). Exceeding either returns `429 RATE_LIMITED` with
   `Retry-After`, even when the password is correct.
2. Look up the account by normalised email and verify with Argon2id. Unknown
   accounts run an equivalent dummy verification so response time does not reveal
   existence.
3. Disabled accounts, unknown accounts and wrong passwords all return
   `401 UNAUTHORIZED` with the single message
   `"Email or password is incorrect."`.
4. On success: create the session row (hashed token, CSRF token, expiry), update
   `last_login_at`, write `auth.login.success` (actor, company if auto-selected,
   request id) and set the cookie.

| Response | Meaning |
| -------- | ------- |
| `200` | Session created; body as §6.0 |
| `401 UNAUTHORIZED` | Generic credential failure |
| `403 ORIGIN_REJECTED` | `Origin` missing/untrusted |
| `422 VALIDATION_ERROR` | Malformed email/password fields |
| `429 RATE_LIMITED` | Login rate limit; honour `Retry-After` |

`Set-Cookie: touche_session=<token>; Max-Age=1800; Path=/; HttpOnly; SameSite=Lax`
(`Secure` and the `__Host-` prefix outside local development). The browser-side
lifetime is the idle window; the absolute expiry is enforced server-side.

### 6.2 `GET /api/v1/auth/me`

Returns §6.0 for the presented cookie. `401 UNAUTHORIZED` when the cookie is
missing, unknown or revoked; `401 SESSION_EXPIRED` when the row exists but the
idle or absolute deadline passed (the row is revoked and audited in that case).
The membership bound to the session is re-validated on every call.

### 6.3 `POST /api/v1/auth/logout`

Requires a valid session **and** `X-CSRF-Token`. Revokes the row immediately
(`revoked_reason='logout'`), writes `auth.logout`, clears the cookie
(`Max-Age=0`) and returns `{"status": "signed_out"}`. Calling it with an
already-revoked session returns `401` (the client clears its cookie regardless).

### 6.4 `GET /api/v1/companies`

```json
{
  "companies": [ { "company_id": "…", "name": "TOUCHE Trading", "country": "GB",
                   "default_currency": "GBP", "status": "active", "role": "admin",
                   "permissions": ["…"] } ],
  "active_company_id": null
}
```

Only companies with an **active membership** for the caller are returned. The
list is derived from the database on every request, so a revoked membership
disappears immediately.

### 6.5 `POST /api/v1/session/company`

```http
POST /api/v1/session/company
Origin: http://localhost:3000
X-CSRF-Token: sD3…43chars
Content-Type: application/json

{ "company_id": "8f14e45f-ceea-4b7b-9d0b-9d1f0f2b7c11" }
```

Behaviour:

1. Authenticate the session and require a valid CSRF token (`403 CSRF_REJECTED`).
2. Verify an **active membership** for `(user_id, company_id)`. The client value is
   only a lookup key; on failure the response is `403 FORBIDDEN` and an
   `access.denied` audit row records the requested company id — no distinction
   between "does not exist" and "not a member".
3. Update `session.company_id`, **rotate** the session and CSRF tokens, reset the
   idle timer, keep the absolute expiry, re-issue the cookie.
4. Write `session.company.switch` and return §6.0.

Errors: `401 UNAUTHORIZED`, `403 CSRF_REJECTED` / `FORBIDDEN`,
`422 VALIDATION_ERROR`.

### 6.6 Session policy and revocation

| Event | Effect |
| ----- | ------ |
| 30 min without activity | Session revoked (`idle_timeout`), `401 SESSION_EXPIRED` |
| 12 h since login | Session revoked (`absolute_timeout`), `401 SESSION_EXPIRED` |
| Account disabled | Session revoked (`user_disabled`), `401 UNAUTHORIZED` |
| Membership revoked | Every session bound to that company is revoked (`membership_revoked`); the next request returns `401`; other companies/memberships are untouched |
| Logout | Revoked immediately, cookie cleared |

### 6.7 Role → permission matrix (implemented)

| Permission | viewer | trader | approver | admin |
| ---------- | :----: | :----: | :------: | :---: |
| `company.view` | ✓ | ✓ | ✓ | ✓ |
| `settings.view` | ✓ | ✓ | ✓ | ✓ |
| `settings.manage` | — | — | — | ✓ |
| `membership.manage` | — | — | — | ✓ |
| `audit.view` | — | — | — | ✓ |
| `trade.write` | — | ✓ | — | — |
| `finance.approve` | — | — | ✓ | — |

An administrator cannot approve financial documents; an approver cannot manage
memberships. Checks use `require_permission(...)`, never role comparisons
(ADR-003).

### 6.8 Reserved identity endpoints (Stage 1B)

`GET /api/v1/audit-records` and `GET/POST/DELETE /api/v1/companies/{id}/memberships`
are designed but **not mounted**; requesting them returns `404`. Membership
administration is performed by the privileged CLI (`python -m app.cli`) until the
Stage 1B admin UI exists.

---



## 7. Trade workspace (implemented in Stage 1B)

All trade endpoints require an authenticated session with an **active company**.
Reads require `company.view`; writes require `trade.write` (traders only — an
administrator is deliberately read-only here, ADR-003/ADR-027). Every response is
`Cache-Control: no-store`.

### 7.1 Counterparties

| Method | Path | Notes |
| ------ | ---- | ----- |
| `GET` | `/counterparties?search=&status=&type=&limit=&cursor=` | `{items, next_cursor, has_more}` |
| `POST` | `/counterparties` | `201`; optional `Idempotency-Key`; duplicate name → `409 CONFLICT` |
| `GET` | `/counterparties/{id}` | `200` + `ETag` |
| `PATCH` | `/counterparties/{id}` | `If-Match` required; unknown fields → `422` |

```json
{
  "id": "…", "company_id": "…", "name": "Acme Metals",
  "type": "buyer", "country": "GB", "contact_name": "Jane Doe",
  "email": "jane@acme.example", "phone": null, "notes": null,
  "status": "active", "version": 1,
  "created_at": "2026-10-22T09:00:00Z", "updated_at": "2026-10-22T09:00:00Z"
}
```

`type` ∈ `buyer | supplier | both`; `status` ∈ `active | archived`; names are
unique per company and trimmed; `country` is ISO-3166 alpha-2 and `email` is
lower-cased.

### 7.2 Products

| Method | Path | Notes |
| ------ | ---- | ----- |
| `GET` | `/products?search=&status=&limit=&cursor=` | search matches SKU or name |
| `POST` | `/products` | `sku` is stored upper case; duplicate → `409 CONFLICT` |
| `GET` | `/products/{id}` | `200` + `ETag` |
| `PATCH` | `/products/{id}` | `If-Match` required |

```json
{
  "id": "…", "company_id": "…", "sku": "ALU-A7", "name": "Aluminium ingot A7",
  "unit": "mt", "currency": "USD", "unit_price": "2450.0000",
  "status": "active", "version": 1,
  "created_at": "…", "updated_at": "…"
}
```

`unit` ∈ `kg | mt | lb | unit | l | m3`; `unit_price` is a non-negative decimal
(18,4) serialised as a string.

### 7.3 Deals

| Method | Path | Notes |
| ------ | ---- | ----- |
| `GET` | `/deals?search=&status=&counterparty_id=&limit=&cursor=` | list projection, no lines/history |
| `POST` | `/deals` | deal + lines + initial `DRAFT` history + audit in one transaction |
| `GET` | `/deals/{id}` | lines, history, `allowed_transitions`, `ETag` |
| `PATCH` | `/deals/{id}` | header fields only; `If-Match` required; closed deal → `409 CONFLICT` |
| `POST` | `/deals/{id}/transitions` | **`Idempotency-Key` required**; optional `If-Match` |

Create request:

```json
{
  "title": "50 MT aluminium ingots",
  "counterparty_id": "…",
  "currency": "USD",
  "expected_close_date": "2026-11-30",
  "notes": "FOB Rotterdam",
  "reference": null,
  "items": [
    { "product_id": "…", "quantity": "50.000", "unit_price": "2450.0000" }
  ]
}
```

Rules: 1–20 lines, each product at most once, `quantity > 0`, `unit_price >= 0`,
counterparty and products must belong to the active company (`400 BAD_REQUEST`
otherwise, with no hint about other tenants). `reference` is generated
(`T-YYMM-XXXXXX`) when omitted and must be 3–32 upper-case characters when
provided.

Detail response (abridged):

```json
{
  "id": "…", "reference": "T-2610-6B44D0", "title": "…", "status": "DRAFT",
  "counterparty_id": "…", "counterparty_name": "Acme Metals", "currency": "USD",
  "total_value": "122500.00", "version": 1,
  "items": [{ "id": "…", "product_id": "…", "sku": "ALU-A7", "name": "…",
              "unit": "mt", "quantity": "50.000", "unit_price": "2450.0000",
              "line_total": "122500.00" }],
  "transitions": [{ "from_status": null, "to_status": "DRAFT", "reason": null,
                    "version_after": 1, "occurred_at": "…" }],
  "allowed_transitions": ["OPEN", "CANCELLED"],
  "closed_at": null, "created_at": "…", "updated_at": "…"
}
```

`PATCH` accepts `title`, `counterparty_id`, `currency`, `expected_close_date`,
`notes`. Sending `status` is a `422 VALIDATION_ERROR` (ADR-025). Lines are
immutable after creation.

### 7.4 Transitions

```http
POST /api/v1/deals/{id}/transitions
Origin: http://localhost:3000
X-CSRF-Token: …
Idempotency-Key: 4f1c… (required)
If-Match: "v3"              (optional, adds optimistic concurrency)
Content-Type: application/json

{ "to": "LOST", "reason": "Buyer withdrew the enquiry." }
```

| Situation | Response |
| --------- | -------- |
| Key missing/invalid | `400 IDEMPOTENCY_KEY_REQUIRED` / `400 BAD_REQUEST` |
| Unknown deal | `404 NOT_FOUND` |
| Target `WON` | `409 TRANSITION_DISABLED` |
| Deal already `WON` | `409 ALREADY_WON` |
| Edge not in the graph | `409 INVALID_TRANSITION` + `details.allowed` |
| `LOST`/`CANCELLED` without a valid reason | `422 REASON_REQUIRED` |
| Stale `If-Match` | `409 VERSION_CONFLICT` + current `ETag` |
| Same key, same body, already applied | `200` replay + `Idempotent-Replay: true` |
| Same key, different body | `409 IDEMPOTENCY_CONFLICT` |

The response is the full deal (§7.3) with the new `ETag`, history and
`allowed_transitions`.

### 7.5 Dashboard

`GET /dashboard/summary` returns `company_id`, `generated_at`, `deals_total`,
`status_counts` (every status, count and value), `pipeline` (per currency, open
statuses only), `counterparties_total/active`, `products_total/active`,
`recent_deals` (5) and `recent_activity` (8 audit rows). All values are computed
in one database transaction for the active company.

---

## 7A. Trade deal → sales order (Stage 2 design)

* `POST /api/v1/deals/{id}/transitions` with `{"to": "WON"}` requires an
  `Idempotency-Key` (the same requirement already enforced for every transition).
* The transition to `WON` and creation of exactly one sales order will commit in
  one transaction. Until the orders module exists the transition stays
  **disabled** (`409 TRANSITION_DISABLED`) — no half-built feature is exposed.
* Replaying the same key returns the original response; a different key after
  `WON` returns `409 ALREADY_WON`.
* Deal and order state machines are independent; the order has its own
  transitions and version.

---

## 7B. Sourcing, pricing and sales quotes (Stage 3, implemented)

### 7B.1 FX snapshots

| Method | Path | Permission | Notes |
| ------ | ---- | ---------- | ----- |
| `GET` | `/api/v1/fx-rates` | `company.view` | Cursor-paginated by recording time; `base_currency`/`quote_currency` filters |
| `POST` | `/api/v1/fx-rates` | `trade.write` | `Idempotency-Key`; unique `(company, pair, effective_at)` → `409 CONFLICT` |
| `GET` | `/api/v1/fx-rates/{id}` | `company.view` | |

A rate is an observation (`base_currency`, `quote_currency`, `rate`, `effective_at`,
`source`). There is no update endpoint: a correction is a new snapshot. Pricing may
only convert via a stored snapshot, so a landed cost is reproducible.

### 7B.2 RFQs

| Method | Path | Permission | Notes |
| ------ | ---- | ---------- | ----- |
| `GET` | `/api/v1/rfqs` | `company.view` | Filters: `search`, `status`, `deal_id`, `supplier_counterparty_id` |
| `POST` | `/api/v1/rfqs` | `trade.write` | Body lists `supplier_ids`; **one RFQ per supplier in one transaction**; returns `{items: [...]}` |
| `GET` | `/api/v1/rfqs/{id}` | `company.view` | Lines, quote summaries, revision metadata, `allowed_transitions` |
| `PATCH` | `/api/v1/rfqs/{id}` | `trade.write` | `If-Match` required; DRAFT/PREPARED only; editing a prepared RFQ returns it to DRAFT and opens the next revision |
| `POST` | `/api/v1/rfqs/{id}/transitions` | `trade.write` | `Idempotency-Key` required; optional `If-Match` |
| `GET` | `/api/v1/rfqs/{id}/revisions/{revision}` | `company.view` | Stored JSON snapshot |

Lifecycle: `DRAFT → PREPARED → SENT → RESPONDED → CLOSED`, plus `CANCELLED` before
dispatch. Preparing writes an append-only `supplier_rfq_revision`; `SENT` requires
`channel` **and** `evidence` (the database also requires `sent_at`); cancelling
requires a reason. `PREPARED` is explicitly not `SENT`.

### 7B.3 Supplier quotes

| Method | Path | Permission | Notes |
| ------ | ---- | ---------- | ----- |
| `GET` | `/api/v1/supplier-quotes` | `company.view` | Filters: `search`, `status`, `rfq_id`, `deal_id`, `supplier_counterparty_id`, `currency` |
| `POST` | `/api/v1/rfqs/{rfq_id}/quotes` | `trade.write` | Only a SENT (or re-quoted RESPONDED) RFQ; one active RECEIVED quote per RFQ |
| `GET` | `/api/v1/supplier-quotes/{id}` | `company.view` | Lines, revisions, supersedes links, `is_active` |
| `POST` | `/api/v1/supplier-quotes/{id}/revisions` | `trade.write` | `If-Match`; creates a **new row** with `revision + 1` and `supersedes_quote_id` |
| `POST` | `/api/v1/supplier-quotes/{id}/withdraw` | `trade.write` | `If-Match`; reason required; audited |
| `GET` | `/api/v1/supplier-quotes/{id}/revisions/{revision}` | `company.view` | Stored JSON snapshot |

Quoted products must appear on the RFQ; description and unit are inherited from the
RFQ line, so a quote cannot rename a product. Recording the first quote moves the
RFQ to `RESPONDED`. Withdrawn or superseded quotes cannot be priced.

### 7B.4 Pricing scenarios

| Method | Path | Permission | Notes |
| ------ | ---- | ---------- | ----- |
| `GET` | `/api/v1/pricing-scenarios` | `company.view` | `status`, `deal_id`, `supplier_quote_id` filters |
| `POST` | `/api/v1/pricing-scenarios` | `trade.write` | Calculates and stores inputs + results in one transaction |
| `GET` | `/api/v1/pricing-scenarios/{id}` | `company.view` | `pricing_inputs`, `calculated_results`, `completeness`, components |
| `PUT` | `/api/v1/pricing-scenarios/{id}` | `trade.write` | `If-Match`; recalculates the **same** quote, replaces components, bumps version |

Rules enforced by the engine and the service:

* cross-currency conversion requires an explicit snapshot with exactly the quote →
  target pair (`400 BAD_REQUEST` otherwise); no rate is ever inferred;
* ORDER costs are allocated pro-rata by line purchase value with cent-exact
  largest-remainder allocation; LINE costs must name a quoted product;
* exactly one of `margin_pct` / `markup_pct`, each `0 ≤ x < 100`
  (`price = cost / (1 − margin)` or `cost × (1 + markup)`);
* derived status: `INCOMPLETE` (a line has no price) → `ESTIMATED` (any estimated
  component) → `VERIFIED_INPUTS`;
* results are stored, never recomputed on read; `calculation_version` is recorded.

### 7B.5 Sales quotes

| Method | Path | Permission | Notes |
| ------ | ---- | ---------- | ----- |
| `GET` | `/api/v1/sales-quotes` | `company.view` | `status`, `deal_id`, `customer_id`, `currency`, `search` |
| `POST` | `/api/v1/sales-quotes` | `trade.write` | Prices copied from the scenario's stored results; starts `DRAFT` |
| `GET` | `/api/v1/sales-quotes/{id}` | `company.view` | Lines, revisions, approval trail, `allowed_transitions`, `can_submit` |
| `POST` | `/api/v1/sales-quotes/{id}/submit` | `trade.write` | `If-Match` + `Idempotency-Key`; scenario must be `VERIFIED_INPUTS` |
| `POST` | `/api/v1/sales-quotes/{id}/approve` | `finance.approve` | `If-Match`; approver must differ from the submitter (`403 FORBIDDEN`) |
| `POST` | `/api/v1/sales-quotes/{id}/reject` | `finance.approve` | `If-Match`; reason 3–500 (`422 REASON_REQUIRED`) |
| `POST` | `/api/v1/sales-quotes/{id}/withdraw` | `trade.write` | `If-Match`; DRAFT/PENDING_APPROVAL only |
| `POST` | `/api/v1/sales-quotes/{id}/revisions` | `trade.write` | `If-Match`; new DRAFT row with `revision + 1` and `supersedes_sales_quote_id` |
| `GET` | `/api/v1/sales-quotes/{id}/revisions/{revision}` | `company.view` | Stored JSON snapshot |

Workflow: `DRAFT → PENDING_APPROVAL → APPROVED | REJECTED`, with `WITHDRAWN`
before approval. Approval requires a second person holding `finance.approve`
(separation of duties); an approved quote is revised, never withdrawn or rejected,
so the approval pair in the database always matches the status.

### 7B.6 Error behaviour specific to this stage

| Case | Response |
| ---- | -------- |
| RFQ not sent yet, or a received quote already exists | `409 CONFLICT` |
| Sending without channel/evidence | `400 BAD_REQUEST` with field detail |
| Preparing an RFQ without lines | `409 CONFLICT` |
| Missing or wrong FX pair | `400 BAD_REQUEST` with field detail |
| Pricing a withdrawn/superseded quote | `409 CONFLICT` |
| Margin **and** markup supplied | `422 VALIDATION_ERROR` (schema) |
| Submitting an `ESTIMATED` scenario | `409 CONFLICT` |
| Approving one's own submission | `403 FORBIDDEN` |
| Stale `If-Match` | `409 VERSION_CONFLICT` with the current `ETag` |


---

## 7C. Stage 4 — orders, procurement, logistics and documents

All paths are under `/api/v1`. Reads require `company.view`; mutations require
`trade.write`; approving a purchase order requires `finance.approve`, and the
approver must not be the creator. Every mutation is CSRF-protected, takes an
`Idempotency-Key`, and updates take `If-Match: "v{n}"`.

### 7C.1 Customer acceptance and conversion

| Method | Path | Purpose |
| ------ | ---- | ------- |
| `POST` | `/deals/{deal_id}/customer-acceptance` | Record channel, timestamp, accepted-by name, evidence reference (and optional document id) for the deal's approved revision |
| `GET` | `/deals/{deal_id}/customer-acceptance` | Acceptance history for the deal |
| `POST` | `/deals/{deal_id}/sales-order` | **The only WON path.** Requires `sales_quote_id` and either `acceptance_evidence_id` or an inline `customer_acceptance`; `fulfilment_model` is `PURCHASE_RESALE` (default) or `BROKERAGE` |

`POST /deals/{id}/sales-order` requires an `Idempotency-Key`. A replay returns the
original `201` with `Idempotent-Replay: true`. A payload change under the same key
is `409 IDEMPOTENCY_CONFLICT`; a new key after the deal is WON is
`409 ALREADY_WON`. The quote must belong to the deal, be `APPROVED`, and be
addressed to the deal's counterparty; acceptance must reference that exact
revision and must not predate the approval.

### 7C.2 Sales orders

| Method | Path | Purpose |
| ------ | ---- | ------- |
| `GET` | `/sales-orders` | Filters: `status`, `customer_id`, `deal_id`, `currency`, `search`, `limit`, `cursor` |
| `GET` | `/sales-orders/{id}` | Frozen items, `accepted_terms`, transitions, amendments, `allowed_transitions` |
| `GET` | `/sales-orders/{id}/fulfilment` | Ordered/allocated/delivered/remaining per line plus `completion_ratio` and `fully_delivered` |
| `POST` | `/sales-orders/{id}/transitions` | `IN_FULFILLMENT`, `FULFILLED` (refused), `CLOSED`, `CANCELLED` (reason required) |
| `POST` | `/sales-orders/{id}/amendments` | Reasoned change to terms/quantities; the accepted snapshot is never rewritten; a quantity cannot fall below allocated |

### 7C.3 Purchase orders

| Method | Path | Purpose |
| ------ | ---- | ------- |
| `GET` | `/purchase-orders` | Filters: `status`, `sales_order_id`, `supplier_id`, `search` |
| `POST` | `/purchase-orders` | Draft for a sales order; refused with `PROCUREMENT_NOT_APPLICABLE` for brokerage |
| `GET` | `/purchase-orders/{id}` | Items, transitions, dispatch and confirmation evidence |
| `POST` | `/purchase-orders/{id}/transitions` | `APPROVED` (finance.approve + second person), `RECORDED_SENT` (channel + timestamp + reference), `SUPPLIER_CONFIRMED` (supplier reference), `IN_FULFILLMENT`, `RECEIVED`, `CANCELLED` (reason) |

### 7C.4 Shipments

| Method | Path | Purpose |
| ------ | ---- | ------- |
| `GET` | `/shipments` | Filters: `status`, `sales_order_id`, `search`, `limit`, `cursor` |
| `POST` | `/shipments` | Plan a full or partial shipment; `transport_mode` is SEA/AIR/ROAD/RAIL/MULTIMODAL; quantities are decimal |
| `GET` | `/shipments/{id}` | Items with delivered quantity, events, references, costs, `is_delayed`, `allowed_transitions` |
| `POST` | `/shipments/{id}/transitions` | Booked/dispatched/in-transit/arrived/delivered/cancelled with the evidence rules below |
| `POST` | `/shipments/{id}/events` | `IN_TRANSIT` or `DELAY_RECORDED` movement note (recorded manually or from a document) |
| `POST` | `/shipments/{id}/costs` | Cost type + `ESTIMATED`/`QUOTED`/`INCURRED`/`DOCUMENTED` + amount/currency/reference |
| `POST` | `/shipments/{id}/references` | Booking, container, B/L, AWB, CMR or tracking reference with `MANUAL`/`DOCUMENT_EVIDENCE` provenance |

Evidence rules: `DISPATCHED` requires a tracking/booking reference, `ARRIVED`
requires the actual arrival timestamp, `DELIVERED` requires a delivery evidence
reference, and `CANCELLED` requires a reason. An ETA is never an arrival.
`tracking_source` accepts only `MANUAL` or `DOCUMENT_EVIDENCE`;
`VERIFIED_EXTERNAL` is refused because no carrier integration exists.

### 7C.5 Documents

| Method | Path | Purpose |
| ------ | ---- | ------- |
| `GET` | `/documents` | Filters: `document_type`, `linked_entity_type`, `linked_entity_id`, `status`, `search`; returns the configured `max_upload_bytes` |
| `POST` | `/documents` | Multipart upload: `document_type`, `linked_entity_type`, `linked_entity_id`, `title`, `file`, optional `supersedes_document_id`, `is_draft` |
| `GET` | `/documents/{id}` | Metadata (no storage path exposed) |
| `GET` | `/documents/{id}/download` | Streams the verified bytes with `Content-Disposition: attachment` and `X-Document-SHA256` |
| `GET` | `/documents/{id}/history` | Every version of the same entity + document type |
| `POST` | `/documents/{id}/archive` | Controlled archival (no silent delete) |
| `POST` | `/documents/{id}/verification` | `VERIFIED` or `REJECTED` with an optional note |
| `GET` | `/sales-orders/{id}/documents/preview` | `kind=commercial_invoice|packing_list`, optional `shipment_id`; always `is_draft: true` |

Uploads are size-limited while streaming (413 `PAYLOAD_TOO_LARGE`), reject
non-allow-listed types (400 `UNSUPPORTED_CONTENT_TYPE`), verify magic prefixes,
sanitise filenames and require the linked entity to exist in the active company
(404 otherwise). A corrupted stored file returns 409
`DOCUMENT_CHECKSUM_MISMATCH`.

### 7C.6 Operations

| Method | Path | Purpose |
| ------ | ---- | ------- |
| `GET` | `/operations/summary` | Real counts: orders by status, order value by currency, open purchase orders, active/delayed/delivered shipments, active documents, delivered shipments without delivery-confirmation evidence |

### 7C.7 Error behaviour specific to this stage

| Situation | Response |
| --------- | -------- |
| Conversion without any acceptance payload | `422 VALIDATION_ERROR` (schema requires one source) |
| Acceptance id from another deal/company, or unknown | `404 NOT_FOUND` / `400 BAD_REQUEST` (`ACCEPTANCE_NOT_FOUND`) |
| Acceptance predates approval, or references a different revision | `400 BAD_REQUEST` / `409 CONFLICT` with the reason |
| Deal already WON, or has an order | `409 ALREADY_WON` |
| Direct `WON` through the deal transition endpoint | `409 TRANSITION_DISABLED` |
| Order/PO/shipment transition with a stale `If-Match` | `409 VERSION_CONFLICT` with the current `ETag` |
| Cancellation without a reason | `422 REASON_REQUIRED` |
| `FULFILLED` requested directly | `409 INVALID_TRANSITION` |
| Purchase-order approval by a trader or the creator | `403 FORBIDDEN` |
| `RECORDED_SENT` without channel/reference | `400 BAD_REQUEST` with per-field details |
| Shipment above the unallocated quantity, or unit mismatch | `400 BAD_REQUEST` with ordered/allocated/remaining |
| Brokerage order procurement | `409 CONFLICT` (`PROCUREMENT_NOT_APPLICABLE`) |
| Upload too large / wrong type / bad link | `413` / `400` / `404` |
| Cross-tenant document access | `404 NOT_FOUND` |
| Archived document download | `409 CONFLICT` (`DOCUMENT_ARCHIVED`) |

## 7D. Stage 5A — Finance integration status (implemented, read-only)

TOUCHE FINANCE is the financial source of truth. Commerce has **no** invoice,
payment, ledger or journal endpoint. Stage 5A exposes one operator status
read that probes Finance's public health endpoint only.

| Method | Path | Auth | Purpose |
| ------ | ---- | ---- | ------- |
| `GET` | `/integrations/finance/status` | Any authenticated Commerce session | One read-only `GET /api/health` probe of the configured loopback Finance URL |

The probe is disabled by default (`TOUCHE_FINANCE_INTEGRATION_ENABLED=false`) and
performs no network I/O while disabled. The base URL is restricted to
`http://127.0.0.1[:port]` or `http://[::1][:port]`; DNS names, HTTPS,
credentials, paths, queries and fragments are rejected at start-up. The request
sends no cookie, bearer token or Tailscale identity header and follows no
redirects. The response body is capped at 8 KiB, and the endpoint must identify
itself as `Server: ToucheFinans/...` with an `application/json` content type;
anything else is reported as `incompatible`, not `healthy`.

Response (`200`):

```json
{
  "state": "healthy",
  "finance_status": "ok",
  "latency_ms": 4.12,
  "detail": "Finance reports a consistent ledger.",
  "checked_at": "2026-10-22T09:30:00+00:00",
  "scope": "health_only",
  "accounting_writes_enabled": false
}
```

`state` is one of `disabled`, `healthy`, `degraded`, `unreachable` or
`incompatible`. A Finance outage does **not** make Commerce unready: this
endpoint still returns `200` with `unreachable`, because Commerce is healthy and
Finance is an optional external system. A request without a Commerce session is
`401 UNAUTHORIZED`.

`scope` is always `health_only` and `accounting_writes_enabled` is always
`false` in Stage 5A. The proposed Finance-side read/write contracts are
specified in `docs/STAGE5_FINANCE_DISCOVERY.md` §8 and are **not** callable yet.

---


## 8. Endpoint map



| Method | Path | Stage | Status |
| ------ | ---- | ----- | ------ |
| `GET` | `/` | 0 | Implemented |
| `GET` | `/api/v1/health/live` | 0 | Implemented |
| `GET` | `/api/v1/health/ready` | 0 | Implemented |
| `GET` | `/api/v1/openapi.json` | 0 | Implemented |
| `POST` | `/api/v1/auth/login` | 1A | Implemented |
| `GET` | `/api/v1/auth/me` | 1A | Implemented |
| `POST` | `/api/v1/auth/logout` | 1A | Implemented |
| `GET` | `/api/v1/companies` | 1A | Implemented |
| `POST` | `/api/v1/session/company` | 1A | Implemented |
| `GET` | `/api/v1/counterparties` | 1B | Implemented |
| `POST` | `/api/v1/counterparties` | 1B | Implemented |
| `GET` | `/api/v1/counterparties/{id}` | 1B | Implemented |
| `PATCH` | `/api/v1/counterparties/{id}` | 1B | Implemented |
| `GET` | `/api/v1/products` | 1B | Implemented |
| `POST` | `/api/v1/products` | 1B | Implemented |
| `GET` | `/api/v1/products/{id}` | 1B | Implemented |
| `PATCH` | `/api/v1/products/{id}` | 1B | Implemented |
| `GET` | `/api/v1/deals` | 1B | Implemented |
| `POST` | `/api/v1/deals` | 1B | Implemented |
| `GET` | `/api/v1/deals/{id}` | 1B | Implemented |
| `PATCH` | `/api/v1/deals/{id}` | 1B | Implemented |
| `POST` | `/api/v1/deals/{id}/transitions` | 1B | Implemented |
| `GET` | `/api/v1/dashboard/summary` | 1B | Implemented |
| `GET` | `/api/v1/fx-rates` | 3 | Implemented |
| `POST` | `/api/v1/fx-rates` | 3 | Implemented |
| `GET` | `/api/v1/fx-rates/{id}` | 3 | Implemented |
| `GET` | `/api/v1/rfqs` | 3 | Implemented |
| `POST` | `/api/v1/rfqs` | 3 | Implemented |
| `GET` | `/api/v1/rfqs/{id}` | 3 | Implemented |
| `PATCH` | `/api/v1/rfqs/{id}` | 3 | Implemented |
| `POST` | `/api/v1/rfqs/{id}/transitions` | 3 | Implemented |
| `GET` | `/api/v1/rfqs/{id}/revisions/{revision}` | 3 | Implemented |
| `GET` | `/api/v1/supplier-quotes` | 3 | Implemented |
| `POST` | `/api/v1/rfqs/{id}/quotes` | 3 | Implemented |
| `GET` | `/api/v1/supplier-quotes/{id}` | 3 | Implemented |
| `POST` | `/api/v1/supplier-quotes/{id}/revisions` | 3 | Implemented |
| `POST` | `/api/v1/supplier-quotes/{id}/withdraw` | 3 | Implemented |
| `GET` | `/api/v1/supplier-quotes/{id}/revisions/{revision}` | 3 | Implemented |
| `GET` | `/api/v1/pricing-scenarios` | 3 | Implemented |
| `POST` | `/api/v1/pricing-scenarios` | 3 | Implemented |
| `GET` | `/api/v1/pricing-scenarios/{id}` | 3 | Implemented |
| `PUT` | `/api/v1/pricing-scenarios/{id}` | 3 | Implemented |
| `GET` | `/api/v1/sales-quotes` | 3 | Implemented |
| `POST` | `/api/v1/sales-quotes` | 3 | Implemented |
| `GET` | `/api/v1/sales-quotes/{id}` | 3 | Implemented |
| `POST` | `/api/v1/sales-quotes/{id}/submit` | 3 | Implemented |
| `POST` | `/api/v1/sales-quotes/{id}/approve` | 3 | Implemented |
| `POST` | `/api/v1/sales-quotes/{id}/reject` | 3 | Implemented |
| `POST` | `/api/v1/sales-quotes/{id}/withdraw` | 3 | Implemented |
| `POST` | `/api/v1/sales-quotes/{id}/revisions` | 3 | Implemented |
| `GET` | `/api/v1/sales-quotes/{id}/revisions/{revision}` | 3 | Implemented |
| `GET` | `/api/v1/audit-records` | 2 | Reserved |
| `GET/POST/DELETE` | `/api/v1/companies/{id}/memberships` | 2 | Reserved |
| `POST` | `/api/v1/deals/{id}/customer-acceptance` | 4 | Implemented |
| `GET` | `/api/v1/deals/{id}/customer-acceptance` | 4 | Implemented |
| `POST` | `/api/v1/deals/{id}/sales-order` | 4 | Implemented |
| `GET` | `/api/v1/sales-orders` | 4 | Implemented |
| `GET` | `/api/v1/sales-orders/{id}` | 4 | Implemented |
| `GET` | `/api/v1/sales-orders/{id}/fulfilment` | 4 | Implemented |
| `POST` | `/api/v1/sales-orders/{id}/transitions` | 4 | Implemented |
| `POST` | `/api/v1/sales-orders/{id}/amendments` | 4 | Implemented |
| `GET` | `/api/v1/purchase-orders` | 4 | Implemented |
| `POST` | `/api/v1/purchase-orders` | 4 | Implemented |
| `GET` | `/api/v1/purchase-orders/{id}` | 4 | Implemented |
| `POST` | `/api/v1/purchase-orders/{id}/transitions` | 4 | Implemented |
| `GET` | `/api/v1/shipments` | 4 | Implemented |
| `POST` | `/api/v1/shipments` | 4 | Implemented |
| `GET` | `/api/v1/shipments/{id}` | 4 | Implemented |
| `POST` | `/api/v1/shipments/{id}/transitions` | 4 | Implemented |
| `POST` | `/api/v1/shipments/{id}/events` | 4 | Implemented |
| `POST` | `/api/v1/shipments/{id}/costs` | 4 | Implemented |
| `POST` | `/api/v1/shipments/{id}/references` | 4 | Implemented |
| `GET` | `/api/v1/documents` | 4 | Implemented |
| `POST` | `/api/v1/documents` | 4 | Implemented |
| `GET` | `/api/v1/documents/{id}` | 4 | Implemented |
| `GET` | `/api/v1/documents/{id}/download` | 4 | Implemented |
| `GET` | `/api/v1/documents/{id}/history` | 4 | Implemented |
| `POST` | `/api/v1/documents/{id}/archive` | 4 | Implemented |
| `POST` | `/api/v1/documents/{id}/verification` | 4 | Implemented |
| `GET` | `/api/v1/sales-orders/{id}/documents/preview` | 4 | Implemented |
| `GET` | `/api/v1/operations/summary` | 4 | Implemented |
| `GET` | `/api/v1/integrations/finance/status` | 5A | Implemented (health only, no accounting writes) |
| `GET` | `/api/v1/finance/status` | 5C | Implemented (mapped read-only connector) |
| `GET` | `/api/v1/finance/capabilities` | 5C | Implemented |
| `GET` | `/api/v1/finance/summary` | 5C | Implemented |
| `GET` | `/api/v1/finance/accounts` | 5C | Implemented |
| `GET` | `/api/v1/finance/aging` | 5C | Implemented |
| `GET` | `/api/v1/finance/intelligence/summary` | 5E | Implemented (read-only analysis) |
| `GET` | `/api/v1/finance/intelligence/orders` | 5E | Implemented |
| `GET` | `/api/v1/finance/intelligence/orders/{id}` | 5E | Implemented |
| `GET` | `/api/v1/finance/intelligence/cost-variance` | 5E | Implemented |
| `GET` | `/api/v1/finance/intelligence/coverage` | 5E | Implemented |
| `GET` | `/api/v1/finance/intelligence/exceptions` | 5E | Implemented |
| `GET` | `/api/v1/finance/intelligence/export` | 5E | Implemented (CSV, audited) |
| `GET` | `/api/v1/ai/status` | 6 | Implemented (provider mode, limits, usage) |
| `GET` | `/api/v1/ai/tools` | 6 | Implemented (registry, classes, blocked actions) |
| `GET` | `/api/v1/ai/suggestions` | 6 | Implemented |
| `POST` | `/api/v1/ai/conversations` | 6 | Implemented |
| `GET` | `/api/v1/ai/conversations[/{id}]` | 6 | Implemented (owner only) |
| `POST` | `/api/v1/ai/conversations/{id}/messages` | 6 | Implemented (202, background run) |
| `GET` | `/api/v1/ai/runs/{id}` | 6 | Implemented |
| `POST` | `/api/v1/ai/runs/{id}/cancel` | 6 | Implemented |
| `GET` | `/api/v1/ai/activity` | 6 | Implemented |
| `GET` | `/api/v1/ai/proposals[/{id}]` | 6 | Implemented |
| `PATCH` | `/api/v1/ai/proposals/{id}` | 6 | Implemented (If-Match, trade.write) |
| `POST` | `/api/v1/ai/proposals/{id}/approve` | 6 | Implemented (If-Match, trade.write; records a decision only) |
| `POST` | `/api/v1/ai/proposals/{id}/reject` | 6 | Implemented (If-Match, trade.write) |

Reserved endpoints do not exist in the running service; requesting them returns
`404 NOT_FOUND`. They are listed so the frontend and future integrations share a
single naming convention.

---

## 9. Versioning and change policy

* Additive fields are allowed in v1 (clients must ignore unknown fields).
* Removing/renaming fields, changing types, or changing error-code semantics
  requires a new namespace (`/api/v2`).
* The OpenAPI document is diffed in CI; an intentional contract change must
  include regenerated `schema.d.ts` and `openapi.json`.




---

## 10. Stage 5C — Finance read-only integration

### 10.1 Authentication and authorization

Every `/api/v1/finance/*` endpoint requires:

1. a valid Commerce session cookie;
2. an active company with a current membership;
3. `company.view`;
4. a tenant-owned `finance_company_mapping` row in `verified` state.

The Finance company id is never a request parameter. The Finance key/secret are
server-side settings and never appear in a response, log, audit row or browser
asset. The old `/api/v1/integrations/finance/status` remains health-only.

### 10.2 Endpoints

| Method | Path | Query | Response |
| ------ | ---- | ----- | -------- |
| `GET` | `/finance/status` | — | connection state, mapping, currencies, data-through |
| `GET` | `/finance/capabilities` | — | mapped company capabilities only |
| `GET` | `/finance/summary` | `currency` | source balances + ledger watermark |
| `GET` | `/finance/accounts` | `currency`, `from`, `to` or `as_of`, `limit`, `offset` | account rows + page |
| `GET` | `/finance/aging` | `type=receivable\|payable`, `currency`, `as_of`, `limit`, `offset` | FIFO buckets, open source ids + page |

`limit` is 1–200; `offset` is 0–1,000,000. A multi-currency Finance company
requires `currency`; supported observed codes include `TL`, `EUR` and `USD`.
No conversion or cross-currency aggregation exists. `from_date` is the
Commerce field name for Finance's `from`.

Status states: `not_configured`, `disabled`, `connected`, `degraded`,
`unavailable`, `auth_error`. Status returns HTTP 200 for a completed observation;
data endpoints return the normalized error envelope when data cannot be served.

### 10.3 Errors

| Commerce code | HTTP | Meaning |
| ------------- | ---- | ------- |
| `FINANCE_NOT_CONFIGURED` | 409 | No explicit mapping |
| `FINANCE_MAPPING_UNVERIFIED` | 409 | Mapping has not passed live verification |
| `FINANCE_MAPPING_DISABLED` | 409 | Mapping deliberately disabled |
| `FINANCE_INTEGRATION_DISABLED` | 503 | Connector disabled / Finance disabled |
| `FINANCE_AUTH_ERROR` | 502 | Finance missing/invalid credentials, scope or auth |
| `FINANCE_COMPANY_DENIED` | 409 | Mapping points at an unauthorized/inactive company |
| `FINANCE_CURRENCY_REQUIRED` | 409 | Multi-currency company needs one code |
| `FINANCE_INVALID_CURRENCY` | 400 | Requested currency not in the ledger |
| `FINANCE_UNAVAILABLE` | 503 | Timeout, unreachable or ledger unavailable |
| `FINANCE_PROTOCOL_ERROR` | 502 | Wrong server/contract/response shape |
| `FINANCE_AUDIT_UNAVAILABLE` | 503 | Required read audit could not be written |

`details.finance_code` preserves Finance's original code (for example
`INVALID_CREDENTIALS`, `COMPANY_DENIED`, `CURRENCY_REQUIRED`,
`AUDIT_UNAVAILABLE`). `details.finance_request_id` is forwarded when available.

### 10.4 Audit and write prohibition

A successful `finance.read` audit row records actor, company, Finance company,
endpoint, currency/date context and request id. The Stage 5C connector has no
Finance write call. Stage 5D adds Commerce reconciliation writes (runs, evidence,
reviews) but still no Finance or accounting write.

---

## 11. Stage 5D — financial reconciliation

### 11.1 Authorization

| Operation | Permission |
| --------- | ---------- |
| read runs, order view, discrepancies, evidence | `company.view` |
| create run, link evidence | `trade.write` |
| CONFIRM / DISPUTE / REQUEST_CHANGES, resolve discrepancy | `finance.reconcile` |

`finance.reconcile` is a distinct capability granted to `approver`; `admin` does
not inherit it. The run creator cannot review their own run. All mutations
require CSRF and `Idempotency-Key`; run/evidence/review/resolution changes also
require `If-Match`.

### 11.2 Endpoints

| Method | Path | Notes |
| ------ | ---- | ----- |
| `GET` | `/api/v1/finance/reconciliation?currency=&order_id=&status=` | no cross-currency total |
| `POST` | `/api/v1/finance/reconciliation/runs` | `sales_order_id`, explicit `currency`, optional `as_of` |
| `GET` | `/api/v1/finance/reconciliation/runs/{id}` | ETag = run version |
| `GET` | `/api/v1/finance/evidence-links?run_id=` | explicit links |
| `POST` | `/api/v1/finance/evidence-links` | server reads amount from Finance snapshot |
| `GET` | `/api/v1/finance/discrepancies?run_id=&code=&severity=&status=&currency=` | queue |
| `GET` | `/api/v1/finance/discrepancies/{id}` | ETag = discrepancy version |
| `POST` | `/api/v1/finance/discrepancies/{id}/resolve` | resolution note required |
| `POST` | `/api/v1/finance/reviews` | `CONFIRM`, `DISPUTE`, `REQUEST_CHANGES` |
| `GET` | `/api/v1/finance/orders/{id}` | order finance projection |

Responses are `Cache-Control: no-store` and `read_only=true` /
`accounting_writes_enabled=false`. Amounts are decimal strings.

### 11.3 State and errors

Run states: `INCOMPLETE`, `UNMATCHED`, `POTENTIAL_MATCH`, `MATCHED_EVIDENCE`,
`VERIFIED`, `DISPUTED`. Only an authorised review can enter `VERIFIED`. An
unlinked run cannot be verified.

| Code | HTTP | Meaning |
| ---- | ---- | ------- |
| `RECONCILIATION_CURRENCY_MISMATCH` | 409 | run/source/order currencies differ |
| `RECONCILIATION_EVIDENCE_INVALID` | 409 | unsupported source or mismatched entity |
| `RECONCILIATION_EVIDENCE_DUPLICATE` | 409 | Finance source id already linked |
| `RECONCILIATION_SOURCE_NOT_MATCHABLE` | 409 | summary/account used as order evidence |
| `RECONCILIATION_NOT_VERIFIABLE` | 409 | missing evidence/blocking discrepancy/wrong state |
| `RECONCILIATION_STATE_INVALID` | 409 | action invalid in the current state |

No endpoint writes a journal, invoice, payment or Finance record. Full domain
and acceptance evidence: `docs/STAGE5D_RECONCILIATION.md`.

---

## 12. Stage 5E — financial intelligence

Operational profitability analysis over facts Commerce already holds. It never
calls Finance and never writes an accounting entry.

### 12.1 Authorization and guarantees

All seven operations are `GET`s behind `company.view`, the established financial
read permission; Stage 5E adds no permission. A write-shaped request to any of
these paths returns `405`. Responses carry `Cache-Control: no-store` and
`Vary: Cookie`. Analytical responses carry `calculation_version`
(`stage5e-1.0.0`), `read_only=true` and `accounting_writes_enabled=false`; the
summary and the order drill-down also carry `statutory_statements=false`. Money
and percentages are decimal strings.

### 12.2 Filters

Shared by `summary`, `orders`, `cost-variance`, `coverage` and `export`:

| Query | Meaning |
| ----- | ------- |
| `from`, `to` | confirmation-date window; `to` defaults to today, `from` to `to` − 364 days |
| `currency` | three letters, upper-cased; filters orders, never converts |
| `fulfilment_model`, `order_status` | enum values from `filter_options` |
| `customer_id`, `supplier_id` | UUIDs from `filter_options` |
| `reconciliation_status` | a Stage 5D run status, or `NONE` |
| `completeness` | `COMPLETE`, `PARTIAL`, `MISSING` or `UNAVAILABLE` |

One analysis covers at most 731 days and 5000 orders.

### 12.3 Endpoints

| Method | Path | Notes |
| ------ | ---- | ----- |
| `GET` | `/api/v1/finance/intelligence/summary` | `metrics[]` per currency, `monthly_commitments`, `cost_comparison`, `margin_distribution`, `discrepancy_categories`, `completeness`, up to 8 `review_orders`, `filter_options` |
| `GET` | `/api/v1/finance/intelligence/orders?limit=&offset=` | order profitability rows, newest confirmation first; `total`, `limit`, `offset` |
| `GET` | `/api/v1/finance/intelligence/orders/{id}` | accepted quote, purchase orders, shipment costs, cost lines, FX assumptions, `checks`, `limitations`, Stage 5D `runs`, `evidence` and `discrepancies` |
| `GET` | `/api/v1/finance/intelligence/cost-variance?limit=&offset=` | only orders whose estimate and documented basis are both complete; `excluded_order_count` |
| `GET` | `/api/v1/finance/intelligence/coverage` | estimate, committed-basis, reconciliation and missing-input counts |
| `GET` | `/api/v1/finance/intelligence/exceptions?status=&severity=&code=&currency=&order_id=&from=&to=&limit=&offset=` | Stage 5D discrepancies enriched with the order; `status` defaults to `OPEN`, an empty `status` means every status |
| `GET` | `/api/v1/finance/intelligence/export` | CSV, see §12.5 |

Resolving an exception stays `POST /api/v1/finance/discrepancies/{id}/resolve`
(§11) and needs `finance.reconcile`.

### 12.4 Semantics clients must respect

* Amounts are per currency and never summed across currencies. A missing or
  unavailable figure is `null` (or `available=false`), never `0`.
* Two bases are kept apart. `ESTIMATED`: accepted value minus the Stage 3 landed-cost
  scenario, recoverable `VAT_CASHFLOW` excluded. `COMMITTED`/`DOCUMENTED`: accepted
  value minus committed purchase orders and shipment costs recorded as `INCURRED` or
  `DOCUMENTED`. `QUOTED`/`ESTIMATED` shipment costs are forecasts and never enter
  the documented basis.
* A part-shipped order has `committed_gross_profit=null`, `committed_status=PARTIAL`
  and `PARTIAL_FULFILMENT` in `missing_components`. A cancelled order has no current
  profitability.
* There is no `actual_profit` field; `classifications.actual_profit` is
  `UNAVAILABLE`.
* A summary metric's `classification` names the metric's kind (for example
  `COMMITTED`) and is fixed. `available` and the `money`/`percentages`/`count`
  values are authoritative; a client must not present a kind label as a figure.

### 12.5 CSV export

`Content-Type: text/csv; charset=utf-8`, `Content-Disposition: attachment;
filename="touche-operational-financial-analysis-YYYYMMDD.csv"`,
`X-Content-Type-Options: nosniff`, `Cache-Control: no-store`. One row per order with
`record_type=OPERATIONAL_ANALYSIS_ORDER`, an `analysis_label`, an `analysis_notice`
stating it is not a statutory statement, the `calculation_version`, the currency,
completeness and reconciliation status on every row, and no actual-profit column.
Text columns whose value starts with `=`, `+`, `-`, `@`, a tab or a carriage return
are prefixed with `'`; numeric columns are never prefixed, so a loss stays a number
(`-50.00`). Each export writes one `finance.read` audit row
(`resource_type=operational_financial_analysis`) with the format, row count and
filters. The browser calls the same path through the same-origin proxy, which
forwards `content-disposition` and `x-content-type-options`.

### 12.6 Errors

| Code | HTTP | Meaning |
| ---- | ---- | ------- |
| `BAD_REQUEST` | 400 | `from` later than `to`, range over 731 days, more than 5000 orders in scope, unknown `reconciliation_status` or `completeness` |
| `VALIDATION_ERROR` | 422 | malformed value (currency not three letters, invalid UUID or date) |
| `NOT_FOUND` | 404 | the order does not exist in the active company (another company's order looks identical) |
| `UNAUTHORIZED` / `FORBIDDEN` | 401 / 403 | no session, no active company, or no `company.view` |
| `METHOD_NOT_ALLOWED` | 405 | any non-`GET` request |

## 13. Stage 6 — AI Office (Trade Director)

Base path `/api/v1/ai`. Every route needs a session, an active company and
`company.view`; editing and deciding a proposal need `trade.write` (re-checked against
the live membership). The company is always the session's active company — no request
field names one. Responses are `no-store`. Errors use the standard envelope.

### 13.1 Endpoints

| Method | Path | Purpose |
|---|---|---|
| `GET` | `/ai/status` | Mode (`DISABLED`/`MOCK`/`REAL`), provider and model, prompt version, limits, today's usage and budgets, `can_approve`, and the literal guarantees `read_only_tools=true`, `accounting_writes_enabled=false`, `sends_messages=false`. Never returns a credential or the provider URL. |
| `GET` | `/ai/tools` | The 16 read-only tools (name, description, class, required permission, `available` for the caller, JSON schema), the four approval classes and the list of blocked actions with the reason. |
| `GET` | `/ai/suggestions` | Suggested starting questions. |
| `POST` | `/ai/conversations` | Start a conversation (`201`). |
| `GET` | `/ai/conversations` | The caller's own conversations in the active company. |
| `GET` | `/ai/conversations/{id}` | Messages (with validated answers and evidence) and proposals. Another user's conversation, even in the same company, is `404`. |
| `POST` | `/ai/conversations/{id}/messages` | Ask a question. `202` with the run and the stored user message; the model runs in the background. |
| `GET` | `/ai/runs/{id}` | Progress (tool calls so far) and, once `COMPLETED`, the assistant message and the proposals it produced. |
| `POST` | `/ai/runs/{id}/cancel` | Cooperative cancel by the run's owner (`202`); `409` if it already finished. |
| `GET` | `/ai/activity` | The caller's recent runs with token and tool counts. |
| `GET` | `/ai/proposals`, `/ai/proposals/{id}` | Drafts and task proposals of the company (`?proposal_status=`, `?conversation_id=`); `ETag: "v{n}"`. |
| `PATCH` | `/ai/proposals/{id}` | Edit wording of a pending proposal. `If-Match` required (`428`/`409 VERSION_CONFLICT`). |
| `POST` | `/ai/proposals/{id}/approve` | Record a human approval. `If-Match` required; body `{notes?, acknowledge_warnings}`. |
| `POST` | `/ai/proposals/{id}/reject` | Record a rejection. |

### 13.2 Run lifecycle and errors

`RUNNING` → `COMPLETED` | `FAILED` | `CANCELLED`. A run carries `provider`, `model`,
`prompt_version`, token counters (`estimated_usage` when the provider did not report
them), `model_steps`, `tool_call_count`, `error_code`, `validation_warnings` and
`safety_flags`. It never carries a prompt or a tool result.

| Code | HTTP | Meaning |
|---|---|---|
| `AI_DISABLED` | 503 | The AI Office is off. |
| `AI_INPUT_TOO_LARGE` | 413 | Empty or oversized message. |
| `AI_TOO_MANY_RUNS` | 429 | Per-user per-minute rate limit or concurrent-run limit. |
| `AI_BUDGET_EXCEEDED` | 429 (admission) / run `error_code` | Daily budget, per-request token budget or step limit. |
| `AI_PROVIDER_UNAVAILABLE` / `_TIMEOUT` / `_RATE_LIMITED` | run `error_code` | Retryable provider failures after the bounded retries. |
| `AI_PROVIDER_AUTH_FAILED` / `_QUOTA_EXCEEDED` / `_BAD_RESPONSE` | run `error_code` | Not retried. |
| `AI_RUN_CANCELLED` | run `error_code` | Cancelled by the owner. |
| `AI_PROPOSAL_STATE_INVALID` | 409 | Proposal already decided, or an unacknowledged `UNVERIFIED_NUMBER`. |
| `AI_ACTION_NOT_SUPPORTED` | 409 | An action type with no executor. |

### 13.3 The answer contract

`message.structured` is the server-validated answer:

```json
{
  "summary": "…",
  "findings": [{"claim": "…", "basis": "CONFIRMED_SOURCE", "evidence": ["E1"],
                "figures": [{"label": "total value", "value": "250.00", "currency": "USD", "evidence": "E1"}],
                "warnings": []}],
  "recommendations": [{"action": "…", "priority": "HIGH", "rationale": "…", "evidence": ["E1"]}],
  "missing_inputs": [{"item": "…", "evidence": ["E1"]}],
  "drafts": [{"kind": "SUPPLIER_FOLLOW_UP", "title": "…", "body": "…", "evidence": ["E1"]}],
  "task_proposals": [{"title": "…", "priority": "MEDIUM", "target": {"entity_type": "DEAL", "entity_id": "…"}, "evidence": ["E1"]}],
  "warnings": ["UNVERIFIED_NUMBER"]
}
```

`message.evidence` holds only the items the answer cites: `id`, `entity_type`,
`entity_id`, `reference`, `label`, `basis`, `as_of`, `completeness`, `facts` (exact
decimal strings from the deterministic services), `warnings`, `tool` and `href` — an
application route computed by the server, or `null`. Validation warning codes:
`UNVERIFIED_NUMBER`, `UNVERIFIED_FIGURE_REMOVED`, `UNKNOWN_EVIDENCE_REMOVED`,
`NO_SOURCE_EVIDENCE`, `BASIS_DOWNGRADED`, `BASIS_INVALID`, `UNKNOWN_TARGET_REMOVED`,
`RESPONSE_NOT_STRUCTURED`, `EDITED_BY_USER`. Safety flags on a run:
`INJECTION:<kind>`, `BLOCKED_TOOL_REQUESTED`, `UNKNOWN_TOOL_REQUESTED`,
`COMPANY_ID_ARGUMENT`, `PERMISSION_DENIED`.

### 13.4 Tools (all `READ_ONLY`, `company.view`)

`get_company_trade_overview`, `search_counterparties`, `search_products`,
`list_active_deals`, `get_deal_details`, `get_supplier_quotes`,
`compare_supplier_offers`, `get_pricing_scenario`, `list_sales_orders`,
`get_order_details`, `get_purchase_commitments`, `get_shipment_status`,
`get_document_metadata`, `get_order_profitability`, `get_finance_reconciliation`,
`list_financial_discrepancies`. Arguments are validated against a closed schema;
result size and list length are bounded; contact details and document contents are
never returned; the Finance application is never queried.

### 13.5 Audit

New append-only actions: `ai.conversation.created`, `ai.run.completed`, `ai.run.failed`,
`ai.run.cancelled`, `ai.tool.executed`, `ai.tool.denied`, `ai.action.blocked`,
`ai.proposal.created`, `ai.proposal.edited`, `ai.proposal.approved`,
`ai.proposal.rejected`. Tool and run events use `actor_type=agent` with the person on
whose authority the agent acted as `actor_id`; details hold counts, tool names and
validated arguments, never prompts or results.


---

## 14. Stage 7A — Communications discovery (not yet verified)

| Method | Path | Authorization | Behavior |
|---|---|---|---|
| GET | `/communications/status` | `company.view` on active company | `DRAFT_ONLY`, both channels `NOT_CONFIGURED`, `external_sending_enabled=false` |
| GET | `/communications/drafts?limit=20` | `company.view` on active company | Most recent 1–50 existing Stage 6 DRAFT proposals; company RLS, `sent=false`, `truncated` pagination signal |

There are **no** POST/send/connect/token/webhook endpoints. `communications.send`
is a reserved permission granted to no current role. AI proposal approval does not
send a message. New contracts need OpenAPI regeneration, full regression and isolated
acceptance before Stage 7A can be marked PASSED.


### 14.1 Stage 7B — recipient readiness, not delivery (CI verified)

`POST /communications/preflight` requires an active Commerce session, CSRF,
`trade.write` permission and body `{draft_id, draft_version, channel, recipient}`.
The server checks draft/company RLS, version, human review and channel-specific
recipient shape without persisting or returning the address. Response has
`draft_id`, `channel`, `sendable=false`, `external_sending_enabled=false`,
`recipient_echoed=false` and `blockers` using only:
`DRAFT_NOT_APPROVED`, `DRAFT_VERSION_MISMATCH`,
`RECIPIENT_INVALID`, `CHANNEL_NOT_CONFIGURED`,
`SEND_PERMISSION_UNAVAILABLE`. No message can be sent or queued.

CI workflow `40019149502` passed (558 backend, 192 frontend and contract
drift); PR #2 merged. Provider integration and Windows browser acceptance
were not run, and the endpoint cannot dispatch a message.


### 14.2 Stage 7C1 — CRM source comparison (CI VERIFIED)

`POST /communications/preflight` optionally accepts `counterparty_id` as
a UUID alongside the previous fields. With an authorized active tenant, the
server compares a valid recipient email/E.164 phone to the selected **active
CRM counterparty**. Missing, mismatched, archived and other-company records
yield the same `CRM_RECIPIENT_MISMATCH` code. There is no recipient address,
CRM record or contact secret in the response.

`CONSENT_UNDOCUMENTED` is always returned, including on a matching CRM entry;
a record match does not assert permission, contact ownership or consent.
The existing `sendable=false`, `external_sending_enabled=false` and
`recipient_echoed=false` guarantees remain unchanged. No send operation exists.
CI workflow `40021727161` passed with 561 backend and 192 frontend tests,
and PR #3 merged. No interactive browser or actual provider/consent evidence
verification was performed.


### 14.3 Stage 7C2 — Suppression registry (CI verified)

`GET /communications/suppressions?limit=50` requires the new
`communications.suppress` capability, currently assigned only to company
administrators. Returns a bounded list of company-scoped contact UUIDs,
channels, reasons, recorders and timestamps — not contact addresses.

`POST /communications/suppressions` requires that capability, verified
session/active company, CSRF and `Idempotency-Key`. Body is
`{counterparty_id, channel: EMAIL|WHATSAPP_BUSINESS,
reason: CONTACT_REQUEST|COMPLIANCE_REVIEW|IMPORTED_BLOCK}`. Returns 201 on
new block, 200 if the company/contact/channel already has a block, or
idempotent replay. The first recorded block is never edited; every new
block and audit row commit atomically. No DELETE, PUT, opt-in or send endpoint.

GitHub Actions run `40025166931` passed with 565 backend tests,
192 frontend tests, migration execution and generated contract drift check.
PR #4 merged at `5bc7bdc`. Windows browser and live provider validation
are still pending.

Preflight adds `RECIPIENT_SUPPRESSED` where a matching company contact
and channel have been blocked; `CONSENT_UNDOCUMENTED` remains unconditional
and `sendable=false` is unchanged. Nothing authenticates a recipient,
grants channel consent or connects a provider.

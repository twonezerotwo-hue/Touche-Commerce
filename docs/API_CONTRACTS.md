# TOUCHE COMMERCE — API contracts

**Version:** v1 · Stage 1A **implemented** for health, authentication, sessions and
company selection; later sections remain the binding design for Stage 1B+.
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
| Idempotency | `Idempotency-Key` header on mutating requests (Stage 1B) |
| Concurrency | `ETag` response header + `If-Match` request header (Stage 1B) |
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
| `CONFLICT` | 409 | Generic state conflict |
| `VERSION_CONFLICT` | 409 | Stale `If-Match` version |
| `IDEMPOTENCY_CONFLICT` | 409 | Reused key with a different payload |
| `IDEMPOTENCY_IN_PROGRESS` | 409 | Duplicate in-flight request; honour `Retry-After` |
| `ALREADY_WON` | 409 | Deal already WON; no second order is created |
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

## 3. Pagination (Stage 1B)

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

## 4. Idempotency (Stage 1B)

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

## 5. Optimistic concurrency (Stage 1B)

Versioned resources return `ETag: "v{version}"` and a `version` field.

```http
PATCH /api/v1/trade-deals/{id}
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



## 7. Trade deal → sales order (Stage 2 design)

* `POST /api/v1/trade-deals/{id}/transitions` with `{"to": "WON"}` requires an
  `Idempotency-Key`.
* The transition to `WON` and creation of exactly one sales order commit in one
  transaction. The `WON` transition is **disabled** until the orders module
  exists (`409 CONFLICT`, code `TRANSITION_DISABLED`) — no half-built feature is
  exposed.
* Replaying the same key returns the original response; a different key after
  `WON` returns `409 ALREADY_WON`.
* Deal and order state machines are independent; the order has its own
  transitions and version.

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
| `GET` | `/api/v1/audit-records` | 1B | Reserved |
| `GET/POST/DELETE` | `/api/v1/companies/{id}/memberships` | 1B | Reserved |
| `GET/POST/PATCH` | `/api/v1/trade-deals` | 2 | Reserved |
| `POST` | `/api/v1/trade-deals/{id}/transitions` | 2 | Reserved |
| `GET/POST/PATCH` | `/api/v1/sales-orders` | 2 | Reserved |
| `GET/POST` | `/api/v1/documents` | 1B | Reserved |

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




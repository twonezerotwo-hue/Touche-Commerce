# TOUCHE COMMERCE — API contracts

**Version:** v1 · Stage 0 (health endpoints implemented; the rest is the binding
design for Stage 1A+).
**Source of truth:** `backend/app/api/v1/schemas/*` → `/api/v1/openapi.json` →
`frontend/src/lib/api/schema.d.ts`.

---

## 1. General conventions

| Item | Contract |
| ---- | -------- |
| Base URL (local) | `http://127.0.0.1:8000` |
| Namespace | `/api/v1` (breaking changes require `/api/v2`) |
| Content type | `application/json; charset=utf-8` |
| Authentication (1A) | `touche_session` cookie, `HttpOnly`, `Secure`, `SameSite=Lax` |
| CSRF (1A) | `X-CSRF-Token` header on every non-GET request |
| Request correlation | `X-Request-ID` header, echoed on every response |
| Idempotency | `Idempotency-Key` header on mutating requests |
| Concurrency | `ETag` response header + `If-Match` request header |
| CORS | Local origins only (`http://localhost:3000`, `http://127.0.0.1:3000`) |
| Caching | No response may be cached: `Cache-Control: no-store` on errors; status pages are `force-dynamic` |

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
| `UNAUTHORIZED` | 401 | Missing/expired session *(Stage 1A)* |
| `FORBIDDEN` | 403 | Authenticated but not permitted, or no active membership *(Stage 1A)* |
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

## 6. Session and company switching (Stage 1A design)

### 6.1 `POST /api/v1/session/company`

Switches the active company for the current session. The active company is
server-side state; the request only *selects* a candidate.

Request:

```json
{ "company_id": "8f14e45f-ceea-4b7b-9d0b-9d1f0f2b7c11" }
```

Success `200`:

```json
{
  "session": {
    "session_id": "…",
    "user_id": "…",
    "company": { "id": "8f14e45f-…", "name": "TOUCHE Trading", "role": "trader" },
    "expires_at": "2026-10-23T10:30:00Z"
  }
}
```

Behaviour:

1. Authenticate the session cookie; reject `401` when absent/expired.
2. Verify an **active, verified membership** for `(user_id, company_id)`; else
   `403 FORBIDDEN` (never reveal whether the company exists).
3. Update `session.company_id`, rotate the session token, reset the idle timer,
   issue a new cookie.
4. Write an audit record (`action='session.company.switch'`, `request_id`).
5. Return only the membership summary, no unrelated company data.

Errors: `401 UNAUTHORIZED`, `403 FORBIDDEN`, `422 VALIDATION_ERROR` (malformed
UUID), `429 RATE_LIMITED` (credential-guessing protection).

### 6.2 Session lifecycle endpoints (Stage 1A)

| Method | Path | Purpose |
| ------ | ---- | ------- |
| `POST` | `/api/v1/auth/login` | Create session (rate limited, CSRF-exempt) |
| `POST` | `/api/v1/auth/logout` | Revoke the current session |
| `GET` | `/api/v1/session` | Current actor, company, roles, permissions, expiry |
| `POST` | `/api/v1/session/company` | Switch active company (above) |

Every authenticated request re-verifies the membership referenced by the
session. Removal of a membership revokes all sessions bound to that company.

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
| `POST` | `/api/v1/auth/login` | 1A | Reserved |
| `POST` | `/api/v1/auth/logout` | 1A | Reserved |
| `GET` | `/api/v1/session` | 1A | Reserved |
| `POST` | `/api/v1/session/company` | 1A | Reserved |
| `GET/POST` | `/api/v1/companies` | 1A | Reserved |
| `GET/POST/DELETE` | `/api/v1/companies/{id}/memberships` | 1A | Reserved |
| `GET` | `/api/v1/audit-records` | 1A | Reserved |
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




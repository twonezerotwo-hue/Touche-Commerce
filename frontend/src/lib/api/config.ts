/**
 * Frontend runtime configuration.
 *
 * The API base URL is the only browser-exposed setting. Secrets never belong in
 * NEXT_PUBLIC_* variables (docs/DECISIONS.md #15).
 */

const DEFAULT_API_BASE_URL = "http://127.0.0.1:8000";
// Must stay comfortably above the backend readiness budget (DB connect timeout
// 3 s + overhead) so a database outage surfaces as "Degraded" (503 envelope)
// rather than as a client-side timeout.
const DEFAULT_TIMEOUT_MS = 10000;

function normaliseBaseUrl(value: string | undefined): string {
  const candidate = (value ?? "").trim().replace(/\/+$/, "");
  return candidate.length > 0 ? candidate : DEFAULT_API_BASE_URL;
}

function parseTimeout(value: string | undefined): number {
  const parsed = Number.parseInt(value ?? "", 10);
  return Number.isFinite(parsed) && parsed > 0 ? parsed : DEFAULT_TIMEOUT_MS;
}

export const API_BASE_URL = normaliseBaseUrl(process.env.NEXT_PUBLIC_API_BASE_URL);
export const API_PREFIX = "/api/v1";
export const API_REQUEST_TIMEOUT_MS = parseTimeout(process.env.NEXT_PUBLIC_API_TIMEOUT_MS);

export const API_URLS = {
  base: API_BASE_URL,
  apiRoot: `${API_BASE_URL}${API_PREFIX}`,
  liveness: `${API_BASE_URL}${API_PREFIX}/health/live`,
  readiness: `${API_BASE_URL}${API_PREFIX}/health/ready`,
  openapi: `${API_BASE_URL}${API_PREFIX}/openapi.json`,
  docs: `${API_BASE_URL}/docs`,
} as const;

/**
 * Thin, typed API client.
 *
 * Response/error shapes come from the OpenAPI-generated types (schema.d.ts),
 * never from hand-written duplicates (docs/DECISIONS.md #14). The client is
 * transport-only: it never invents a success state, it reports exactly what the
 * backend answered.
 */

import { API_BASE_URL, API_PREFIX, API_REQUEST_TIMEOUT_MS } from "./config";
import type { components } from "./schema";

export type HealthLive = components["schemas"]["HealthLiveResponse"];
export type HealthReadiness = components["schemas"]["ReadinessResponse"];
export type HealthCheck = components["schemas"]["HealthCheckResult"];
export type ApiErrorEnvelope = components["schemas"]["ErrorEnvelope"];

export interface ApiSuccess<T> {
  ok: true;
  status: number;
  requestId: string | null;
  latencyMs: number;
  data: T;
}

export interface ApiFailure {
  ok: false;
  status: number | null;
  code: string;
  message: string;
  requestId: string | null;
  details: unknown;
  latencyMs: number;
}

export type ApiResult<T> = ApiSuccess<T> | ApiFailure;

export interface OpenApiContract {
  title: string | null;
  version: string | null;
  operationCount: number;
}

const HTTP_METHODS = new Set(["get", "put", "post", "delete", "options", "head", "patch", "trace"]);

function isRecord(value: unknown): value is Record<string, unknown> {
  return typeof value === "object" && value !== null && !Array.isArray(value);
}

export function parseErrorEnvelope(payload: unknown): ApiErrorEnvelope | null {
  if (!isRecord(payload) || !isRecord(payload.error)) return null;
  const error = payload.error;
  if (typeof error.code !== "string" || typeof error.message !== "string") return null;
  return payload as ApiErrorEnvelope;
}

export function summariseOpenApi(payload: unknown): OpenApiContract | null {
  if (!isRecord(payload) || typeof payload.openapi !== "string") return null;

  let operationCount = 0;
  if (isRecord(payload.paths)) {
    for (const pathItem of Object.values(payload.paths)) {
      if (!isRecord(pathItem)) continue;
      for (const key of Object.keys(pathItem)) {
        if (HTTP_METHODS.has(key.toLowerCase())) operationCount += 1;
      }
    }
  }

  const info = isRecord(payload.info) ? payload.info : {};
  return {
    title: typeof info.title === "string" ? info.title : null,
    version: typeof info.version === "string" ? info.version : null,
    operationCount,
  };
}

async function readJson(response: Response): Promise<unknown> {
  try {
    return (await response.json()) as unknown;
  } catch {
    return null;
  }
}

async function getJson<T>(path: string): Promise<ApiResult<T>> {
  const url = `${API_BASE_URL}${API_PREFIX}${path}`;
  const startedAt = Date.now();
  const controller = new AbortController();
  const timeout = setTimeout(() => controller.abort(), API_REQUEST_TIMEOUT_MS);

  try {
    const response = await fetch(url, {
      cache: "no-store",
      headers: { Accept: "application/json" },
      signal: controller.signal,
    });
    const latencyMs = Date.now() - startedAt;
    const headerRequestId = response.headers.get("x-request-id");
    const payload = await readJson(response);

    if (!response.ok) {
      const envelope = parseErrorEnvelope(payload);
      return {
        ok: false,
        status: response.status,
        code: envelope?.error.code ?? `HTTP_${response.status}`,
        message: envelope?.error.message ?? "The API returned an unexpected error response.",
        requestId: envelope?.error.request_id ?? headerRequestId,
        details: envelope?.error.details ?? null,
        latencyMs,
      };
    }

    if (payload === null) {
      return {
        ok: false,
        status: response.status,
        code: "INVALID_RESPONSE",
        message: "The API responded with a body that is not valid JSON.",
        requestId: headerRequestId,
        details: null,
        latencyMs,
      };
    }

    return {
      ok: true,
      status: response.status,
      requestId: headerRequestId,
      latencyMs,
      data: payload as T,
    };
  } catch (error) {
    const latencyMs = Date.now() - startedAt;
    const aborted = error instanceof DOMException && error.name === "AbortError";
    return {
      ok: false,
      status: null,
      code: aborted ? "TIMEOUT" : "UNREACHABLE",
      message: aborted
        ? `The API did not answer within ${API_REQUEST_TIMEOUT_MS} ms.`
        : `Cannot reach the API at ${API_BASE_URL}. Confirm FastAPI is running.`,
      requestId: null,
      details: null,
      latencyMs,
    };
  } finally {
    clearTimeout(timeout);
  }
}

/** GET /api/v1/health/live — process liveness (no database dependency). */
export function fetchLiveness(): Promise<ApiResult<HealthLive>> {
  return getJson<HealthLive>("/health/live");
}

/** GET /api/v1/health/ready — readiness incl. PostgreSQL probe. */
export function fetchReadiness(): Promise<ApiResult<HealthReadiness>> {
  return getJson<HealthReadiness>("/health/ready");
}

/** GET /api/v1/openapi.json — proves the typed contract is being served. */
export async function fetchContract(): Promise<ApiResult<OpenApiContract>> {
  const result = await getJson<unknown>("/openapi.json");
  if (!result.ok) return result;

  const summary = summariseOpenApi(result.data);
  if (!summary) {
    return {
      ok: false,
      status: result.status,
      code: "INVALID_CONTRACT",
      message: "The OpenAPI document could not be parsed.",
      requestId: result.requestId,
      details: null,
      latencyMs: result.latencyMs,
    };
  }
  return { ...result, data: summary };
}

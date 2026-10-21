/**
 * Presentation helpers that translate raw API results into UI state.
 *
 * Kept pure and framework-free so they can be unit tested and reused by any
 * future screen without duplicating status logic.
 */

import type { ApiResult, HealthReadiness } from "./api/client";

export type ProbeState = "operational" | "degraded" | "unreachable";

export const PROBE_STATE_LABEL: Record<ProbeState, string> = {
  operational: "Operational",
  degraded: "Degraded",
  unreachable: "Unreachable",
};

export const PROBE_STATE_BADGE: Record<ProbeState, "success" | "warning" | "danger"> = {
  operational: "success",
  degraded: "warning",
  unreachable: "danger",
};

export const PROBE_STATE_DOT: Record<ProbeState, string> = {
  operational: "bg-jade-400",
  degraded: "bg-amber-400",
  unreachable: "bg-crimson-400",
};

export interface DatabaseSummary {
  state: ProbeState;
  detail: string;
  server: string | null;
  role: string | null;
  latencyMs: number | null;
  errorCode: string | null;
}

function isRecord(value: unknown): value is Record<string, unknown> {
  return typeof value === "object" && value !== null;
}

/** A readiness failure is "degraded"; anything else means the API is unreachable. */
export function stateFromCode(code: string): ProbeState {
  return code === "NOT_READY" ? "degraded" : "unreachable";
}

export function stateFromResult(result: ApiResult<unknown>): ProbeState {
  return result.ok ? "operational" : stateFromCode(result.code);
}

function firstCheck(details: unknown): Record<string, unknown> | null {
  if (!isRecord(details)) return null;
  const checks = details.checks;
  if (!Array.isArray(checks) || checks.length === 0) return null;
  const [first] = checks;
  return isRecord(first) ? first : null;
}

export function summariseDatabase(result: ApiResult<HealthReadiness>): DatabaseSummary {
  if (result.ok) {
    const check =
      result.data.checks.find((item) => item.name === "database") ?? result.data.checks[0];
    if (!check) {
      return {
        state: "degraded",
        detail: "The readiness response contained no database check.",
        server: null,
        role: null,
        latencyMs: null,
        errorCode: null,
      };
    }
    const serverMatch = /PostgreSQL\s+([0-9][^\s,]*)/.exec(check.detail);
    const roleMatch = /role '([^']+)'/.exec(check.detail);
    return {
      state: "operational",
      detail: check.detail,
      server: serverMatch?.[1] ?? null,
      role: roleMatch?.[1] ?? null,
      latencyMs: check.latency_ms,
      errorCode: check.error_code ?? null,
    };
  }

  const check = firstCheck(result.details);
  const detail = typeof check?.detail === "string" ? check.detail : result.message;
  const latency = typeof check?.latency_ms === "number" ? check.latency_ms : null;
  const errorCode = typeof check?.error_code === "string" ? check.error_code : result.code;

  return {
    state: stateFromCode(result.code),
    detail,
    server: null,
    role: null,
    latencyMs: latency,
    errorCode,
  };
}

export function formatLatency(latencyMs: number | null): string {
  if (latencyMs === null || Number.isNaN(latencyMs)) return "—";
  if (latencyMs < 1) return "<1 ms";
  return `${Number(latencyMs.toFixed(2))} ms`;
}

/** Deterministic UTC rendering (identical on server and client). */
export function formatUtcTimestamp(iso: string | null | undefined): string {
  if (!iso) return "—";
  const parsed = new Date(iso);
  if (Number.isNaN(parsed.getTime())) return iso;

  const pad = (value: number): string => String(value).padStart(2, "0");
  return (
    `${parsed.getUTCFullYear()}-${pad(parsed.getUTCMonth() + 1)}-${pad(parsed.getUTCDate())} ` +
    `${pad(parsed.getUTCHours())}:${pad(parsed.getUTCMinutes())}:${pad(parsed.getUTCSeconds())} UTC`
  );
}

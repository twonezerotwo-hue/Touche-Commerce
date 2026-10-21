import { describe, expect, it } from "vitest";

import type { ApiFailure, ApiSuccess, HealthReadiness } from "./api/client";
import {
  PROBE_STATE_LABEL,
  formatLatency,
  formatUtcTimestamp,
  stateFromCode,
  stateFromResult,
  summariseDatabase,
} from "./status";

function success<T>(data: T): ApiSuccess<T> {
  return { ok: true, status: 200, requestId: "req-success", latencyMs: 3.2, data };
}

function failure(code: string, details: unknown = null): ApiFailure {
  return {
    ok: false,
    status: 503,
    code,
    message: "The service is not ready to handle requests.",
    requestId: "req-failure",
    details,
    latencyMs: 4,
  };
}

const readyPayload: HealthReadiness = {
  status: "ready",
  service: "touche-commerce-api",
  version: "0.1.0",
  environment: "local",
  checked_at: "2026-10-22T09:30:00Z",
  checks: [
    {
      name: "database",
      status: "ok",
      latency_ms: 4.12,
      detail: "PostgreSQL 17.6 reachable as role 'touche_app'.",
      error_code: null,
    },
  ],
};

describe("stateFromCode", () => {
  it("maps a readiness failure to degraded", () => {
    expect(stateFromCode("NOT_READY")).toBe("degraded");
  });

  it("maps transport and unexpected failures to unreachable", () => {
    expect(stateFromCode("UNREACHABLE")).toBe("unreachable");
    expect(stateFromCode("TIMEOUT")).toBe("unreachable");
    expect(stateFromCode("INTERNAL_ERROR")).toBe("unreachable");
  });
});

describe("stateFromResult", () => {
  it("is operational only for a successful response", () => {
    expect(stateFromResult(success({ ok: true }))).toBe("operational");
  });

  it("is degraded for a 503 readiness envelope", () => {
    expect(stateFromResult(failure("NOT_READY"))).toBe("degraded");
  });
});

describe("summariseDatabase", () => {
  it("extracts server version, role and latency from the readiness payload", () => {
    const summary = summariseDatabase(success(readyPayload));

    expect(summary.state).toBe("operational");
    expect(summary.server).toBe("17.6");
    expect(summary.role).toBe("touche_app");
    expect(summary.latencyMs).toBe(4.12);
    expect(summary.detail).toContain("PostgreSQL 17.6");
  });

  it("surfaces the failed check from the error envelope details", () => {
    const summary = summariseDatabase(
      failure("NOT_READY", {
        status: "not_ready",
        checks: [
          {
            name: "database",
            status: "error",
            latency_ms: 5020.4,
            detail: "connection timeout expired",
            error_code: "DATABASE_UNAVAILABLE",
          },
        ],
      }),
    );

    expect(summary.state).toBe("degraded");
    expect(summary.errorCode).toBe("DATABASE_UNAVAILABLE");
    expect(summary.detail).toBe("connection timeout expired");
    expect(summary.latencyMs).toBe(5020.4);
    expect(summary.server).toBeNull();
  });

  it("reports the transport message when no check details exist", () => {
    const summary = summariseDatabase(failure("UNREACHABLE"));

    expect(summary.state).toBe("unreachable");
    expect(summary.detail).toBe("The service is not ready to handle requests.");
    expect(summary.errorCode).toBe("UNREACHABLE");
  });
});

describe("formatting", () => {
  it("formats latency values", () => {
    expect(formatLatency(null)).toBe("—");
    expect(formatLatency(0.4)).toBe("<1 ms");
    expect(formatLatency(4.12)).toBe("4.12 ms");
    expect(formatLatency(5020.4)).toBe("5020.4 ms");
  });

  it("renders deterministic UTC timestamps", () => {
    expect(formatUtcTimestamp("2026-10-22T09:30:05Z")).toBe("2026-10-22 09:30:05 UTC");
    expect(formatUtcTimestamp("not-a-date")).toBe("not-a-date");
    expect(formatUtcTimestamp(null)).toBe("—");
  });

  it("exposes operator-facing labels", () => {
    expect(PROBE_STATE_LABEL.operational).toBe("Operational");
    expect(PROBE_STATE_LABEL.degraded).toBe("Degraded");
    expect(PROBE_STATE_LABEL.unreachable).toBe("Unreachable");
  });
});

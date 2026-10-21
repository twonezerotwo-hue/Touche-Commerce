import { afterEach, describe, expect, it, vi } from "vitest";

import {
  fetchContract,
  fetchLiveness,
  fetchReadiness,
  parseErrorEnvelope,
  summariseOpenApi,
} from "./client";

function jsonResponse(
  body: unknown,
  init: { status?: number; headers?: Record<string, string> } = {},
): Response {
  return new Response(JSON.stringify(body), {
    status: init.status ?? 200,
    headers: { "content-type": "application/json", ...(init.headers ?? {}) },
  });
}

const livePayload = {
  status: "ok",
  service: "touche-commerce-api",
  version: "0.1.0",
  environment: "local",
  checked_at: "2026-10-22T09:30:00Z",
};

afterEach(() => {
  vi.unstubAllGlobals();
});

describe("fetchLiveness", () => {
  it("returns typed data, status and the echoed request id", async () => {
    const fetchMock = vi
      .fn()
      .mockResolvedValue(jsonResponse(livePayload, { headers: { "x-request-id": "req-abc" } }));
    vi.stubGlobal("fetch", fetchMock);

    const result = await fetchLiveness();

    expect(result.ok).toBe(true);
    if (!result.ok) throw new Error("expected a successful result");
    expect(result.data.service).toBe("touche-commerce-api");
    expect(result.status).toBe(200);
    expect(result.requestId).toBe("req-abc");
    expect(result.latencyMs).toBeGreaterThanOrEqual(0);
    expect(fetchMock).toHaveBeenCalledWith(
      expect.stringContaining("/api/v1/health/live"),
      expect.objectContaining({ cache: "no-store" }),
    );
  });

  it("parses the standard error envelope on a 503 readiness failure", async () => {
    vi.stubGlobal(
      "fetch",
      vi.fn().mockResolvedValue(
        jsonResponse(
          {
            error: {
              code: "NOT_READY",
              message: "The service is not ready to handle requests.",
              request_id: "req-envelope",
              timestamp: "2026-10-22T09:30:00Z",
              details: { status: "not_ready", checks: [] },
            },
          },
          { status: 503 },
        ),
      ),
    );

    const result = await fetchReadiness();

    expect(result.ok).toBe(false);
    if (result.ok) throw new Error("expected a failure result");
    expect(result.code).toBe("NOT_READY");
    expect(result.status).toBe(503);
    expect(result.requestId).toBe("req-envelope");
    expect(result.details).toEqual({ status: "not_ready", checks: [] });
  });

  it("reports a network failure as UNREACHABLE without throwing", async () => {
    vi.stubGlobal("fetch", vi.fn().mockRejectedValue(new TypeError("fetch failed")));

    const result = await fetchLiveness();

    expect(result.ok).toBe(false);
    if (result.ok) throw new Error("expected a failure result");
    expect(result.code).toBe("UNREACHABLE");
    expect(result.status).toBeNull();
    expect(result.message).toContain("Cannot reach the API");
  });

  it("reports an aborted request as TIMEOUT", async () => {
    vi.stubGlobal(
      "fetch",
      vi.fn().mockRejectedValue(new DOMException("The operation was aborted.", "AbortError")),
    );

    const result = await fetchLiveness();

    expect(result.ok).toBe(false);
    if (result.ok) throw new Error("expected a failure result");
    expect(result.code).toBe("TIMEOUT");
  });

  it("rejects a non-JSON success body instead of inventing a status", async () => {
    vi.stubGlobal(
      "fetch",
      vi.fn().mockResolvedValue(
        new Response("<html>gateway error</html>", {
          status: 200,
          headers: { "content-type": "text/html" },
        }),
      ),
    );

    const result = await fetchLiveness();

    expect(result.ok).toBe(false);
    if (result.ok) throw new Error("expected a failure result");
    expect(result.code).toBe("INVALID_RESPONSE");
  });
});

describe("OpenAPI contract", () => {
  it("counts operations in the generated document", async () => {
    vi.stubGlobal(
      "fetch",
      vi.fn().mockResolvedValue(
        jsonResponse({
          openapi: "3.1.0",
          info: { title: "TOUCHE COMMERCE API", version: "0.1.0" },
          paths: {
            "/api/v1/health/live": { get: {} },
            "/api/v1/health/ready": { get: {}, parameters: [] },
          },
        }),
      ),
    );

    const result = await fetchContract();

    expect(result.ok).toBe(true);
    if (!result.ok) throw new Error("expected a successful result");
    expect(result.data.operationCount).toBe(2);
    expect(result.data.title).toBe("TOUCHE COMMERCE API");
    expect(result.data.version).toBe("0.1.0");
  });

  it("returns null for documents that are not OpenAPI", () => {
    expect(summariseOpenApi({ hello: "world" })).toBeNull();
    expect(summariseOpenApi(null)).toBeNull();
  });

  it("ignores non-method keys inside a path item", () => {
    const summary = summariseOpenApi({
      openapi: "3.1.0",
      paths: { "/x": { parameters: [], get: {}, summary: "ignored" } },
    });

    expect(summary?.operationCount).toBe(1);
  });
});

describe("parseErrorEnvelope", () => {
  it("accepts the documented envelope", () => {
    expect(
      parseErrorEnvelope({
        error: { code: "NOT_FOUND", message: "missing", request_id: null, timestamp: "x" },
      })?.error.code,
    ).toBe("NOT_FOUND");
  });

  it("rejects unrelated payloads", () => {
    expect(parseErrorEnvelope({ detail: "nope" })).toBeNull();
    expect(parseErrorEnvelope("text")).toBeNull();
  });
});

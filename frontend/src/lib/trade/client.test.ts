import { afterEach, describe, expect, it, vi } from "vitest";

import { createDeal, newIdempotencyKey, transitionDeal } from "./client";

function jsonResponse(
  body: unknown,
  init: { status?: number; headers?: Record<string, string> } = {},
): Response {
  return new Response(JSON.stringify(body), {
    status: init.status ?? 200,
    headers: { "content-type": "application/json", ...(init.headers ?? {}) },
  });
}

const dealPayload = {
  id: "d1",
  company_id: "c1",
  reference: "T-2610-ABC123",
  title: "50 MT aluminium",
  status: "DRAFT",
  counterparty_id: "cp1",
  counterparty_name: "Acme Metals",
  currency: "USD",
  expected_close_date: null,
  notes: null,
  total_value: "122500.00",
  version: 1,
  created_by: "u1",
  closed_at: null,
  created_at: "2026-10-22T09:00:00Z",
  updated_at: "2026-10-22T09:00:00Z",
  items: [],
  transitions: [],
  allowed_transitions: ["OPEN", "CANCELLED"],
};

afterEach(() => {
  vi.unstubAllGlobals();
});

describe("trade client", () => {
  it("sends CSRF, a fresh idempotency key and the If-Match version", async () => {
    const fetchMock = vi
      .fn()
      .mockResolvedValue(
        jsonResponse(dealPayload, { headers: { etag: '"v2"', "x-request-id": "r1" } }),
      );
    vi.stubGlobal("fetch", fetchMock);

    const result = await transitionDeal("d1", { to: "OPEN", reason: null }, "csrf-token", '"v1"');

    expect(result.ok).toBe(true);
    if (!result.ok) throw new Error("expected success");
    expect(result.etag).toBe('"v2"');

    const [url, init] = fetchMock.mock.calls[0] as [string, RequestInit];
    expect(url).toBe("/api/v1/deals/d1/transitions");
    expect(init.method).toBe("POST");
    const headers = init.headers as Record<string, string>;
    expect(headers["X-CSRF-Token"]).toBe("csrf-token");
    expect(headers["If-Match"]).toBe('"v1"');
    expect(headers["Idempotency-Key"]).toBeTruthy();
    expect(headers["Idempotency-Key"]).not.toBe("csrf-token");
    expect(JSON.parse(String(init.body))).toEqual({ to: "OPEN", reason: null });
  });

  it("maps the API error envelope and keeps the request id", async () => {
    vi.stubGlobal(
      "fetch",
      vi.fn().mockResolvedValue(
        jsonResponse(
          {
            error: {
              code: "TRANSITION_DISABLED",
              message: "The WON transition is disabled.",
              request_id: "req-9",
              timestamp: "2026-10-22T09:00:00Z",
              details: null,
            },
          },
          { status: 409, headers: { "x-request-id": "req-9" } },
        ),
      ),
    );

    const result = await transitionDeal("d1", { to: "WON" }, "csrf");

    expect(result.ok).toBe(false);
    if (result.ok) throw new Error("expected a failure");
    expect(result.code).toBe("TRANSITION_DISABLED");
    expect(result.requestId).toBe("req-9");
  });

  it("reports an unreachable API instead of throwing", async () => {
    vi.stubGlobal("fetch", vi.fn().mockRejectedValue(new Error("offline")));

    const result = await createDeal(
      {
        title: "Deal",
        counterparty_id: "cp1",
        currency: "USD",
        items: [{ product_id: "p1", quantity: "1.000", unit_price: "10.0000" }],
      },
      "csrf",
    );

    expect(result.ok).toBe(false);
    if (result.ok) throw new Error("expected a failure");
    expect(result.code).toBe("UNREACHABLE");
  });

  it("generates unique idempotency keys", () => {
    const keys = new Set(Array.from({ length: 20 }, () => newIdempotencyKey()));
    expect(keys.size).toBe(20);
    for (const key of keys) expect(key.length).toBeGreaterThanOrEqual(8);
  });
});

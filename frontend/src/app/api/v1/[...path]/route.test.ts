import { NextRequest } from "next/server";
import { afterEach, describe, expect, it, vi } from "vitest";

import { GET } from "./route";

afterEach(() => {
  vi.unstubAllGlobals();
});

function context(...path: string[]) {
  return { params: Promise.resolve({ path }) };
}

describe("same-origin API proxy", () => {
  it("passes the CSV download headers through and drops unlisted ones", async () => {
    const fetchMock = vi.fn().mockResolvedValue(
      new Response("record_type\r\n", {
        status: 200,
        headers: {
          "content-type": "text/csv; charset=utf-8",
          "content-disposition": 'attachment; filename="analysis-20261023.csv"',
          "x-content-type-options": "nosniff",
          "x-internal-debug": "must-not-leak",
        },
      }),
    );
    vi.stubGlobal("fetch", fetchMock);

    const response = await GET(
      new NextRequest("http://localhost:3000/api/v1/finance/intelligence/export?currency=USD", {
        headers: { cookie: "session=abc", "x-unlisted": "dropped" },
      }),
      context("finance", "intelligence", "export"),
    );

    expect(response.status).toBe(200);
    expect(response.headers.get("content-disposition")).toBe(
      'attachment; filename="analysis-20261023.csv"',
    );
    expect(response.headers.get("x-content-type-options")).toBe("nosniff");
    expect(response.headers.get("content-type")).toContain("text/csv");
    expect(response.headers.get("cache-control")).toBe("no-store");
    expect(response.headers.get("x-internal-debug")).toBeNull();

    const [target, init] = fetchMock.mock.calls[0] as [URL, RequestInit];
    expect(target.pathname).toBe("/api/v1/finance/intelligence/export");
    expect(target.search).toBe("?currency=USD");
    const forwarded = init.headers as Headers;
    expect(forwarded.get("cookie")).toBe("session=abc");
    expect(forwarded.get("x-unlisted")).toBeNull();
  });

  it("reports an unreachable API as a standard error envelope", async () => {
    vi.stubGlobal("fetch", vi.fn().mockRejectedValue(new Error("connect ECONNREFUSED")));

    const response = await GET(
      new NextRequest("http://localhost:3000/api/v1/finance/intelligence/summary"),
      context("finance", "intelligence", "summary"),
    );

    expect(response.status).toBe(502);
    const body = (await response.json()) as { error: { code: string } };
    expect(body.error.code).toBe("UPSTREAM_UNAVAILABLE");
  });
});

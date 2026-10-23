/**
 * Same-origin API proxy.
 *
 * The browser only ever calls /api/v1/* on the Next.js origin, so the session
 * cookie is first-party, `Set-Cookie` attributes are honoured by the browser,
 * and CSRF/Origin validation behave the same locally as in production.
 *
 * Only an explicit allow-list of headers is forwarded in either direction: the
 * proxy must not become a generic tunnel.
 */

import type { NextRequest } from "next/server";

import { API_PROXY_TARGET } from "@/lib/api/config";

export const dynamic = "force-dynamic";
export const runtime = "nodejs";

const REQUEST_HEADERS = [
  "accept",
  "content-type",
  "cookie",
  "origin",
  "user-agent",
  "x-csrf-token",
  "x-request-id",
  "if-match",
  "idempotency-key",
] as const;

const RESPONSE_HEADERS = [
  "cache-control",
  "content-disposition",
  "content-type",
  "etag",
  "retry-after",
  "vary",
  "x-content-type-options",
  "x-request-id",
] as const;

const BODYLESS_METHODS = new Set(["GET", "HEAD"]);

async function proxy(
  request: NextRequest,
  context: { params: Promise<{ path: string[] }> },
): Promise<Response> {
  const { path } = await context.params;
  const target = new URL(`${API_PROXY_TARGET}/api/v1/${path.join("/")}`);
  target.search = request.nextUrl.search;

  const headers = new Headers();
  for (const name of REQUEST_HEADERS) {
    const value = request.headers.get(name);
    if (value !== null) headers.set(name, value);
  }

  let upstream: Response;
  try {
    upstream = await fetch(target, {
      method: request.method,
      headers,
      body: BODYLESS_METHODS.has(request.method) ? undefined : await request.arrayBuffer(),
      redirect: "manual",
      cache: "no-store",
      signal: AbortSignal.timeout(15000),
    });
  } catch {
    return Response.json(
      {
        error: {
          code: "UPSTREAM_UNAVAILABLE",
          message: "The TOUCHE COMMERCE API is not reachable.",
          request_id: null,
          timestamp: new Date().toISOString(),
          details: null,
        },
      },
      { status: 502, headers: { "cache-control": "no-store" } },
    );
  }

  const responseHeaders = new Headers();
  for (const name of RESPONSE_HEADERS) {
    const value = upstream.headers.get(name);
    if (value !== null) responseHeaders.set(name, value);
  }
  for (const cookie of upstream.headers.getSetCookie()) {
    responseHeaders.append("set-cookie", cookie);
  }
  responseHeaders.set("cache-control", "no-store");

  return new Response(upstream.body, {
    status: upstream.status,
    statusText: upstream.statusText,
    headers: responseHeaders,
  });
}

export {
  proxy as DELETE,
  proxy as GET,
  proxy as HEAD,
  proxy as OPTIONS,
  proxy as PATCH,
  proxy as POST,
  proxy as PUT,
};

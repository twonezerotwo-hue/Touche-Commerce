/**
 * Server-side GET against the API with the incoming session cookie.
 *
 * Used by server components for lists, detail pages and the dashboard. The
 * browser never sees the cookie value or the token; it only receives rendered
 * output. A failure is returned as data (never thrown) so a page can show a real
 * error instead of an empty state that looks like "no records".
 */

import { cookies } from "next/headers";

import { translate } from "@/lib/i18n/messages";
import { getServerLocale } from "@/lib/i18n/server";

import { API_BASE_URL, API_PREFIX, API_REQUEST_TIMEOUT_MS } from "@/lib/api/config";
import { parseErrorEnvelope, type ApiResult } from "@/lib/api/client";

export async function serverGet<T>(path: string): Promise<ApiResult<T>> {
  const cookieHeader = (await cookies()).toString();
  const locale = await getServerLocale();
  const startedAt = Date.now();

  try {
    const response = await fetch(`${API_BASE_URL}${API_PREFIX}${path}`, {
      headers: { accept: "application/json", cookie: cookieHeader },
      cache: "no-store",
      signal: AbortSignal.timeout(API_REQUEST_TIMEOUT_MS),
    });
    const latencyMs = Date.now() - startedAt;
    const payload: unknown = await response.json().catch(() => null);
    const requestId = response.headers.get("x-request-id");

    if (!response.ok) {
      const envelope = parseErrorEnvelope(payload);
      return {
        ok: false,
        status: response.status,
        code: envelope?.error.code ?? `HTTP_${response.status}`,
        message: envelope?.error.message ?? translate(locale, "failUnexpected"),
        requestId: envelope?.error.request_id ?? requestId,
        details: envelope?.error.details ?? null,
        latencyMs,
      };
    }

    if (payload === null) {
      return {
        ok: false,
        status: response.status,
        code: "INVALID_RESPONSE",
        message: translate(locale, "failBadJson"),
        requestId,
        details: null,
        latencyMs,
      };
    }

    return { ok: true, status: response.status, requestId, latencyMs, data: payload as T };
  } catch {
    return {
      ok: false,
      status: null,
      code: "UNREACHABLE",
      message: translate(locale, "failUnreachableAt", { url: API_BASE_URL }),
      requestId: null,
      details: null,
      latencyMs: Date.now() - startedAt,
    };
  }
}

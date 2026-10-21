/**
 * Browser-side authentication client.
 *
 * All calls go to the same-origin proxy (/api/v1/*) so the HttpOnly cookie is
 * first-party. Tokens are never read from or written to localStorage; the CSRF
 * token arrives as a prop from the server-rendered session and is sent back in
 * a header, exactly as documented in docs/API_CONTRACTS.md.
 */

import { parseErrorEnvelope } from "@/lib/api/client";
import { BROWSER_API_PREFIX } from "@/lib/api/config";

import type { AuthSession, LogoutResult } from "./types";

export interface ActionResultSuccess<T> {
  ok: true;
  data: T;
}

export interface ActionResultFailure {
  ok: false;
  code: string;
  message: string;
  retryAfterSeconds: number | null;
}

export type ActionResult<T> = ActionResultSuccess<T> | ActionResultFailure;

interface RequestOptions {
  method: "POST";
  path: string;
  body?: unknown;
  csrfToken?: string;
}

async function request<T>({
  method,
  path,
  body,
  csrfToken,
}: RequestOptions): Promise<ActionResult<T>> {
  const headers: Record<string, string> = { accept: "application/json" };
  if (body !== undefined) headers["content-type"] = "application/json";
  if (csrfToken) headers["X-CSRF-Token"] = csrfToken;

  try {
    const response = await fetch(`${BROWSER_API_PREFIX}${path}`, {
      method,
      headers,
      body: body === undefined ? undefined : JSON.stringify(body),
      credentials: "same-origin",
      cache: "no-store",
    });

    const payload = (await response.json().catch(() => null)) as unknown;

    if (!response.ok) {
      const envelope = parseErrorEnvelope(payload);
      const retryAfter = Number.parseInt(response.headers.get("retry-after") ?? "", 10);
      return {
        ok: false,
        code: envelope?.error.code ?? `HTTP_${response.status}`,
        message: envelope?.error.message ?? "The request could not be completed.",
        retryAfterSeconds: Number.isFinite(retryAfter) ? retryAfter : null,
      };
    }

    return { ok: true, data: payload as T };
  } catch {
    return {
      ok: false,
      code: "UNREACHABLE",
      message: "Cannot reach the API. Confirm the service is running and try again.",
      retryAfterSeconds: null,
    };
  }
}

export function login(email: string, password: string): Promise<ActionResult<AuthSession>> {
  return request<AuthSession>({
    method: "POST",
    path: "/auth/login",
    body: { email, password },
  });
}

export function logout(csrfToken: string): Promise<ActionResult<LogoutResult>> {
  return request<LogoutResult>({ method: "POST", path: "/auth/logout", csrfToken });
}

export function switchCompany(
  companyId: string,
  csrfToken: string,
): Promise<ActionResult<AuthSession>> {
  return request<AuthSession>({
    method: "POST",
    path: "/session/company",
    body: { company_id: companyId },
    csrfToken,
  });
}

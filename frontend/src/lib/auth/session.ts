/**
 * Server-side session loading.
 *
 * Server components talk to FastAPI directly and forward the incoming cookie
 * header, so the session is verified on the server on every render. The browser
 * never receives the token: it stays in the HttpOnly cookie.
 */

import { cache } from "react";

import { cookies } from "next/headers";

import { API_BASE_URL, API_PREFIX, API_REQUEST_TIMEOUT_MS } from "@/lib/api/config";
import { translate } from "@/lib/i18n/messages";
import { getServerLocale } from "@/lib/i18n/server";

import type { AuthSession, SessionState } from "./types";

const SESSION_COOKIE_MARKER = "touche_session";

export const loadSession = cache(async (): Promise<SessionState> => {
  const cookieStore = await cookies();
  const cookieHeader = cookieStore.toString();
  const locale = await getServerLocale();
  if (!cookieHeader.includes(SESSION_COOKIE_MARKER)) {
    return { status: "anonymous" };
  }

  try {
    const response = await fetch(`${API_BASE_URL}${API_PREFIX}/auth/me`, {
      headers: { accept: "application/json", cookie: cookieHeader },
      cache: "no-store",
      signal: AbortSignal.timeout(API_REQUEST_TIMEOUT_MS),
    });

    if (response.status === 401) {
      return { status: "anonymous" };
    }
    if (!response.ok) {
      return {
        status: "unavailable",
        message: translate(locale, "failSessionHttp", { status: response.status }),
      };
    }
    return { status: "authenticated", session: (await response.json()) as AuthSession };
  } catch {
    return {
      status: "unavailable",
      message: translate(locale, "failUnreachableAt", { url: API_BASE_URL }),
    };
  }
});

/** True when the session carries a usable CSRF token for mutations. */
export function csrfTokenOf(session: AuthSession): string {
  return session.session.csrf_token;
}

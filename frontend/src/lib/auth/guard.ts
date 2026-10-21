/**
 * Pure route-guard decisions.
 *
 * Kept free of Next.js imports so the redirect rules can be unit tested without
 * a browser or a running server (see guard.test.ts). Layouts call these helpers
 * and then perform the redirect.
 */

import type { SessionState } from "./types";

export interface RouteDecision {
  /** Where to send the visitor, or null to render the requested route. */
  redirectTo: string | null;
  /** Machine-readable reason, useful for assertions and logging. */
  reason: "anonymous" | "company-required" | "already-signed-in" | null;
}

export function loginPath(nextPath: string): string {
  return `/login?next=${encodeURIComponent(nextPath)}`;
}

/** Only same-origin absolute paths are accepted as post-login redirects. */
export function safeNextPath(candidate: string | null | undefined, fallback = "/"): string {
  if (!candidate) return fallback;
  if (!candidate.startsWith("/") || candidate.startsWith("//")) return fallback;
  return candidate;
}

export function resolveRoute(state: SessionState, pathname: string): RouteDecision {
  if (state.status === "unavailable") {
    return { redirectTo: null, reason: null };
  }

  if (state.status === "anonymous") {
    if (pathname === "/login") return { redirectTo: null, reason: null };
    return { redirectTo: loginPath(pathname), reason: "anonymous" };
  }

  const hasCompany = state.session.session.company !== null;

  if (pathname === "/login") {
    return {
      redirectTo: hasCompany ? "/" : "/select-company",
      reason: "already-signed-in",
    };
  }

  if (!hasCompany && pathname !== "/select-company") {
    return { redirectTo: "/select-company", reason: "company-required" };
  }

  return { redirectTo: null, reason: null };
}

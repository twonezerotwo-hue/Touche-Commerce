import { describe, expect, it } from "vitest";

import { loginPath, resolveRoute, safeNextPath } from "./guard";
import type { AuthSession, SessionState } from "./types";

function sessionWithCompany(companyId: string | null): AuthSession {
  return {
    user: {
      user_id: "11111111-1111-4111-8111-111111111111",
      email: "amina@touche.example",
      display_name: "Amina Haddad",
      status: "active",
    },
    session: {
      session_id: "22222222-2222-4222-8222-222222222222",
      company:
        companyId === null
          ? null
          : {
              company_id: companyId,
              name: "TOUCHE Trading",
              country: "GB",
              default_currency: "GBP",
              status: "active",
              role: "admin",
              permissions: ["company.view"],
            },
      created_at: "2026-10-22T08:00:00Z",
      last_activity_at: "2026-10-22T08:05:00Z",
      idle_expires_at: "2026-10-22T08:35:00Z",
      expires_at: "2026-10-22T20:00:00Z",
      csrf_token: "csrf-token",
      ip_address: null,
      user_agent: null,
    },
    memberships: [],
  };
}

const authenticated = (companyId: string | null): SessionState => ({
  status: "authenticated",
  session: sessionWithCompany(companyId),
});

describe("resolveRoute", () => {
  it("redirects an anonymous visitor to login and remembers the destination", () => {
    const decision = resolveRoute({ status: "anonymous" }, "/account");

    expect(decision.reason).toBe("anonymous");
    expect(decision.redirectTo).toBe(loginPath("/account"));
    expect(decision.redirectTo).toBe("/login?next=%2Faccount");
  });

  it("leaves the login page alone for anonymous visitors", () => {
    expect(resolveRoute({ status: "anonymous" }, "/login")).toEqual({
      redirectTo: null,
      reason: null,
    });
  });

  it("sends a signed-in user without a company to company selection", () => {
    const decision = resolveRoute(authenticated(null), "/");

    expect(decision.reason).toBe("company-required");
    expect(decision.redirectTo).toBe("/select-company");
  });

  it("allows company selection itself when no company is active", () => {
    expect(resolveRoute(authenticated(null), "/select-company").redirectTo).toBeNull();
  });

  it("renders the workspace once a company is active", () => {
    expect(resolveRoute(authenticated("33333333-3333-4333-8333-333333333333"), "/account")).toEqual(
      { redirectTo: null, reason: null },
    );
  });

  it("keeps a signed-in user away from the login screen", () => {
    expect(resolveRoute(authenticated("33333333-3333-4333-8333-333333333333"), "/login")).toEqual({
      redirectTo: "/",
      reason: "already-signed-in",
    });
    expect(resolveRoute(authenticated(null), "/login")).toEqual({
      redirectTo: "/select-company",
      reason: "already-signed-in",
    });
  });

  it("never redirects when the API is unreachable", () => {
    expect(resolveRoute({ status: "unavailable", message: "down" }, "/")).toEqual({
      redirectTo: null,
      reason: null,
    });
  });
});

describe("safeNextPath", () => {
  it("accepts same-origin paths only", () => {
    expect(safeNextPath("/account")).toBe("/account");
    expect(safeNextPath("/account?tab=1")).toBe("/account?tab=1");
    expect(safeNextPath("https://evil.example/steal")).toBe("/");
    expect(safeNextPath("//evil.example")).toBe("/");
    expect(safeNextPath(null)).toBe("/");
    expect(safeNextPath("", "/select-company")).toBe("/select-company");
  });
});

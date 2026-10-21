import { render, screen } from "@testing-library/react";
import { describe, expect, it } from "vitest";

import { AccountSummary } from "./account-summary";
import type { AuthSession } from "@/lib/auth/types";

const SESSION: AuthSession = {
  user: {
    user_id: "11111111-1111-4111-8111-111111111111",
    email: "amina@touche.example",
    display_name: "Amina Haddad",
    status: "active",
  },
  session: {
    session_id: "22222222-2222-4222-8222-222222222222",
    company: {
      company_id: "33333333-3333-4333-8333-333333333333",
      name: "TOUCHE Trading",
      country: "GB",
      default_currency: "GBP",
      status: "active",
      role: "approver",
      permissions: ["company.view", "finance.approve"],
    },
    created_at: "2026-10-22T08:00:00Z",
    last_activity_at: "2026-10-22T08:10:00Z",
    idle_expires_at: "2026-10-22T08:40:00Z",
    expires_at: "2026-10-22T20:00:00Z",
    csrf_token: "csrf",
    ip_address: "127.0.0.1",
    user_agent: "vitest",
  },
  memberships: [],
};

describe("AccountSummary", () => {
  it("renders the authenticated identity, company and permissions", () => {
    render(<AccountSummary session={SESSION} />);

    expect(screen.getByText("Amina Haddad")).toBeInTheDocument();
    expect(screen.getByText("amina@touche.example")).toBeInTheDocument();
    expect(screen.getByText("TOUCHE Trading · GB")).toBeInTheDocument();
    expect(screen.getByText("Approver")).toBeInTheDocument();
    expect(screen.getByText("finance.approve")).toBeInTheDocument();
    expect(screen.getByText("company.view")).toBeInTheDocument();
    expect(screen.getByText("2026-10-22 20:00:00 UTC")).toBeInTheDocument();
    expect(screen.getByText(/127\.0\.0\.1 · vitest/)).toBeInTheDocument();
  });

  it("states explicitly when no company is selected", () => {
    render(
      <AccountSummary
        session={{
          ...SESSION,
          session: { ...SESSION.session, company: null },
        }}
      />,
    );

    expect(screen.getByText("Not selected")).toBeInTheDocument();
    expect(screen.getByText("No active company")).toBeInTheDocument();
    expect(
      screen.getByText("No permissions apply until a company is selected."),
    ).toBeInTheDocument();
  });
});

import { render, screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { beforeEach, describe, expect, it, vi } from "vitest";

import { CompanySwitcher } from "./company-switcher";
import type { CompanyAccess } from "@/lib/auth/types";

const refreshMock = vi.fn();
const switchCompanyMock = vi.fn();

vi.mock("next/navigation", () => ({
  useRouter: () => ({ refresh: refreshMock, replace: vi.fn(), push: vi.fn() }),
}));

vi.mock("@/lib/auth/client", () => ({
  switchCompany: (...args: unknown[]) => switchCompanyMock(...args),
}));

function company(overrides: Partial<CompanyAccess>): CompanyAccess {
  return {
    company_id: "c1",
    name: "TOUCHE Trading",
    country: "GB",
    default_currency: "GBP",
    status: "active",
    role: "admin",
    permissions: ["company.view"],
    ...overrides,
  };
}

const COMPANIES: CompanyAccess[] = [
  company({ company_id: "c1", name: "TOUCHE Trading", role: "admin" }),
  company({
    company_id: "c2",
    name: "Meridian Commodities",
    country: "AE",
    default_currency: "USD",
    role: "viewer",
  }),
];

beforeEach(() => {
  refreshMock.mockReset();
  switchCompanyMock.mockReset();
});

describe("CompanySwitcher", () => {
  it("lists every company with role and marks the active one", () => {
    render(<CompanySwitcher companies={COMPANIES} activeCompanyId="c1" csrfToken="csrf-token" />);

    expect(screen.getByText("TOUCHE Trading")).toBeInTheDocument();
    expect(screen.getByText("Meridian Commodities")).toBeInTheDocument();
    expect(screen.getByText("Current")).toBeInTheDocument();
    expect(screen.getByText(/GB · GBP · Administrator/)).toBeInTheDocument();
    expect(screen.getByText(/AE · USD · Viewer/)).toBeInTheDocument();
    expect(screen.getByRole("button", { name: /TOUCHE Trading/ })).toBeDisabled();
  });

  it("switches company with the CSRF token and refreshes server data", async () => {
    const user = userEvent.setup();
    switchCompanyMock.mockResolvedValue({ ok: true, data: {} });
    render(<CompanySwitcher companies={COMPANIES} activeCompanyId="c1" csrfToken="csrf-token" />);

    await user.click(screen.getByRole("button", { name: /Meridian Commodities/ }));

    await waitFor(() => expect(switchCompanyMock).toHaveBeenCalledWith("c2", "csrf-token"));
    await waitFor(() => expect(refreshMock).toHaveBeenCalled());
  });

  it("shows the server error and does not refresh when switching is refused", async () => {
    const user = userEvent.setup();
    switchCompanyMock.mockResolvedValue({
      ok: false,
      code: "FORBIDDEN",
      message: "You are not authorised to access that company.",
      retryAfterSeconds: null,
    });
    render(<CompanySwitcher companies={COMPANIES} activeCompanyId="c1" csrfToken="csrf-token" />);

    await user.click(screen.getByRole("button", { name: /Meridian Commodities/ }));

    expect(await screen.findByRole("alert")).toHaveTextContent(
      "You are not authorised to access that company.",
    );
    expect(refreshMock).not.toHaveBeenCalled();
  });

  it("explains an empty membership list instead of rendering nothing", () => {
    render(<CompanySwitcher companies={[]} activeCompanyId={null} csrfToken="csrf-token" />);

    expect(screen.getByText("No company access")).toBeInTheDocument();
  });
});

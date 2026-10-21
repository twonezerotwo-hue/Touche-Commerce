import { render, screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { beforeEach, describe, expect, it, vi } from "vitest";

import { LogoutButton } from "./logout-button";

const replaceMock = vi.fn();
const refreshMock = vi.fn();
const logoutMock = vi.fn();

vi.mock("next/navigation", () => ({
  useRouter: () => ({ replace: replaceMock, refresh: refreshMock, push: vi.fn() }),
}));

vi.mock("@/lib/auth/client", () => ({
  logout: (...args: unknown[]) => logoutMock(...args),
}));

beforeEach(() => {
  replaceMock.mockReset();
  refreshMock.mockReset();
  logoutMock.mockReset();
});

describe("LogoutButton", () => {
  it("revokes the session with the CSRF token and returns to login", async () => {
    const user = userEvent.setup();
    logoutMock.mockResolvedValue({ ok: true, data: { status: "signed_out" } });
    render(<LogoutButton csrfToken="csrf-token" />);

    await user.click(screen.getByRole("button", { name: /sign out/i }));

    await waitFor(() => expect(logoutMock).toHaveBeenCalledWith("csrf-token"));
    await waitFor(() => expect(replaceMock).toHaveBeenCalledWith("/login"));
    expect(refreshMock).toHaveBeenCalled();
  });

  it("reports a failed revocation and stays on the page", async () => {
    const user = userEvent.setup();
    logoutMock.mockResolvedValue({
      ok: false,
      code: "UNREACHABLE",
      message: "Cannot reach the API.",
      retryAfterSeconds: null,
    });
    render(<LogoutButton csrfToken="csrf-token" />);

    await user.click(screen.getByRole("button", { name: /sign out/i }));

    expect(await screen.findByRole("alert")).toHaveTextContent("Cannot reach the API.");
    expect(replaceMock).not.toHaveBeenCalled();
  });
});

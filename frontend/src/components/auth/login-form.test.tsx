import { render, screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";

import { LoginForm } from "./login-form";

const replaceMock = vi.fn();
const refreshMock = vi.fn();
const loginMock = vi.fn();

vi.mock("next/navigation", () => ({
  useRouter: () => ({ replace: replaceMock, refresh: refreshMock, push: vi.fn() }),
}));

vi.mock("@/lib/auth/client", () => ({
  login: (...args: unknown[]) => loginMock(...args),
}));

function sessionPayload(company: unknown) {
  return {
    ok: true as const,
    data: {
      user: {
        user_id: "u1",
        email: "amina@touche.example",
        display_name: "Amina Haddad",
        status: "active",
      },
      session: {
        session_id: "s1",
        company,
        created_at: "2026-10-22T08:00:00Z",
        last_activity_at: "2026-10-22T08:00:00Z",
        idle_expires_at: "2026-10-22T08:30:00Z",
        expires_at: "2026-10-22T20:00:00Z",
        csrf_token: "csrf",
      },
      memberships: [],
    },
  };
}

beforeEach(() => {
  replaceMock.mockReset();
  refreshMock.mockReset();
  loginMock.mockReset();
});

afterEach(() => {
  vi.clearAllMocks();
});

describe("LoginForm", () => {
  it("rejects an empty submit with field-level messages and no API call", async () => {
    const user = userEvent.setup();
    render(<LoginForm nextPath="/account" />);

    await user.click(screen.getByRole("button", { name: /sign in/i }));

    expect(await screen.findByText("Enter your work email.")).toBeInTheDocument();
    expect(screen.getByText("Enter your password.")).toBeInTheDocument();
    expect(loginMock).not.toHaveBeenCalled();
    expect(screen.getByLabelText("Email")).toHaveAttribute("aria-invalid", "true");
  });

  it("rejects a malformed email before calling the API", async () => {
    const user = userEvent.setup();
    render(<LoginForm nextPath="/" />);

    await user.type(screen.getByLabelText("Email"), "not-an-email");
    await user.type(screen.getByLabelText("Password"), "some-password");
    await user.click(screen.getByRole("button", { name: /sign in/i }));

    expect(await screen.findByText("Enter a valid email address.")).toBeInTheDocument();
    expect(loginMock).not.toHaveBeenCalled();
  });

  it("signs in and navigates to the requested page when a company is active", async () => {
    const user = userEvent.setup();
    loginMock.mockResolvedValue(sessionPayload({ company_id: "c1", name: "TOUCHE Trading" }));
    render(<LoginForm nextPath="/account" />);

    await user.type(screen.getByLabelText("Email"), "  amina@touche.example ");
    await user.type(screen.getByLabelText("Password"), "correct horse battery");
    await user.click(screen.getByRole("button", { name: /sign in/i }));

    await waitFor(() =>
      expect(loginMock).toHaveBeenCalledWith("amina@touche.example", "correct horse battery"),
    );
    await waitFor(() => expect(replaceMock).toHaveBeenCalledWith("/account"));
    expect(refreshMock).toHaveBeenCalled();
  });

  it("routes to company selection when the session has no active company", async () => {
    const user = userEvent.setup();
    loginMock.mockResolvedValue(sessionPayload(null));
    render(<LoginForm nextPath="/account" />);

    await user.type(screen.getByLabelText("Email"), "amina@touche.example");
    await user.type(screen.getByLabelText("Password"), "correct horse battery");
    await user.click(screen.getByRole("button", { name: /sign in/i }));

    await waitFor(() => expect(replaceMock).toHaveBeenCalledWith("/select-company"));
  });

  it("shows the generic API message on invalid credentials", async () => {
    const user = userEvent.setup();
    loginMock.mockResolvedValue({
      ok: false,
      code: "UNAUTHORIZED",
      message: "Email or password is incorrect.",
      retryAfterSeconds: null,
    });
    render(<LoginForm nextPath="/" />);

    await user.type(screen.getByLabelText("Email"), "amina@touche.example");
    await user.type(screen.getByLabelText("Password"), "wrong");
    await user.click(screen.getByRole("button", { name: /sign in/i }));

    const alert = await screen.findByRole("alert");
    expect(alert).toHaveTextContent("Email or password is incorrect.");
    expect(replaceMock).not.toHaveBeenCalled();
  });

  it("explains a rate limit with the retry window", async () => {
    const user = userEvent.setup();
    loginMock.mockResolvedValue({
      ok: false,
      code: "RATE_LIMITED",
      message: "Too many attempts.",
      retryAfterSeconds: 42,
    });
    render(<LoginForm nextPath="/" />);

    await user.type(screen.getByLabelText("Email"), "amina@touche.example");
    await user.type(screen.getByLabelText("Password"), "wrong");
    await user.click(screen.getByRole("button", { name: /sign in/i }));

    expect(await screen.findByRole("alert")).toHaveTextContent(
      "Too many sign-in attempts. Try again in 42 seconds.",
    );
  });

  it("never writes credentials to storage", async () => {
    const user = userEvent.setup();
    loginMock.mockResolvedValue(sessionPayload({ company_id: "c1", name: "TOUCHE Trading" }));
    const setItemSpy = vi.spyOn(Storage.prototype, "setItem");
    render(<LoginForm nextPath="/" />);

    await user.type(screen.getByLabelText("Email"), "amina@touche.example");
    await user.type(screen.getByLabelText("Password"), "correct horse battery");
    await user.click(screen.getByRole("button", { name: /sign in/i }));

    await waitFor(() => expect(replaceMock).toHaveBeenCalled());
    expect(setItemSpy).not.toHaveBeenCalled();
  });
});

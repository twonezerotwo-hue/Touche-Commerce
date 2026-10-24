import { render, screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { beforeEach, describe, expect, it, vi } from "vitest";

import type { Deal } from "@/lib/trade/types";

import { TransitionPanel } from "./transition-panel";

const refreshMock = vi.fn();
const transitionMock = vi.fn();

vi.mock("next/navigation", () => ({
  useRouter: () => ({ refresh: refreshMock, push: vi.fn(), replace: vi.fn(), back: vi.fn() }),
}));

vi.mock("@/lib/trade/client", () => ({
  transitionDeal: (...args: unknown[]) => transitionMock(...args),
}));

function deal(overrides: Partial<Deal> = {}): Deal {
  return {
    id: "d1",
    company_id: "c1",
    reference: "T-2610-ABC123",
    title: "50 MT aluminium",
    status: "OPEN",
    counterparty_id: "cp1",
    counterparty_name: "Acme Metals",
    currency: "USD",
    expected_close_date: null,
    notes: null,
    total_value: "122500.00",
    version: 3,
    created_by: "u1",
    closed_at: null,
    created_at: "2026-10-22T09:00:00Z",
    updated_at: "2026-10-22T09:00:00Z",
    items: [],
    transitions: [],
    allowed_transitions: ["NEGOTIATION", "LOST", "CANCELLED"],
    ...overrides,
  };
}

beforeEach(() => {
  refreshMock.mockReset();
  transitionMock.mockReset();
});

describe("TransitionPanel", () => {
  it("renders only the allowed transitions and keeps Won disabled", () => {
    render(<TransitionPanel deal={deal()} csrfToken="csrf" canWrite />);

    expect(screen.getByRole("button", { name: /negotiation/i })).toBeInTheDocument();
    expect(screen.getByRole("button", { name: /lost/i })).toBeInTheDocument();
    expect(screen.getByRole("button", { name: /cancelled/i })).toBeInTheDocument();
    expect(screen.getByRole("button", { name: /won/i })).toBeDisabled();
    expect(screen.getByText(/Won is set only when a sales order is created/i)).toBeInTheDocument();
  });

  it("requires a reason before calling the API for LOST", async () => {
    const user = userEvent.setup();
    render(<TransitionPanel deal={deal()} csrfToken="csrf" canWrite />);

    await user.click(screen.getByRole("button", { name: /^lost$/i }));
    await user.click(screen.getByRole("button", { name: /confirm lost/i }));

    expect(
      await screen.findByText(/reason of at least 3 characters is required/i),
    ).toBeInTheDocument();
    expect(transitionMock).not.toHaveBeenCalled();
  });

  it("sends the reason and If-Match version, then refreshes the page", async () => {
    const user = userEvent.setup();
    transitionMock.mockResolvedValue({ ok: true, data: deal({ status: "LOST" }), etag: '"v4"' });
    render(<TransitionPanel deal={deal()} csrfToken="csrf" canWrite />);

    await user.click(screen.getByRole("button", { name: /^lost$/i }));
    await user.type(screen.getByLabelText(/reason/i), "Buyer withdrew budget");
    await user.click(screen.getByRole("button", { name: /confirm lost/i }));

    await waitFor(() =>
      expect(transitionMock).toHaveBeenCalledWith(
        "d1",
        { to: "LOST", reason: "Buyer withdrew budget" },
        "csrf",
        '"v3"',
      ),
    );
    expect(await screen.findByText(/deal moved to lost/i)).toBeInTheDocument();
    expect(refreshMock).toHaveBeenCalled();
  });

  it("explains a version conflict instead of pretending it worked", async () => {
    const user = userEvent.setup();
    transitionMock.mockResolvedValue({
      ok: false,
      code: "VERSION_CONFLICT",
      message: "The deal was modified by another request.",
      requestId: "r1",
    });
    render(<TransitionPanel deal={deal()} csrfToken="csrf" canWrite />);

    await user.click(screen.getByRole("button", { name: /negotiation/i }));
    await user.click(screen.getByRole("button", { name: /confirm negotiation/i }));

    expect(await screen.findByRole("alert")).toHaveTextContent(/reload before retrying/i);
    expect(refreshMock).not.toHaveBeenCalled();
  });

  it("is read-only without trade.write and inert for terminal deals", () => {
    const { rerender } = render(
      <TransitionPanel deal={deal()} csrfToken="csrf" canWrite={false} />,
    );
    expect(screen.getByText(/read-only access/i)).toBeInTheDocument();

    rerender(
      <TransitionPanel
        deal={deal({ status: "LOST", allowed_transitions: [] })}
        csrfToken="csrf"
        canWrite
      />,
    );
    expect(screen.getByText(/terminal status/i)).toBeInTheDocument();
  });
});

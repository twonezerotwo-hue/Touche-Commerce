import { render, screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { beforeEach, describe, expect, it, vi } from "vitest";

import type { Rfq } from "@/lib/sourcing/types";

import { RfqActions } from "./rfq-actions";

const refreshMock = vi.fn();
const transitionMock = vi.fn();

vi.mock("next/navigation", () => ({
  useRouter: () => ({ refresh: refreshMock, push: vi.fn(), replace: vi.fn(), back: vi.fn() }),
}));

vi.mock("@/lib/sourcing/client", () => ({
  transitionRfq: (...args: unknown[]) => transitionMock(...args),
}));

function rfq(overrides: Partial<Rfq> = {}): Rfq {
  return {
    id: "rfq-1",
    company_id: "company-1",
    deal_id: "deal-1",
    deal_reference: "T-2610-ABC123",
    supplier_counterparty_id: "cp-1",
    supplier_name: "Supplier One",
    reference_number: "RFQ-2610-ABC123",
    requested_currency: "USD",
    requested_delivery_terms: "CIF",
    delivery_location: "Rotterdam, NL",
    response_due_date: null,
    notes: null,
    status: "PREPARED",
    revision: 1,
    version: 2,
    sent_channel: null,
    sent_at: null,
    sent_evidence: null,
    created_by: "user-1",
    created_at: "2026-10-22T09:00:00Z",
    updated_at: "2026-10-22T09:30:00Z",
    items: [],
    quotes: [],
    revisions: [],
    allowed_transitions: ["SENT", "CANCELLED"],
    is_editable: true,
    ...overrides,
  };
}

describe("RfqActions", () => {
  beforeEach(() => {
    refreshMock.mockReset();
    transitionMock.mockReset();
  });

  it("explains that a read-only member cannot change an RFQ", () => {
    render(<RfqActions rfq={rfq()} csrfToken="csrf" canWrite={false} />);

    expect(screen.getByText(/Read-only access/i)).toBeInTheDocument();
    expect(screen.queryByRole("button", { name: /Sent/i })).not.toBeInTheDocument();
  });

  it("refuses to call the API when sending without evidence", async () => {
    const user = userEvent.setup();
    render(<RfqActions rfq={rfq()} csrfToken="csrf" canWrite />);

    await user.click(screen.getByRole("button", { name: /Sent/i }));
    await user.click(screen.getByRole("button", { name: /Confirm Sent/i }));

    expect(
      await screen.findByText(/Sending needs a channel and recorded evidence/i),
    ).toBeInTheDocument();
    expect(transitionMock).not.toHaveBeenCalled();
  });

  it("sends the current ETag and reports the new status", async () => {
    const user = userEvent.setup();
    transitionMock.mockResolvedValue({
      ok: true,
      etag: '"v3"',
      data: rfq({ status: "SENT", version: 3, allowed_transitions: ["CANCELLED"] }),
    });

    render(<RfqActions rfq={rfq()} csrfToken="csrf" canWrite />);

    await user.click(screen.getByRole("button", { name: /Sent/i }));
    await user.type(screen.getByLabelText(/Evidence/i), "message-id:<abc@touche>");
    await user.click(screen.getByRole("button", { name: /Confirm Sent/i }));

    await waitFor(() => expect(transitionMock).toHaveBeenCalledTimes(1));
    const [id, payload, csrf, etagHeader] = transitionMock.mock.calls[0] as [
      string,
      Record<string, unknown>,
      string,
      string,
    ];
    expect(id).toBe("rfq-1");
    expect(payload).toMatchObject({
      to: "SENT",
      channel: "email",
      evidence: "message-id:<abc@touche>",
    });
    expect(csrf).toBe("csrf");
    expect(etagHeader).toBe('"v2"');
    expect(await screen.findByText(/RFQ moved to Sent/i)).toBeInTheDocument();
    expect(refreshMock).toHaveBeenCalled();
  });

  it("surfaces a version conflict with a reload instruction", async () => {
    const user = userEvent.setup();
    transitionMock.mockResolvedValue({
      ok: false,
      code: "VERSION_CONFLICT",
      message: "The RFQ was modified by another request.",
      requestId: null,
    });

    render(<RfqActions rfq={rfq()} csrfToken="csrf" canWrite />);

    await user.click(screen.getByRole("button", { name: /Cancelled/i }));
    await user.type(screen.getByLabelText(/Reason/i), "Supplier pricing withdrawn");
    await user.click(screen.getByRole("button", { name: /Confirm Cancelled/i }));

    expect(await screen.findByText(/Reload the RFQ before retrying/i)).toBeInTheDocument();
    expect(refreshMock).not.toHaveBeenCalled();
  });
});

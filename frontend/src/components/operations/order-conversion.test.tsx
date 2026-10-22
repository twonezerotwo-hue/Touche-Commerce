import { render, screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { beforeEach, describe, expect, it, vi } from "vitest";

import type { SalesQuoteOption } from "@/lib/operations/types";

import { OrderConversionPanel } from "./order-conversion";

const pushMock = vi.fn();
const refreshMock = vi.fn();
const acceptMock = vi.fn();
const convertMock = vi.fn();

vi.mock("next/navigation", () => ({
  useRouter: () => ({ push: pushMock, refresh: refreshMock, replace: vi.fn(), back: vi.fn() }),
}));

vi.mock("@/lib/operations/client", () => ({
  recordCustomerAcceptance: (...args: unknown[]) => acceptMock(...args),
  convertDealToOrder: (...args: unknown[]) => convertMock(...args),
}));

function quote(overrides: Partial<SalesQuoteOption> = {}): SalesQuoteOption {
  return {
    id: "quote-1",
    quote_number: "SQ-2610-ABC",
    revision: 1,
    status: "APPROVED",
    currency: "USD",
    total_value: "250.00",
    customer_name: "Buyer Ltd",
    deal_id: "deal-1",
    approved_at: "2026-10-22T09:00:00Z",
    ...overrides,
  };
}

function renderPanel({
  quotes = [quote()],
  acceptances = [],
  canWrite = true,
}: {
  quotes?: SalesQuoteOption[];
  acceptances?: {
    id: string;
    sales_quote_id: string;
    accepted_by_name: string;
    channel: string;
    accepted_at: string;
    sales_quote_revision: number;
    evidence_reference: string;
  }[];
  canWrite?: boolean;
} = {}) {
  return render(
    <OrderConversionPanel
      dealId="deal-1"
      quotes={quotes}
      acceptances={acceptances.map((item) => ({
        company_id: "company-1",
        deal_id: "deal-1",
        evidence_document_id: null,
        notes: null,
        recorded_by: "user-1",
        recorded_at: item.accepted_at,
        ...item,
      }))}
      csrfToken="csrf"
      canWrite={canWrite}
      brokerage={false}
      onBrokerageChange={() => undefined}
    />,
  );
}

describe("OrderConversionPanel", () => {
  beforeEach(() => {
    pushMock.mockReset();
    refreshMock.mockReset();
    acceptMock.mockReset();
    convertMock.mockReset();
  });

  it("states that internal approval is not customer acceptance", () => {
    renderPanel();
    expect(screen.getByText(/Approval is not acceptance/i)).toBeInTheDocument();
  });

  it("refuses to convert without an approved quote", () => {
    renderPanel({ quotes: [quote({ status: "PENDING_APPROVAL" })] });
    expect(screen.getByText(/No approved quote/i)).toBeInTheDocument();
  });

  it("explains read-only access", () => {
    renderPanel({ canWrite: false });
    expect(screen.getByText(/Read-only access/i)).toBeInTheDocument();
  });

  it("never calls the API when the acceptance evidence is missing", async () => {
    const user = userEvent.setup();
    renderPanel();

    await user.type(screen.getByLabelText(/Accepted by/i), "Dana Buyer");
    await user.click(screen.getByRole("button", { name: /Record acceptance and convert/i }));

    expect(await screen.findByText(/evidence reference is required/i)).toBeInTheDocument();
    expect(acceptMock).not.toHaveBeenCalled();
    expect(convertMock).not.toHaveBeenCalled();
  });

  it("records acceptance, converts with that evidence and opens the order", async () => {
    const user = userEvent.setup();
    acceptMock.mockResolvedValue({ ok: true, etag: null, data: { id: "evidence-1" } });
    convertMock.mockResolvedValue({
      ok: true,
      etag: '"v1"',
      data: { id: "order-1", order_number: "SO-2610-ABC" },
    });

    renderPanel();
    await user.type(screen.getByLabelText(/Accepted by/i), "Dana Buyer");
    await user.type(screen.getByLabelText(/Evidence reference/i), "signed quote SQ-2610-ABC");
    await user.click(screen.getByRole("button", { name: /Record acceptance and convert/i }));

    await waitFor(() => expect(convertMock).toHaveBeenCalledTimes(1));
    const [dealId, payload, csrf] = convertMock.mock.calls[0] as [
      string,
      Record<string, unknown>,
      string,
    ];
    expect(dealId).toBe("deal-1");
    expect(payload).toMatchObject({
      sales_quote_id: "quote-1",
      acceptance_evidence_id: "evidence-1",
    });
    expect(csrf).toBe("csrf");
    expect(pushMock).toHaveBeenCalledWith("/orders/order-1");
  });

  it("reuses recorded acceptance instead of asking for it twice", () => {
    renderPanel({
      acceptances: [
        {
          id: "evidence-1",
          sales_quote_id: "quote-1",
          accepted_by_name: "Dana Buyer",
          channel: "SIGNED_QUOTE",
          accepted_at: "2026-10-22T10:00:00Z",
          sales_quote_revision: 1,
          evidence_reference: "signed quote SQ-2610-ABC",
        },
      ],
    });

    expect(screen.getByText(/Acceptance already recorded/i)).toBeInTheDocument();
    expect(screen.queryByLabelText(/Accepted by/i)).not.toBeInTheDocument();
  });
});

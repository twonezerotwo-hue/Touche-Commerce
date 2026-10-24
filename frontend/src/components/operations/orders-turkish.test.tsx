import { render, screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { beforeEach, describe, expect, it, vi } from "vitest";

import { OrderActions } from "./order-actions";
import { OrderConversionPanel } from "./order-conversion";
import { OperationsStatusBadge } from "./status-badge";
import { LocaleProvider } from "@/lib/i18n/locale-provider";
import {
  acceptanceChannelText,
  documentTypeText,
  fulfilmentModelText,
  operationsStatusText,
  transportModeText,
} from "@/lib/i18n/value-labels";
import { translate } from "@/lib/i18n/messages";
import type { SalesOrder, SalesQuoteOption } from "@/lib/operations/types";

const refreshMock = vi.fn();
const pushMock = vi.fn();
const acceptMock = vi.fn();
const convertMock = vi.fn();
const transitionMock = vi.fn();
const amendMock = vi.fn();

vi.mock("next/navigation", () => ({
  useRouter: () => ({ refresh: refreshMock, push: pushMock, replace: vi.fn(), back: vi.fn() }),
}));
vi.mock("@/lib/operations/client", () => ({
  recordCustomerAcceptance: (...args: unknown[]) => acceptMock(...args),
  convertDealToOrder: (...args: unknown[]) => convertMock(...args),
  transitionSalesOrder: (...args: unknown[]) => transitionMock(...args),
  amendSalesOrder: (...args: unknown[]) => amendMock(...args),
}));

const inTurkish = (ui: React.ReactElement) =>
  render(<LocaleProvider initialLocale="tr">{ui}</LocaleProvider>);

const approved: SalesQuoteOption = {
  id: "quote-1",
  quote_number: "SQ-2610-ABC",
  revision: 1,
  status: "APPROVED",
  currency: "USD",
  total_value: "250.00",
  customer_name: "Buyer Ltd",
  deal_id: "deal-1",
  approved_at: "2026-10-22T09:00:00Z",
} as SalesQuoteOption;

function order(overrides: Partial<SalesOrder> = {}): SalesOrder {
  return {
    id: "o1",
    order_number: "SO-2610-001",
    status: "CONFIRMED",
    version: 2,
    allowed_transitions: ["CLOSED", "CANCELLED"],
    ...overrides,
  } as SalesOrder;
}

beforeEach(() => {
  refreshMock.mockReset();
  pushMock.mockReset();
  acceptMock.mockReset();
  convertMock.mockReset();
  transitionMock.mockReset();
  amendMock.mockReset();
});

describe("operations vocabulary", () => {
  it("translates every code the API stores and leaves unknown codes readable", () => {
    const tr = (key: Parameters<typeof translate>[1]) => translate("tr", key);
    expect(operationsStatusText(tr, "IN_FULFILLMENT")).toBe("Karşılanıyor");
    expect(operationsStatusText(tr, "SOMETHING_NEW")).toBe("SOMETHING NEW");
    expect(documentTypeText(tr, "BILL_OF_LADING")).toBe("Konşimento");
    expect(transportModeText(tr, "SEA")).toBe("Deniz");
    expect(fulfilmentModelText(tr, "BROKERAGE")).toBe("Komisyonculuk");
    expect(acceptanceChannelText(tr, "SIGNED_QUOTE")).toBe("imzalı teklif");
    const en = (key: Parameters<typeof translate>[1]) => translate("en", key);
    expect(operationsStatusText(en, "IN_TRANSIT")).toBe("In transit");
    expect(documentTypeText(en, "OTHER")).toBe("Supporting document");
  });

  it("shows a status badge in the reader's language", () => {
    inTurkish(<OperationsStatusBadge status="DELIVERED" />);
    expect(screen.getByText("Teslim edildi")).toBeInTheDocument();
  });
});

describe("order actions in Turkish", () => {
  it("offers Turkish controls and records a cancellation with its reason", async () => {
    const user = userEvent.setup();
    transitionMock.mockResolvedValue({ ok: true, data: { status: "CANCELLED" } });
    inTurkish(<OrderActions order={order()} csrfToken="c" canWrite />);

    expect(screen.getByRole("button", { name: "Siparişi kapat" })).toBeInTheDocument();
    await user.click(screen.getByRole("button", { name: "Siparişi iptal et" }));
    expect(screen.getByText(/İptal, gerekçesiyle kaydedilir/)).toBeVisible();

    await user.click(screen.getByRole("button", { name: "Onayla" }));
    expect(
      await screen.findByText("İptal için en az 3 karakterlik bir gerekçe gerekir."),
    ).toBeInTheDocument();
    expect(transitionMock).not.toHaveBeenCalled();

    await user.type(screen.getByLabelText("Gerekçe (zorunlu)"), "Müşteri vazgeçti");
    await user.click(screen.getByRole("button", { name: "Onayla" }));
    await waitFor(() =>
      expect(transitionMock).toHaveBeenCalledWith(
        "o1",
        "CANCELLED",
        "Müşteri vazgeçti",
        "c",
        '"v2"',
      ),
    );
    expect(await screen.findByText("Sipariş artık: iptal edildi.")).toBeInTheDocument();
  });

  it("is read-only in Turkish for a role without the trade permission", () => {
    inTurkish(<OrderActions order={order()} csrfToken="c" canWrite={false} />);
    expect(screen.getByText("Salt okunur erişim")).toBeInTheDocument();
    expect(
      screen.getByText("Bir siparişi değiştirmek için trade.write gerekir."),
    ).toBeInTheDocument();
  });
});

describe("conversion panel in Turkish", () => {
  const renderPanel = (quotes = [approved]) =>
    inTurkish(
      <OrderConversionPanel
        dealId="deal-1"
        quotes={quotes}
        acceptances={[]}
        csrfToken="c"
        canWrite
        brokerage={false}
        onBrokerageChange={() => undefined}
      />,
    );

  it("explains approval versus acceptance and validates the evidence in Turkish", async () => {
    const user = userEvent.setup();
    renderPanel();
    expect(screen.getByText("Onay, kabul değildir")).toBeInTheDocument();
    expect(screen.getByLabelText("Onaylı teklif revizyonu")).toBeInTheDocument();
    expect(
      screen.getByRole("option", { name: "Alım-satım (TOUCHE satın alır)" }),
    ).toBeInTheDocument();
    expect(screen.getByRole("option", { name: "imzalı teklif" })).toHaveValue("SIGNED_QUOTE");

    await user.type(screen.getByLabelText(/Kabul eden/), "Dana Buyer");
    await user.click(screen.getByRole("button", { name: "Onayı kaydet ve dönüştür" }));
    expect(await screen.findByText(/Bir kanıt referansı gerekir/)).toBeInTheDocument();
    expect(acceptMock).not.toHaveBeenCalled();
  });

  it("says so in Turkish when no quote is approved", () => {
    renderPanel([]);
    expect(screen.getByText("Onaylı teklif yok")).toBeInTheDocument();
  });
});

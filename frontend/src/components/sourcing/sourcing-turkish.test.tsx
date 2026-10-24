import { render, screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { beforeEach, describe, expect, it, vi } from "vitest";

import { PricingForm } from "./pricing-form";
import { QuoteForm } from "./quote-form";
import { RfqActions } from "./rfq-actions";
import { SalesQuoteActions } from "./sales-quote-actions";
import { SourcingStatusBadge } from "./status-badge";
import { LocaleProvider } from "@/lib/i18n/locale-provider";
import { translate } from "@/lib/i18n/messages";
import { costBasisText, costTypeText, sourcingStatusText } from "@/lib/i18n/value-labels";
import type { Rfq, SalesQuote, SupplierQuote } from "@/lib/sourcing/types";

const refreshMock = vi.fn();
const transitionMock = vi.fn();
const actMock = vi.fn();
const createScenarioMock = vi.fn();
const recordQuoteMock = vi.fn();

vi.mock("next/navigation", () => ({
  useRouter: () => ({ refresh: refreshMock, push: vi.fn(), replace: vi.fn(), back: vi.fn() }),
}));
vi.mock("@/lib/sourcing/client", () => ({
  transitionRfq: (...args: unknown[]) => transitionMock(...args),
  actOnSalesQuote: (...args: unknown[]) => actMock(...args),
  createPricingScenario: (...args: unknown[]) => createScenarioMock(...args),
  recordSupplierQuote: (...args: unknown[]) => recordQuoteMock(...args),
}));

const inTurkish = (ui: React.ReactElement) =>
  render(<LocaleProvider initialLocale="tr">{ui}</LocaleProvider>);

const rfq = (overrides: Partial<Rfq> = {}): Rfq =>
  ({
    id: "rfq-1",
    status: "PREPARED",
    version: 2,
    allowed_transitions: ["SENT", "CANCELLED"],
    delivery_location: "Rotterdam, NL",
    requested_currency: "USD",
    items: [
      {
        id: "i1",
        product_id: "p1",
        sku: "ALM-01",
        description: "Almonds",
        quantity: "250.000",
        unit: "kg",
      },
    ],
    ...overrides,
  }) as Rfq;

const salesQuote = (overrides: Partial<SalesQuote> = {}): SalesQuote =>
  ({
    id: "sq-1",
    status: "DRAFT",
    version: 1,
    allowed_transitions: ["WITHDRAWN"],
    can_submit: true,
    scenario_status: "ESTIMATED",
    superseded_by_sales_quote_id: null,
    ...overrides,
  }) as SalesQuote;

const supplierQuote = {
  id: "q1",
  currency: "EUR",
  items: [{ id: "qi1", product_id: "p1", sku: "ALM-01" }],
} as SupplierQuote;

beforeEach(() => {
  refreshMock.mockReset();
  transitionMock.mockReset();
  actMock.mockReset();
  createScenarioMock.mockReset();
  recordQuoteMock.mockReset();
});

describe("sourcing words", () => {
  it("every sourcing status code has a Turkish word and falls back to the code when unknown", () => {
    const t = (key: Parameters<typeof translate>[1]) => translate("tr", key);
    expect(sourcingStatusText(t, "PENDING_APPROVAL")).toBe("Onay bekliyor");
    expect(sourcingStatusText(t, "VERIFIED_INPUTS")).toBe("Girdiler doğrulandı");
    expect(sourcingStatusText(t, "RESPONDED")).toBe("Yanıtlandı");
    expect(sourcingStatusText(t, "SOMETHING_NEW")).toBe("SOMETHING_NEW");
  });

  it("translates the landed-cost vocabulary", () => {
    const t = (key: Parameters<typeof translate>[1]) => translate("tr", key);
    expect(costTypeText(t, "CUSTOMS_DUTY")).toBe("Gümrük vergisi");
    expect(costTypeText(t, "NEW_COST")).toBe("NEW COST");
    expect(costBasisText(t, "ORDER")).toBe("Siparişin tamamı (oransal)");
  });

  it("shows the status badge in the reader's language", () => {
    inTurkish(<SourcingStatusBadge status="PENDING_APPROVAL" />);
    expect(screen.getByText("Onay bekliyor")).toBeInTheDocument();
  });
});

describe("RFQ lifecycle panel in Turkish", () => {
  it("is read-only without trade.write", () => {
    inTurkish(<RfqActions rfq={rfq()} csrfToken="c" canWrite={false} />);
    expect(screen.getByText("Salt okunur erişim")).toBeInTheDocument();
    expect(
      screen.getByText("Bir RFQ'yu değiştirmek için trade.write gerekir."),
    ).toBeInTheDocument();
  });

  it("will not send without a channel and evidence, and says so in Turkish", async () => {
    const user = userEvent.setup();
    inTurkish(<RfqActions rfq={rfq()} csrfToken="c" canWrite />);
    await user.click(screen.getByRole("button", { name: "Gönderildi" }));
    await user.click(screen.getByRole("button", { name: "Onayla: Gönderildi" }));
    expect(
      await screen.findByText(
        "Göndermek için bir kanal ve kayıtlı kanıt gerekir (örneğin ileti numarası).",
      ),
    ).toBeInTheDocument();
    expect(transitionMock).not.toHaveBeenCalled();
  });

  it("requires a cancellation reason", async () => {
    const user = userEvent.setup();
    inTurkish(<RfqActions rfq={rfq()} csrfToken="c" canWrite />);
    await user.click(screen.getByRole("button", { name: "İptal edildi" }));
    await user.click(screen.getByRole("button", { name: "Onayla: İptal edildi" }));
    expect(
      await screen.findByText("Bir RFQ'yu iptal etmek için en az 3 karakterlik gerekçe gerekir."),
    ).toBeInTheDocument();
  });
});

describe("sales quote workflow panel in Turkish", () => {
  it("offers submission to a trader and asks for confirmation", async () => {
    const user = userEvent.setup();
    inTurkish(<SalesQuoteActions quote={salesQuote()} csrfToken="c" canWrite canApprove={false} />);
    await user.click(screen.getByRole("button", { name: "Onaya sun" }));
    expect(screen.getByText("Bu teklif onaya sunulsun mu?")).toBeInTheDocument();
  });

  it("explains that unverified inputs block approval", async () => {
    const user = userEvent.setup();
    inTurkish(
      <SalesQuoteActions
        quote={salesQuote({ can_submit: false })}
        csrfToken="c"
        canWrite
        canApprove={false}
      />,
    );
    await user.click(screen.getByRole("button", { name: "Onaya sun" }));
    expect(screen.getByText("Girdiler doğrulanmadı")).toBeInTheDocument();
    expect(screen.getByText(/Fiyatlandırma senaryosunun durumu: Tahmini\./)).toBeInTheDocument();
  });

  it("is read-only without any permission", () => {
    inTurkish(
      <SalesQuoteActions quote={salesQuote()} csrfToken="c" canWrite={false} canApprove={false} />,
    );
    expect(
      screen.getByText("İş akışı için trade.write, onay için finance.approve gerekir."),
    ).toBeInTheDocument();
  });

  it("approval stays hidden from someone without finance.approve", () => {
    inTurkish(
      <SalesQuoteActions
        quote={salesQuote({ status: "PENDING_APPROVAL", allowed_transitions: [] })}
        csrfToken="c"
        canWrite
        canApprove={false}
      />,
    );
    expect(screen.queryByRole("button", { name: "Onayla" })).not.toBeInTheDocument();
  });
});

describe("pricing form in Turkish", () => {
  it("labels the landed-cost inputs in Turkish and keeps the cost type codes", async () => {
    inTurkish(<PricingForm quote={supplierQuote} fxRates={[]} csrfToken="c" />);
    expect(screen.getByLabelText("Hedef para birimi")).toBeInTheDocument();
    expect(screen.getByRole("option", { name: "Fiyat üzerinden marj" })).toBeInTheDocument();
    expect(screen.getByRole("option", { name: "Navlun" })).toBeInTheDocument();
    expect((screen.getByRole("option", { name: "Navlun" }) as HTMLOptionElement).value).toBe(
      "FREIGHT",
    );
  });

  it("does not call the API when a cost has no source reference", async () => {
    const user = userEvent.setup();
    inTurkish(<PricingForm quote={supplierQuote} fxRates={[]} csrfToken="c" />);
    await user.click(screen.getByRole("button", { name: "Toplam ithalat maliyetini hesapla" }));
    expect(
      await screen.findByText(
        "Her maliyet bileşeni için en az 3 karakterlik kaynak referansı gerekir.",
      ),
    ).toBeInTheDocument();
    expect(createScenarioMock).not.toHaveBeenCalled();
  });
});

describe("supplier quote form in Turkish", () => {
  it("pre-fills the payment terms in Turkish and validates before calling the API", async () => {
    const user = userEvent.setup();
    inTurkish(<QuoteForm rfq={rfq()} csrfToken="c" defaultCurrency="USD" />);
    expect(screen.getByLabelText("Ödeme koşulları")).toHaveValue("30 gün vadeli");
    await user.click(screen.getByRole("button", { name: "Teklifi kaydet" }));
    await waitFor(() =>
      expect(screen.getByText("Teklifin geçerlilik tarihi zorunludur.")).toBeInTheDocument(),
    );
    expect(recordQuoteMock).not.toHaveBeenCalled();
    expect(screen.getByLabelText("ALM-01 birim fiyatı")).toBeInTheDocument();
  });
});

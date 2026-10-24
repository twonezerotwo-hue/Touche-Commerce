import { fireEvent, render, screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { beforeEach, describe, expect, it, vi } from "vitest";

import { DealEditForm } from "./deal-edit-form";
import { DealForm } from "./deal-form";
import { TransitionPanel } from "./transition-panel";
import { LocaleProvider } from "@/lib/i18n/locale-provider";
import type { Counterparty, Deal, Product } from "@/lib/trade/types";

const refreshMock = vi.fn();
const transitionMock = vi.fn();
const updateMock = vi.fn();

vi.mock("next/navigation", () => ({
  useRouter: () => ({ refresh: refreshMock, push: vi.fn(), replace: vi.fn(), back: vi.fn() }),
}));
vi.mock("@/lib/trade/client", () => ({
  transitionDeal: (...args: unknown[]) => transitionMock(...args),
  updateDeal: (...args: unknown[]) => updateMock(...args),
  createDeal: vi.fn(),
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

const buyer = { id: "b1", name: "Rotterdam Foods", type: "supplier" } as Counterparty;
const product = {
  id: "p1",
  sku: "ALU-A7",
  name: "Aluminium",
  unit: "mt",
  unit_price: "2450.0000",
} as Product;

function inTurkish(ui: React.ReactElement) {
  return render(<LocaleProvider initialLocale="tr">{ui}</LocaleProvider>);
}

beforeEach(() => {
  refreshMock.mockReset();
  transitionMock.mockReset();
  updateMock.mockReset();
});

describe("deal form in Turkish", () => {
  it("labels everything in Turkish, shows the stored type word translated and validates in Turkish", () => {
    inTurkish(
      <DealForm
        counterparties={[buyer]}
        products={[product]}
        csrfToken="c"
        defaultCurrency="TRY"
      />,
    );
    expect(screen.getByText("Anlaşma başlığı")).toBeInTheDocument();
    expect(screen.getByLabelText("Başlık")).toBeInTheDocument();
    expect(screen.getByLabelText("Karşı taraf")).toBeInTheDocument();
    expect(screen.getByRole("option", { name: "Rotterdam Foods · Tedarikçi" })).toHaveValue("b1");
    expect(screen.getByLabelText("Beklenen kapanış")).toBeInTheDocument();
    expect(screen.getByLabelText("Miktar (mt)")).toBeInTheDocument();
    expect(screen.getByRole("button", { name: "Kalem ekle" })).toBeInTheDocument();

    const form = screen.getByRole("button", { name: "Anlaşma oluştur" }).closest("form");
    if (!form) throw new Error("no form");
    fireEvent.submit(form);
    expect(screen.getByRole("alert")).toHaveTextContent("Anlaşma başlığı zorunludur.");
  });

  it("asks for master data in Turkish when there is none", () => {
    inTurkish(<DealForm counterparties={[]} products={[]} csrfToken="c" defaultCurrency="TRY" />);
    expect(screen.getByText("Ana veri gerekli")).toBeInTheDocument();
  });
});

describe("status transitions in Turkish", () => {
  it("offers the allowed moves in Turkish and requires a reason in Turkish", async () => {
    const user = userEvent.setup();
    inTurkish(<TransitionPanel deal={deal()} csrfToken="csrf" canWrite />);
    expect(screen.getByRole("button", { name: /Görüşmede/ })).toBeInTheDocument();
    expect(screen.getByRole("button", { name: /Kazanıldı/ })).toBeDisabled();
    expect(
      screen.getByText(/yalnızca anlaşmadan bir satış siparişi oluşturulduğunda/),
    ).toBeVisible();

    await user.click(screen.getByRole("button", { name: /^Kaybedildi/ }));
    await user.click(screen.getByRole("button", { name: /Kaybedildi durumunu onayla/ }));
    expect(await screen.findByText(/en az 3 karakterlik bir gerekçe/)).toBeInTheDocument();
    expect(transitionMock).not.toHaveBeenCalled();
  });

  it("confirms a move in Turkish and sends the API its own vocabulary", async () => {
    const user = userEvent.setup();
    transitionMock.mockResolvedValue({ ok: true, data: { status: "NEGOTIATION" } });
    inTurkish(<TransitionPanel deal={deal()} csrfToken="csrf" canWrite />);

    await user.click(screen.getByRole("button", { name: /Görüşmede/ }));
    await user.click(screen.getByRole("button", { name: /Görüşmede durumunu onayla/ }));

    await waitFor(() =>
      expect(transitionMock).toHaveBeenCalledWith(
        "d1",
        { to: "NEGOTIATION", reason: null },
        "csrf",
        '"v3"',
      ),
    );
    expect(await screen.findByText("Anlaşma Görüşmede durumuna alındı.")).toBeInTheDocument();
  });

  it("explains a closed deal and a missing permission in Turkish", () => {
    const { unmount } = inTurkish(
      <TransitionPanel
        deal={deal({ status: "WON", allowed_transitions: [] })}
        csrfToken="c"
        canWrite
      />,
    );
    expect(screen.getByText("Kapanmış anlaşma")).toBeInTheDocument();
    expect(screen.getByText(/Kazanıldı bir son durumdur/)).toBeInTheDocument();
    unmount();
    inTurkish(<TransitionPanel deal={deal()} csrfToken="c" canWrite={false} />);
    expect(screen.getByText("Salt okunur erişim")).toBeInTheDocument();
  });
});

describe("deal edit form in Turkish", () => {
  it("shows Turkish labels and the version-conflict hint", async () => {
    updateMock.mockResolvedValue({
      ok: false,
      code: "VERSION_CONFLICT",
      message: "Version conflict.",
    });
    inTurkish(<DealEditForm deal={deal()} csrfToken="c" canWrite />);
    expect(screen.getByLabelText("Başlık")).toHaveValue("50 MT aluminium");
    expect(screen.getByText("If-Match v3 ile gönderilir")).toBeInTheDocument();
    await userEvent.click(screen.getByRole("button", { name: "Değişiklikleri kaydet" }));
    expect(await screen.findByRole("alert")).toHaveTextContent(
      "Version conflict. Güncel sürümü görmek için sayfayı yenileyin.",
    );
  });

  it("refuses edits on a closed deal in Turkish", () => {
    inTurkish(<DealEditForm deal={deal({ status: "LOST" })} csrfToken="c" canWrite />);
    expect(screen.getByText("Kapanmış anlaşma")).toBeInTheDocument();
    expect(screen.getByText(/başlık alanları düzenlenemez/)).toBeInTheDocument();
  });
});

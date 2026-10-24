import { fireEvent, render, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { beforeEach, describe, expect, it, vi } from "vitest";

import { CounterpartyForm } from "./counterparty-form";
import { ProductForm } from "./product-form";
import { LocaleProvider } from "@/lib/i18n/locale-provider";
import type { Locale } from "@/lib/i18n/messages";
import { counterpartyTypeLabel, recordStatusLabel } from "@/lib/i18n/value-labels";
import * as trade from "@/lib/trade/client";

vi.mock("@/lib/trade/client", async (importOriginal) => {
  const original = await importOriginal<typeof import("@/lib/trade/client")>();
  return { ...original, createProduct: vi.fn(), createCounterparty: vi.fn() };
});
vi.mock("next/navigation", () => ({
  useRouter: () => ({ push: vi.fn(), refresh: vi.fn(), replace: vi.fn(), back: vi.fn() }),
}));

const mocked = vi.mocked(trade);

/** Submit past the browser's own `required` check, to exercise the form's message. */
function submitForm(buttonName: string) {
  const form = screen.getByRole("button", { name: buttonName }).closest("form");
  if (!form) throw new Error("no form");
  fireEvent.submit(form);
}

function inLocale(locale: Locale, ui: React.ReactElement) {
  return render(<LocaleProvider initialLocale={locale}>{ui}</LocaleProvider>);
}

beforeEach(() => {
  mocked.createProduct.mockReset();
  mocked.createCounterparty.mockReset();
});

describe("product form", () => {
  it("is read-only without the trade permission, in both languages", () => {
    const { unmount } = inLocale("en", <ProductForm csrfToken="c" canWrite={false} />);
    expect(screen.getByText("Read-only access")).toBeVisible();
    expect(screen.getByText(/requires trade.write/)).toBeVisible();
    unmount();
    inLocale("tr", <ProductForm csrfToken="c" canWrite={false} />);
    expect(screen.getByText("Salt okunur erişim")).toBeVisible();
    expect(screen.getByText(/trade.write yetkisi gerekir/)).toBeVisible();
  });

  it("validates in Turkish and confirms the new product in Turkish", async () => {
    mocked.createProduct.mockResolvedValue({
      ok: true,
      data: { sku: "ALU-A7" },
    } as Awaited<ReturnType<typeof trade.createProduct>>);
    inLocale("tr", <ProductForm csrfToken="c" canWrite />);

    await userEvent.click(screen.getByRole("button", { name: "Yeni ürün" }));
    submitForm("Ürün oluştur");
    expect(screen.getByRole("alert")).toHaveTextContent("Stok kodu ve ad zorunludur.");
    expect(mocked.createProduct).not.toHaveBeenCalled();

    await userEvent.type(screen.getByLabelText("Stok kodu"), "alu-a7");
    await userEvent.type(screen.getByLabelText("Ad"), "Alüminyum külçe");
    await userEvent.type(screen.getByLabelText("Birim fiyat"), "2450");
    await userEvent.click(screen.getByRole("button", { name: "Ürün oluştur" }));
    expect(await screen.findByText("ALU-A7 eklendi.")).toBeVisible();
    expect(mocked.createProduct).toHaveBeenCalledWith(
      expect.objectContaining({ sku: "ALU-A7", name: "Alüminyum külçe" }),
      "c",
    );
  });
});

describe("counterparty form", () => {
  it("labels the fields and the type options in Turkish while keeping stored values", async () => {
    inLocale("tr", <CounterpartyForm csrfToken="c" canWrite />);
    await userEvent.click(screen.getByRole("button", { name: "Yeni karşı taraf" }));
    expect(screen.getByLabelText("Ad")).toBeInTheDocument();
    expect(screen.getByLabelText("İlgili kişi adı")).toBeInTheDocument();
    expect(screen.getByLabelText("E-posta")).toBeInTheDocument();
    const type = screen.getByLabelText("Tür");
    expect(screen.getByRole("option", { name: "Tedarikçi" })).toHaveValue("supplier");
    expect(type).toHaveValue("buyer"); // the API still receives its own vocabulary

    submitForm("Karşı taraf oluştur");
    expect(screen.getByRole("alert")).toHaveTextContent("Karşı taraf adı zorunludur.");
  });

  it("shows the server's reason with the request reference in the reader's language", async () => {
    mocked.createCounterparty.mockResolvedValue({
      ok: false,
      code: "CONFLICT",
      message: "Name already exists",
      requestId: "req-9",
    } as Awaited<ReturnType<typeof trade.createCounterparty>>);
    inLocale("tr", <CounterpartyForm csrfToken="c" canWrite />);
    await userEvent.click(screen.getByRole("button", { name: "Yeni karşı taraf" }));
    await userEvent.type(screen.getByLabelText("Ad"), "Acme");
    await userEvent.click(screen.getByRole("button", { name: "Karşı taraf oluştur" }));
    expect(await screen.findByRole("alert")).toHaveTextContent("Name already exists (istek req-9)");
  });
});

describe("stored vocabulary shown in the reader's language", () => {
  it("translates known status and type words and leaves unknown ones alone", () => {
    const t = (key: string) =>
      ({ statusActive: "Aktif", typeBoth: "Alıcı ve tedarikçi" })[key] ?? key;
    expect(recordStatusLabel(t as never, "active")).toBe("Aktif");
    expect(counterpartyTypeLabel(t as never, "both")).toBe("Alıcı ve tedarikçi");
    expect(recordStatusLabel(t as never, "something-new")).toBe("something-new");
  });
});

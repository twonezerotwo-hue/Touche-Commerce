import { fireEvent, render, screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { beforeEach, describe, expect, it, vi } from "vitest";

import { DealForm } from "./deal-form";
import * as trade from "@/lib/trade/client";
import type { Counterparty, Product } from "@/lib/trade/types";

vi.mock("@/lib/trade/client", async (importOriginal) => {
  const original = await importOriginal<typeof import("@/lib/trade/client")>();
  return { ...original, createDeal: vi.fn() };
});
const push = vi.fn();
vi.mock("next/navigation", () => ({
  useRouter: () => ({ push, refresh: vi.fn(), replace: vi.fn(), back: vi.fn() }),
}));

const mocked = vi.mocked(trade);

const buyer = {
  id: "11111111-1111-4111-8111-111111111111",
  name: "Rotterdam Foods",
  type: "buyer",
} as Counterparty;
const product = {
  id: "22222222-2222-4222-8222-222222222222",
  sku: "ALU-A7",
  name: "Aluminium ingot",
  unit: "mt",
  unit_price: "2450.0000",
} as Product;

beforeEach(() => {
  mocked.createDeal.mockReset();
  push.mockReset();
});

describe("deal form", () => {
  it("shows the form when there is master data (it once rendered nothing)", () => {
    render(
      <DealForm
        counterparties={[buyer]}
        products={[product]}
        csrfToken="c"
        defaultCurrency="USD"
      />,
    );
    expect(screen.getByLabelText("Title")).toBeInTheDocument();
    expect(screen.getByLabelText("Counterparty")).toBeInTheDocument();
    expect(screen.getByRole("button", { name: "Create deal" })).toBeInTheDocument();
  });

  it("asks for master data first when there is none", () => {
    render(
      <DealForm counterparties={[]} products={[product]} csrfToken="c" defaultCurrency="USD" />,
    );
    expect(screen.getByText("Master data required")).toBeInTheDocument();
    expect(screen.queryByRole("button", { name: "Create deal" })).not.toBeInTheDocument();
  });

  it("creates the deal with its lines and opens it", async () => {
    mocked.createDeal.mockResolvedValue({
      ok: true,
      data: { id: "33333333-3333-4333-8333-333333333333" },
    } as Awaited<ReturnType<typeof trade.createDeal>>);
    render(
      <DealForm
        counterparties={[buyer]}
        products={[product]}
        csrfToken="c"
        defaultCurrency="USD"
      />,
    );

    await userEvent.type(screen.getByLabelText("Title"), "50 MT aluminium, Q4");
    await userEvent.click(screen.getByRole("button", { name: "Create deal" }));

    await waitFor(() => expect(mocked.createDeal).toHaveBeenCalledTimes(1));
    expect(mocked.createDeal).toHaveBeenCalledWith(
      expect.objectContaining({
        title: "50 MT aluminium, Q4",
        counterparty_id: buyer.id,
        currency: "USD",
        items: [{ product_id: product.id, quantity: "1.000", unit_price: "2450.0000" }],
      }),
      "c",
    );
    await waitFor(() =>
      expect(push).toHaveBeenCalledWith("/deals/33333333-3333-4333-8333-333333333333"),
    );
  });

  it("refuses a missing title before calling the API", () => {
    render(
      <DealForm
        counterparties={[buyer]}
        products={[product]}
        csrfToken="c"
        defaultCurrency="USD"
      />,
    );
    const form = screen.getByRole("button", { name: "Create deal" }).closest("form");
    if (!form) throw new Error("no form");
    fireEvent.submit(form);
    expect(screen.getByRole("alert")).toHaveTextContent("A deal title is required.");
    expect(mocked.createDeal).not.toHaveBeenCalled();
  });
});

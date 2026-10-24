import { render, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { describe, expect, it, vi } from "vitest";

import { DocumentDownloads, documentUrl } from "./document-downloads";
import { LocaleProvider } from "@/lib/i18n/locale-provider";
import type { Locale } from "@/lib/i18n/messages";

vi.mock("next/navigation", () => ({
  useRouter: () => ({ push: vi.fn(), refresh: vi.fn(), replace: vi.fn(), back: vi.fn() }),
}));

const ORDER = "11111111-1111-4111-8111-111111111111";

function renderPanel(locale: Locale = "en") {
  return render(
    <LocaleProvider initialLocale={locale}>
      <DocumentDownloads
        documents={[
          { kind: "order_confirmation", entityId: ORDER },
          { kind: "commercial_invoice", entityId: ORDER },
          { kind: "shipment_register" },
        ]}
      />
    </LocaleProvider>,
  );
}

describe("documentUrl", () => {
  it("addresses the generator with the record, format and language", () => {
    expect(documentUrl({ kind: "proforma_invoice", entityId: ORDER }, "pdf", "tr")).toBe(
      `/api/v1/generated-documents/proforma_invoice?format=pdf&locale=tr&entity_id=${ORDER}`,
    );
    expect(documentUrl({ kind: "shipment_register" }, "csv", "en")).toBe(
      "/api/v1/generated-documents/shipment_register?format=csv&locale=en",
    );
  });
});

describe("document downloads", () => {
  it("offers all four formats for every document, as plain download links", () => {
    renderPanel();
    expect(screen.getAllByRole("link")).toHaveLength(12);
    const pdf = screen.getByRole("link", { name: "Download Order confirmation as PDF" });
    expect(pdf).toHaveAttribute("download");
    expect(pdf).toHaveAttribute("href", expect.stringContaining("format=pdf&locale=en"));
    expect(
      screen.getByRole("link", { name: "Download Commercial invoice (draft) as Word" }),
    ).toBeInTheDocument();
    expect(screen.getByText(/Nothing is sent to anyone/)).toBeInTheDocument();
    expect(screen.getByText(/never a tax invoice/)).toBeInTheDocument();
  });

  it("defaults to the interface language and lets the reader pick another per download", async () => {
    renderPanel("tr");
    const select = screen.getByLabelText("Belge dili");
    expect(select).toHaveValue("tr");
    expect(
      screen.getByRole("link", { name: "Sipariş onayı belgesini PDF olarak indir" }),
    ).toHaveAttribute("href", expect.stringContaining("locale=tr"));

    await userEvent.selectOptions(select, "en");
    expect(
      screen.getByRole("link", { name: "Sipariş onayı belgesini PDF olarak indir" }),
    ).toHaveAttribute("href", expect.stringContaining("locale=en"));
  });
});

import { render, screen, waitFor, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { beforeEach, describe, expect, it, vi } from "vitest";

import { ImportWizard } from "./import-wizard";
import { LocaleProvider } from "@/lib/i18n/locale-provider";
import type { Locale } from "@/lib/i18n/messages";
import * as client from "@/lib/imports/client";
import type { ImportReport, ImportResult } from "@/lib/imports/client";

vi.mock("@/lib/imports/client", async (importOriginal) => {
  const original = await importOriginal<typeof import("@/lib/imports/client")>();
  return {
    ...original,
    inspectImport: vi.fn(),
    previewImport: vi.fn(),
    commitImport: vi.fn(),
  };
});
vi.mock("next/navigation", () => ({
  useRouter: () => ({ push: vi.fn(), refresh: vi.fn(), replace: vi.fn(), back: vi.fn() }),
}));

const mocked = vi.mocked(client);

function ok<T>(data: T): ImportResult<T> {
  return { ok: true, data };
}

const inspect = {
  kind: "products" as const,
  source_sha256: "a".repeat(64),
  headers: [
    { heading: "sku", field: "sku" },
    { heading: "name", field: "name" },
    { heading: "unit", field: "unit" },
    { heading: "currency", field: "currency" },
    { heading: "unit_price", field: "unit_price" },
    { heading: "mystery", field: null },
  ],
  fields: ["currency", "name", "sku", "unit", "unit_price"],
  required: ["currency", "name", "sku", "unit", "unit_price"],
};

function report(overrides: Partial<ImportReport> = {}): ImportReport {
  return {
    kind: "products",
    filename: "katalog.csv",
    source_sha256: "b".repeat(64),
    total_rows: 3,
    new_rows: 2,
    existing_rows: 1,
    invalid_rows: 0,
    rows: [
      { row: 2, status: "NEW", values: { sku: "A-1", name: "One" }, errors: [] },
      { row: 3, status: "NEW", values: { sku: "A-2", name: "Two" }, errors: [] },
      {
        row: 4,
        status: "EXISTS",
        values: { sku: "A-3", name: "Three" },
        errors: ["Already exists in this company; it will not be changed."],
      },
    ],
    already_imported: false,
    can_commit: true,
    ...overrides,
  };
}

function renderWizard(locale: Locale = "en", canWrite = true) {
  return render(
    <LocaleProvider initialLocale={locale}>
      <ImportWizard csrfToken="csrf-token" canWrite={canWrite} />
    </LocaleProvider>,
  );
}

async function chooseFile() {
  const input = screen.getByLabelText(/File \(\.csv|Dosya \(\.csv/);
  await userEvent.upload(
    input,
    new File(["sku,name\nA-1,One\n"], "katalog.csv", { type: "text/csv" }),
  );
}

beforeEach(() => {
  mocked.inspectImport.mockResolvedValue(ok(inspect));
  mocked.previewImport.mockResolvedValue(ok(report()));
});

describe("import wizard", () => {
  it("asks for a file before reading anything", async () => {
    renderWizard();
    await userEvent.click(screen.getByRole("button", { name: "Read file" }));
    expect(screen.getByRole("alert")).toHaveTextContent("Choose a file first.");
    expect(mocked.inspectImport).not.toHaveBeenCalled();
  });

  it("maps the columns it recognises and blocks the preview until required ones are matched", async () => {
    mocked.inspectImport.mockResolvedValue(
      ok({ ...inspect, headers: [{ heading: "Kod", field: null }, ...inspect.headers.slice(1)] }),
    );
    renderWizard();
    await chooseFile();
    await userEvent.click(screen.getByRole("button", { name: "Read file" }));

    expect(await screen.findByText("Match the columns")).toBeInTheDocument();
    expect(mocked.inspectImport).toHaveBeenCalledWith("products", expect.any(File), "csrf-token");
    const preview = screen.getByRole("button", { name: "Preview import" });
    expect(preview).toBeDisabled(); // "sku" has no column yet

    await userEvent.selectOptions(screen.getByLabelText("Goes into: Kod"), "sku");
    expect(preview).toBeEnabled();
    await userEvent.click(preview);
    expect(mocked.previewImport).toHaveBeenCalledWith(
      "products",
      expect.any(File),
      expect.objectContaining({ Kod: "sku", name: "name" }),
      "csrf-token",
    );
  });

  async function reachReview() {
    renderWizard();
    await chooseFile();
    await userEvent.click(screen.getByRole("button", { name: "Read file" }));
    await userEvent.click(await screen.findByRole("button", { name: "Preview import" }));
    return screen.findByRole("status");
  }

  it("shows the review, and only imports after the existing-record choice and a confirmation", async () => {
    const summary = await reachReview();
    expect(summary).toHaveTextContent("3 rows · 2 new · 1 already exist · 0 invalid");
    const table = screen.getByRole("table");
    expect(within(table).getByText("Already exists")).toBeInTheDocument();
    expect(within(table).getAllByText("New")).toHaveLength(2);

    const commit = screen.getByRole("button", { name: "Import 2 records" });
    expect(commit).toBeDisabled();
    await userEvent.click(screen.getByLabelText(/I reviewed this preview/));
    expect(commit).toBeDisabled(); // an existing record is still unresolved
    expect(screen.getByText(/Some records already exist/)).toBeInTheDocument();
    await userEvent.click(screen.getByLabelText(/Skip records that already exist/));
    expect(commit).toBeEnabled();

    mocked.commitImport.mockResolvedValue(
      ok({
        batch_id: "11111111-1111-4111-8111-111111111111",
        kind: "products",
        source_sha256: "b".repeat(64),
        total_rows: 3,
        created_rows: 2,
        skipped_rows: 1,
        replayed: false,
      }),
    );
    await userEvent.click(commit);
    expect(mocked.commitImport).toHaveBeenCalledWith(
      "products",
      expect.any(File),
      expect.any(Object),
      "b".repeat(64),
      true,
      "csrf-token",
    );
    expect(await screen.findByText("Import finished")).toBeInTheDocument();
    expect(screen.getByText("2 created, 1 skipped.")).toBeInTheDocument();
    expect(screen.getByRole("link", { name: "View products" })).toHaveAttribute(
      "href",
      "/products",
    );
  });

  it("never offers to import a file with invalid rows or one that was already imported", async () => {
    mocked.previewImport.mockResolvedValue(
      ok(
        report({
          invalid_rows: 1,
          existing_rows: 0,
          new_rows: 1,
          total_rows: 2,
          rows: [
            { row: 2, status: "NEW", values: { sku: "A" }, errors: [] },
            { row: 3, status: "INVALID", values: { sku: "B" }, errors: ["unit: invalid value"] },
          ],
        }),
      ),
    );
    await reachReview();
    expect(
      screen.getByText("Fix the invalid rows in the file and upload it again."),
    ).toBeInTheDocument();
    await userEvent.click(screen.getByLabelText(/I reviewed this preview/));
    expect(screen.getByRole("button", { name: "Import 1 records" })).toBeDisabled();
  });

  it("warns that an identical file was imported before", async () => {
    mocked.previewImport.mockResolvedValue(
      ok(report({ already_imported: true, existing_rows: 0, new_rows: 3 })),
    );
    await reachReview();
    expect(
      screen.getByText("This exact file was already imported into this company."),
    ).toBeInTheDocument();
    await userEvent.click(screen.getByLabelText(/I reviewed this preview/));
    expect(screen.getByRole("button", { name: "Import 3 records" })).toBeDisabled();
  });

  it("shows the server's reason when the file is rejected", async () => {
    mocked.inspectImport.mockResolvedValue({
      ok: false,
      code: "BAD_REQUEST",
      message: "Spreadsheet formulas cannot be imported",
      requestId: "req-1",
    });
    renderWizard();
    await chooseFile();
    await userEvent.click(screen.getByRole("button", { name: "Read file" }));
    await waitFor(() =>
      expect(screen.getByRole("alert")).toHaveTextContent(
        "Spreadsheet formulas cannot be imported (BAD_REQUEST)",
      ),
    );
  });

  it("is read-only for a role without the trade permission", () => {
    renderWizard("en", false);
    expect(screen.getByText(/Importing needs the trade permission/)).toBeInTheDocument();
    expect(screen.queryByRole("button", { name: "Read file" })).not.toBeInTheDocument();
  });

  it("renders the whole flow in Turkish", async () => {
    renderWizard("tr");
    expect(screen.getByLabelText("Ne aktarıyorsunuz?")).toBeInTheDocument();
    await chooseFile();
    await userEvent.click(screen.getByRole("button", { name: "Dosyayı oku" }));
    await userEvent.click(await screen.findByRole("button", { name: "Önizlemeyi göster" }));
    expect(await screen.findByRole("status")).toHaveTextContent(
      "3 satır · 2 yeni · 1 zaten var · 0 hatalı",
    );
    expect(screen.getByRole("button", { name: "2 kaydı içe aktar" })).toBeInTheDocument();
  });
});

describe("template download", () => {
  it("starts with a byte-order mark so Excel reads Turkish characters", () => {
    expect(client.templateCsv("products").startsWith("﻿sku,name,unit,currency,unit_price")).toBe(
      true,
    );
    expect(client.templateCsv("counterparties")).toContain("Ayşe Yılmaz");
    expect(client.templateCsv("counterparties")).not.toContain("=");
  });
});

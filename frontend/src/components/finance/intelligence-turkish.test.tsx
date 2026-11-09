import { render, screen } from "@testing-library/react";
import { describe, expect, it, vi } from "vitest";

import { ExportCsvButton } from "./export-csv-button";
import { CompletenessBar, MonthlyCommitmentsChart, RankedCountChart } from "./intelligence-charts";
import { IntelligenceExceptionsTable } from "./intelligence-exceptions";
import { IntelligenceFilterBar } from "./intelligence-filters";
import { MetricCard } from "./intelligence-metrics";
import { IntelligenceOrdersTable } from "./intelligence-orders-table";
import { Pager } from "./pager";
import { categoryWord, completenessWord, metricTexts } from "@/lib/finance/intelligence-text";
import type {
  FinancialException,
  IntelligenceFilterOptions,
  IntelligenceMetric,
  OrderProfitability,
} from "@/lib/finance/intelligence";
import { LocaleProvider } from "@/lib/i18n/locale-provider";
import { translate } from "@/lib/i18n/messages";

vi.mock("next/navigation", () => ({
  useRouter: () => ({ push: vi.fn(), refresh: vi.fn(), replace: vi.fn(), back: vi.fn() }),
}));

const inTurkish = (ui: React.ReactElement) =>
  render(<LocaleProvider initialLocale="tr">{ui}</LocaleProvider>);
const tTr = (key: Parameters<typeof translate>[1], params?: Record<string, string | number>) =>
  translate("tr", key, params);
const tEn = (key: Parameters<typeof translate>[1], params?: Record<string, string | number>) =>
  translate("en", key, params);

const metric = (overrides: Partial<IntelligenceMetric> = {}): IntelligenceMetric =>
  ({
    key: "purchase_commitments",
    label: "Purchase commitments",
    kind: "MONEY",
    money: [{ currency: "TRY", amount: "1234.50" }],
    percentages: [],
    percentage: null,
    count: null,
    available: true,
    classification: "COMMITTED",
    completeness: "PARTIAL",
    meaning: "Committed supplier purchase orders grouped by their own currency.",
    ...overrides,
  }) as IntelligenceMetric;

const order = (overrides: Partial<OrderProfitability> = {}): OrderProfitability =>
  ({
    sales_order_id: "o1",
    order_number: "SO-2610-001",
    customer_name: "Buyer Ltd",
    status: "CONFIRMED",
    fulfilment_model: "PURCHASE_RESALE",
    currency: "USD",
    sales_value: "250.00",
    estimated_gross_profit: null,
    estimated_gross_margin_pct: null,
    committed_gross_profit: "-12.50",
    committed_gross_margin_pct: "-5.00",
    documented_total_cost: null,
    cost_variance: null,
    cost_variance_pct: null,
    completeness: "PARTIAL",
    cancelled: false,
    partial_fulfilment: true,
    purchase_currency_mismatch: false,
    cost_currency_mismatch: false,
    missing_components: ["PRICING_ESTIMATE", "SHIPMENT_COST_MISSING"],
    reconciliation_status: null,
    open_discrepancy_count: 2,
    blocking_discrepancy_count: 1,
    ...overrides,
  }) as OrderProfitability;

describe("intelligence words", () => {
  it("translates the eight backend metrics by key and keeps English as the backend wrote it", () => {
    const base = metric({ key: "accepted_sales_order_value", label: "Accepted sales order value" });
    expect(metricTexts(tTr, "tr", base).label).toBe("Kabul edilen satış siparişi değeri");
    expect(metricTexts(tEn, "en", base)).toEqual({ label: base.label, meaning: base.meaning });
  });

  it("falls back to the backend text for a metric it does not know", () => {
    const unknown = metric({ key: "brand_new_metric", label: "Brand new", meaning: "A new idea." });
    expect(metricTexts(tTr, "tr", unknown)).toEqual({ label: "Brand new", meaning: "A new idea." });
  });

  it("keeps the blocking count of the open-discrepancies meaning", () => {
    const open = metric({
      key: "open_discrepancies",
      label: "Open discrepancies",
      meaning: "Open Stage 5D findings in the filtered orders; 3 blocking.",
    });
    expect(metricTexts(tTr, "tr", open).meaning).toContain("3 tanesi engelleyen");
  });

  it("gives missing inputs, statuses and codes Turkish words and keeps English upper-case words", () => {
    expect(categoryWord(tTr, "tr", "SHIPMENT_COST_MISSING")).toBe("Sevkiyat gideri eksik");
    expect(categoryWord(tTr, "tr", "MATCHED_EVIDENCE")).toBe("KANITLA EŞLEŞTİ");
    expect(categoryWord(tTr, "tr", "AMOUNT_MISMATCH")).toBe("Tutar uyuşmazlığı");
    expect(categoryWord(tTr, "tr", "SOMETHING_NEW")).toBe("SOMETHING NEW");
    expect(categoryWord(tEn, "en", "SHIPMENT_COST_MISSING")).toBe("SHIPMENT COST MISSING");
    expect(completenessWord(tTr, "COMPLETE")).toBe("TAMAM");
    expect(completenessWord(tEn, "COMPLETE")).toBe("COMPLETE");
  });
});

describe("intelligence screens in Turkish", () => {
  it("shows a metric with its class, its per-currency figure and its completeness", () => {
    inTurkish(<MetricCard metric={metric()} />);
    expect(screen.getByText("Satın alma taahhütleri")).toBeInTheDocument();
    expect(screen.getByText("TAAHHÜT EDİLEN")).toBeInTheDocument();
    expect(screen.getByText("KISMİ")).toBeInTheDocument();
    expect(screen.getByText(/1\.234,50/)).toBeInTheDocument();
    expect(screen.getByText("TRY")).toBeInTheDocument();
  });

  it("says an unavailable metric is unavailable instead of showing zero", () => {
    inTurkish(<MetricCard metric={metric({ available: false, money: [] })} />);
    expect(screen.getByText("Mevcut değil")).toBeInTheDocument();
    expect(screen.getByText("MEVCUT DEĞİL")).toBeInTheDocument();
    expect(screen.queryByText(/0,00/)).toBeNull();
  });

  it("writes Turkish percentages with the sign first", () => {
    inTurkish(
      <MetricCard
        metric={metric({
          key: "estimated_gross_margin",
          kind: "PERCENT",
          money: [],
          percentages: [{ currency: "USD", value: "18.50" }],
          classification: "ESTIMATED",
          completeness: "COMPLETE",
        })}
      />,
    );
    expect(screen.getByText("%18,50")).toBeInTheDocument();
    expect(screen.getByText("TAHMİNİ")).toBeInTheDocument();
  });

  it("labels the orders table, its flags and its missing inputs", () => {
    inTurkish(<IntelligenceOrdersTable items={[order()]} />);
    expect(screen.getByRole("columnheader", { name: "Tahmini marj" })).toBeInTheDocument();
    expect(screen.getByText("Kısmi karşılama")).toBeInTheDocument();
    expect(
      screen.getByText("Eksik: Fiyatlandırma tahmini, Sevkiyat gideri eksik"),
    ).toBeInTheDocument();
    expect(screen.getAllByText("Mevcut değil").length).toBeGreaterThan(0);
    expect(screen.getByText("Çalıştırma yok")).toBeInTheDocument();
    expect(screen.getByText("2 açık · 1 engelleyen")).toBeInTheDocument();
  });

  it("keeps a loss visibly negative in both languages", () => {
    inTurkish(<IntelligenceOrdersTable items={[order()]} />);
    expect(document.querySelector("[data-negative]")).not.toBeNull();
  });

  it("shows an empty orders table in Turkish", () => {
    inTurkish(<IntelligenceOrdersTable items={[]} />);
    expect(screen.getByText("Uyan sipariş yok")).toBeInTheDocument();
  });

  it("shows the monthly chart's summary and table in Turkish", () => {
    inTurkish(
      <MonthlyCommitmentsChart
        rows={[
          {
            month: "2026-10",
            currency: "TRY",
            accepted_value: "5000.00",
            purchase_commitments: "3200.00",
            order_count: 2,
          },
        ]}
      />,
    );
    expect(screen.getByText("Aylık taahhütler")).toBeInTheDocument();
    expect(screen.getByText("Tablo görünümü")).toBeInTheDocument();
    const item = screen.getByRole("listitem", { name: /kabul edilen/ });
    expect(item.getAttribute("aria-label")).toContain("5.000,00");
    expect(item.getAttribute("aria-label")).toContain("2 sipariş");
  });

  it("names ranked categories and completeness segments in Turkish", () => {
    inTurkish(
      <>
        <RankedCountChart
          title="Eksik girdiler"
          items={[{ key: "PRICING_ESTIMATE", count: 3 }]}
          emptyTitle="Eksik bir şey yok"
          columnLabel="Sipariş"
        />
        <CompletenessBar
          title="Sipariş bütünlüğü"
          counts={[
            { status: "COMPLETE", count: 4 },
            { status: "MISSING", count: 1 },
          ]}
        />
      </>,
    );
    expect(screen.getAllByText("Fiyatlandırma tahmini").length).toBeGreaterThan(0);
    expect(screen.getAllByText("TAMAM").length).toBeGreaterThan(0);
    expect(screen.getAllByText("EKSİK").length).toBeGreaterThan(0);
  });

  it("labels the filter bar and translates the option words", () => {
    const options = {
      currencies: ["USD"],
      customers: [],
      suppliers: [],
      order_statuses: ["CONFIRMED"],
      fulfilment_models: ["PURCHASE_RESALE"],
      reconciliation_statuses: ["VERIFIED"],
      completeness_statuses: ["COMPLETE"],
    } as IntelligenceFilterOptions;
    inTurkish(<IntelligenceFilterBar action="/x" filters={{}} options={options} />);
    expect(screen.getByLabelText("Sipariş durumu")).toBeInTheDocument();
    expect(screen.getByRole("option", { name: "Tüm para birimleri" })).toBeInTheDocument();
    expect(screen.getByRole("option", { name: "Teyit edildi" })).toHaveAttribute(
      "value",
      "CONFIRMED",
    );
    expect(screen.getByRole("option", { name: "DOĞRULANDI" })).toHaveAttribute("value", "VERIFIED");
    expect(screen.getByRole("button", { name: "Uygula" })).toBeInTheDocument();
  });

  it("shows the pager and the export button in Turkish", () => {
    inTurkish(
      <>
        <Pager basePath="/x" total={30} limit={25} offset={0} params={{}} noun="order" />
        <ExportCsvButton filters={{}} orderCount={3} />
      </>,
    );
    expect(screen.getByText("30 sipariş · başlangıç 0")).toBeInTheDocument();
    expect(screen.getByRole("link", { name: "Sonraki" })).toBeInTheDocument();
    expect(screen.getByRole("button", { name: /CSV olarak dışa aktar/ })).toBeInTheDocument();
  });

  it("shows exceptions with the Turkish code and a read-only resolution", () => {
    const item = {
      id: "e1",
      sales_order_id: "o1",
      order_number: "SO-1",
      customer_name: "Buyer",
      currency: "USD",
      created_at: "2026-10-22T09:00:00Z",
      code: "AMOUNT_MISMATCH",
      severity: "WARNING",
      status: "OPEN",
      title: "Amount differs",
      detail: "10 vs 12",
      run_id: "r1",
      finance_source_reference: null,
      resolution_notes: null,
      reviewer_name: null,
      version: 1,
    } as unknown as FinancialException;
    inTurkish(<IntelligenceExceptionsTable items={[item]} csrfToken="c" canReview={false} />);
    expect(screen.getByText("Tutar uyuşmazlığı")).toBeInTheDocument();
    expect(screen.getByText("UYARI")).toBeInTheDocument();
    expect(screen.getByText("AÇIK")).toBeInTheDocument();
    expect(screen.getByText(/Finans referansı yok/)).toBeInTheDocument();
    expect(screen.queryByRole("button", { name: "Çöz" })).toBeNull();
  });
});

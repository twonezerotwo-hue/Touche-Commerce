import { render, screen } from "@testing-library/react";
import { describe, expect, it, vi } from "vitest";

import { DiscrepancyQueue } from "./discrepancy-queue";
import { FinanceFilters } from "./filters";
import { FinanceOverview } from "./overview";
import { ClassificationBadge, ReconciliationStatusBadge } from "./reconciliation-status-badge";
import { FinanceStatusBadge } from "./status-badge";
import { FinanceAccountsTable, FinanceAgingTable } from "./tables";
import { formatReconciliationMoney, formatReconciliationPercent } from "@/lib/finance/format";
import type { ReconciliationDiscrepancy } from "@/lib/finance/reconciliation";
import type {
  FinanceAccounts,
  FinanceAging,
  FinanceStatus,
  FinanceSummary,
} from "@/lib/finance/types";
import { LocaleProvider } from "@/lib/i18n/locale-provider";
import { translate } from "@/lib/i18n/messages";
import {
  classificationText,
  discrepancyCodeText,
  discrepancyStatusText,
  financeStateText,
  reconciliationStatusText,
  severityText,
} from "@/lib/i18n/value-labels";

vi.mock("next/navigation", () => ({
  useRouter: () => ({ refresh: vi.fn(), push: vi.fn(), replace: vi.fn(), back: vi.fn() }),
}));

const inTurkish = (ui: React.ReactElement) =>
  render(<LocaleProvider initialLocale="tr">{ui}</LocaleProvider>);
const tr = (key: Parameters<typeof translate>[1]) => translate("tr", key);

const status = {
  state: "connected",
  detail: "Finance reports a consistent ledger.",
  checked_at: "2026-10-22T12:00:00+00:00",
  latency_ms: 4.2,
  mapping: { finance_company_id: "gursar", finance_company_name: "Gursar Mimarlik" },
  finance_status: "ok",
  available_currencies: ["TRY"],
  data_through: "2026-10-20",
} as unknown as FinanceStatus;

const summary = {
  as_of: "2026-10-20",
  currency: "TRY",
  ledger: { document_count: 24, line_count: 48 },
  balances: {
    cash: { amount: "1234.50", amount_kurus: 123450 },
    receivables: { amount: "200.00", amount_kurus: 20000 },
    payables: { amount: "300.00", amount_kurus: 30000 },
    revenue: { amount: "400.00", amount_kurus: 40000 },
    cost: { amount: "50.00", amount_kurus: 5000 },
    gross_profit: { amount: "350.00", amount_kurus: 35000 },
  },
} as unknown as FinanceSummary;

describe("finance words keep their meaning in Turkish", () => {
  it("connection states, reconciliation statuses and the four evidence classes have words", () => {
    expect(financeStateText(tr, "connected")).toBe("BAĞLI");
    expect(financeStateText(tr, "auth_error")).toBe("YETKİ HATASI");
    expect(reconciliationStatusText(tr, "POTENTIAL_MATCH")).toBe("OLASI EŞLEŞME");
    expect(reconciliationStatusText(tr, "VERIFIED")).toBe("DOĞRULANDI");
    expect(classificationText(tr, "ESTIMATED")).toBe("TAHMİNİ");
    expect(classificationText(tr, "COMMITTED")).toBe("TAAHHÜT EDİLEN");
    expect(classificationText(tr, "DOCUMENTED")).toBe("BELGELENEN");
    expect(classificationText(tr, "UNAVAILABLE")).toBe("MEVCUT DEĞİL");
    expect(discrepancyStatusText(tr, "OPEN")).toBe("AÇIK");
    expect(severityText(tr, "BLOCKING")).toBe("ENGELLEYEN");
    expect(discrepancyCodeText(tr, "AMOUNT_MISMATCH")).toBe("Tutar uyuşmazlığı");
  });

  it("never shows an unknown or missing classification as a stronger one", () => {
    expect(classificationText(tr, undefined)).toBe("MEVCUT DEĞİL");
    expect(classificationText(tr, "SOMETHING_NEW")).toBe("MEVCUT DEĞİL");
  });

  it("keeps the English wording that existed before the language switch", () => {
    const en = (key: Parameters<typeof translate>[1]) => translate("en", key);
    expect(financeStateText(en, "not_configured")).toBe("NOT_CONFIGURED");
    expect(classificationText(en, "FINANCE_OBSERVED")).toBe("FINANCE OBSERVED");
    expect(discrepancyCodeText(en, "MISSING_FINANCE_REFERENCE")).toBe("MISSING_FINANCE_REFERENCE");
  });

  it("formats backend percentages and money without changing the figures", () => {
    expect(formatReconciliationPercent("62.50")).toBe("62.50%");
    expect(formatReconciliationPercent("62.50", "n/a", "tr")).toBe("%62,50");
    expect(formatReconciliationPercent(null, "Mevcut değil", "tr")).toBe("Mevcut değil");
    expect(formatReconciliationMoney(null, "TRY", "Mevcut değil", "tr")).toBe("Mevcut değil");
    expect(formatReconciliationMoney("1234.50", "TRY", "x", "tr").replace(/\s/g, " ")).toContain(
      "1.234,50",
    );
    expect(formatReconciliationMoney("1234.50", "TRY", "x", "en")).toContain("1,234.50");
  });
});

describe("finance screens in Turkish", () => {
  it("shows the badges as words", () => {
    inTurkish(
      <>
        <FinanceStatusBadge state="degraded" />
        <ReconciliationStatusBadge status="MATCHED_EVIDENCE" />
        <ClassificationBadge value="COMMITTED" />
        <ClassificationBadge value={undefined} />
      </>,
    );
    expect(screen.getByText("KISITLI")).toBeInTheDocument();
    expect(screen.getByText("KANITLA EŞLEŞTİ")).toBeInTheDocument();
    expect(screen.getByText("TAAHHÜT EDİLEN")).toBeInTheDocument();
    expect(screen.getByText("MEVCUT DEĞİL")).toBeInTheDocument();
  });

  it("reads the ledger overview in Turkish with Turkish number formatting", () => {
    inTurkish(<FinanceOverview status={status} summary={summary} />);
    expect(screen.getByText("Finans bağlantısı")).toBeInTheDocument();
    expect(screen.getByText("Eşlenen şirket")).toBeInTheDocument();
    expect(screen.getByText("Nakit")).toBeInTheDocument();
    expect(screen.getByText("Brüt kâr")).toBeInTheDocument();
    expect(screen.getByText(/1\.234,50/)).toBeInTheDocument();
    expect(screen.getByText("Mevcut değil")).toBeInTheDocument();
  });

  it("explains that no summary is loaded instead of showing zero", () => {
    inTurkish(<FinanceOverview status={status} summary={null} />);
    expect(screen.getByText(/Finans özeti yüklenmedi/)).toBeInTheDocument();
  });

  it("labels the account and aging tables", () => {
    const accounts = {
      currency: "TRY",
      accounts: [
        {
          account_code: "120",
          name: "Alicilar",
          type: "VARLIK",
          debit: { amount: "100.00" },
          credit: { amount: "40.00" },
          balance: { amount: "60.00" },
        },
      ],
    } as unknown as FinanceAccounts;
    const aging = {
      type: "receivable",
      currency: "TRY",
      items: [],
    } as unknown as FinanceAging;
    inTurkish(
      <>
        <FinanceAccountsTable data={accounts} />
        <FinanceAgingTable data={aging} />
      </>,
    );
    expect(screen.getByRole("columnheader", { name: "Hesap" })).toBeInTheDocument();
    expect(screen.getByRole("columnheader", { name: "Bakiye" })).toBeInTheDocument();
    expect(screen.getByText("Alacak yaşlandırma kalemi yok")).toBeInTheDocument();
  });

  it("labels the filters and keeps their submitted values", () => {
    inTurkish(
      <FinanceFilters
        currencies={["TRY", "USD"]}
        view="receivables"
        currency="TRY"
        fromDate=""
        toDate=""
        asOf=""
      />,
    );
    expect(screen.getByLabelText("Görünüm")).toBeInTheDocument();
    expect(screen.getByLabelText("Tarih itibarıyla")).toBeInTheDocument();
    expect(screen.getByRole("option", { name: "Alacaklar" })).toHaveValue("receivables");
    expect(screen.getByRole("button", { name: "Uygula" })).toBeInTheDocument();
  });

  it("shows the discrepancy queue in Turkish and read-only without finance.reconcile", () => {
    const item = {
      id: "d1",
      run_id: "r1",
      code: "AMOUNT_MISMATCH",
      severity: "BLOCKING",
      status: "OPEN",
      title: "Amount differs",
      detail: "Expected 10, observed 12.",
      created_at: "2026-10-22T09:00:00Z",
      resolution_notes: null,
      version: 1,
    } as unknown as ReconciliationDiscrepancy;
    inTurkish(<DiscrepancyQueue items={[item]} csrfToken="c" canReview={false} />);
    expect(screen.getByText("Tutar uyuşmazlığı")).toBeInTheDocument();
    expect(screen.getByText("ENGELLEYEN")).toBeInTheDocument();
    expect(screen.getByText("AÇIK")).toBeInTheDocument();
    expect(screen.getByRole("columnheader", { name: "Bulgu" })).toBeInTheDocument();
    expect(screen.queryByRole("button", { name: "Çöz" })).toBeNull();
  });

  it("offers resolving to someone with finance.reconcile", () => {
    const item = {
      id: "d1",
      run_id: "r1",
      code: "SOURCE_STALE",
      severity: "WARNING",
      status: "OPEN",
      title: "Stale",
      detail: "Old data",
      created_at: "2026-10-22T09:00:00Z",
      resolution_notes: null,
      version: 1,
    } as unknown as ReconciliationDiscrepancy;
    inTurkish(<DiscrepancyQueue items={[item]} csrfToken="c" canReview />);
    expect(screen.getByRole("button", { name: "Çöz" })).toBeDisabled();
  });

  it("shows an empty queue as such", () => {
    inTurkish(<DiscrepancyQueue items={[]} csrfToken="c" canReview />);
    expect(screen.getByText("Uyuşmazlık yok")).toBeInTheDocument();
  });
});

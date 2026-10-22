import { render, screen } from "@testing-library/react";
import { describe, expect, it } from "vitest";

import { FinanceFilters } from "./filters";
import { FinanceOverview } from "./overview";
import { FinanceStatusBadge } from "./status-badge";
import { FinanceAccountsTable, FinanceAgingTable } from "./tables";
import type {
  FinanceAccounts,
  FinanceAging,
  FinanceStatus,
  FinanceSummary,
} from "@/lib/finance/types";

const connectedStatus = {
  state: "connected",
  detail: "Finance reports a consistent ledger.",
  checked_at: "2026-10-22T12:00:00+00:00",
  latency_ms: 4.2,
  mapping: {
    finance_company_id: "gursar_mimarlik",
    finance_company_name: "Gursar Mimarlik",
    status: "verified",
    configured_at: "2026-10-22T11:00:00+00:00",
    last_verified_at: "2026-10-22T11:00:00+00:00",
  },
  finance_status: "ok",
  available_currencies: ["EUR", "TL", "USD"],
  data_through: "2026-10-20",
  finance_request_id: "fin-1",
  scope: "finance_read",
  read_only: true,
  accounting_writes_enabled: false,
} as FinanceStatus;

const summary = {
  company_id: "gursar_mimarlik",
  name: "Gursar Mimarlik",
  holding_id: "touche_holding",
  active: true,
  as_of: "2026-10-20",
  data_through: "2026-10-20",
  currency: "TL",
  currencies: ["EUR", "TL", "USD"],
  source: "finance_ledger",
  ledger: {
    document_count: 24,
    line_count: 48,
    first_date: "2026-09-01",
    last_date: "2026-10-20",
  },
  balances: {
    cash: { amount: "100.00", amount_kurus: 10000 },
    receivables: { amount: "200.00", amount_kurus: 20000 },
    payables: { amount: "300.00", amount_kurus: 30000 },
    revenue: { amount: "400.00", amount_kurus: 40000 },
    cost: { amount: "50.00", amount_kurus: 5000 },
    gross_profit: { amount: "350.00", amount_kurus: 35000 },
  },
  fetched_at: "2026-10-22T12:00:00+00:00",
  finance_request_id: "fin-1",
  read_only: true,
  accounting_writes_enabled: false,
} as FinanceSummary;

const accounts = {
  company_id: "gursar_mimarlik",
  from_date: "2026-01-01",
  as_of: "2026-02-28",
  currency: "TL",
  accounts: [
    {
      account_code: "120",
      name: "Alicilar",
      type: "VARLIK",
      debit: { amount: "100.00", amount_kurus: 10000 },
      credit: { amount: "40.00", amount_kurus: 4000 },
      balance: { amount: "60.00", amount_kurus: 6000 },
    },
  ],
  page: { limit: 25, offset: 0, total: 1, next_offset: null },
  source: "finance_ledger",
  fetched_at: "2026-10-22T12:00:00+00:00",
  read_only: true,
  accounting_writes_enabled: false,
} as FinanceAccounts;

const aging = {
  company_id: "gursar_mimarlik",
  type: "receivable",
  account: "120",
  as_of: "2026-10-20",
  currency: "TL",
  summary: {
    total: { amount: "600.00", amount_kurus: 60000 },
    overdue: { amount: "600.00", amount_kurus: 60000 },
    overdue_ratio: 100,
  },
  items: [
    {
      counterparty: "Customer A",
      counterparty_key_type: "ledger.cari",
      buckets: {
        not_due: { amount: "0.00", amount_kurus: 0 },
        days_1_30: { amount: "0.00", amount_kurus: 0 },
        days_31_60: { amount: "600.00", amount_kurus: 60000 },
        days_61_90: { amount: "0.00", amount_kurus: 0 },
        days_over_90: { amount: "0.00", amount_kurus: 0 },
      },
      total: { amount: "600.00", amount_kurus: 60000 },
      advance: { amount: "0.00", amount_kurus: 0 },
      overdue: true,
      overdue_amount: { amount: "600.00", amount_kurus: 60000 },
      open_items: [
        {
          source_id: "JRN-TEST-001",
          source: "ledger.fisler",
          due_date: "2026-01-31",
          remaining: { amount: "600.00", amount_kurus: 60000 },
        },
      ],
    },
  ],
  page: { limit: 25, offset: 0, total: 1, next_offset: null },
  source: "finance_ledger",
  fetched_at: "2026-10-22T12:00:00+00:00",
  read_only: true,
  accounting_writes_enabled: false,
} as FinanceAging;

describe("FinanceOverview", () => {
  it("shows the mapped company, currencies, watermark and source balances", () => {
    render(<FinanceOverview status={connectedStatus} summary={summary} />);
    expect(screen.getByText("CONNECTED")).toBeInTheDocument();
    expect(screen.getByText("Gursar Mimarlik")).toBeInTheDocument();
    expect(screen.getByText("EUR · TL · USD")).toBeInTheDocument();
    expect(screen.getByText("100.00 TL")).toBeInTheDocument();
    expect(screen.getByText("Not available")).toBeInTheDocument();
  });

  it("never invents a balance when no summary was loaded", () => {
    render(<FinanceOverview status={connectedStatus} summary={null} />);
    expect(screen.getByText(/No Finance summary is loaded/)).toBeInTheDocument();
    expect(screen.queryByText("100.00 TL")).toBeNull();
  });

  it("shows NOT_CONFIGURED and updates the mapped company on tenant switch", () => {
    const notConfigured = {
      ...connectedStatus,
      state: "not_configured",
      mapping: null,
      available_currencies: [],
      detail: "No Finance company mapping is configured.",
    } as FinanceStatus;
    const { rerender } = render(<FinanceOverview status={notConfigured} summary={null} />);
    expect(screen.getByText("NOT_CONFIGURED")).toBeInTheDocument();
    expect(screen.getByText("Not configured")).toBeInTheDocument();

    const otherCompany = {
      ...connectedStatus,
      mapping: {
        ...connectedStatus.mapping,
        finance_company_id: "touche_enerji",
        finance_company_name: "Touche Enerji",
      },
    } as FinanceStatus;
    rerender(<FinanceOverview status={otherCompany} summary={null} />);
    expect(screen.getByText("Touche Enerji")).toBeInTheDocument();
    expect(screen.queryByText("Gursar Mimarlik")).toBeNull();
  });

  it("renders auth and unavailable states explicitly", () => {
    const { rerender } = render(<FinanceStatusBadge state="auth_error" />);
    expect(screen.getByText("AUTH_ERROR")).toBeInTheDocument();
    rerender(<FinanceStatusBadge state="unavailable" />);
    expect(screen.getByText("UNAVAILABLE")).toBeInTheDocument();
  });
});

describe("Finance tables", () => {
  it("renders accounts and an explicit empty state", () => {
    const { rerender } = render(<FinanceAccountsTable data={accounts} />);
    expect(screen.getByText("120")).toBeInTheDocument();
    expect(screen.getByText("Alicilar")).toBeInTheDocument();
    expect(screen.getByText("60.00 TL")).toBeInTheDocument();

    rerender(<FinanceAccountsTable data={{ ...accounts, accounts: [] }} />);
    expect(screen.getByText("No accounts returned")).toBeInTheDocument();
  });

  it("renders aging buckets and open Finance source ids", () => {
    render(<FinanceAgingTable data={aging} />);
    expect(screen.getByText("Customer A")).toBeInTheDocument();
    expect(screen.getByText(/JRN-TEST-001/)).toBeInTheDocument();
    expect(screen.getByText(/ledger.cari/)).toBeInTheDocument();
  });

  it("renders an empty aging message for the requested side", () => {
    render(<FinanceAgingTable data={{ ...aging, type: "payable", items: [] }} />);
    expect(screen.getByText("No payable aging items")).toBeInTheDocument();
  });
});

describe("FinanceFilters", () => {
  it("keeps the explicit currency and view selection", () => {
    render(
      <FinanceFilters
        currencies={["EUR", "TL", "USD"]}
        view="accounts"
        currency="TL"
        fromDate="2026-01-01"
        toDate="2026-02-28"
        asOf=""
      />,
    );
    expect(screen.getByLabelText("Currency")).toHaveValue("TL");
    expect(screen.getByLabelText("View")).toHaveValue("accounts");
    expect(screen.getByText("EUR")).toBeInTheDocument();
    expect(screen.getByText("USD")).toBeInTheDocument();
  });
});

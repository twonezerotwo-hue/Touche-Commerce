import { render, screen } from "@testing-library/react";
import { describe, expect, it, vi } from "vitest";

import { DiscrepancyQueue } from "./discrepancy-queue";
import { ReviewPanel } from "./reconciliation-actions";
import { ReconciliationDetail } from "./reconciliation-detail";
import { ReconciliationOverview } from "./reconciliation-overview";
import { DiscrepancySeverityBadge, ReconciliationStatusBadge } from "./reconciliation-status-badge";
import type {
  ReconciliationDiscrepancy,
  ReconciliationList,
  ReconciliationRun,
} from "@/lib/finance/reconciliation";
import type { FinanceStatus } from "@/lib/finance/types";

vi.mock("next/navigation", () => ({
  useRouter: () => ({ push: vi.fn(), refresh: vi.fn(), replace: vi.fn(), back: vi.fn() }),
}));

const financeStatus = {
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
  data_through: "2026-10-20",
  available_currencies: ["USD"],
  scope: "finance_read",
  read_only: true,
  accounting_writes_enabled: false,
} as FinanceStatus;

const discrepancy: ReconciliationDiscrepancy = {
  id: "discrepancy-1",
  run_id: "run-1",
  code: "MISSING_FINANCE_REFERENCE",
  severity: "WARNING",
  status: "OPEN",
  title: "No Finance source is linked to this order yet",
  detail: "This is an unavailable capability and is not proof that a real invoice is missing.",
  expected: { order_level_finance_reference: "linked evidence" },
  observed: { order_level_finance_reference: "not linked" },
  source_entity_type: "SALES_ORDER",
  source_entity_id: "order-1",
  finance_source_reference_id: null,
  assigned_to: null,
  resolution_notes: null,
  resolved_by: null,
  resolved_at: null,
  created_at: "2026-10-22T12:00:00+00:00",
  updated_at: "2026-10-22T12:00:00+00:00",
  version: 1,
};

function run(overrides: Partial<ReconciliationRun> = {}): ReconciliationRun {
  return {
    id: "run-1",
    company_id: "company-1",
    sales_order_id: "order-1",
    order_number: "SO-2610-ABC123",
    customer_name: "Buyer Ltd",
    finance_company_id: "gursar_mimarlik",
    currency: "USD",
    finance_currency: "USD",
    as_of: "2026-10-22",
    data_through: "2026-10-22",
    status: "UNMATCHED",
    calculation_version: "stage5d-1.0.0",
    version: 1,
    created_at: "2026-10-22T12:00:00+00:00",
    updated_at: "2026-10-22T12:00:00+00:00",
    evidence_count: 0,
    open_discrepancy_count: 1,
    blocking_discrepancy_count: 0,
    metrics: {
      accepted_sales_order_value: "250.00",
      purchase_commitments_total: "150.00",
      purchase_commitment_count: 1,
      estimated_landed_cost: "170.00",
      recorded_operational_costs: "20.00",
      estimate_vs_recorded_variance: "150.00",
      commitment_based_margin: "80.00",
      commitment_based_margin_pct: "32.00",
      document_supported_margin: null,
      completeness_score: "100.00",
      completeness_checks: [
        {
          key: "accepted_sales_order",
          label: "Accepted sales order",
          satisfied: true,
          detail: "Stored.",
        },
      ],
    },
    classifications: {
      accepted_sales_order_value: "DOCUMENTED",
      purchase_commitments_total: "COMMITTED",
      estimated_landed_cost: "ESTIMATED",
      recorded_operational_costs: "DOCUMENTED",
      estimate_vs_recorded_variance: "ESTIMATED",
      commitment_based_margin: "COMMITTED",
      document_supported_margin: "UNAVAILABLE",
      actual_profit: "UNAVAILABLE",
    },
    limitations: [
      "Finance exposes no structured invoice or payment objects.",
      "Commitment-based margin is not accounting profit.",
    ],
    finance_snapshot: {
      currency: "USD",
      summary: {
        balances: {
          receivables: { amount: "250.00" },
          payables: { amount: "100.00" },
        },
      },
    },
    source_references: [
      {
        id: "ref-1",
        source_type: "AGING_RECEIVABLE",
        source_reference: "FIN-AR-1",
        is_transaction_level: true,
        currency: "USD",
        observed_amount: "250.00",
        as_of: "2026-10-22",
        data_through: "2026-10-22",
        content_hash: "a".repeat(64),
        payload: { counterparty_label: "Buyer Ltd" },
      },
      {
        id: "ref-2",
        source_type: "SUMMARY",
        source_reference: "summary:USD:2026-10-22",
        is_transaction_level: false,
        currency: "USD",
        observed_amount: null,
        as_of: "2026-10-22",
        data_through: "2026-10-22",
        content_hash: "b".repeat(64),
        payload: {},
      },
    ],
    evidence_links: [],
    discrepancies: [discrepancy],
    reviews: [],
    created_by: "user-1",
    read_only: true,
    accounting_writes_enabled: false,
    ...overrides,
  };
}

const list: ReconciliationList = {
  items: [
    {
      id: "run-1",
      sales_order_id: "order-1",
      order_number: "SO-2610-ABC123",
      customer_name: "Buyer Ltd",
      currency: "USD",
      as_of: "2026-10-22",
      data_through: "2026-10-22",
      status: "UNMATCHED",
      version: 1,
      created_at: "2026-10-22T12:00:00+00:00",
      evidence_count: 0,
      open_discrepancy_count: 1,
      blocking_discrepancy_count: 0,
    },
  ],
  total: 1,
  limit: 25,
  offset: 0,
  currency: "USD",
  status_counts: {
    INCOMPLETE: 0,
    UNMATCHED: 1,
    POTENTIAL_MATCH: 0,
    MATCHED_EVIDENCE: 0,
    VERIFIED: 0,
    DISPUTED: 0,
  },
  open_discrepancy_count: 1,
  blocking_discrepancy_count: 0,
  read_only: true,
  accounting_writes_enabled: false,
};

describe("Stage 5D reconciliation UI", () => {
  it("labels the explicit reconciliation states", () => {
    const { rerender } = render(<ReconciliationStatusBadge status="UNMATCHED" />);
    expect(screen.getByText("UNMATCHED")).toBeInTheDocument();
    rerender(<ReconciliationStatusBadge status="MATCHED_EVIDENCE" />);
    expect(screen.getByText("MATCHED EVIDENCE")).toBeInTheDocument();
    rerender(<ReconciliationStatusBadge status="VERIFIED" />);
    expect(screen.getByText("VERIFIED")).toBeInTheDocument();
    rerender(<DiscrepancySeverityBadge severity="BLOCKING" />);
    expect(screen.getByText("BLOCKING")).toBeInTheDocument();
  });

  it("shows the financial overview without inventing unavailable metrics", () => {
    render(
      <ReconciliationOverview
        status={financeStatus}
        list={list}
        latest={null}
        currency="USD"
        orders={[]}
        csrfToken="csrf"
        canCreate={false}
      />,
    );
    expect(screen.getByText("Run a reconciliation")).toBeInTheDocument();
    expect(screen.getAllByText("Not available").length).toBeGreaterThan(0);
    expect(screen.getByText("SO-2610-ABC123")).toBeInTheDocument();
    expect(screen.getByText(/No cross-currency total exists/)).toBeInTheDocument();
    expect(
      screen.getByText(/Document-supported margin and actual profit remain/),
    ).toBeInTheDocument();
  });

  it("renders the run snapshot and never labels commitment margin as profit", () => {
    render(<ReconciliationDetail run={run()} csrfToken="csrf" canLink={false} canReview={false} />);
    expect(screen.getByText("FIN-AR-1")).toBeInTheDocument();
    expect(screen.getByText("summary:USD:2026-10-22")).toBeInTheDocument();
    expect(screen.getAllByText("Not available").length).toBeGreaterThan(0);
    expect(screen.getByText("No Finance source is linked to this order yet")).toBeInTheDocument();
    expect(screen.getByText(/not accounting profit/)).toBeInTheDocument();
    expect(screen.getByText(/Financial review needs/)).toBeInTheDocument();
  });

  it("keeps the discrepancy queue read-only without finance.reconcile", () => {
    render(<DiscrepancyQueue items={[discrepancy]} csrfToken="csrf" canReview={false} />);
    expect(screen.getByText("MISSING_FINANCE_REFERENCE")).toBeInTheDocument();
    expect(screen.queryByRole("button", { name: "Resolve" })).toBeNull();
  });

  it("offers confirmation only for matched evidence", () => {
    const { rerender } = render(<ReviewPanel run={run()} csrfToken="csrf" canReview />);
    expect(screen.getByRole("option", { name: "Confirm and verify" })).toBeDisabled();
    rerender(<ReviewPanel run={run({ status: "MATCHED_EVIDENCE" })} csrfToken="csrf" canReview />);
    expect(screen.getByRole("option", { name: "Confirm and verify" })).not.toBeDisabled();
  });

  it("renders explicit empty and unavailable states", () => {
    render(
      <ReconciliationDetail
        run={run({ evidence_links: [], discrepancies: [], reviews: [] })}
        csrfToken="csrf"
        canLink={false}
        canReview={false}
      />,
    );
    expect(screen.getByText("No evidence linked")).toBeInTheDocument();
    expect(screen.getByText("No discrepancies were generated.")).toBeInTheDocument();
    expect(screen.getByText("No financial review has been recorded.")).toBeInTheDocument();
  });
});

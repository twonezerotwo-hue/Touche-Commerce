import { render, screen, waitFor, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { afterEach, describe, expect, it, vi } from "vitest";

import { ExportCsvButton } from "./export-csv-button";
import {
  ChartGrid,
  CompletenessBar,
  CostComparisonChart,
  MarginDistributionChart,
  MonthlyCommitmentsChart,
  RankedCountChart,
} from "./intelligence-charts";
import { IntelligenceDetail } from "./intelligence-detail";
import { IntelligenceExceptionsTable } from "./intelligence-exceptions";
import { IntelligenceFilterBar } from "./intelligence-filters";
import { MetricCard } from "./intelligence-metrics";
import { IntelligenceOrdersTable } from "./intelligence-orders-table";
import { Pager } from "./pager";
import type {
  FinancialException,
  IntelligenceMetric,
  OrderIntelligenceDetail,
  OrderProfitability,
} from "@/lib/finance/intelligence";

vi.mock("next/navigation", () => ({
  useRouter: () => ({ push: vi.fn(), refresh: vi.fn(), replace: vi.fn(), back: vi.fn() }),
}));

afterEach(() => {
  vi.unstubAllGlobals();
});

const ORDER_ID = "7f1c1b3e-0000-4000-8000-000000000001";
const RUN_ID = "7f1c1b3e-0000-4000-8000-0000000000aa";

function metric(overrides: Partial<IntelligenceMetric> = {}): IntelligenceMetric {
  return {
    key: "accepted_value",
    label: "Accepted order value",
    kind: "MONEY",
    money: [
      { currency: "USD", amount: "250.00" },
      { currency: "EUR", amount: "100.00" },
    ],
    percentages: [],
    percentage: null,
    count: null,
    available: true,
    classification: "DOCUMENTED",
    completeness: "COMPLETE",
    meaning: "Documented customer acceptance, not revenue recognition.",
    as_of: "2026-10-23",
    data_through: null,
    ...overrides,
  };
}

function order(overrides: Partial<OrderProfitability> = {}): OrderProfitability {
  return {
    sales_order_id: ORDER_ID,
    order_number: "SO-2610-ABC123",
    customer_name: "Buyer Ltd",
    status: "CONFIRMED",
    fulfilment_model: "PURCHASE_RESALE",
    currency: "USD",
    confirmed_at: "2026-10-20T09:00:00+00:00",
    expected_delivery_date: null,
    sales_value: "250.00",
    estimated_gross_profit: "80.00",
    estimated_gross_margin_pct: "32.00",
    committed_gross_profit: null,
    committed_gross_margin_pct: null,
    documented_operational_cost: "20.00",
    documented_total_cost: null,
    cost_variance: null,
    cost_variance_pct: null,
    estimate_status: "COMPLETE",
    committed_status: "PARTIAL",
    completeness: "PARTIAL",
    missing_components: ["SHIPMENT_COSTS"],
    classifications: {
      sales_value: "DOCUMENTED",
      estimated_gross_profit: "ESTIMATED",
      committed_gross_profit: "UNAVAILABLE",
      documented_operational_cost: "DOCUMENTED",
      cost_variance: "UNAVAILABLE",
      actual_profit: "UNAVAILABLE",
    },
    purchase_currency_mismatch: false,
    cost_currency_mismatch: false,
    partial_fulfilment: true,
    cancelled: false,
    reconciliation_status: "UNMATCHED",
    latest_run_id: RUN_ID,
    latest_run_at: "2026-10-22T12:00:00+00:00",
    data_through: "2026-10-20",
    open_discrepancy_count: 2,
    blocking_discrepancy_count: 1,
    run_count: 1,
    ...overrides,
  };
}

function exception(overrides: Partial<FinancialException> = {}): FinancialException {
  return {
    id: "disc-1",
    run_id: RUN_ID,
    sales_order_id: ORDER_ID,
    order_number: "SO-2610-ABC123",
    customer_name: "Buyer Ltd",
    currency: "USD",
    order_status: "CONFIRMED",
    code: "MISSING_FINANCE_REFERENCE",
    severity: "WARNING",
    status: "OPEN",
    title: "No Finance source is linked to this order yet",
    detail: "An unavailable capability, not proof that an invoice is missing.",
    expected: {},
    observed: {},
    source_entity_type: null,
    source_entity_id: null,
    finance_source_reference: null,
    reviewer_name: null,
    resolution_notes: null,
    resolved_at: null,
    created_at: "2026-10-22T12:00:00+00:00",
    updated_at: "2026-10-22T12:00:00+00:00",
    version: 1,
    ...overrides,
  };
}

function detail(orderOverrides: Partial<OrderProfitability> = {}): OrderIntelligenceDetail {
  return {
    order: order(orderOverrides),
    quote: {
      quote_id: "quote-1",
      quote_number: "SQ-2610-0001",
      revision: 2,
      status: "APPROVED",
      currency: "USD",
      incoterm: "CIF",
      named_delivery_place: "Rotterdam",
      payment_terms: "30 days net",
      valid_until: "2026-12-01",
      lines: [
        {
          product_id: "prod-1",
          description: "Aluminium ingot",
          quantity: "100.000",
          unit: "MT",
          unit_price: "2.50",
          line_total: "250.00",
        },
      ],
    },
    purchase_orders: [
      {
        purchase_order_id: "po-1",
        po_number: "PO-2610-0001",
        status: "APPROVED",
        currency: "USD",
        total_cost: "150.00",
        supplier_name: "Supplier One",
        classification: "COMMITTED",
      },
    ],
    shipments: [
      {
        shipment_id: "shp-1",
        shipment_number: "SHP-2610-0001",
        status: "DELIVERED",
        costs: [
          {
            cost_id: "cost-1",
            cost_type: "FREIGHT",
            stage: "INCURRED",
            currency: "USD",
            amount: "20.00",
            reference: "freight-1",
            classification: "DOCUMENTED",
          },
        ],
      },
    ],
    cost_lines: [
      {
        cost_type: "VAT_CASHFLOW",
        original_amount: "18.00",
        original_currency: "USD",
        converted_amount: "18.00",
        target_currency: "USD",
        basis: "ORDER",
        verification_status: "VERIFIED",
        source_reference: "vat-1",
        fx_rate: null,
        fx_snapshot_id: null,
        is_expense: false,
      },
    ],
    fx_assumptions: [],
    checks: [
      {
        key: "po",
        label: "Approved purchase order",
        satisfied: true,
        detail: "PO-2610-0001 is approved.",
      },
      {
        key: "ship",
        label: "Shipment cost evidence",
        satisfied: false,
        detail: "No INCURRED cost is recorded.",
      },
    ],
    limitations: ["Actual profit needs a Finance invoice source that does not exist yet."],
    runs: [
      {
        run_id: RUN_ID,
        status: "UNMATCHED",
        as_of: "2026-10-22",
        data_through: "2026-10-20",
        currency: "USD",
        created_at: "2026-10-22T12:00:00+00:00",
        evidence_count: 0,
        open_discrepancy_count: 2,
        latest_decision: null,
        latest_review_at: null,
      },
    ],
    evidence: [],
    discrepancies: [exception()],
    read_only: true,
    accounting_writes_enabled: false,
    statutory_statements: false,
  };
}

describe("MetricCard", () => {
  it("shows each currency on its own line and never a combined total", () => {
    render(<MetricCard metric={metric()} />);
    const card = screen.getByText("Accepted order value").closest("[data-metric]") as HTMLElement;
    expect(within(card).getByText(/250\.00/)).toBeInTheDocument();
    expect(within(card).getByText(/100\.00/)).toBeInTheDocument();
    expect(within(card).getByText("USD")).toBeInTheDocument();
    expect(within(card).getByText("EUR")).toBeInTheDocument();
    expect(within(card).queryByText(/350/)).not.toBeInTheDocument();
    expect(within(card).getByText("DOCUMENTED")).toBeInTheDocument();
    expect(within(card).getByText("COMPLETE")).toBeInTheDocument();
  });

  it("says Not available instead of showing zero for an unavailable metric", () => {
    render(
      <MetricCard
        metric={metric({
          available: false,
          classification: "UNAVAILABLE",
          completeness: "UNAVAILABLE",
          money: [{ currency: "USD", amount: "0.00" }],
        })}
      />,
    );
    expect(screen.getByText("Not available")).toBeInTheDocument();
    expect(screen.queryByText(/0\.00/)).not.toBeInTheDocument();
  });

  it("does not label a figure-less metric with the kind the API reports for it", () => {
    render(
      <MetricCard
        metric={metric({
          key: "committed_gross_profit",
          label: "Committed gross profit",
          available: false,
          classification: "COMMITTED",
          completeness: "PARTIAL",
          money: [],
        })}
      />,
    );
    const card = screen.getByText("Committed gross profit").closest("[data-metric]") as HTMLElement;
    expect(within(card).getByText("Not available")).toBeInTheDocument();
    expect(within(card).getByText("UNAVAILABLE")).toBeInTheDocument();
    expect(within(card).queryByText("COMMITTED")).not.toBeInTheDocument();
  });

  it("tints a loss and leaves a gain alone, keeping the minus sign in the text", () => {
    render(
      <MetricCard
        metric={metric({
          key: "estimated_gross_margin",
          label: "Estimated gross margin",
          kind: "PERCENT",
          money: [],
          percentages: [
            { currency: "USD", value: "-12.50" },
            { currency: "EUR", value: "21.75" },
          ],
        })}
      />,
    );
    const loss = screen.getByText("-12.50%");
    expect(loss).toHaveClass("text-crimson-400");
    const gain = screen.getByText("21.75%");
    expect(gain).toHaveClass("text-mist-100");
    expect(gain).not.toHaveClass("text-crimson-400");
  });

  it("never lets a coverage ratio wear the VERIFIED label, even at 0.00%", () => {
    render(
      <MetricCard
        metric={metric({
          key: "reconciliation_coverage",
          label: "Reconciliation coverage",
          kind: "PERCENT",
          money: [],
          percentage: "0.00",
          classification: "VERIFIED",
        })}
      />,
    );
    const card = screen
      .getByText("Reconciliation coverage")
      .closest("[data-metric]") as HTMLElement;
    expect(within(card).getByText("0.00%")).toBeInTheDocument();
    expect(within(card).queryByText("VERIFIED")).not.toBeInTheDocument();
    expect(within(card).getByText("COMPLETE")).toBeInTheDocument();
  });
});

describe("charts", () => {
  const monthly = [
    {
      month: "2026-09",
      currency: "USD",
      accepted_value: "250.00",
      purchase_commitments: "150.00",
      order_count: 1,
    },
    {
      month: "2026-09",
      currency: "EUR",
      accepted_value: "100.00",
      purchase_commitments: "60.00",
      order_count: 2,
    },
  ];

  it("draws one scale per currency, with a legend and a table view", () => {
    render(<MonthlyCommitmentsChart rows={monthly} />);
    expect(screen.getByLabelText("Legend")).toHaveTextContent("Accepted value");
    expect(screen.getByLabelText("Legend")).toHaveTextContent("Purchase commitments");
    expect(screen.getByText("Table view")).toBeInTheDocument();
    const marks = screen.getAllByLabelText(/· accepted/);
    expect(marks).toHaveLength(2);
    expect(screen.getByLabelText(/2026-09 · USD · accepted/)).toBeInTheDocument();
    expect(screen.getByLabelText(/2026-09 · EUR · accepted/)).toBeInTheDocument();
    expect(document.body.textContent).not.toMatch(/350\.00/);
  });

  it("says '1 order' in the tooltip, not '1 orders'", () => {
    render(<MonthlyCommitmentsChart rows={monthly} />);
    expect(screen.getByText("1 order")).toBeInTheDocument();
    expect(screen.getByText("2 orders")).toBeInTheDocument();
    expect(screen.queryByText("1 orders")).not.toBeInTheDocument();
  });

  it("scrolls a year of months inside its panel and anchors edge tooltips to the edge", () => {
    const months = Array.from({ length: 12 }, (_, index) => ({
      month: `2026-${String(index + 1).padStart(2, "0")}`,
      currency: "USD",
      accepted_value: "1000.00",
      purchase_commitments: "700.00",
      order_count: index + 1,
    }));
    const { container } = render(<MonthlyCommitmentsChart rows={months} />);

    const scroller = container.querySelector("[data-chart-scroll]") as HTMLElement;
    expect(scroller).toHaveClass("overflow-x-auto");
    // The panel is a grid item: without min-w-0 it would grow to the plot's width.
    expect(container.querySelector("section")).toHaveClass("min-w-0");
    expect(within(scroller).getAllByRole("listitem")).toHaveLength(12);
    for (const label of scroller.querySelectorAll('[role="listitem"] > p')) {
      expect(label).toHaveClass("whitespace-nowrap");
    }

    const tips = Array.from(scroller.querySelectorAll('[role="listitem"] > [aria-hidden="true"]'));
    expect(tips[0]).toHaveClass("left-0");
    expect(tips[11]).toHaveClass("right-0");
    expect(tips[5]).toHaveClass("left-1/2");
    for (const tip of tips) expect(tip).toHaveClass("top-0");
  });

  it("states emptiness instead of drawing an empty plot", () => {
    render(<MonthlyCommitmentsChart rows={[]} />);
    expect(screen.getByText("No monthly commitments")).toBeInTheDocument();
    expect(screen.queryByText("Table view")).not.toBeInTheDocument();
  });

  it("compares estimated and documented cost inside each currency", () => {
    render(
      <CostComparisonChart
        rows={[
          {
            currency: "USD",
            estimated_cost: "170.00",
            documented_cost: "170.00",
            variance: "0.00",
            order_count: 1,
          },
        ]}
      />,
    );
    expect(screen.getByLabelText(/Estimated cost .*170\.00/)).toBeInTheDocument();
    expect(screen.getByLabelText(/Documented cost .*170\.00/)).toBeInTheDocument();
    expect(screen.getByLabelText("Legend")).toBeInTheDocument();
  });

  it("lists margin bands with their order counts", () => {
    render(
      <MarginDistributionChart
        buckets={[
          { key: "LOSS", label: "LOSS", count: 1 },
          { key: "30+", label: "30+", count: 4 },
        ]}
      />,
    );
    expect(screen.getByLabelText("30+: 4 orders")).toBeInTheDocument();
    expect(screen.getByLabelText("LOSS: 1 order")).toBeInTheDocument();
  });

  it("ranks categories by count, largest first", () => {
    render(
      <RankedCountChart
        title="Exception categories"
        items={[
          { key: "SOURCE_STALE", count: 1 },
          { key: "MISSING_EVIDENCE", count: 4 },
        ]}
        emptyTitle="No open exceptions"
      />,
    );
    const rows = screen.getAllByRole("listitem");
    expect(rows[0]).toHaveAttribute("aria-label", "MISSING EVIDENCE: 4");
    expect(rows[1]).toHaveAttribute("aria-label", "SOURCE STALE: 1");
  });

  it("names every completeness segment with its count", () => {
    render(
      <CompletenessBar
        title="Order completeness"
        counts={[
          { status: "COMPLETE", count: 3 },
          { status: "PARTIAL", count: 1 },
          { status: "MISSING", count: 0 },
          { status: "UNAVAILABLE", count: 2 },
        ]}
      />,
    );
    for (const label of ["COMPLETE", "PARTIAL", "MISSING", "UNAVAILABLE"]) {
      expect(screen.getAllByText(label).length).toBeGreaterThan(0);
    }
    expect(screen.getByText("Table view")).toBeInTheDocument();
  });

  it("keeps a tiny completeness share visible instead of sub-pixel", () => {
    const { container } = render(
      <CompletenessBar
        title="Tiny segments"
        counts={[
          { status: "COMPLETE", count: 1 },
          { status: "PARTIAL", count: 1 },
          { status: "MISSING", count: 0 },
          { status: "UNAVAILABLE", count: 5000 },
        ]}
      />,
    );
    const segments = container.querySelectorAll('div[aria-hidden="true"] > div');
    expect(segments).toHaveLength(3);
    for (const segment of segments) expect(segment).toHaveClass("min-w-1");
    expect(screen.getAllByText("5000").length).toBeGreaterThan(0);
  });

  it("renders an empty chart as plain text, not as a panel inside the panel", () => {
    const { container } = render(<MonthlyCommitmentsChart rows={[]} />);
    const panel = container.querySelector("section") as HTMLElement;
    expect(within(panel).getByText("No monthly commitments")).toBeInTheDocument();
    expect(panel.querySelectorAll(".panel")).toHaveLength(0);
  });

  it("gives a category label its full text on hover and two lines before it clips", () => {
    render(
      <RankedCountChart
        title="Exception categories"
        items={[{ key: "MISSING_FINANCE_REFERENCE", count: 4 }]}
        emptyTitle="none"
      />,
    );
    const label = screen.getByTitle("MISSING FINANCE REFERENCE");
    expect(label).toHaveTextContent("MISSING FINANCE REFERENCE");
    expect(label).toHaveClass("line-clamp-2");
    expect(label).not.toHaveClass("truncate");
  });

  it("anchors margin-band tooltips to the edges of the chart", () => {
    const { container } = render(
      <MarginDistributionChart
        buckets={["LOSS", "0-9.99", "10-19.99", "20-29.99", "30+"].map((label) => ({
          key: label,
          label,
          count: 3,
        }))}
      />,
    );
    const tips = Array.from(container.querySelectorAll('[role="listitem"] > [aria-hidden="true"]'));
    expect(tips).toHaveLength(5);
    expect(tips[0]).toHaveClass("left-0");
    expect(tips[2]).toHaveClass("left-1/2");
    expect(tips[4]).toHaveClass("right-0");
  });

  it("lets an odd last panel span both columns instead of sitting alone", () => {
    const { container } = render(
      <ChartGrid>
        <div>one</div>
        <div>two</div>
        <div>three</div>
      </ChartGrid>,
    );
    const grid = container.firstElementChild as HTMLElement;
    expect(grid).toHaveClass("grid-cols-1", "xl:grid-cols-2");
    expect(grid.className).toContain("xl:[&>*:last-child:nth-child(odd)]:col-span-2");
  });
});

describe("IntelligenceOrdersTable", () => {
  it("links to the order analysis and keeps missing figures as words", () => {
    render(<IntelligenceOrdersTable items={[order()]} />);
    expect(screen.getByRole("link", { name: "SO-2610-ABC123" })).toHaveAttribute(
      "href",
      `/finance/intelligence/orders/${ORDER_ID}`,
    );
    expect(screen.getAllByText("Not available").length).toBeGreaterThan(0);
    expect(screen.getByText("Partial fulfilment")).toBeInTheDocument();
    expect(screen.getByText(/Missing: SHIPMENT COSTS/)).toBeInTheDocument();
    expect(screen.getByText("2 open · 1 blocking")).toBeInTheDocument();
  });

  it("tints a loss-making margin but not a cost variance, where negative is a saving", () => {
    const { container } = render(
      <IntelligenceOrdersTable
        items={[
          order({
            estimated_gross_profit: "-100.00",
            estimated_gross_margin_pct: "-40.00",
            cost_variance: "-1.50",
            cost_variance_pct: "-0.50",
          }),
        ]}
      />,
    );
    const tinted = container.querySelectorAll("[data-negative]");
    expect(tinted).toHaveLength(1);
    expect(tinted[0]).toHaveTextContent(/-.*100\.00/);
    expect(tinted[0]).toHaveClass("text-crimson-400");
    const variance = screen.getByText(/-.*1\.50/);
    expect(variance).not.toHaveClass("text-crimson-400");
    // The percentage line uses the full-strength tint (the /80 variant fell below 4.5:1).
    expect(screen.getByText("-40.00%")).toHaveClass("text-crimson-400");
    expect(screen.getByText("-0.50%")).not.toHaveClass("text-crimson-400");
  });

  it("shows an empty state for no orders", () => {
    render(<IntelligenceOrdersTable items={[]} />);
    expect(screen.getByText("No orders match")).toBeInTheDocument();
  });

  it("keeps the order number whole, clamps a long customer name and folds status into the order cell", () => {
    const longName = "Anatolian Agricultural Commodities & Dried Fruit Export Trading Company Ltd.";
    render(<IntelligenceOrdersTable items={[order({ customer_name: longName })]} />);

    const link = screen.getByRole("link", { name: "SO-2610-ABC123" });
    expect(link).toHaveClass("whitespace-nowrap");
    const cell = link.closest("td") as HTMLElement;
    const name = within(cell).getByText(longName);
    expect(name).toHaveClass("line-clamp-2");
    expect(name).toHaveAttribute("title", longName);
    expect(within(cell).getByText("CONFIRMED")).toBeInTheDocument();
    expect(within(cell).getByText("PURCHASE RESALE")).toBeInTheDocument();

    expect(screen.queryByRole("columnheader", { name: "Status" })).not.toBeInTheDocument();
    for (const header of screen.getAllByRole("columnheader")) {
      if (/margin|cost|value|variance/i.test(header.textContent ?? "")) {
        expect(header).toHaveClass("whitespace-normal");
      }
    }
  });
});

describe("IntelligenceExceptionsTable", () => {
  it("offers resolution only to a reviewer on an open item", () => {
    const { rerender } = render(
      <IntelligenceExceptionsTable items={[exception()]} csrfToken="csrf" canReview />,
    );
    expect(screen.getByRole("button", { name: "Resolve" })).toBeInTheDocument();
    expect(screen.getByRole("link", { name: "SO-2610-ABC123" })).toHaveAttribute(
      "href",
      `/finance/intelligence/orders/${ORDER_ID}`,
    );

    rerender(
      <IntelligenceExceptionsTable items={[exception()]} csrfToken="csrf" canReview={false} />,
    );
    expect(screen.queryByRole("button", { name: "Resolve" })).not.toBeInTheDocument();

    rerender(
      <IntelligenceExceptionsTable
        items={[
          exception({
            status: "RESOLVED",
            resolution_notes: "Linked F-USD-AR-1.",
            reviewer_name: "Amina",
          }),
        ]}
        csrfToken="csrf"
        canReview
      />,
    );
    expect(screen.queryByRole("button", { name: "Resolve" })).not.toBeInTheDocument();
    expect(screen.getByText("Linked F-USD-AR-1.")).toBeInTheDocument();
  });

  it("keeps the finding and its resolution control together in one wide column", () => {
    render(
      <IntelligenceExceptionsTable
        items={[exception({ finance_source_reference: "F-USD-AR-1" })]}
        csrfToken="csrf"
        canReview
      />,
    );

    expect(screen.getAllByRole("columnheader").map((header) => header.textContent)).toEqual([
      "Order",
      "Exception",
      "Finding and resolution",
    ]);
    const finding = screen.getByText("No Finance source is linked to this order yet");
    const cell = finding.closest("td") as HTMLElement;
    expect(cell).toHaveClass("min-w-[280px]");
    expect(within(cell).getByRole("button", { name: "Resolve" })).toBeInTheDocument();
    expect(within(cell).getByText("F-USD-AR-1")).toBeInTheDocument();
    expect(within(cell).getByRole("link", { name: "Open run" })).toHaveAttribute(
      "href",
      `/finance/reconciliation/${RUN_ID}`,
    );

    const orderCell = screen.getByRole("link", { name: "SO-2610-ABC123" }).closest("td");
    expect(orderCell).toHaveTextContent("USD");
    expect(orderCell).toHaveTextContent("22 Oct 2026");
    const exceptionCell = screen.getByText("MISSING FINANCE REFERENCE").closest("td");
    expect(exceptionCell).toHaveTextContent("WARNING");
    expect(exceptionCell).toHaveTextContent("OPEN");
  });
});

describe("IntelligenceDetail", () => {
  it("separates the bases, keeps actual profit unavailable and states the limitations", () => {
    render(<IntelligenceDetail detail={detail()} csrfToken="csrf" canReview={false} />);
    expect(screen.getByText("Actual profit").closest(".panel")).toHaveTextContent("Not available");
    expect(screen.getByText("Estimated gross profit")).toBeInTheDocument();
    expect(screen.getByText("Committed gross profit")).toBeInTheDocument();
    expect(
      screen.getByText("Actual profit needs a Finance invoice source that does not exist yet."),
    ).toBeInTheDocument();
    expect(screen.getByText("Approved purchase order")).toBeInTheDocument();
    expect(screen.getByText(/Shipment cost evidence/)).toBeInTheDocument();
    expect(screen.getByRole("link", { name: "PO-2610-0001" })).toBeInTheDocument();
    expect(screen.getByRole("link", { name: "SHP-2610-0001" })).toBeInTheDocument();
    expect(
      screen.getByText("No Finance source has been linked to this order."),
    ).toBeInTheDocument();
    expect(screen.getByText("Exceptions for this order")).toBeInTheDocument();
  });

  it("shows the documented operational cost it has, and the total as unavailable", () => {
    render(<IntelligenceDetail detail={detail()} csrfToken="csrf" canReview={false} />);
    const tile = screen.getByText("Documented operational cost").closest(".panel") as HTMLElement;
    expect(tile).toHaveTextContent(/20\.00/);
    expect(within(tile).getByText("DOCUMENTED")).toBeInTheDocument();
    expect(tile).toHaveTextContent("Total with purchases: Not available");
    expect(screen.queryByText("Documented cost")).not.toBeInTheDocument();
  });

  it("never writes 'Not available of estimate' and shows a variance percentage only when it exists", () => {
    const { rerender } = render(
      <IntelligenceDetail detail={detail()} csrfToken="csrf" canReview={false} />,
    );
    const empty = screen.getByText("Cost variance").closest(".panel") as HTMLElement;
    expect(empty).toHaveTextContent("Not available");
    expect(empty).not.toHaveTextContent("of estimate");

    rerender(
      <IntelligenceDetail
        detail={detail({
          cost_variance: "-1.50",
          cost_variance_pct: "-0.73",
          classifications: { ...order().classifications, cost_variance: "ESTIMATED" },
        })}
        csrfToken="csrf"
        canReview={false}
      />,
    );
    const filled = screen.getByText("Cost variance").closest(".panel") as HTMLElement;
    expect(filled).toHaveTextContent("-0.73% of estimate");
    expect(within(filled).getByText("ESTIMATED")).toBeInTheDocument();
  });

  it("never lets a badge name a kind for a figure that is not shown", () => {
    render(
      <IntelligenceDetail
        detail={detail({
          committed_gross_profit: null,
          classifications: { ...order().classifications, committed_gross_profit: "COMMITTED" },
        })}
        csrfToken="csrf"
        canReview={false}
      />,
    );
    const tile = screen.getByText("Committed gross profit").closest(".panel") as HTMLElement;
    expect(tile).toHaveTextContent("Not available");
    expect(within(tile).getByText("UNAVAILABLE")).toBeInTheDocument();
    expect(within(tile).queryByText("COMMITTED")).not.toBeInTheDocument();
  });

  it("tints a negative estimated profit and margin on the detail tile", () => {
    const { rerender } = render(
      <IntelligenceDetail
        detail={detail({
          estimated_gross_profit: "-100.00",
          estimated_gross_margin_pct: "-40.00",
        })}
        csrfToken="csrf"
        canReview={false}
      />,
    );
    const loss = screen.getByText("Estimated gross profit").closest(".panel") as HTMLElement;
    expect(loss.querySelectorAll("[data-negative]")).toHaveLength(2);
    expect(loss).toHaveTextContent("-40.00% margin");

    rerender(<IntelligenceDetail detail={detail()} csrfToken="csrf" canReview={false} />);
    const gain = screen.getByText("Estimated gross profit").closest(".panel") as HTMLElement;
    expect(gain.querySelectorAll("[data-negative]")).toHaveLength(0);
  });

  it("marks a non-expense cost line as excluded", () => {
    render(<IntelligenceDetail detail={detail()} csrfToken="csrf" canReview={false} />);
    const row = screen.getByText("VAT CASHFLOW").closest("tr") as HTMLElement;
    expect(within(row).getByText("No")).toBeInTheDocument();
  });
});

describe("IntelligenceFilterBar and Pager", () => {
  const options = {
    currencies: ["EUR", "USD"],
    customers: [{ id: "c1", name: "Buyer Ltd" }],
    suppliers: [],
    order_statuses: ["CONFIRMED"],
    fulfilment_models: ["PURCHASE_RESALE"],
    reconciliation_statuses: ["VERIFIED"],
    completeness_statuses: ["COMPLETE" as const],
  };

  it("pre-selects active filters, preserves hidden state and offers Clear", () => {
    render(
      <IntelligenceFilterBar
        action="/finance/intelligence/orders"
        filters={{ currency: "USD", from: "2026-01-01" }}
        options={options}
        hidden={{ view: "variance" }}
      />,
    );
    expect(screen.getByLabelText("Currency")).toHaveValue("USD");
    expect(screen.getByLabelText("From")).toHaveValue("2026-01-01");
    expect(screen.getByRole("option", { name: "Buyer Ltd" })).toBeInTheDocument();
    expect(screen.getByRole("link", { name: "Clear" })).toHaveAttribute(
      "href",
      "/finance/intelligence/orders?view=variance",
    );
    expect(document.querySelector('input[type="hidden"][name="view"]')).toHaveAttribute(
      "value",
      "variance",
    );
  });

  it("puts every filter label above its control, dates included", () => {
    render(<IntelligenceFilterBar action="/finance/intelligence" filters={{}} options={options} />);
    for (const label of ["From", "To", "Currency", "Completeness"]) {
      expect(screen.getByText(label)).toHaveClass("block");
    }
  });

  it("pages forward and back while keeping the filters", () => {
    render(
      <Pager
        basePath="/finance/intelligence/orders"
        total={60}
        limit={25}
        offset={25}
        params={{ currency: "USD" }}
        noun="order"
      />,
    );
    expect(screen.getByRole("link", { name: "Previous" })).toHaveAttribute(
      "href",
      "/finance/intelligence/orders?currency=USD&offset=0",
    );
    expect(screen.getByRole("link", { name: "Next" })).toHaveAttribute(
      "href",
      "/finance/intelligence/orders?currency=USD&offset=50",
    );
    expect(screen.getByText(/60 orders/)).toBeInTheDocument();
  });
});

describe("ExportCsvButton", () => {
  it("downloads the file with the server's name and sends the active filters", async () => {
    const fetchMock = vi.fn().mockResolvedValue(
      new Response("record_type\r\n", {
        status: 200,
        headers: {
          "content-type": "text/csv",
          "content-disposition": 'attachment; filename="analysis-20261023.csv"',
        },
      }),
    );
    vi.stubGlobal("fetch", fetchMock);
    const createObjectURL = vi.fn(() => "blob:mock");
    const revokeObjectURL = vi.fn();
    Object.defineProperty(URL, "createObjectURL", { value: createObjectURL, configurable: true });
    Object.defineProperty(URL, "revokeObjectURL", { value: revokeObjectURL, configurable: true });
    const downloads: string[] = [];
    vi.spyOn(HTMLAnchorElement.prototype, "click").mockImplementation(function (
      this: HTMLAnchorElement,
    ) {
      downloads.push(this.download);
    });

    render(<ExportCsvButton filters={{ currency: "USD" }} orderCount={3} />);
    expect(screen.getByText("3 orders")).toBeInTheDocument();
    await userEvent.click(screen.getByRole("button", { name: /Export CSV/ }));

    await waitFor(() => expect(downloads).toEqual(["analysis-20261023.csv"]));
    const [url, init] = fetchMock.mock.calls[0] as [string, RequestInit];
    expect(url).toMatch(/\/finance\/intelligence\/export\?currency=USD$/);
    expect(init.credentials).toBe("same-origin");
    expect(revokeObjectURL).toHaveBeenCalledWith("blob:mock");
    expect(screen.queryByText("Export failed")).not.toBeInTheDocument();
  });

  it("shows a refusal on the page instead of saving the error as a file", async () => {
    vi.stubGlobal(
      "fetch",
      vi.fn().mockResolvedValue(
        new Response(
          JSON.stringify({
            error: {
              code: "BAD_REQUEST",
              message: "The selected analysis contains more than 5000 orders.",
              request_id: "req-9",
              timestamp: "2026-10-23T09:00:00+00:00",
              details: null,
            },
          }),
          { status: 400, headers: { "content-type": "application/json" } },
        ),
      ),
    );
    const click = vi.spyOn(HTMLAnchorElement.prototype, "click").mockImplementation(() => {});

    render(<ExportCsvButton filters={{}} />);
    await userEvent.click(screen.getByRole("button", { name: /Export CSV/ }));

    expect(await screen.findByText("Export failed")).toBeInTheDocument();
    expect(screen.getByText(/more than 5000 orders/)).toBeInTheDocument();
    expect(screen.getByText(/BAD_REQUEST · request req-9/)).toBeInTheDocument();
    expect(click).not.toHaveBeenCalled();
  });

  it("reports an unreachable API", async () => {
    vi.stubGlobal("fetch", vi.fn().mockRejectedValue(new Error("offline")));
    render(<ExportCsvButton filters={{}} />);
    await userEvent.click(screen.getByRole("button", { name: /Export CSV/ }));
    expect(await screen.findByText(/Cannot reach the API/)).toBeInTheDocument();
  });
});

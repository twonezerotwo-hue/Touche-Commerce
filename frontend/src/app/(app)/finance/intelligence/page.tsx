import Link from "next/link";

import { ApiErrorAlert } from "@/components/finance/api-error-alert";
import { ExportCsvButton } from "@/components/finance/export-csv-button";
import {
  ChartGrid,
  CompletenessBar,
  CostComparisonChart,
  MarginDistributionChart,
  MonthlyCommitmentsChart,
  RankedCountChart,
} from "@/components/finance/intelligence-charts";
import { IntelligenceFilterBar } from "@/components/finance/intelligence-filters";
import { MetricGrid } from "@/components/finance/intelligence-metrics";
import { IntelligenceOrdersTable } from "@/components/finance/intelligence-orders-table";
import { Alert } from "@/components/ui/alert";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { PageHeader } from "@/components/ui/page-header";
import { serverGet } from "@/lib/api/server";
import { loadSession } from "@/lib/auth/session";
import {
  INTELLIGENCE_ANALYSIS_NOTICE,
  intelligenceQuery,
  parseIntelligenceFilters,
  type IntelligenceCoverage,
  type IntelligenceSummary,
} from "@/lib/finance/intelligence";
import { formatDate, withQuery } from "@/lib/trade/format";

export const dynamic = "force-dynamic";
export const metadata = { title: "Financial intelligence" };

const BASE = "/finance/intelligence";

export default async function FinancialIntelligencePage({
  searchParams,
}: {
  searchParams: Promise<Record<string, string | string[] | undefined>>;
}) {
  const state = await loadSession();
  if (state.status !== "authenticated") return null;

  const filters = parseIntelligenceFilters(await searchParams);
  const query = intelligenceQuery(filters);
  const suffix = query ? `?${query}` : "";

  const [summaryResult, coverageResult] = await Promise.all([
    serverGet<IntelligenceSummary>(`/finance/intelligence/summary${suffix}`),
    serverGet<IntelligenceCoverage>(`/finance/intelligence/coverage${suffix}`),
  ]);

  const header = (
    <PageHeader
      eyebrow="Finance · Stage 5E"
      back={{ href: "/finance", label: "Finance" }}
      meta={
        <div className="flex flex-wrap items-center gap-2">
          <Badge variant="secondary">Operational analysis</Badge>
          <Badge variant="outline">Read-only</Badge>
          {summaryResult.ok ? (
            <span className="font-mono text-[10px] text-mist-600">
              {summaryResult.data.calculation_version}
            </span>
          ) : null}
        </div>
      }
      title="Financial intelligence"
      description="Order profitability from real Commerce facts: accepted value, committed purchases, recorded costs and reconciliation evidence — kept in separate bases, per currency."
      actions={
        <div className="flex flex-wrap gap-2">
          <Button asChild size="sm">
            <Link href={withQuery(`${BASE}/orders`, filters)}>Order profitability</Link>
          </Button>
          <Button asChild size="sm" variant="outline">
            <Link href={`${BASE}/exceptions`}>Exceptions</Link>
          </Button>
        </div>
      }
    />
  );

  if (!summaryResult.ok) {
    return (
      <div className="mx-auto max-w-[1360px] space-y-5">
        {header}
        <ApiErrorAlert title="Financial intelligence unavailable" failure={summaryResult} />
      </div>
    );
  }

  const summary = summaryResult.data;
  const coverage = coverageResult.ok ? coverageResult.data : null;

  return (
    <div className="mx-auto max-w-[1360px] space-y-5">
      {header}

      <Alert variant="info" title="What this is — and is not">
        {INTELLIGENCE_ANALYSIS_NOTICE}
      </Alert>

      <IntelligenceFilterBar action={BASE} filters={filters} options={summary.filter_options} />

      <div className="flex flex-wrap items-start justify-between gap-3">
        <p className="text-[11px] text-mist-500">
          <span className="font-mono text-mist-300">{summary.order_count}</span> order
          {summary.order_count === 1 ? "" : "s"} ({summary.active_order_count} active,{" "}
          {summary.cancelled_order_count} cancelled) · as of {formatDate(summary.as_of)} · Finance
          data through {formatDate(summary.data_through ?? null)}
        </p>
        <ExportCsvButton filters={filters} orderCount={summary.order_count} />
      </div>

      <MetricGrid metrics={summary.metrics} />

      <ChartGrid>
        <MonthlyCommitmentsChart rows={summary.monthly_commitments} />
        <CostComparisonChart rows={summary.cost_comparison} />
        <MarginDistributionChart buckets={summary.margin_distribution} />
        <RankedCountChart
          title="Exception categories"
          description="Open Stage 5D discrepancies grouped by code. Resolving one never changes Finance."
          items={summary.discrepancy_categories}
          emptyTitle="No open exceptions"
          columnLabel="Open"
        />
      </ChartGrid>

      <ChartGrid>
        <CompletenessBar
          title="Order completeness"
          description="How much of each order's cost picture is documented."
          counts={summary.completeness}
        />
        {coverage ? (
          <CompletenessBar
            title="Estimate coverage"
            description="Orders with a complete landed-cost estimate."
            counts={coverage.estimate}
          />
        ) : null}
        {coverage ? (
          <CompletenessBar
            title="Committed-basis coverage"
            description="Orders whose purchase commitments and recorded costs are complete."
            counts={coverage.committed}
          />
        ) : null}
        {coverage ? (
          <RankedCountChart
            title="Reconciliation coverage"
            description="Orders by the status of their latest Stage 5D run."
            items={coverage.reconciliation}
            emptyTitle="No reconciliation data"
            columnLabel="Orders"
          />
        ) : null}
        {coverage ? (
          <RankedCountChart
            title="Missing inputs"
            description="Which inputs most often keep a figure unavailable."
            items={coverage.missing_components}
            emptyTitle="Nothing is missing"
            columnLabel="Orders"
          />
        ) : null}
      </ChartGrid>
      {!coverageResult.ok ? (
        <ApiErrorAlert title="Coverage unavailable" failure={coverageResult} />
      ) : null}

      <div className="panel overflow-hidden">
        <div className="flex flex-wrap items-center justify-between gap-3 px-4 py-3">
          <div>
            <p className="eyebrow">Orders needing review</p>
            <p className="mt-1 text-[11px] text-mist-500">
              Active orders with open exceptions or missing/partial cost data. Blocking exceptions
              come first; up to eight, newest first within each group.
            </p>
          </div>
          <Button asChild variant="outline" size="sm">
            <Link href={withQuery(`${BASE}/orders`, filters)}>All orders</Link>
          </Button>
        </div>
        <div className="hairline" />
        <IntelligenceOrdersTable
          items={summary.review_orders}
          emptyTitle="Nothing needs review"
          emptyDescription="Every order in this range is complete and free of open exceptions."
        />
      </div>
    </div>
  );
}

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
  intelligenceQuery,
  parseIntelligenceFilters,
  type IntelligenceCoverage,
  type IntelligenceSummary,
} from "@/lib/finance/intelligence";
import { getServerT, titleFor } from "@/lib/i18n/server";
import { formatDate, withQuery } from "@/lib/trade/format";

export const dynamic = "force-dynamic";
export const generateMetadata = () => titleFor("intTitle");

const BASE = "/finance/intelligence";

export default async function FinancialIntelligencePage({
  searchParams,
}: {
  searchParams: Promise<Record<string, string | string[] | undefined>>;
}) {
  const state = await loadSession();
  if (state.status !== "authenticated") return null;

  const { t, locale } = await getServerT();
  const filters = parseIntelligenceFilters(await searchParams);
  const query = intelligenceQuery(filters);
  const suffix = query ? `?${query}` : "";

  const [summaryResult, coverageResult] = await Promise.all([
    serverGet<IntelligenceSummary>(`/finance/intelligence/summary${suffix}`),
    serverGet<IntelligenceCoverage>(`/finance/intelligence/coverage${suffix}`),
  ]);

  const header = (
    <PageHeader
      eyebrow={t("intEyebrow")}
      back={{ href: "/finance", label: t("finBackFinance") }}
      meta={
        <div className="flex flex-wrap items-center gap-2">
          <Badge variant="secondary">{t("intBadgeAnalysis")}</Badge>
          <Badge variant="outline">{t("intBadgeReadOnly")}</Badge>
          {summaryResult.ok ? (
            <span className="font-mono text-[10px] text-mist-600">
              {summaryResult.data.calculation_version}
            </span>
          ) : null}
        </div>
      }
      title={t("intTitle")}
      description={t("intDescription")}
      actions={
        <div className="flex flex-wrap gap-2">
          <Button asChild size="sm">
            <Link href={withQuery(`${BASE}/orders`, filters)}>{t("intBtnOrders")}</Link>
          </Button>
          <Button asChild size="sm" variant="outline">
            <Link href={`${BASE}/exceptions`}>{t("intBtnExceptions")}</Link>
          </Button>
        </div>
      }
    />
  );

  if (!summaryResult.ok) {
    return (
      <div className="mx-auto max-w-[1360px] space-y-5">
        {header}
        <ApiErrorAlert title={t("intUnavailable")} failure={summaryResult} />
      </div>
    );
  }

  const summary = summaryResult.data;
  const coverage = coverageResult.ok ? coverageResult.data : null;

  return (
    <div className="mx-auto max-w-[1360px] space-y-5">
      {header}

      <Alert variant="info" title={t("intWhatTitle")}>
        {t("intNotice")}
      </Alert>

      <IntelligenceFilterBar action={BASE} filters={filters} options={summary.filter_options} />

      <div className="flex flex-wrap items-start justify-between gap-3">
        <p className="text-[11px] text-mist-500">
          {t(summary.order_count === 1 ? "intOrderLineOne" : "intOrderLineMany", {
            count: summary.order_count,
            active: summary.active_order_count,
            cancelled: summary.cancelled_order_count,
            asOf: formatDate(summary.as_of, locale),
            through: formatDate(summary.data_through ?? null, locale),
          })}
        </p>
        <ExportCsvButton filters={filters} orderCount={summary.order_count} />
      </div>

      <MetricGrid metrics={summary.metrics} />

      <ChartGrid>
        <MonthlyCommitmentsChart rows={summary.monthly_commitments} />
        <CostComparisonChart rows={summary.cost_comparison} />
        <MarginDistributionChart buckets={summary.margin_distribution} />
        <RankedCountChart
          title={t("intExceptionsTitle")}
          description={t("intExceptionsDesc")}
          items={summary.discrepancy_categories}
          emptyTitle={t("intNoOpenExceptions")}
          columnLabel={t("intColOpen")}
        />
      </ChartGrid>

      <ChartGrid>
        <CompletenessBar
          title={t("intCompletenessTitle")}
          description={t("intCompletenessDesc")}
          counts={summary.completeness}
        />
        {coverage ? (
          <CompletenessBar
            title={t("intEstimateCoverageTitle")}
            description={t("intEstimateCoverageDesc")}
            counts={coverage.estimate}
          />
        ) : null}
        {coverage ? (
          <CompletenessBar
            title={t("intCommittedCoverageTitle")}
            description={t("intCommittedCoverageDesc")}
            counts={coverage.committed}
          />
        ) : null}
        {coverage ? (
          <RankedCountChart
            title={t("intReconCoverageTitle")}
            description={t("intReconCoverageDesc")}
            items={coverage.reconciliation}
            emptyTitle={t("intNoReconData")}
            columnLabel={t("intColOrders")}
          />
        ) : null}
        {coverage ? (
          <RankedCountChart
            title={t("intMissingInputsTitle")}
            description={t("intMissingInputsDesc")}
            items={coverage.missing_components}
            emptyTitle={t("intNothingMissing")}
            columnLabel={t("intColOrders")}
          />
        ) : null}
      </ChartGrid>
      {!coverageResult.ok ? (
        <ApiErrorAlert title={t("intCoverageUnavailable")} failure={coverageResult} />
      ) : null}

      <div className="panel overflow-hidden">
        <div className="flex flex-wrap items-center justify-between gap-3 px-4 py-3">
          <div>
            <p className="eyebrow">{t("intReviewTitle")}</p>
            <p className="mt-1 text-[11px] text-mist-500">{t("intReviewNote")}</p>
          </div>
          <Button asChild variant="outline" size="sm">
            <Link href={withQuery(`${BASE}/orders`, filters)}>{t("intAllOrders")}</Link>
          </Button>
        </div>
        <div className="hairline" />
        <IntelligenceOrdersTable
          items={summary.review_orders}
          emptyTitle={t("intNothingReview")}
          emptyDescription={t("intNothingReviewDesc")}
        />
      </div>
    </div>
  );
}

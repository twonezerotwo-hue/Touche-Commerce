import Link from "next/link";

import { ApiErrorAlert } from "@/components/finance/api-error-alert";
import { ExportCsvButton } from "@/components/finance/export-csv-button";
import { IntelligenceFilterBar } from "@/components/finance/intelligence-filters";
import { IntelligenceOrdersTable } from "@/components/finance/intelligence-orders-table";
import { Pager } from "@/components/finance/pager";
import { Alert } from "@/components/ui/alert";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { PageHeader } from "@/components/ui/page-header";
import { serverGet } from "@/lib/api/server";
import { loadSession } from "@/lib/auth/session";
import {
  intelligenceQuery,
  parseIntelligenceFilters,
  type CostVarianceList,
  type IntelligenceFilterOptions,
  type IntelligenceSummary,
  type OrderIntelligenceList,
} from "@/lib/finance/intelligence";
import { getServerT, titleFor } from "@/lib/i18n/server";
import { formatDate, withQuery } from "@/lib/trade/format";

export const dynamic = "force-dynamic";
export const generateMetadata = () => titleFor("intOrdTitle");

const BASE = "/finance/intelligence/orders";
const PAGE_SIZE = 25;

const NO_OPTIONS: IntelligenceFilterOptions = {
  currencies: [],
  customers: [],
  suppliers: [],
  order_statuses: [],
  fulfilment_models: [],
  reconciliation_statuses: [],
  completeness_statuses: [],
};

export default async function OrderProfitabilityPage({
  searchParams,
}: {
  searchParams: Promise<Record<string, string | string[] | undefined>>;
}) {
  const state = await loadSession();
  if (state.status !== "authenticated") return null;

  const { t, locale } = await getServerT();
  const params = await searchParams;
  const filters = parseIntelligenceFilters(params);
  const view = params.view === "variance" ? "variance" : "all";
  const rawOffset = Array.isArray(params.offset) ? params.offset[0] : params.offset;
  const offset = Math.max(0, Number.parseInt(rawOffset ?? "0", 10) || 0);

  const query = intelligenceQuery(filters, { limit: PAGE_SIZE, offset });
  const endpoint = view === "variance" ? "cost-variance" : "orders";

  // Filter options come from the summary; the list endpoints do not return them.
  const [listResult, optionsResult] = await Promise.all([
    serverGet<OrderIntelligenceList | CostVarianceList>(
      `/finance/intelligence/${endpoint}?${query}`,
    ),
    serverGet<IntelligenceSummary>("/finance/intelligence/summary"),
  ]);
  const options = optionsResult.ok ? optionsResult.data.filter_options : NO_OPTIONS;
  const tabParams = { ...filters };

  return (
    <div className="mx-auto max-w-[1360px] space-y-5">
      <PageHeader
        eyebrow={t("intEyebrow")}
        back={{ href: "/finance/intelligence", label: t("intBackIntelligence") }}
        meta={
          <div className="flex flex-wrap items-center gap-2">
            <Badge variant="secondary">{t("intBadgeAnalysis")}</Badge>
            <Badge variant="outline">{t("intBadgeReadOnly")}</Badge>
          </div>
        }
        title={t("intOrdTitle")}
        description={t("intOrdDescription")}
        actions={
          <div className="flex flex-wrap gap-2">
            <Button asChild size="sm" variant="outline">
              <Link href="/finance/intelligence/exceptions">{t("intBtnExceptions")}</Link>
            </Button>
          </div>
        }
      />

      <Alert variant="info" title={t("intNoticeTitle")}>
        {t("intNotice")}
      </Alert>

      {!optionsResult.ok ? (
        <ApiErrorAlert title={t("ordFilterOptionsUnavailable")} failure={optionsResult} />
      ) : null}

      <div className="panel flex flex-wrap items-center gap-2 px-3 py-2">
        {(
          [
            ["all", t("ordTabAll")],
            ["variance", t("ordTabVariance")],
          ] as const
        ).map(([tab, label]) => (
          <Link
            key={tab}
            href={withQuery(BASE, { ...tabParams, view: tab === "all" ? null : tab })}
            aria-current={view === tab ? "page" : undefined}
            className={
              view === tab
                ? "rounded-md bg-accent-400/10 px-3 py-1.5 text-[11.5px] text-accent-200"
                : "rounded-md px-3 py-1.5 text-[11.5px] text-mist-500 hover:bg-white/[0.04] hover:text-mist-200"
            }
          >
            {label}
          </Link>
        ))}
      </div>

      <IntelligenceFilterBar
        action={BASE}
        filters={filters}
        options={options}
        hidden={view === "variance" ? { view } : {}}
      />

      {!listResult.ok ? (
        <ApiErrorAlert title={t("intOrdUnavailable")} failure={listResult} />
      ) : (
        <>
          <div className="flex flex-wrap items-start justify-between gap-3">
            <p className="text-[11px] text-mist-500">
              {"as_of" in listResult.data
                ? t("ordAsOfLine", {
                    date: formatDate(listResult.data.as_of, locale),
                    version: listResult.data.calculation_version,
                  })
                : t("ordCalcLine", { version: listResult.data.calculation_version })}
            </p>
            <ExportCsvButton
              filters={filters}
              orderCount={view === "all" ? listResult.data.total : undefined}
            />
          </div>

          {"excluded_order_count" in listResult.data ? (
            <Alert variant="info" title={t("ordVarianceTitle")}>
              {t(
                listResult.data.excluded_order_count === 1
                  ? "ordVarianceBodyOne"
                  : "ordVarianceBodyMany",
                { count: listResult.data.excluded_order_count },
              )}
            </Alert>
          ) : null}

          <div className="panel overflow-hidden">
            <IntelligenceOrdersTable
              items={listResult.data.items}
              emptyTitle={view === "variance" ? t("ordNoComparable") : t("intNoOrdersMatch")}
              emptyDescription={
                view === "variance" ? t("ordNoComparableDesc") : t("intNoOrdersMatchDesc")
              }
            />
          </div>

          <Pager
            basePath={BASE}
            total={listResult.data.total}
            limit={listResult.data.limit}
            offset={listResult.data.offset}
            params={{ ...tabParams, view: view === "variance" ? view : null }}
            noun="order"
          />
        </>
      )}
    </div>
  );
}

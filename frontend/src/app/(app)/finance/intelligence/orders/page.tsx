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
  INTELLIGENCE_ANALYSIS_NOTICE,
  intelligenceQuery,
  parseIntelligenceFilters,
  type CostVarianceList,
  type IntelligenceFilterOptions,
  type IntelligenceSummary,
  type OrderIntelligenceList,
} from "@/lib/finance/intelligence";
import { formatDate, withQuery } from "@/lib/trade/format";

export const dynamic = "force-dynamic";
export const metadata = { title: "Order profitability" };

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
        eyebrow="Finance · Stage 5E"
        back={{ href: "/finance/intelligence", label: "Intelligence" }}
        meta={
          <div className="flex flex-wrap items-center gap-2">
            <Badge variant="secondary">Operational analysis</Badge>
            <Badge variant="outline">Read-only</Badge>
          </div>
        }
        title="Order profitability"
        description="Every accepted order with its estimated, committed and documented position, per currency."
        actions={
          <div className="flex flex-wrap gap-2">
            <Button asChild size="sm" variant="outline">
              <Link href="/finance/intelligence/exceptions">Exceptions</Link>
            </Button>
          </div>
        }
      />

      <Alert variant="info" title="Operational figures">
        {INTELLIGENCE_ANALYSIS_NOTICE}
      </Alert>

      {!optionsResult.ok ? (
        <ApiErrorAlert title="Filter options unavailable" failure={optionsResult} />
      ) : null}

      <div className="panel flex flex-wrap items-center gap-2 px-3 py-2">
        {(
          [
            ["all", "All orders"],
            ["variance", "Cost variance"],
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
        <ApiErrorAlert title="Order profitability unavailable" failure={listResult} />
      ) : (
        <>
          <div className="flex flex-wrap items-start justify-between gap-3">
            <p className="text-[11px] text-mist-500">
              {"as_of" in listResult.data ? `As of ${formatDate(listResult.data.as_of)} · ` : ""}
              calculation {listResult.data.calculation_version}
            </p>
            <ExportCsvButton
              filters={filters}
              orderCount={view === "all" ? listResult.data.total : undefined}
            />
          </div>

          {"excluded_order_count" in listResult.data ? (
            <Alert variant="info" title="Variance needs two complete bases">
              A variance exists only where both the landed-cost estimate and the documented basis
              are complete. {listResult.data.excluded_order_count} order
              {listResult.data.excluded_order_count === 1 ? " is" : "s are"} excluded because one
              side is incomplete; quoted costs are never presented as variance.
            </Alert>
          ) : null}

          <div className="panel overflow-hidden">
            <IntelligenceOrdersTable
              items={listResult.data.items}
              emptyTitle={view === "variance" ? "No comparable orders" : "No orders match"}
              emptyDescription={
                view === "variance"
                  ? "No order in this range has both a complete estimate and a complete documented basis."
                  : "No accepted orders fall inside the selected range and filters."
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

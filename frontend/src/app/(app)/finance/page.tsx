import Link from "next/link";

import { FinanceFilters } from "@/components/finance/filters";
import { FinanceOverview } from "@/components/finance/overview";
import { FinanceAccountsTable, FinanceAgingTable } from "@/components/finance/tables";
import { Alert } from "@/components/ui/alert";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { EmptyState } from "@/components/ui/empty-state";
import { PageHeader } from "@/components/ui/page-header";
import { serverGet } from "@/lib/api/server";
import { loadSession } from "@/lib/auth/session";
import {
  parseFinanceView,
  type FinanceAccounts,
  type FinanceAging,
  type FinanceStatus,
  type FinanceSummary,
} from "@/lib/finance/types";
import { getServerT, titleFor, type ServerTranslator } from "@/lib/i18n/server";
import { formatDate, withQuery } from "@/lib/trade/format";

export const dynamic = "force-dynamic";
export const generateMetadata = () => titleFor("finTitle");

const PAGE_SIZE = 25;

interface FinanceSearchParams {
  view?: string;
  currency?: string;
  from?: string;
  to?: string;
  as_of?: string;
  offset?: string;
}

function financeCode(details: unknown): string | null {
  if (typeof details !== "object" || details === null) return null;
  const value = (details as Record<string, unknown>).finance_code;
  return typeof value === "string" ? value : null;
}

function errorAlert(
  t: ServerTranslator["t"],
  title: string,
  failure: { code: string; message: string; requestId: string | null; details: unknown },
) {
  const code = financeCode(failure.details);
  return (
    <Alert variant="danger" title={title}>
      <span>{failure.message}</span>
      <span className="mt-1 block font-mono text-[10px] text-mist-500">
        {failure.code}
        {code ? ` · ${t("finFinanceCodeSuffix", { code })}` : ""}
        {failure.requestId ? ` · ${t("finRequestSuffix", { id: failure.requestId })}` : ""}
      </span>
    </Alert>
  );
}

export default async function FinancePage({
  searchParams,
}: {
  searchParams: Promise<FinanceSearchParams>;
}) {
  const state = await loadSession();
  if (state.status !== "authenticated") return null;
  const { t, locale } = await getServerT();

  const params = await searchParams;
  const view = parseFinanceView(params.view);
  const statusResult = await serverGet<FinanceStatus>("/finance/status");

  if (!statusResult.ok) {
    return (
      <div className="mx-auto max-w-[1360px] space-y-5">
        <PageHeader
          eyebrow={t("finEyebrow")}
          title={t("finTitle")}
          description={t("finStatusHint")}
        />
        {errorAlert(t, t("finStatusUnavailableTitle"), statusResult)}
      </div>
    );
  }

  const status = statusResult.data;
  const canRead = status.state === "connected" || status.state === "degraded";
  const currencies = status.available_currencies ?? [];
  const requested = (params.currency ?? "").toUpperCase();
  const currency = currencies.includes(requested)
    ? requested
    : currencies.length === 1
      ? currencies[0]
      : "";
  const fromDate = params.from ?? "";
  const toDate = params.to ?? "";
  const asOf = params.as_of ?? "";
  const offset = Math.max(0, Number.parseInt(params.offset ?? "0", 10) || 0);

  const canFetch = canRead && (currencies.length <= 1 || currency !== "");
  const summaryPath = `/finance/summary${currency ? `?currency=${encodeURIComponent(currency)}` : ""}`;
  const detailPath = (() => {
    if (!canFetch) return null;
    if (view === "accounts") {
      const query = new URLSearchParams({
        limit: String(PAGE_SIZE),
        offset: String(offset),
      });
      if (currency) query.set("currency", currency);
      if (fromDate) query.set("from", fromDate);
      if (toDate) query.set("to", toDate);
      return `/finance/accounts?${query.toString()}`;
    }
    if (view === "receivables" || view === "payables") {
      const query = new URLSearchParams({
        type: view === "receivables" ? "receivable" : "payable",
        limit: String(PAGE_SIZE),
        offset: String(offset),
      });
      if (currency) query.set("currency", currency);
      if (asOf) query.set("as_of", asOf);
      return `/finance/aging?${query.toString()}`;
    }
    return null;
  })();

  const [summaryResult, detailResult] = await Promise.all([
    canFetch ? serverGet<FinanceSummary>(summaryPath) : Promise.resolve(null),
    detailPath ? serverGet<FinanceAccounts | FinanceAging>(detailPath) : Promise.resolve(null),
  ]);

  const summary = summaryResult?.ok ? summaryResult.data : null;
  const tabParams = {
    currency: currency || null,
    from: fromDate || null,
    to: toDate || null,
    as_of: asOf || null,
  };
  const tabLabels = {
    overview: t("finTabOverview"),
    accounts: t("finTabAccounts"),
    receivables: t("finTabReceivables"),
    payables: t("finTabPayables"),
  } as const;

  return (
    <div className="mx-auto max-w-[1360px] space-y-5">
      <PageHeader
        eyebrow={t("finEyebrow")}
        meta={
          <>
            <Badge variant="secondary">{t("finReadOnlyBadge")}</Badge>
            <span className="font-mono text-[10px] text-mist-600">
              {t("finDataThrough", { date: formatDate(status.data_through ?? null, locale) })}
            </span>
          </>
        }
        title={t("finTitle")}
        description={t("finDescription")}
        actions={
          <div className="flex flex-wrap gap-2">
            <Button asChild size="sm">
              <Link href="/finance/reconciliation">{t("finBtnReconciliation")}</Link>
            </Button>
            <Button asChild variant="outline" size="sm">
              <Link href="/finance/discrepancies">{t("finBtnDiscrepancies")}</Link>
            </Button>
            <Button asChild variant="outline" size="sm">
              <Link href="/finance/intelligence">{t("finBtnIntelligence")}</Link>
            </Button>
            <Button asChild variant="ghost" size="sm">
              <Link href="/">{t("finBackCommand")}</Link>
            </Button>
          </div>
        }
      />

      {status.state === "degraded" ? (
        <Alert variant="warning" title={t("finDegradedTitle")}>
          {t("finDegradedBody", { detail: status.detail })}
        </Alert>
      ) : null}
      {status.state === "not_configured" ? (
        <Alert variant="info" title={t("finNotConfiguredTitle")}>
          {t("finNotConfiguredBody")}
          <span className="mt-1 block font-mono text-[10.5px] text-mist-400">
            python -m app.cli finance-map set --company &quot;…&quot; --finance-company … --actor …
          </span>
        </Alert>
      ) : null}
      {status.state === "disabled" ? (
        <Alert variant="info" title={t("finDisabledTitle")}>
          {t("finDisabledBody")}
        </Alert>
      ) : null}
      {status.state === "auth_error" ? (
        <Alert variant="danger" title={t("finStAuthError")}>
          {t("finAuthErrorBody")}
        </Alert>
      ) : null}
      {status.state === "unavailable" ? (
        <Alert variant="danger" title={t("finStUnavailable")}>
          {t("finUnavailableBody")}
        </Alert>
      ) : null}

      <div className="panel flex flex-wrap items-center gap-2 px-3 py-2">
        {(["overview", "accounts", "receivables", "payables"] as const).map((tab) => (
          <Link
            key={tab}
            href={withQuery("/finance", { ...tabParams, view: tab })}
            className={
              view === tab
                ? "rounded-md bg-accent-400/10 px-3 py-1.5 text-[11.5px] text-accent-200"
                : "rounded-md px-3 py-1.5 text-[11.5px] text-mist-500 hover:bg-white/[0.04] hover:text-mist-200"
            }
          >
            {tabLabels[tab]}
          </Link>
        ))}
        {canRead ? (
          <div className="ml-auto">
            <FinanceFilters
              currencies={currencies}
              view={view}
              currency={currency}
              fromDate={fromDate}
              toDate={toDate}
              asOf={asOf}
            />
          </div>
        ) : null}
      </div>

      {canRead && currencies.length > 1 && !currency ? (
        <Alert variant="info" title={t("finSelectOneTitle")}>
          {t("finSelectOneBody", { currencies: currencies.join(", ") })}
        </Alert>
      ) : null}

      {summaryResult && !summaryResult.ok
        ? errorAlert(t, t("finSummaryUnavailable"), summaryResult)
        : null}

      {view === "overview" ? <FinanceOverview status={status} summary={summary} /> : null}

      {view === "accounts" ? (
        detailResult && !detailResult.ok ? (
          errorAlert(t, t("finAccountsUnavailable"), detailResult)
        ) : detailResult && detailResult.ok ? (
          <div className="space-y-3">
            <FinanceAccountsTable data={detailResult.data as FinanceAccounts} />
            <Pager
              t={t}
              page={(detailResult.data as FinanceAccounts).page}
              offset={offset}
              params={{ ...tabParams, view }}
            />
          </div>
        ) : (
          <EmptyState title={t("finSelectCurrency")} description={t("finAccountsSelectHint")} />
        )
      ) : null}

      {view === "receivables" || view === "payables" ? (
        detailResult && !detailResult.ok ? (
          errorAlert(t, t("finAgingUnavailable"), detailResult)
        ) : detailResult && detailResult.ok ? (
          <div className="space-y-3">
            <FinanceAgingTable data={detailResult.data as FinanceAging} />
            <Pager
              t={t}
              page={(detailResult.data as FinanceAging).page}
              offset={offset}
              params={{ ...tabParams, view }}
            />
          </div>
        ) : (
          <EmptyState title={t("finSelectCurrency")} description={t("finAgingSelectHint")} />
        )
      ) : null}
    </div>
  );
}

function Pager({
  t,
  page,
  offset,
  params,
}: {
  t: ServerTranslator["t"];
  page: { total: number; next_offset?: number | null; limit: number };
  offset: number;
  params: Record<string, string | null>;
}) {
  const previous = offset > 0 ? Math.max(0, offset - page.limit) : null;
  return (
    <div className="flex items-center justify-between gap-3 text-[10.5px] text-mist-500">
      <span>{t(page.total === 1 ? "finRowOne" : "finRowMany", { count: page.total, offset })}</span>
      <div className="flex items-center gap-2">
        {previous !== null ? (
          <Link
            href={withQuery("/finance", { ...params, offset: String(previous) })}
            className="rounded border border-white/10 px-2.5 py-1 hover:text-mist-200"
          >
            {t("pagePrevious")}
          </Link>
        ) : null}
        {page.next_offset !== null ? (
          <Link
            href={withQuery("/finance", { ...params, offset: String(page.next_offset) })}
            className="rounded border border-white/10 px-2.5 py-1 hover:text-mist-200"
          >
            {t("pageNext")}
          </Link>
        ) : null}
      </div>
    </div>
  );
}

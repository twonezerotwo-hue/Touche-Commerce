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
import { formatDate, withQuery } from "@/lib/trade/format";

export const dynamic = "force-dynamic";
export const metadata = { title: "Finance" };

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
  title: string,
  failure: { code: string; message: string; requestId: string | null; details: unknown },
) {
  const code = financeCode(failure.details);
  return (
    <Alert variant="danger" title={title}>
      <span>{failure.message}</span>
      <span className="mt-1 block font-mono text-[10px] text-mist-500">
        {failure.code}
        {code ? ` · Finance: ${code}` : ""}
        {failure.requestId ? ` · request ${failure.requestId}` : ""}
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

  const params = await searchParams;
  const view = parseFinanceView(params.view);
  const statusResult = await serverGet<FinanceStatus>("/finance/status");

  if (!statusResult.ok) {
    return (
      <div className="mx-auto max-w-[1360px] space-y-5">
        <PageHeader
          eyebrow="Finance"
          title="Finance"
          description="Read-only TOUCHE FINANCE data for this company."
        />
        {errorAlert("Finance status unavailable", statusResult)}
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

  return (
    <div className="mx-auto max-w-[1360px] space-y-5">
      <PageHeader
        eyebrow="Finance"
        meta={
          <>
            <Badge variant="secondary">Read-only</Badge>
            <span className="font-mono text-[10px] text-mist-600">
              data through {formatDate(status.data_through ?? null)}
            </span>
          </>
        }
        title="Finance"
        description="Financial truth stays in TOUCHE FINANCE. This workspace reads a mapped company through the authenticated integration contract; it never posts an invoice, payment or journal entry."
        actions={
          <Button asChild variant="outline" size="sm">
            <Link href="/">Back to Command Center</Link>
          </Button>
        }
      />

      {status.state === "degraded" ? (
        <Alert variant="warning" title="Finance reports degraded data">
          {status.detail} Treat the data-through date as the source watermark, not today&apos;s
          date.
        </Alert>
      ) : null}
      {status.state === "not_configured" ? (
        <Alert variant="info" title="Not configured">
          An authorised company admin must configure an explicit Finance mapping. No company is
          matched by name:
          <span className="mt-1 block font-mono text-[10.5px] text-mist-400">
            python -m app.cli finance-map set --company &quot;…&quot; --finance-company … --actor …
          </span>
        </Alert>
      ) : null}
      {status.state === "disabled" ? (
        <Alert variant="info" title="Integration disabled">
          Finance integration is disabled by configuration. No network request was made.
        </Alert>
      ) : null}
      {status.state === "auth_error" ? (
        <Alert variant="danger" title="AUTH_ERROR">
          Finance rejected or could not verify the server-side service credentials. No credential
          value is exposed here.
        </Alert>
      ) : null}
      {status.state === "unavailable" ? (
        <Alert variant="danger" title="UNAVAILABLE">
          Finance is not reachable or the Finance ledger is temporarily unavailable.
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
            {tab === "overview"
              ? "Overview"
              : tab === "accounts"
                ? "Accounts"
                : tab === "receivables"
                  ? "Receivables"
                  : "Payables"}
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
        <Alert variant="info" title="Select one currency">
          This Finance company has {currencies.join(", ")} ledgers. Commerce does not convert or
          aggregate them; choose one currency above to load a single-currency view.
        </Alert>
      ) : null}

      {summaryResult && !summaryResult.ok
        ? errorAlert("Finance summary unavailable", summaryResult)
        : null}

      {view === "overview" ? <FinanceOverview status={status} summary={summary} /> : null}

      {view === "accounts" ? (
        detailResult && !detailResult.ok ? (
          errorAlert("Finance accounts unavailable", detailResult)
        ) : detailResult && detailResult.ok ? (
          <div className="space-y-3">
            <FinanceAccountsTable data={detailResult.data as FinanceAccounts} />
            <Pager
              page={(detailResult.data as FinanceAccounts).page}
              offset={offset}
              params={{ ...tabParams, view }}
            />
          </div>
        ) : (
          <EmptyState
            title="Select a currency"
            description="Finance accounts are shown one currency at a time."
          />
        )
      ) : null}

      {view === "receivables" || view === "payables" ? (
        detailResult && !detailResult.ok ? (
          errorAlert("Finance aging unavailable", detailResult)
        ) : detailResult && detailResult.ok ? (
          <div className="space-y-3">
            <FinanceAgingTable data={detailResult.data as FinanceAging} />
            <Pager
              page={(detailResult.data as FinanceAging).page}
              offset={offset}
              params={{ ...tabParams, view }}
            />
          </div>
        ) : (
          <EmptyState
            title="Select a currency"
            description="Finance aging is shown one currency at a time."
          />
        )
      ) : null}
    </div>
  );
}

function Pager({
  page,
  offset,
  params,
}: {
  page: { total: number; next_offset?: number | null; limit: number };
  offset: number;
  params: Record<string, string | null>;
}) {
  const previous = offset > 0 ? Math.max(0, offset - page.limit) : null;
  return (
    <div className="flex items-center justify-between gap-3 text-[10.5px] text-mist-500">
      <span>
        {page.total} row{page.total === 1 ? "" : "s"} · offset {offset}
      </span>
      <div className="flex items-center gap-2">
        {previous !== null ? (
          <Link
            href={withQuery("/finance", { ...params, offset: String(previous) })}
            className="rounded border border-white/10 px-2.5 py-1 hover:text-mist-200"
          >
            Previous
          </Link>
        ) : null}
        {page.next_offset !== null ? (
          <Link
            href={withQuery("/finance", { ...params, offset: String(page.next_offset) })}
            className="rounded border border-white/10 px-2.5 py-1 hover:text-mist-200"
          >
            Next
          </Link>
        ) : null}
      </div>
    </div>
  );
}

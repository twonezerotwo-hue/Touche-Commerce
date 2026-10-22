import Link from "next/link";

import { DiscrepancyQueue } from "@/components/finance/discrepancy-queue";
import { Alert } from "@/components/ui/alert";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { PageHeader } from "@/components/ui/page-header";
import { Select } from "@/components/ui/select";
import { serverGet } from "@/lib/api/server";
import { loadSession } from "@/lib/auth/session";
import type { FinanceStatus } from "@/lib/finance/types";
import type { ReconciliationDiscrepancyList } from "@/lib/finance/reconciliation";

export const dynamic = "force-dynamic";
export const metadata = { title: "Discrepancies" };

const PAGE_SIZE = 50;
const STATUSES = ["OPEN", "RESOLVED", "DISMISSED"] as const;
const SEVERITIES = ["BLOCKING", "ERROR", "WARNING", "INFO"] as const;
const CODES = [
  "MISSING_EVIDENCE",
  "MISSING_FINANCE_REFERENCE",
  "AMOUNT_MISMATCH",
  "CURRENCY_MISMATCH",
  "DUPLICATE_REFERENCE",
  "INCOMPLETE_COSTS",
  "UNMATCHED_FINANCE_ITEM",
  "SOURCE_STALE",
  "COMPANY_MAPPING_INVALID",
  "MANUAL_REVIEW_REQUIRED",
] as const;

interface SearchParams {
  status?: string;
  severity?: string;
  code?: string;
  currency?: string;
  offset?: string;
}

export default async function DiscrepanciesPage({
  searchParams,
}: {
  searchParams: Promise<SearchParams>;
}) {
  const state = await loadSession();
  if (state.status !== "authenticated") return null;
  const params = await searchParams;
  const permissions = state.session.session.company?.permissions ?? [];
  const canReview = permissions.includes("finance.reconcile");
  const offset = Math.max(0, Number.parseInt(params.offset ?? "0", 10) || 0);

  const statusResult = await serverGet<FinanceStatus>("/finance/status");
  const currencies = statusResult.ok ? (statusResult.data.available_currencies ?? []) : [];
  const requested = (params.currency ?? "").toUpperCase();
  const currency = currencies.includes(requested)
    ? requested
    : currencies.length === 1
      ? currencies[0]
      : "";

  const query = new URLSearchParams({
    limit: String(PAGE_SIZE),
    offset: String(offset),
  });
  if (params.status) query.set("status", params.status);
  if (params.severity) query.set("severity", params.severity);
  if (params.code) query.set("code", params.code);
  if (currency) query.set("currency", currency);
  const result = await serverGet<ReconciliationDiscrepancyList>(
    `/finance/discrepancies?${query.toString()}`,
  );

  const filters = {
    status: params.status ?? "",
    severity: params.severity ?? "",
    code: params.code ?? "",
    currency,
  };

  return (
    <div className="mx-auto max-w-[1360px] space-y-5">
      <PageHeader
        eyebrow="Finance · Stage 5D"
        back={{ href: "/finance/reconciliation", label: "Reconciliation" }}
        meta={<Badge variant="secondary">Exception queue</Badge>}
        title="Discrepancies"
        description="Deterministic evidence gaps, amount and currency differences, duplicates and stale data. Resolving an item does not change Finance."
        actions={
          <div className="flex flex-wrap gap-2">
            <Button asChild size="sm" variant="outline">
              <Link href="/finance/reconciliation">Reconciliation runs</Link>
            </Button>
            <Button asChild size="sm" variant="ghost">
              <Link href="/finance">Finance ledger</Link>
            </Button>
          </div>
        }
      />

      <div className="panel flex flex-wrap items-end gap-2 px-4 py-3">
        <form
          action="/finance/discrepancies"
          method="get"
          className="flex flex-wrap items-end gap-2"
        >
          <div className="space-y-1">
            <label htmlFor="discrepancy-status" className="eyebrow">
              Status
            </label>
            <Select
              id="discrepancy-status"
              name="status"
              defaultValue={filters.status}
              className="h-8 w-[140px] text-[12px]"
            >
              <option value="">All</option>
              {STATUSES.map((value) => (
                <option key={value} value={value}>
                  {value}
                </option>
              ))}
            </Select>
          </div>
          <div className="space-y-1">
            <label htmlFor="discrepancy-severity" className="eyebrow">
              Severity
            </label>
            <Select
              id="discrepancy-severity"
              name="severity"
              defaultValue={filters.severity}
              className="h-8 w-[140px] text-[12px]"
            >
              <option value="">All</option>
              {SEVERITIES.map((value) => (
                <option key={value} value={value}>
                  {value}
                </option>
              ))}
            </Select>
          </div>
          <div className="space-y-1">
            <label htmlFor="discrepancy-code" className="eyebrow">
              Code
            </label>
            <Select
              id="discrepancy-code"
              name="code"
              defaultValue={filters.code}
              className="h-8 w-[230px] text-[12px]"
            >
              <option value="">All codes</option>
              {CODES.map((value) => (
                <option key={value} value={value}>
                  {value}
                </option>
              ))}
            </Select>
          </div>
          {currencies.length > 1 ? (
            <div className="space-y-1">
              <label htmlFor="discrepancy-currency" className="eyebrow">
                Currency
              </label>
              <Select
                id="discrepancy-currency"
                name="currency"
                defaultValue={currency}
                className="h-8 w-[120px] text-[12px]"
              >
                <option value="">All</option>
                {currencies.map((value) => (
                  <option key={value} value={value}>
                    {value}
                  </option>
                ))}
              </Select>
            </div>
          ) : null}
          <Button type="submit" size="sm" variant="subtle">
            Apply
          </Button>
          {filters.status || filters.severity || filters.code ? (
            <Button asChild size="sm" variant="ghost">
              <Link href="/finance/discrepancies">Clear</Link>
            </Button>
          ) : null}
        </form>
        <span className="ml-auto text-[10px] text-mist-600">
          {canReview
            ? "You can resolve items with finance.reconcile."
            : "Read-only: resolving needs finance.reconcile."}
        </span>
      </div>

      {!result.ok ? (
        <Alert variant="danger" title="Discrepancies unavailable">
          {result.message}
        </Alert>
      ) : (
        <div className="panel overflow-hidden">
          <div className="px-4 py-3 text-[10.5px] text-mist-500">
            {result.data.total} finding{result.data.total === 1 ? "" : "s"} · offset {offset}
          </div>
          <div className="hairline" />
          <DiscrepancyQueue
            items={result.data.items}
            csrfToken={state.session.session.csrf_token}
            canReview={canReview}
          />
        </div>
      )}
    </div>
  );
}

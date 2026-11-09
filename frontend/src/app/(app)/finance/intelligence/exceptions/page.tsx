import Link from "next/link";

import { ApiErrorAlert } from "@/components/finance/api-error-alert";
import { IntelligenceExceptionsTable } from "@/components/finance/intelligence-exceptions";
import { Pager } from "@/components/finance/pager";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { PageHeader } from "@/components/ui/page-header";
import { Select } from "@/components/ui/select";
import { serverGet } from "@/lib/api/server";
import { loadSession } from "@/lib/auth/session";
import type { FinancialExceptionList } from "@/lib/finance/intelligence";
import { exceptionCodeWord } from "@/lib/finance/intelligence-text";
import { getServerT, titleFor } from "@/lib/i18n/server";
import { discrepancyStatusText, severityText } from "@/lib/i18n/value-labels";

export const dynamic = "force-dynamic";
export const generateMetadata = () => titleFor("exTitle");

const BASE = "/finance/intelligence/exceptions";
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

const DATE_PATTERN = /^\d{4}-\d{2}-\d{2}$/;
const UUID_PATTERN = /^[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}$/i;

type Params = Record<string, string | string[] | undefined>;

function one(params: Params, key: string): string | undefined {
  const value = params[key];
  return (Array.isArray(value) ? value[0] : value)?.trim();
}

function oneOf<T extends string>(value: string | undefined, allowed: readonly T[]): T | "" {
  const upper = value?.toUpperCase();
  return allowed.find((item) => item === upper) ?? "";
}

export default async function FinancialExceptionsPage({
  searchParams,
}: {
  searchParams: Promise<Params>;
}) {
  const state = await loadSession();
  if (state.status !== "authenticated") return null;

  const { t, locale } = await getServerT();
  const params = await searchParams;
  const permissions = state.session.session.company?.permissions ?? [];
  const canReview = permissions.includes("finance.reconcile");
  const rawOffset = one(params, "offset");
  const offset = Math.max(0, Number.parseInt(rawOffset ?? "0", 10) || 0);

  // No status means open items; "ALL" lifts the status filter (the API reads "" as every status).
  const statusParam = one(params, "status")?.toUpperCase();
  const status = statusParam === "ALL" ? "" : (STATUSES.find((v) => v === statusParam) ?? "OPEN");
  const severity = oneOf(one(params, "severity"), SEVERITIES);
  const code = oneOf(one(params, "code"), CODES);
  const currencyRaw = one(params, "currency") ?? "";
  const currency = /^[A-Za-z]{3}$/.test(currencyRaw) ? currencyRaw.toUpperCase() : "";
  const orderRaw = one(params, "order_id") ?? "";
  const orderId = UUID_PATTERN.test(orderRaw) ? orderRaw.toLowerCase() : "";
  const fromRaw = one(params, "from") ?? "";
  const toRaw = one(params, "to") ?? "";
  const from = DATE_PATTERN.test(fromRaw) ? fromRaw : "";
  const to = DATE_PATTERN.test(toRaw) ? toRaw : "";

  const query = new URLSearchParams({ limit: String(PAGE_SIZE), offset: String(offset) });
  query.set("status", status);
  if (severity) query.set("severity", severity);
  if (code) query.set("code", code);
  if (currency) query.set("currency", currency);
  if (orderId) query.set("order_id", orderId);
  if (from) query.set("from", from);
  if (to) query.set("to", to);

  const result = await serverGet<FinancialExceptionList>(
    `/finance/intelligence/exceptions?${query.toString()}`,
  );

  const pagerParams = {
    status: status === "" ? "ALL" : status,
    severity,
    code,
    currency,
    order_id: orderId,
    from,
    to,
  };
  const filtered = Boolean(
    status !== "OPEN" || severity || code || currency || orderId || from || to,
  );

  return (
    <div className="mx-auto max-w-[1360px] space-y-5">
      <PageHeader
        eyebrow={t("intEyebrow")}
        back={{ href: "/finance/intelligence", label: t("intBackIntelligence") }}
        meta={<Badge variant="secondary">{t("exBadge")}</Badge>}
        title={t("exTitle")}
        description={t("exDescription")}
        actions={
          <div className="flex flex-wrap gap-2">
            <Button asChild size="sm" variant="outline">
              <Link href="/finance/intelligence/orders">{t("exBtnOrders")}</Link>
            </Button>
            <Button asChild size="sm" variant="ghost">
              <Link href="/finance/discrepancies">{t("exBtnQueue")}</Link>
            </Button>
          </div>
        }
      />

      <form action={BASE} method="get" className="panel flex flex-wrap items-end gap-2 px-4 py-3">
        <div className="space-y-1">
          <label htmlFor="exception-status" className="eyebrow block">
            {t("exStatus")}
          </label>
          <Select
            id="exception-status"
            name="status"
            defaultValue={status === "" ? "ALL" : status}
            className="h-8 w-[140px] text-[12px]"
          >
            <option value="ALL">{t("exAll")}</option>
            {STATUSES.map((value) => (
              <option key={value} value={value}>
                {discrepancyStatusText(t, value)}
              </option>
            ))}
          </Select>
        </div>
        <div className="space-y-1">
          <label htmlFor="exception-severity" className="eyebrow block">
            {t("exSeverity")}
          </label>
          <Select
            id="exception-severity"
            name="severity"
            defaultValue={severity}
            className="h-8 w-[140px] text-[12px]"
          >
            <option value="">{t("exAll")}</option>
            {SEVERITIES.map((value) => (
              <option key={value} value={value}>
                {severityText(t, value)}
              </option>
            ))}
          </Select>
        </div>
        <div className="space-y-1">
          <label htmlFor="exception-code" className="eyebrow block">
            {t("exCode")}
          </label>
          <Select
            id="exception-code"
            name="code"
            defaultValue={code}
            className="h-8 w-[230px] text-[12px]"
          >
            <option value="">{t("exAllCodes")}</option>
            {CODES.map((value) => (
              <option key={value} value={value}>
                {exceptionCodeWord(t, locale, value)}
              </option>
            ))}
          </Select>
        </div>
        <div className="space-y-1">
          <label htmlFor="exception-currency" className="eyebrow block">
            {t("exCurrency")}
          </label>
          <Input
            id="exception-currency"
            name="currency"
            defaultValue={currency}
            maxLength={3}
            placeholder={t("exAnyPlaceholder")}
            className="h-8 w-[80px] text-[12px] uppercase"
          />
        </div>
        <div className="space-y-1">
          <label htmlFor="exception-from" className="eyebrow block">
            {t("exFrom")}
          </label>
          <Input
            id="exception-from"
            name="from"
            type="date"
            defaultValue={from}
            className="h-8 w-[145px] text-[12px]"
          />
        </div>
        <div className="space-y-1">
          <label htmlFor="exception-to" className="eyebrow block">
            {t("exTo")}
          </label>
          <Input
            id="exception-to"
            name="to"
            type="date"
            defaultValue={to}
            className="h-8 w-[145px] text-[12px]"
          />
        </div>
        {orderId ? <input type="hidden" name="order_id" value={orderId} /> : null}
        <Button type="submit" size="sm" variant="subtle">
          {t("intApply")}
        </Button>
        {filtered ? (
          <Button asChild size="sm" variant="ghost">
            <Link href={BASE}>{t("intClear")}</Link>
          </Button>
        ) : null}
        <span className="ml-auto text-[10px] text-mist-600">
          {canReview ? t("exCanResolve") : t("exCannotResolve")}
        </span>
      </form>

      {!result.ok ? (
        <ApiErrorAlert title={t("exUnavailable")} failure={result} />
      ) : (
        <div className="space-y-3">
          <div className="panel overflow-hidden">
            <div className="px-4 py-3 text-[10.5px] text-mist-500">
              {t(result.data.total === 1 ? "exCountOne" : "exCountMany", {
                count: result.data.total,
              })}
            </div>
            <div className="hairline" />
            <IntelligenceExceptionsTable
              items={result.data.items}
              csrfToken={state.session.session.csrf_token}
              canReview={canReview}
            />
          </div>
          <Pager
            basePath={BASE}
            total={result.data.total}
            limit={result.data.limit}
            offset={result.data.offset}
            params={pagerParams}
            noun="exception"
          />
        </div>
      )}
    </div>
  );
}

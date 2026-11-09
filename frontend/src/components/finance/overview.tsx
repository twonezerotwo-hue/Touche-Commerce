"use client";

import { Banknote, Building2, Coins, Database, Landmark, ReceiptText } from "lucide-react";

import { FinanceStatusBadge } from "@/components/finance/status-badge";
import {
  Card,
  CardContent,
  CardDescription,
  CardHeader,
  CardHeading,
  CardTitle,
} from "@/components/ui/card";
import { Stat } from "@/components/ui/stat";
import { formatFinanceMoney } from "@/lib/finance/format";
import type { FinanceStatus, FinanceSummary } from "@/lib/finance/types";
import { useLocale } from "@/lib/i18n/locale-provider";
import { formatDate, formatTimestamp } from "@/lib/trade/format";

export interface FinanceOverviewProps {
  status: FinanceStatus;
  summary: FinanceSummary | null;
}

/** Read-only Finance truth, including every state in which data is not current. */
export function FinanceOverview({ status, summary }: FinanceOverviewProps) {
  const { t, locale } = useLocale();
  const mapping = status.mapping;
  const currencies = status.available_currencies ?? [];
  const currency = summary?.currency ?? null;
  const money = (value: { amount: string } | undefined): string =>
    value ? formatFinanceMoney(value, currency, locale) : "—";
  return (
    <div className="space-y-4">
      <Card>
        <CardHeader>
          <CardHeading>
            <div className="flex flex-wrap items-center gap-2">
              <CardTitle>{t("finConnection")}</CardTitle>
              <FinanceStatusBadge state={status.state} />
            </div>
            <CardDescription>{status.detail}</CardDescription>
          </CardHeading>
          <p className="font-mono text-[10px] whitespace-nowrap text-mist-600">
            {t("finCheckedAt", { time: formatTimestamp(status.checked_at, locale) })}
          </p>
        </CardHeader>
        <CardContent className="grid gap-x-6 gap-y-4 sm:grid-cols-2 lg:grid-cols-4">
          <div>
            <p className="eyebrow flex items-center gap-1.5">
              <Building2 className="size-3" aria-hidden /> {t("finMappedCompany")}
            </p>
            <p className="mt-1 text-[12.5px] text-mist-200">
              {mapping?.finance_company_name ??
                mapping?.finance_company_id ??
                t("finNotConfiguredTitle")}
            </p>
            {mapping?.finance_company_id ? (
              <p className="mt-0.5 font-mono text-[10px] text-mist-600">
                {mapping.finance_company_id}
              </p>
            ) : null}
          </div>
          <div>
            <p className="eyebrow flex items-center gap-1.5">
              <Coins className="size-3" aria-hidden /> {t("finCurrencies")}
            </p>
            <p className="mt-1 text-[12.5px] text-mist-200">
              {currencies.length > 0 ? currencies.join(" · ") : t("finNotReported")}
            </p>
            <p className="mt-0.5 text-[10px] text-mist-600">{t("finOneCurrencyNote")}</p>
          </div>
          <div>
            <p className="eyebrow flex items-center gap-1.5">
              <Database className="size-3" aria-hidden /> {t("finDataThroughLabel")}
            </p>
            <p className="mt-1 text-[12.5px] text-mist-200">
              {formatDate(status.data_through ?? null, locale)}
            </p>
            <p className="mt-0.5 text-[10px] text-mist-600">{t("finWatermark")}</p>
          </div>
          <div>
            <p className="eyebrow flex items-center gap-1.5">
              <Landmark className="size-3" aria-hidden /> {t("finHealth")}
            </p>
            <p className="mt-1 text-[12.5px] text-mist-200">
              {status.finance_status ?? t("finNotReported")}
            </p>
            <p className="mt-0.5 text-[10px] text-mist-600">
              {t("finLatency", { ms: status.latency_ms.toFixed(1) })}
            </p>
          </div>
        </CardContent>
      </Card>

      {summary ? (
        <div className="grid gap-3 sm:grid-cols-2 xl:grid-cols-3">
          <Stat
            label={t("finCash")}
            value={money(summary.balances.cash)}
            detail={t("finCashDetail", { count: summary.ledger.document_count })}
            icon={<Banknote className="size-4" aria-hidden />}
          />
          <Stat
            label={t("finReceivables")}
            value={money(summary.balances.receivables)}
            detail={t("finReceivablesDetail", { count: summary.ledger.line_count })}
            icon={<ReceiptText className="size-4" aria-hidden />}
            tone="jade"
          />
          <Stat
            label={t("finPayables")}
            value={money(summary.balances.payables)}
            detail={t("finPayablesDetail", { date: formatDate(summary.as_of ?? null, locale) })}
            icon={<ReceiptText className="size-4" aria-hidden />}
            tone="amber"
          />
          <Stat
            label={t("finRevenue")}
            value={money(summary.balances.revenue)}
            detail={t("finRevenueDetail")}
          />
          <Stat
            label={t("finCost")}
            value={money(summary.balances.cost)}
            detail={t("finCostDetail")}
          />
          <Stat
            label={t("finGrossProfit")}
            value={money(summary.balances.gross_profit)}
            detail={t("finGrossProfitDetail")}
            tone="jade"
          />
        </div>
      ) : (
        <Card variant="inset">
          <CardContent className="py-4 text-[12px] text-mist-400">{t("finNoSummary")}</CardContent>
        </Card>
      )}

      <div className="panel px-4 py-3 text-[11px] leading-relaxed text-mist-500">
        {t("finInvoicesNotePre")}{" "}
        <span className="text-mist-300">{t("finInvoicesNoteStrong")}</span>
        {t("finInvoicesNotePost")}
      </div>
    </div>
  );
}

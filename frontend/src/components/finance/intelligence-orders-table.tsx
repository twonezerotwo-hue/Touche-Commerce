"use client";

import Link from "next/link";

import { ReconciliationStatusBadge } from "@/components/finance/reconciliation-status-badge";
import { Badge } from "@/components/ui/badge";
import { EmptyState } from "@/components/ui/empty-state";
import {
  Table,
  TableBody,
  TableCell,
  TableHead,
  TableHeader,
  TableRow,
} from "@/components/ui/table";
import { formatReconciliationMoney, formatReconciliationPercent } from "@/lib/finance/format";
import { completenessTone, isNegative, type OrderProfitability } from "@/lib/finance/intelligence";
import {
  categoryWord,
  completenessWord,
  modelWord,
  statusWord,
} from "@/lib/finance/intelligence-text";
import { useLocale } from "@/lib/i18n/locale-provider";

/**
 * Amount with its percentage; a missing amount is words, never a zero. `loss` tints a
 * negative profit or margin (not used for cost variance, where negative is a saving).
 */
function AmountCell({
  amount,
  percent,
  currency,
  loss = false,
}: {
  amount: string | null | undefined;
  percent?: string | null;
  currency: string;
  loss?: boolean;
}) {
  const { t, locale } = useLocale();
  if (amount === null || amount === undefined) {
    return <span className="text-[10.5px] text-mist-600">{t("intNotAvailable")}</span>;
  }
  const negative = loss && isNegative(amount);
  return (
    <>
      <span
        className={`font-mono text-[11px] ${negative ? "text-crimson-400" : "text-mist-200"}`}
        data-negative={negative || undefined}
      >
        {formatReconciliationMoney(amount, currency, t("intNotAvailable"), locale)}
      </span>
      {percent !== undefined ? (
        <span
          className={`block font-mono text-[10px] ${negative ? "text-crimson-400" : "text-mist-500"}`}
        >
          {formatReconciliationPercent(percent, t("intNotAvailable"), locale)}
        </span>
      ) : null}
    </>
  );
}

export function OrderFlags({ order }: { order: OrderProfitability }) {
  const { t, locale } = useLocale();
  const flags: string[] = [];
  if (order.cancelled) flags.push(t("flagCancelled"));
  if (order.partial_fulfilment) flags.push(t("flagPartialFulfilment"));
  if (order.purchase_currency_mismatch) flags.push(t("flagPoCurrencyMismatch"));
  if (order.cost_currency_mismatch) flags.push(t("flagCostCurrencyMismatch"));
  if (flags.length === 0 && order.missing_components.length === 0) return null;
  return (
    <div className="mt-1 space-y-1">
      {flags.length > 0 ? (
        <div className="flex flex-wrap gap-1">
          {flags.map((flag) => (
            <Badge key={flag} variant="outline">
              {flag}
            </Badge>
          ))}
        </div>
      ) : null}
      {order.missing_components.length > 0 ? (
        <p className="max-w-[220px] text-[10px] leading-snug text-mist-600">
          {t("flagMissing", {
            list: order.missing_components.map((key) => categoryWord(t, locale, key)).join(", "),
          })}
        </p>
      ) : null}
    </div>
  );
}

export function IntelligenceOrdersTable({
  items,
  emptyTitle,
  emptyDescription,
}: {
  items: readonly OrderProfitability[];
  emptyTitle?: string;
  emptyDescription?: string;
}) {
  const { t, locale } = useLocale();
  if (items.length === 0) {
    return (
      <EmptyState
        embedded
        title={emptyTitle ?? t("intNoOrdersMatch")}
        description={emptyDescription ?? t("intNoOrdersMatchDesc")}
      />
    );
  }
  return (
    <Table>
      <TableHeader>
        <TableRow>
          <TableHead className="pl-4">{t("intColOrder")}</TableHead>
          <TableHead className="text-right whitespace-normal">{t("intColSalesValue")}</TableHead>
          <TableHead className="text-right whitespace-normal">{t("intColEstMargin")}</TableHead>
          <TableHead className="text-right whitespace-normal">
            {t("intColCommittedMargin")}
          </TableHead>
          <TableHead className="text-right whitespace-normal">{t("intColDocCost")}</TableHead>
          <TableHead className="text-right whitespace-normal">{t("intColCostVariance")}</TableHead>
          <TableHead>{t("intColCompleteness")}</TableHead>
          <TableHead className="pr-4">{t("intColReconciliation")}</TableHead>
        </TableRow>
      </TableHeader>
      <TableBody>
        {items.map((order) => (
          <TableRow key={order.sales_order_id}>
            {/* The order number never breaks at its hyphens, a long customer name is
                clamped (full text on hover) and the status sits under it, so the row
                stays short and the figures keep their columns. */}
            <TableCell className="min-w-[170px] pl-4">
              <Link
                href={`/finance/intelligence/orders/${order.sales_order_id}`}
                className="font-mono text-[11.5px] whitespace-nowrap text-accent-200 hover:text-accent-100"
              >
                {order.order_number}
              </Link>
              <span
                className="mt-0.5 line-clamp-2 max-w-[200px] text-[10px] text-mist-600"
                title={order.customer_name}
              >
                {order.customer_name}
              </span>
              <span className="mt-1.5 flex flex-wrap items-center gap-x-2 gap-y-1">
                <Badge variant="outline">{statusWord(t, locale, order.status)}</Badge>
                <span className="text-[10px] text-mist-600">
                  {modelWord(t, locale, order.fulfilment_model)}
                </span>
              </span>
            </TableCell>
            <TableCell className="text-right whitespace-nowrap">
              <AmountCell amount={order.sales_value} currency={order.currency} />
              <span className="block font-mono text-[10px] text-mist-600">{order.currency}</span>
            </TableCell>
            <TableCell className="text-right whitespace-nowrap">
              <AmountCell
                amount={order.estimated_gross_profit}
                percent={order.estimated_gross_margin_pct}
                currency={order.currency}
                loss
              />
            </TableCell>
            <TableCell className="text-right whitespace-nowrap">
              <AmountCell
                amount={order.committed_gross_profit}
                percent={order.committed_gross_margin_pct}
                currency={order.currency}
                loss
              />
            </TableCell>
            <TableCell className="text-right whitespace-nowrap">
              <AmountCell amount={order.documented_total_cost} currency={order.currency} />
            </TableCell>
            <TableCell className="text-right whitespace-nowrap">
              <AmountCell
                amount={order.cost_variance}
                percent={order.cost_variance_pct}
                currency={order.currency}
              />
            </TableCell>
            <TableCell className="min-w-[150px]">
              <Badge variant={completenessTone(order.completeness)}>
                {completenessWord(t, order.completeness)}
              </Badge>
              <OrderFlags order={order} />
            </TableCell>
            <TableCell className="pr-4">
              {order.reconciliation_status ? (
                <ReconciliationStatusBadge status={order.reconciliation_status} />
              ) : (
                <Badge variant="outline">{t("intNoRun")}</Badge>
              )}
              {order.open_discrepancy_count > 0 ? (
                <span className="mt-1 block text-[10px] text-mist-500">
                  {order.blocking_discrepancy_count > 0
                    ? t("intOpenBlocking", {
                        open: order.open_discrepancy_count,
                        blocking: order.blocking_discrepancy_count,
                      })
                    : t("intOpenCount", { count: order.open_discrepancy_count })}
                </span>
              ) : null}
            </TableCell>
          </TableRow>
        ))}
      </TableBody>
    </Table>
  );
}

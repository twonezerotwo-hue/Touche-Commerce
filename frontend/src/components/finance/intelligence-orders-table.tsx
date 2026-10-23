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
import { completenessTone, humanize, type OrderProfitability } from "@/lib/finance/intelligence";

/** Amount with its percentage; a missing amount is words, never a zero. */
function AmountCell({
  amount,
  percent,
  currency,
}: {
  amount: string | null | undefined;
  percent?: string | null;
  currency: string;
}) {
  if (amount === null || amount === undefined) {
    return <span className="text-[10.5px] text-mist-600">Not available</span>;
  }
  return (
    <>
      <span className="font-mono text-[11px] text-mist-200">
        {formatReconciliationMoney(amount, currency)}
      </span>
      {percent !== undefined ? (
        <span className="block font-mono text-[10px] text-mist-500">
          {formatReconciliationPercent(percent)}
        </span>
      ) : null}
    </>
  );
}

export function OrderFlags({ order }: { order: OrderProfitability }) {
  const flags: string[] = [];
  if (order.cancelled) flags.push("Cancelled");
  if (order.partial_fulfilment) flags.push("Partial fulfilment");
  if (order.purchase_currency_mismatch) flags.push("PO currency mismatch");
  if (order.cost_currency_mismatch) flags.push("Cost currency mismatch");
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
          Missing: {order.missing_components.map(humanize).join(", ")}
        </p>
      ) : null}
    </div>
  );
}

export function IntelligenceOrdersTable({
  items,
  emptyTitle = "No orders match",
  emptyDescription = "No accepted orders fall inside the selected range and filters.",
}: {
  items: readonly OrderProfitability[];
  emptyTitle?: string;
  emptyDescription?: string;
}) {
  if (items.length === 0) {
    return <EmptyState title={emptyTitle} description={emptyDescription} />;
  }
  return (
    <Table>
      <TableHeader>
        <TableRow>
          <TableHead className="pl-4">Order</TableHead>
          <TableHead className="text-right whitespace-normal">Sales value</TableHead>
          <TableHead className="text-right whitespace-normal">Estimated margin</TableHead>
          <TableHead className="text-right whitespace-normal">Committed margin</TableHead>
          <TableHead className="text-right whitespace-normal">Documented cost</TableHead>
          <TableHead className="text-right whitespace-normal">Cost variance</TableHead>
          <TableHead>Completeness</TableHead>
          <TableHead className="pr-4">Reconciliation</TableHead>
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
                <Badge variant="outline">{humanize(order.status)}</Badge>
                <span className="text-[10px] text-mist-600">
                  {humanize(order.fulfilment_model)}
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
              />
            </TableCell>
            <TableCell className="text-right whitespace-nowrap">
              <AmountCell
                amount={order.committed_gross_profit}
                percent={order.committed_gross_margin_pct}
                currency={order.currency}
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
              <Badge variant={completenessTone(order.completeness)}>{order.completeness}</Badge>
              <OrderFlags order={order} />
            </TableCell>
            <TableCell className="pr-4">
              {order.reconciliation_status ? (
                <ReconciliationStatusBadge status={order.reconciliation_status} />
              ) : (
                <Badge variant="outline">No run</Badge>
              )}
              {order.open_discrepancy_count > 0 ? (
                <span className="mt-1 block text-[10px] text-mist-500">
                  {order.open_discrepancy_count} open
                  {order.blocking_discrepancy_count > 0
                    ? ` · ${order.blocking_discrepancy_count} blocking`
                    : ""}
                </span>
              ) : null}
            </TableCell>
          </TableRow>
        ))}
      </TableBody>
    </Table>
  );
}

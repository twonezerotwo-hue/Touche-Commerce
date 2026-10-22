import Link from "next/link";

import { OperationsStatusBadge } from "@/components/operations/status-badge";
import { Alert } from "@/components/ui/alert";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { EmptyState } from "@/components/ui/empty-state";
import { PageHeader } from "@/components/ui/page-header";
import { Select } from "@/components/ui/select";
import {
  Table,
  TableBody,
  TableCell,
  TableHead,
  TableHeader,
  TableRow,
} from "@/components/ui/table";
import { serverGet } from "@/lib/api/server";
import { loadSession } from "@/lib/auth/session";
import { SALES_ORDER_STATUSES, type SalesOrderList } from "@/lib/operations/types";
import { formatMoney, formatTimestamp, withQuery } from "@/lib/trade/format";

export const dynamic = "force-dynamic";
export const metadata = { title: "Sales orders" };

const PAGE_SIZE = 25;

export default async function OrdersPage({
  searchParams,
}: {
  searchParams: Promise<{ status?: string; cursor?: string }>;
}) {
  const state = await loadSession();
  if (state.status !== "authenticated") return null;

  const params = await searchParams;
  const query = new URLSearchParams({ limit: String(PAGE_SIZE) });
  if (params.status) query.set("status", params.status);
  if (params.cursor) query.set("cursor", params.cursor);

  const result = await serverGet<SalesOrderList>(`/sales-orders?${query.toString()}`);
  const filters = { status: params.status ?? "" };

  return (
    <div className="mx-auto max-w-[1360px] space-y-5">
      <PageHeader
        eyebrow="Execution"
        meta={
          <Badge variant="secondary">
            {result.ok ? `${result.data.items.length} on this page` : "Unavailable"}
          </Badge>
        }
        title="Sales orders"
        description="Created only from an approved quote revision plus recorded customer acceptance. The accepted commercial facts are frozen on the order and never re-read from the catalogue."
      />

      <div className="panel overflow-hidden">
        <form action="/orders" method="get" className="flex flex-wrap items-end gap-2 px-4 py-3">
          <div className="space-y-1">
            <label htmlFor="orders-status" className="eyebrow">
              Status
            </label>
            <Select
              id="orders-status"
              name="status"
              defaultValue={filters.status}
              className="h-8 w-[190px] text-[12px]"
            >
              <option value="">All statuses</option>
              {SALES_ORDER_STATUSES.map((status) => (
                <option key={status} value={status}>
                  {status.replaceAll("_", " ")}
                </option>
              ))}
            </Select>
          </div>
          <Button type="submit" size="sm" variant="subtle">
            Apply
          </Button>
          {filters.status ? (
            <Button asChild size="sm" variant="ghost">
              <Link href="/orders">Clear</Link>
            </Button>
          ) : null}
        </form>

        <div className="hairline" />

        {!result.ok ? (
          <div className="p-4">
            <Alert variant="danger" title="Sales orders unavailable">
              {result.message}
            </Alert>
          </div>
        ) : result.data.items.length === 0 ? (
          <div className="p-4">
            <EmptyState
              title="No sales orders yet"
              description="An order appears here once a deal with an approved quote and documented customer acceptance is converted."
            />
          </div>
        ) : null}

        {result.ok && result.data.items.length > 0 ? (
          <Table bare>
            <TableHeader>
              <TableRow>
                <TableHead className="pl-4">Order</TableHead>
                <TableHead>Customer</TableHead>
                <TableHead>Source</TableHead>
                <TableHead>Model</TableHead>
                <TableHead>Status</TableHead>
                <TableHead className="text-right">Total</TableHead>
                <TableHead>Delivery</TableHead>
                <TableHead className="pr-4 text-right">Updated</TableHead>
              </TableRow>
            </TableHeader>
            <TableBody>
              {result.data.items.map((order) => (
                <TableRow key={order.id}>
                  <TableCell className="pl-4">
                    <Link
                      href={`/orders/${order.id}`}
                      className="font-mono text-[11.5px] text-accent-200 transition-colors hover:text-accent-100"
                    >
                      {order.order_number}
                    </Link>
                  </TableCell>
                  <TableCell className="max-w-[190px] truncate text-[12px] text-mist-100">
                    {order.customer_name}
                  </TableCell>
                  <TableCell className="text-[11px] text-mist-400">
                    <span className="font-mono">
                      {order.quote_number} r{order.sales_quote_revision}
                    </span>
                    <span className="block text-[10px] text-mist-600">{order.deal_reference}</span>
                  </TableCell>
                  <TableCell className="text-[10.5px] tracking-[0.04em] text-mist-500 uppercase">
                    {order.fulfilment_model.replaceAll("_", " ")}
                  </TableCell>
                  <TableCell>
                    <OperationsStatusBadge status={order.status} />
                  </TableCell>
                  <TableCell className="text-right whitespace-nowrap text-[12px] text-mist-200">
                    {formatMoney(order.order_total, order.currency)}
                  </TableCell>
                  <TableCell className="whitespace-nowrap text-[11px] text-mist-400">
                    {order.expected_delivery_date ?? "—"}
                  </TableCell>
                  <TableCell className="pr-4 text-right font-mono text-[10.5px] whitespace-nowrap text-mist-600">
                    {formatTimestamp(order.updated_at)}
                  </TableCell>
                </TableRow>
              ))}
            </TableBody>
          </Table>
        ) : null}

        <div className="flex flex-wrap items-center justify-between gap-3 border-t border-white/[0.06] px-4 py-3">
          <p className="text-[10.5px] text-mist-600">
            Fulfilment is derived from delivered shipment quantities, never from this status alone.
          </p>
          <div className="flex items-center gap-3">
            {params.cursor ? (
              <Button asChild variant="ghost" size="xs">
                <Link href={withQuery("/orders", filters)}>First page</Link>
              </Button>
            ) : null}
            {result.ok && result.data.has_more && result.data.next_cursor ? (
              <Button asChild variant="outline" size="sm">
                <Link
                  href={withQuery("/orders", {
                    ...filters,
                    cursor: result.data.next_cursor,
                  })}
                >
                  Next page
                </Link>
              </Button>
            ) : null}
          </div>
        </div>
      </div>
    </div>
  );
}

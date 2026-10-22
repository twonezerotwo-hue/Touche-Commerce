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
import { PURCHASE_ORDER_STATUSES, type PurchaseOrderList } from "@/lib/operations/types";
import { formatDate, formatMoney, formatTimestamp, withQuery } from "@/lib/trade/format";

export const dynamic = "force-dynamic";
export const metadata = { title: "Purchase orders" };

const PAGE_SIZE = 25;

export default async function PurchaseOrdersPage({
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

  const result = await serverGet<PurchaseOrderList>(`/purchase-orders?${query.toString()}`);
  const filters = { status: params.status ?? "" };

  return (
    <div className="mx-auto max-w-[1360px] space-y-5">
      <PageHeader
        eyebrow="Execution"
        meta={<Badge variant="secondary">Procurement</Badge>}
        title="Supplier purchase orders"
        description="Optional procurement for purchase-and-resale orders. A draft is never treated as sent: dispatch is recorded with a channel, a timestamp and an external reference."
        actions={
          <Button asChild variant="outline" size="sm">
            <Link href="/orders">Sales orders</Link>
          </Button>
        }
      />

      <div className="panel overflow-hidden">
        <form
          action="/purchase-orders"
          method="get"
          className="flex flex-wrap items-end gap-2 px-4 py-3"
        >
          <div className="space-y-1">
            <label htmlFor="po-filter-status" className="eyebrow">
              Status
            </label>
            <Select
              id="po-filter-status"
              name="status"
              defaultValue={filters.status}
              className="h-8 w-[190px] text-[12px]"
            >
              <option value="">All statuses</option>
              {PURCHASE_ORDER_STATUSES.map((status) => (
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
              <Link href="/purchase-orders">Clear</Link>
            </Button>
          ) : null}
        </form>

        <div className="hairline" />

        {!result.ok ? (
          <div className="p-4">
            <Alert variant="danger" title="Purchase orders unavailable">
              {result.message}
            </Alert>
          </div>
        ) : result.data.items.length === 0 ? (
          <div className="p-4">
            <EmptyState
              title="No purchase orders yet"
              description="A purchase order is created against a confirmed sales order when TOUCHE is the buyer. Brokerage deals never need one."
            />
          </div>
        ) : null}

        {result.ok && result.data.items.length > 0 ? (
          <Table bare>
            <TableHeader>
              <TableRow>
                <TableHead className="pl-4">PO</TableHead>
                <TableHead>Supplier</TableHead>
                <TableHead>Sales order</TableHead>
                <TableHead>Status</TableHead>
                <TableHead className="text-right">Cost</TableHead>
                <TableHead>Expected dispatch</TableHead>
                <TableHead className="pr-4 text-right">Updated</TableHead>
              </TableRow>
            </TableHeader>
            <TableBody>
              {result.data.items.map((po) => (
                <TableRow key={po.id}>
                  <TableCell className="pl-4">
                    <Link
                      href={`/purchase-orders/${po.id}`}
                      className="font-mono text-[11.5px] text-accent-200 hover:text-accent-100"
                    >
                      {po.po_number}
                    </Link>
                  </TableCell>
                  <TableCell className="max-w-[190px] truncate text-[12px] text-mist-100">
                    {po.supplier_name}
                  </TableCell>
                  <TableCell className="font-mono text-[11px] text-mist-400">
                    <Link href={`/orders/${po.sales_order_id}`} className="hover:text-accent-200">
                      {po.order_number}
                    </Link>
                  </TableCell>
                  <TableCell>
                    <OperationsStatusBadge status={po.status} />
                  </TableCell>
                  <TableCell className="text-right whitespace-nowrap text-[12px] text-mist-200">
                    {formatMoney(po.total_cost, po.currency)}
                  </TableCell>
                  <TableCell className="whitespace-nowrap text-[11px] text-mist-400">
                    {formatDate(po.expected_dispatch_date)}
                  </TableCell>
                  <TableCell className="pr-4 text-right font-mono text-[10.5px] whitespace-nowrap text-mist-600">
                    {formatTimestamp(po.updated_at)}
                  </TableCell>
                </TableRow>
              ))}
            </TableBody>
          </Table>
        ) : null}

        <div className="flex flex-wrap items-center justify-between gap-3 border-t border-white/[0.06] px-4 py-3">
          <p className="text-[10.5px] text-mist-600">
            Nothing is emailed or messaged to a supplier by this platform.
          </p>
          <div className="flex items-center gap-3">
            {params.cursor ? (
              <Button asChild variant="ghost" size="xs">
                <Link href={withQuery("/purchase-orders", filters)}>First page</Link>
              </Button>
            ) : null}
            {result.ok && result.data.has_more && result.data.next_cursor ? (
              <Button asChild variant="outline" size="sm">
                <Link
                  href={withQuery("/purchase-orders", {
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

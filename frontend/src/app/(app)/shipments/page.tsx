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
import { DocumentDownloads } from "@/components/documents/document-downloads";
import { canGenerateDocuments } from "@/lib/documents/access";
import { delayLabel } from "@/lib/operations/format";
import { SHIPMENT_STATUSES, type ShipmentList } from "@/lib/operations/types";
import { formatDate, formatTimestamp, withQuery } from "@/lib/trade/format";

export const dynamic = "force-dynamic";
export const metadata = { title: "Shipments" };

const PAGE_SIZE = 25;

export default async function ShipmentsPage({
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

  const result = await serverGet<ShipmentList>(`/shipments?${query.toString()}`);
  const filters = { status: params.status ?? "" };

  return (
    <div className="mx-auto max-w-[1360px] space-y-5">
      <PageHeader
        eyebrow="Logistics"
        meta={<Badge variant="secondary">Shipment register</Badge>}
        title="Shipments"
        description="Partial shipments allocate quantities from confirmed orders. Dispatch, arrival and delivery each need their own evidence; an ETA is never treated as an arrival."
        actions={
          <Button asChild size="sm">
            <Link href="/shipments/new">Plan shipment</Link>
          </Button>
        }
      />
      {canGenerateDocuments(state.session.session.company) ? (
        <DocumentDownloads documents={[{ kind: "shipment_register" }]} />
      ) : null}

      <div className="panel overflow-hidden">
        <form action="/shipments" method="get" className="flex flex-wrap items-end gap-2 px-4 py-3">
          <div className="space-y-1">
            <label htmlFor="shipment-filter-status" className="eyebrow">
              Status
            </label>
            <Select
              id="shipment-filter-status"
              name="status"
              defaultValue={filters.status}
              className="h-8 w-[190px] text-[12px]"
            >
              <option value="">All statuses</option>
              {SHIPMENT_STATUSES.map((status) => (
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
              <Link href="/shipments">Clear</Link>
            </Button>
          ) : null}
        </form>

        <div className="hairline" />

        {!result.ok ? (
          <div className="p-4">
            <Alert variant="danger" title="Shipments unavailable">
              {result.message}
            </Alert>
          </div>
        ) : result.data.items.length === 0 ? (
          <div className="p-4">
            <EmptyState
              title="No shipments yet"
              description="Plan a shipment from a confirmed order to allocate part or all of its quantities."
            />
          </div>
        ) : null}

        {result.ok && result.data.items.length > 0 ? (
          <Table bare>
            <TableHeader>
              <TableRow>
                <TableHead className="pl-4">Shipment</TableHead>
                <TableHead>Order</TableHead>
                <TableHead>Route</TableHead>
                <TableHead>Mode</TableHead>
                <TableHead>Status</TableHead>
                <TableHead>ETA</TableHead>
                <TableHead>Timing</TableHead>
                <TableHead className="pr-4 text-right">Updated</TableHead>
              </TableRow>
            </TableHeader>
            <TableBody>
              {result.data.items.map((shipment) => (
                <TableRow key={shipment.id}>
                  <TableCell className="pl-4">
                    <Link
                      href={`/shipments/${shipment.id}`}
                      className="font-mono text-[11.5px] text-accent-200 hover:text-accent-100"
                    >
                      {shipment.shipment_number}
                    </Link>
                    <span className="block text-[10px] text-mist-600">
                      {shipment.carrier ?? "No carrier"} · {shipment.forwarder ?? "No forwarder"}
                    </span>
                  </TableCell>
                  <TableCell className="font-mono text-[11px] text-mist-400">
                    <Link
                      href={`/orders/${shipment.sales_order_id}`}
                      className="hover:text-accent-200"
                    >
                      {shipment.order_number}
                    </Link>
                  </TableCell>
                  <TableCell className="max-w-[220px] text-[11px] text-mist-300">
                    {shipment.origin} → {shipment.destination}
                  </TableCell>
                  <TableCell className="text-[10.5px] tracking-[0.04em] text-mist-400 uppercase">
                    {shipment.transport_mode}
                  </TableCell>
                  <TableCell>
                    <OperationsStatusBadge status={shipment.status} />
                  </TableCell>
                  <TableCell className="whitespace-nowrap text-[11px] text-mist-400">
                    {formatDate(shipment.estimated_arrival_at)}
                  </TableCell>
                  <TableCell className="text-[10.5px]">
                    {shipment.is_delayed ? (
                      <span className="text-crimson-400">
                        {delayLabel(true, shipment.estimated_arrival_at)}
                      </span>
                    ) : (
                      <span className="text-mist-500">
                        {delayLabel(false, shipment.estimated_arrival_at)}
                      </span>
                    )}
                  </TableCell>
                  <TableCell className="pr-4 text-right font-mono text-[10.5px] whitespace-nowrap text-mist-600">
                    {formatTimestamp(shipment.updated_at)}
                  </TableCell>
                </TableRow>
              ))}
            </TableBody>
          </Table>
        ) : null}

        <div className="flex flex-wrap items-center justify-between gap-3 border-t border-white/[0.06] px-4 py-3">
          <p className="text-[10.5px] text-mist-600">
            Tracking references are recorded by hand or from documents; there is no live carrier
            feed.
          </p>
          <div className="flex items-center gap-3">
            {params.cursor ? (
              <Button asChild variant="ghost" size="xs">
                <Link href={withQuery("/shipments", filters)}>First page</Link>
              </Button>
            ) : null}
            {result.ok && result.data.has_more && result.data.next_cursor ? (
              <Button asChild variant="outline" size="sm">
                <Link
                  href={withQuery("/shipments", {
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

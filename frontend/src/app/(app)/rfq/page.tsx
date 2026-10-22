import Link from "next/link";
import { ArrowRight, FileText, Plus } from "lucide-react";

import { SourcingStatusBadge } from "@/components/sourcing/status-badge";
import { Alert } from "@/components/ui/alert";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { EmptyState } from "@/components/ui/empty-state";
import { Input } from "@/components/ui/input";
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
import { RFQ_STATUSES, type RfqList } from "@/lib/sourcing/types";
import { formatDate, formatTimestamp, withQuery } from "@/lib/trade/format";

export const dynamic = "force-dynamic";
export const metadata = { title: "RFQs" };

const PAGE_SIZE = 25;

export default async function RfqListPage({
  searchParams,
}: {
  searchParams: Promise<{ search?: string; status?: string; cursor?: string }>;
}) {
  const state = await loadSession();
  if (state.status !== "authenticated") return null;

  const params = await searchParams;
  const canWrite = state.session.session.company?.permissions.includes("trade.write") ?? false;

  const query = new URLSearchParams({ limit: String(PAGE_SIZE) });
  if (params.search) query.set("search", params.search);
  if (params.status) query.set("status", params.status);
  if (params.cursor) query.set("cursor", params.cursor);

  const result = await serverGet<RfqList>(`/rfqs?${query.toString()}`);
  const filters = { search: params.search ?? "", status: params.status ?? "" };
  const filtered = Boolean(filters.search || filters.status);

  return (
    <div className="mx-auto max-w-[1360px] space-y-5">
      <PageHeader
        eyebrow="Sourcing"
        meta={<Badge variant="secondary">RFQs</Badge>}
        title="Supplier requests"
        description="One RFQ per supplier, prepared as an immutable revision before it is sent. Sending records the channel and the evidence; a quote is always attributable to the request it answers."
        actions={
          canWrite ? (
            <Button asChild size="sm">
              <Link href="/rfq/new">
                <Plus className="size-3.5" aria-hidden />
                New RFQ
              </Link>
            </Button>
          ) : (
            <Badge variant="outline">Read-only · trade.write required</Badge>
          )
        }
      />

      <div className="panel overflow-hidden">
        <form action="/rfq" method="get" className="flex flex-wrap items-end gap-2 px-4 py-3">
          <div className="space-y-1">
            <label htmlFor="rfq-filter-search" className="eyebrow">
              Search
            </label>
            <Input
              id="rfq-filter-search"
              name="search"
              defaultValue={filters.search}
              placeholder="Reference, supplier or place"
              maxLength={160}
              className="h-8 w-[240px] text-[12px]"
            />
          </div>
          <div className="space-y-1">
            <label htmlFor="rfq-filter-status" className="eyebrow">
              Status
            </label>
            <Select
              id="rfq-filter-status"
              name="status"
              defaultValue={filters.status}
              className="h-8 w-[160px] text-[12px]"
            >
              <option value="">All statuses</option>
              {RFQ_STATUSES.map((status) => (
                <option key={status} value={status}>
                  {status.replaceAll("_", " ")}
                </option>
              ))}
            </Select>
          </div>
          <Button type="submit" size="sm" variant="subtle">
            Apply
          </Button>
          {filtered ? (
            <Button asChild size="sm" variant="ghost">
              <Link href="/rfq">Clear</Link>
            </Button>
          ) : null}
        </form>

        <div className="hairline" />

        {!result.ok ? (
          <div className="p-4">
            <Alert variant="danger" title="RFQs unavailable">
              {result.message}
            </Alert>
          </div>
        ) : result.data.items.length === 0 ? (
          <div className="p-4">
            <EmptyState
              icon={<FileText className="size-4" aria-hidden />}
              title={filtered ? "No RFQs match these filters" : "No RFQs yet"}
              description={
                filtered
                  ? "Adjust the status filter or search term."
                  : "Create a request from a deal to start comparing supplier offers."
              }
              action={
                !filtered && canWrite ? (
                  <Button asChild size="sm">
                    <Link href="/rfq/new">New RFQ</Link>
                  </Button>
                ) : null
              }
              className="border-dashed bg-transparent py-10"
            />
          </div>
        ) : null}

        {result.ok && result.data.items.length > 0 ? (
          <Table bare>
            <TableHeader>
              <TableRow>
                <TableHead className="pl-4">Reference</TableHead>
                <TableHead>Supplier</TableHead>
                <TableHead>Deal</TableHead>
                <TableHead>Status</TableHead>
                <TableHead>Due</TableHead>
                <TableHead className="text-right">Lines</TableHead>
                <TableHead className="text-right">Quotes</TableHead>
                <TableHead className="pr-4 text-right">Updated</TableHead>
              </TableRow>
            </TableHeader>
            <TableBody>
              {result.data.items.map((rfq) => (
                <TableRow key={rfq.id}>
                  <TableCell className="pl-4">
                    <Link
                      href={`/rfq/${rfq.id}`}
                      className="font-mono text-[11.5px] text-accent-200 transition-colors hover:text-accent-100"
                    >
                      {rfq.reference_number}
                    </Link>
                  </TableCell>
                  <TableCell className="max-w-[200px] truncate text-[12px] text-mist-100">
                    {rfq.supplier_name}
                  </TableCell>
                  <TableCell className="font-mono text-[11px] text-mist-500">
                    {rfq.deal_reference}
                  </TableCell>
                  <TableCell>
                    <SourcingStatusBadge status={rfq.status} />
                  </TableCell>
                  <TableCell className="whitespace-nowrap text-[11.5px] text-mist-400">
                    {formatDate(rfq.response_due_date)}
                  </TableCell>
                  <TableCell className="text-right text-[11.5px] text-mist-300">
                    {rfq.item_count}
                  </TableCell>
                  <TableCell className="text-right text-[11.5px] text-mist-300">
                    {rfq.quote_count}
                  </TableCell>
                  <TableCell className="pr-4 text-right font-mono text-[10.5px] whitespace-nowrap text-mist-600">
                    {formatTimestamp(rfq.updated_at)}
                  </TableCell>
                </TableRow>
              ))}
            </TableBody>
          </Table>
        ) : null}

        <div className="flex flex-wrap items-center justify-between gap-3 border-t border-white/[0.06] px-4 py-3">
          <p className="text-[10.5px] text-mist-600">
            {result.ok
              ? `${result.data.items.length} on this page${
                  result.data.has_more ? " · older RFQs available" : " · end of list"
                }`
              : "—"}
          </p>
          <div className="flex items-center gap-3">
            {params.cursor ? (
              <Button asChild variant="ghost" size="xs">
                <Link href={withQuery("/rfq", filters)}>First page</Link>
              </Button>
            ) : null}
            {result.ok && result.data.has_more && result.data.next_cursor ? (
              <Button asChild variant="outline" size="sm">
                <Link href={withQuery("/rfq", { ...filters, cursor: result.data.next_cursor })}>
                  Next page
                  <ArrowRight className="size-3.5" aria-hidden />
                </Link>
              </Button>
            ) : null}
          </div>
        </div>
      </div>
    </div>
  );
}

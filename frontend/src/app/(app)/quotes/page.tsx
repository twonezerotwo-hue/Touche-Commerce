import Link from "next/link";
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
import { SourcingStatusBadge } from "@/components/sourcing/status-badge";
import { serverGet } from "@/lib/api/server";
import { loadSession } from "@/lib/auth/session";
import { SUPPLIER_QUOTE_STATUSES, type SupplierQuoteList } from "@/lib/sourcing/types";
import { formatDate, formatMoney, formatTimestamp, withQuery } from "@/lib/trade/format";

export const dynamic = "force-dynamic";
export const metadata = { title: "Supplier quotes" };

const PAGE_SIZE = 25;

export default async function SupplierQuotesPage({
  searchParams,
}: {
  searchParams: Promise<{ search?: string; status?: string; cursor?: string }>;
}) {
  const state = await loadSession();
  if (state.status !== "authenticated") return null;

  const params = await searchParams;
  const query = new URLSearchParams({ limit: String(PAGE_SIZE) });
  if (params.search) query.set("search", params.search);
  if (params.status) query.set("status", params.status);
  if (params.cursor) query.set("cursor", params.cursor);

  const result = await serverGet<SupplierQuoteList>(`/supplier-quotes?${query.toString()}`);
  const filters = { search: params.search ?? "", status: params.status ?? "" };

  return (
    <div className="mx-auto max-w-[1360px] space-y-5">
      <PageHeader
        eyebrow="Sourcing"
        meta={<Badge variant="secondary">Supplier quotes</Badge>}
        title="Supplier quotes"
        description="Every price a supplier gave, including superseded revisions and withdrawals. A withdrawn or superseded quote can no longer be priced."
      />

      <div className="panel overflow-hidden">
        <form action="/quotes" method="get" className="flex flex-wrap items-end gap-2 px-4 py-3">
          <div className="space-y-1">
            <label htmlFor="quotes-filter-search" className="eyebrow">
              Search
            </label>
            <Input
              id="quotes-filter-search"
              name="search"
              defaultValue={filters.search}
              placeholder="Supplier, RFQ or source"
              maxLength={160}
              className="h-8 w-[240px] text-[12px]"
            />
          </div>
          <div className="space-y-1">
            <label htmlFor="quotes-filter-status" className="eyebrow">
              Status
            </label>
            <Select
              id="quotes-filter-status"
              name="status"
              defaultValue={filters.status}
              className="h-8 w-[160px] text-[12px]"
            >
              <option value="">All statuses</option>
              {SUPPLIER_QUOTE_STATUSES.map((status) => (
                <option key={status} value={status}>
                  {status}
                </option>
              ))}
            </Select>
          </div>
          <Button type="submit" size="sm" variant="subtle">
            Apply
          </Button>
          {filters.search || filters.status ? (
            <Button asChild size="sm" variant="ghost">
              <Link href="/quotes">Clear</Link>
            </Button>
          ) : null}
        </form>

        <div className="hairline" />

        {!result.ok ? (
          <div className="p-4">
            <Alert variant="danger" title="Quotes unavailable">
              {result.message}
            </Alert>
          </div>
        ) : result.data.items.length === 0 ? (
          <div className="p-4">
            <EmptyState
              title="No supplier quotes yet"
              description="Record a quote from a sent RFQ. Prices are stored with their source reference and revision."
              className="border-dashed bg-transparent py-10"
            />
          </div>
        ) : null}

        {result.ok && result.data.items.length > 0 ? (
          <Table bare>
            <TableHeader>
              <TableRow>
                <TableHead className="pl-4">RFQ</TableHead>
                <TableHead>Supplier</TableHead>
                <TableHead>Deal</TableHead>
                <TableHead>Status</TableHead>
                <TableHead className="text-right">Revision</TableHead>
                <TableHead className="text-right">Total</TableHead>
                <TableHead>Valid until</TableHead>
                <TableHead className="pr-4 text-right">Received</TableHead>
              </TableRow>
            </TableHeader>
            <TableBody>
              {result.data.items.map((quote) => (
                <TableRow key={quote.id}>
                  <TableCell className="pl-4">
                    <Link
                      href={`/quotes/${quote.id}`}
                      className="font-mono text-[11.5px] text-accent-200 transition-colors hover:text-accent-100"
                    >
                      {quote.rfq_reference}
                    </Link>
                  </TableCell>
                  <TableCell className="max-w-[200px] truncate text-[12px] text-mist-100">
                    {quote.supplier_name}
                  </TableCell>
                  <TableCell className="font-mono text-[11px] text-mist-500">
                    {quote.deal_reference}
                  </TableCell>
                  <TableCell>
                    <div className="flex items-center gap-1.5">
                      <SourcingStatusBadge status={quote.status} />
                      {quote.superseded_by_quote_id ? (
                        <Badge variant="outline">superseded</Badge>
                      ) : null}
                    </div>
                  </TableCell>
                  <TableCell className="text-right font-mono text-[11px] text-mist-400">
                    r{quote.revision}
                  </TableCell>
                  <TableCell className="text-right whitespace-nowrap">
                    <span className="data-value text-[12px] text-mist-200">
                      {formatMoney(quote.total_value, quote.currency)}
                    </span>
                  </TableCell>
                  <TableCell className="whitespace-nowrap text-[11.5px] text-mist-400">
                    {formatDate(quote.valid_until)}
                  </TableCell>
                  <TableCell className="pr-4 text-right font-mono text-[10.5px] whitespace-nowrap text-mist-600">
                    {formatTimestamp(quote.received_at)}
                  </TableCell>
                </TableRow>
              ))}
            </TableBody>
          </Table>
        ) : null}

        <div className="flex flex-wrap items-center justify-between gap-3 border-t border-white/[0.06] px-4 py-3">
          <p className="text-[10.5px] text-mist-600">
            {result.ok ? `${result.data.items.length} on this page` : "—"}
          </p>
          <div className="flex items-center gap-3">
            {params.cursor ? (
              <Button asChild variant="ghost" size="xs">
                <Link href={withQuery("/quotes", filters)}>First page</Link>
              </Button>
            ) : null}
            {result.ok && result.data.has_more && result.data.next_cursor ? (
              <Button asChild variant="outline" size="sm">
                <Link href={withQuery("/quotes", { ...filters, cursor: result.data.next_cursor })}>
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

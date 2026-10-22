import Link from "next/link";
import { ArrowRight, CalendarClock, Handshake, Plus, Search, X } from "lucide-react";

import { DealStatusBadge } from "@/components/trade/status-badge";
import { Alert } from "@/components/ui/alert";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { EmptyState } from "@/components/ui/empty-state";
import { Input } from "@/components/ui/input";
import { PageHeader } from "@/components/ui/page-header";
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
import { formatDate, formatMoney, formatTimestamp, withQuery } from "@/lib/trade/format";
import { DEAL_STATUSES, type DealList } from "@/lib/trade/types";
import { cn } from "@/lib/utils";

export const dynamic = "force-dynamic";
export const metadata = { title: "Deals" };

const PAGE_SIZE = 25;

export default async function DealsPage({
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

  const result = await serverGet<DealList>(`/deals?${query.toString()}`);
  const filters = { search: params.search ?? "", status: params.status ?? "" };
  const filtered = Boolean(filters.search || filters.status);
  const today = new Date().toISOString().slice(0, 10);

  return (
    <div className="mx-auto max-w-[1360px] space-y-5">
      <PageHeader
        eyebrow="Trade workspace"
        meta={<Badge variant="secondary">Deals</Badge>}
        title="Deals"
        description="Every status change is a recorded transition with an actor, a version and an audit row. Won stays disabled until sales orders exist in a later stage."
        actions={
          canWrite ? (
            <Button asChild size="sm">
              <Link href="/deals/new">
                <Plus className="size-3.5" aria-hidden />
                New deal
              </Link>
            </Button>
          ) : (
            <Badge variant="outline">Read-only · trade.write required</Badge>
          )
        }
      />

      <div className="panel overflow-hidden">
        <div className="flex flex-wrap items-center justify-between gap-3 px-4 py-3">
          <nav aria-label="Filter by status" className="flex flex-wrap items-center gap-1.5">
            <FilterPill
              href={withQuery("/deals", { search: filters.search })}
              active={filters.status === ""}
            >
              All
            </FilterPill>
            {DEAL_STATUSES.map((status) => (
              <FilterPill
                key={status}
                href={withQuery("/deals", { search: filters.search, status })}
                active={filters.status === status}
              >
                {status}
              </FilterPill>
            ))}
          </nav>

          <form action="/deals" method="get" className="flex items-center gap-2">
            <input type="hidden" name="status" value={filters.status} />
            <div className="relative">
              <Search
                className="pointer-events-none absolute top-1/2 left-3 size-3.5 -translate-y-1/2 text-mist-600"
                aria-hidden
              />
              <Input
                id="deals-search"
                name="search"
                defaultValue={filters.search}
                placeholder="Reference or title"
                aria-label="Search reference or title"
                maxLength={160}
                className="h-8 w-[220px] pl-8 text-[12px]"
              />
            </div>
            <Button type="submit" size="sm" variant="subtle">
              Search
            </Button>
            {filters.search ? (
              <Button asChild size="iconSm" variant="ghost" aria-label="Clear search">
                <Link href={withQuery("/deals", { status: filters.status })}>
                  <X className="size-3.5" aria-hidden />
                </Link>
              </Button>
            ) : null}
          </form>
        </div>

        <div className="hairline" />

        {!result.ok ? (
          <div className="p-4">
            <Alert variant="danger" title="Deals unavailable">
              {result.message}
              {result.requestId ? (
                <span className="ml-1 font-mono text-[11px]">({result.requestId})</span>
              ) : null}
            </Alert>
          </div>
        ) : result.data.items.length === 0 ? (
          <div className="p-4">
            <EmptyState
              icon={<Handshake className="size-4" aria-hidden />}
              title={filtered ? "No deals match these filters" : "No deals yet"}
              description={
                filtered
                  ? "Adjust the status filter or search term, or clear everything to see the full workspace."
                  : canWrite
                    ? "Create the first deal to start a versioned, auditable pipeline."
                    : "A member with trade.write can create the first deal."
              }
              action={
                filtered ? (
                  <Button asChild variant="outline" size="sm">
                    <Link href="/deals">Clear filters</Link>
                  </Button>
                ) : canWrite ? (
                  <Button asChild size="sm">
                    <Link href="/deals/new">New deal</Link>
                  </Button>
                ) : null
              }
              className="border-dashed bg-transparent py-10"
            />
          </div>
        ) : (
          <Table bare>
            <TableHeader>
              <TableRow>
                <TableHead className="pl-4">Reference</TableHead>
                <TableHead>Title</TableHead>
                <TableHead>Counterparty</TableHead>
                <TableHead>Status</TableHead>
                <TableHead>Expected close</TableHead>
                <TableHead className="text-right">Value</TableHead>
                <TableHead className="pr-4 text-right">Created</TableHead>
                <TableHead className="w-8 pr-3">
                  <span className="sr-only">Open</span>
                </TableHead>
              </TableRow>
            </TableHeader>
            <TableBody>
              {result.data.items.map((deal) => {
                const overdue =
                  deal.expected_close_date !== null &&
                  deal.expected_close_date < today &&
                  ["DRAFT", "OPEN", "NEGOTIATION"].includes(deal.status);
                return (
                  <TableRow key={deal.id}>
                    <TableCell className="pl-4">
                      <Link
                        href={`/deals/${deal.id}`}
                        className="font-mono text-[11.5px] text-accent-200 transition-colors hover:text-accent-100"
                      >
                        {deal.reference}
                      </Link>
                    </TableCell>
                    <TableCell className="max-w-[260px] truncate text-[12px] text-mist-100">
                      {deal.title}
                    </TableCell>
                    <TableCell className="max-w-[200px] truncate text-[12px]">
                      {deal.counterparty_name}
                    </TableCell>
                    <TableCell>
                      <DealStatusBadge status={deal.status} />
                    </TableCell>
                    <TableCell className="whitespace-nowrap">
                      <span className="flex items-center gap-1.5 text-[11.5px] text-mist-400">
                        {overdue ? (
                          <CalendarClock className="size-3 text-amber-400" aria-hidden />
                        ) : null}
                        {formatDate(deal.expected_close_date)}
                      </span>
                      {overdue ? (
                        <span className="mt-0.5 block text-[9.5px] tracking-[0.08em] text-amber-400 uppercase">
                          Past expected close
                        </span>
                      ) : null}
                    </TableCell>
                    <TableCell className="text-right whitespace-nowrap">
                      <span className="data-value text-[12px] text-mist-200">
                        {formatMoney(deal.total_value, deal.currency)}
                      </span>
                    </TableCell>
                    <TableCell className="pr-4 text-right font-mono text-[10.5px] whitespace-nowrap text-mist-600">
                      {formatTimestamp(deal.created_at)}
                    </TableCell>
                    <TableCell className="pr-3 text-right">
                      <Link
                        href={`/deals/${deal.id}`}
                        aria-label={`Open ${deal.reference}`}
                        className="inline-flex text-mist-600 transition-colors hover:text-accent-300"
                      >
                        <ArrowRight className="size-3.5" aria-hidden />
                      </Link>
                    </TableCell>
                  </TableRow>
                );
              })}
            </TableBody>
          </Table>
        )}

        <div className="flex flex-wrap items-center justify-between gap-3 border-t border-white/[0.06] px-4 py-3">
          <p className="text-[10.5px] text-mist-600">
            {result.ok ? (
              <>
                Showing <span className="data-value text-mist-400">{result.data.items.length}</span>{" "}
                {result.data.items.length === 1 ? "deal" : "deals"} on this page
                {result.data.has_more ? " · older deals available" : " · end of list"}
              </>
            ) : (
              "—"
            )}
          </p>
          <div className="flex items-center gap-3">
            {params.cursor ? (
              <Button asChild variant="ghost" size="xs">
                <Link href={withQuery("/deals", filters)}>First page</Link>
              </Button>
            ) : null}
            {result.ok && result.data.has_more && result.data.next_cursor ? (
              <Button asChild variant="outline" size="sm">
                <Link href={withQuery("/deals", { ...filters, cursor: result.data.next_cursor })}>
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

function FilterPill({
  href,
  active,
  children,
}: {
  href: string;
  active: boolean;
  children: React.ReactNode;
}) {
  return (
    <Link
      href={href}
      aria-current={active ? "true" : undefined}
      className={cn(
        "rounded-full border px-2.5 py-1 text-[10.5px] tracking-[0.02em] transition-colors",
        active
          ? "border-accent-400/35 bg-accent-400/10 text-accent-200"
          : "border-white/10 text-mist-500 hover:border-white/20 hover:text-mist-300",
      )}
    >
      {children}
    </Link>
  );
}

import Link from "next/link";
import { Plus, Search } from "lucide-react";

import { DealStatusBadge } from "@/components/trade/status-badge";
import { Alert } from "@/components/ui/alert";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
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

  return (
    <div className="mx-auto max-w-[1320px] space-y-6">
      <header className="flex flex-wrap items-end justify-between gap-4">
        <div>
          <div className="flex items-center gap-3">
            <span className="eyebrow">Trade workspace</span>
            <Badge variant="secondary">Deals</Badge>
          </div>
          <h1 className="mt-3 font-display text-[28px] leading-tight tracking-tight text-mist-100">
            Deals
          </h1>
          <p className="mt-2 max-w-2xl text-[13px] leading-relaxed text-mist-500">
            Every status change is a recorded transition with an actor, a version and an audit row.
            Won stays disabled until sales orders exist.
          </p>
        </div>
        {canWrite ? (
          <Button asChild size="sm">
            <Link href="/deals/new">
              <Plus className="size-3.5" aria-hidden />
              New deal
            </Link>
          </Button>
        ) : (
          <Badge variant="outline">Read-only: trade.write required</Badge>
        )}
      </header>

      <div className="flex flex-wrap items-center gap-1.5">
        <Link
          href={withQuery("/deals", { search: filters.search })}
          className={
            filters.status === ""
              ? "rounded-full border border-gold-400/30 bg-gold-400/10 px-3 py-1 text-[11px] text-gold-200"
              : "rounded-full border border-white/10 px-3 py-1 text-[11px] text-mist-400 hover:border-white/20"
          }
        >
          All
        </Link>
        {DEAL_STATUSES.map((status) => (
          <Link
            key={status}
            href={withQuery("/deals", { search: filters.search, status })}
            className={
              filters.status === status
                ? "rounded-full border border-gold-400/30 bg-gold-400/10 px-3 py-1 text-[11px] text-gold-200"
                : "rounded-full border border-white/10 px-3 py-1 text-[11px] text-mist-400 hover:border-white/20"
            }
          >
            {status}
          </Link>
        ))}
      </div>

      <form
        action="/deals"
        method="get"
        className="panel flex flex-wrap items-end gap-3 rounded-xl p-4"
      >
        <input type="hidden" name="status" value={filters.status} />
        <div className="min-w-[240px] flex-1 space-y-1.5">
          <label
            htmlFor="deals-search"
            className="block text-[10.5px] uppercase tracking-[0.16em] text-mist-500"
          >
            Search reference or title
          </label>
          <Input
            id="deals-search"
            name="search"
            defaultValue={filters.search}
            placeholder="T-2610 or aluminium"
            maxLength={160}
          />
        </div>
        <Button type="submit" size="sm" variant="outline">
          <Search className="size-3.5" aria-hidden />
          Search
        </Button>
        {filters.search ? (
          <Link
            href={withQuery("/deals", { status: filters.status })}
            className="text-[11.5px] text-mist-500 underline-offset-4 hover:text-mist-300 hover:underline"
          >
            Clear search
          </Link>
        ) : null}
      </form>

      {!result.ok ? (
        <Alert variant="danger" title="Deals unavailable">
          {result.message}
        </Alert>
      ) : result.data.items.length === 0 ? (
        <div className="panel rounded-xl p-10 text-center">
          <p className="font-display text-lg text-mist-200">No deals match</p>
          <p className="mx-auto mt-2 max-w-md text-[12.5px] leading-relaxed text-mist-500">
            {filters.search || filters.status
              ? "Adjust the filters, or clear them to see every deal in this company."
              : "No deals exist yet in this company. Create one to start the workflow."}
          </p>
        </div>
      ) : (
        <Table>
          <TableHeader>
            <TableRow>
              <TableHead>Reference</TableHead>
              <TableHead>Title</TableHead>
              <TableHead>Counterparty</TableHead>
              <TableHead>Status</TableHead>
              <TableHead className="text-right">Value</TableHead>
              <TableHead>Expected close</TableHead>
              <TableHead className="text-right">Created</TableHead>
            </TableRow>
          </TableHeader>
          <TableBody>
            {result.data.items.map((deal) => (
              <TableRow key={deal.id}>
                <TableCell>
                  <Link
                    href={`/deals/${deal.id}`}
                    className="font-mono text-[12px] text-gold-200 hover:text-gold-100"
                  >
                    {deal.reference}
                  </Link>
                </TableCell>
                <TableCell className="max-w-[280px] truncate text-mist-100">{deal.title}</TableCell>
                <TableCell>{deal.counterparty_name}</TableCell>
                <TableCell>
                  <DealStatusBadge status={deal.status} />
                </TableCell>
                <TableCell className="text-right text-mist-200">
                  {formatMoney(deal.total_value, deal.currency)}
                </TableCell>
                <TableCell>{formatDate(deal.expected_close_date)}</TableCell>
                <TableCell className="text-right text-[11.5px] text-mist-500">
                  {formatTimestamp(deal.created_at)}
                </TableCell>
              </TableRow>
            ))}
          </TableBody>
        </Table>
      )}

      <div className="flex items-center justify-between gap-3">
        <p className="text-[11px] text-mist-600">
          {result.ok ? `${result.data.items.length} shown` : "—"}
          {result.ok && result.data.has_more ? " · more available" : ""}
        </p>
        <div className="flex items-center gap-3">
          {params.cursor ? (
            <Link
              href={withQuery("/deals", filters)}
              className="text-[11.5px] text-mist-500 hover:text-mist-300"
            >
              First page
            </Link>
          ) : null}
          {result.ok && result.data.has_more && result.data.next_cursor ? (
            <Button asChild variant="outline" size="sm">
              <Link href={withQuery("/deals", { ...filters, cursor: result.data.next_cursor })}>
                Next page
              </Link>
            </Button>
          ) : null}
        </div>
      </div>
    </div>
  );
}

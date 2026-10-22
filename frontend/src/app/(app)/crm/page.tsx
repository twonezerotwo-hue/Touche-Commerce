import Link from "next/link";
import { Search } from "lucide-react";

import { CounterpartyForm } from "@/components/trade/counterparty-form";
import { Alert } from "@/components/ui/alert";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
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
import { formatTimestamp, withQuery } from "@/lib/trade/format";
import type { CounterpartyList } from "@/lib/trade/types";

export const dynamic = "force-dynamic";
export const metadata = { title: "CRM" };

const PAGE_SIZE = 25;

export default async function CrmPage({
  searchParams,
}: {
  searchParams: Promise<{ search?: string; status?: string; cursor?: string }>;
}) {
  const state = await loadSession();
  if (state.status !== "authenticated") return null;

  const params = await searchParams;
  const company = state.session.session.company;
  const canWrite = company?.permissions.includes("trade.write") ?? false;

  const query = new URLSearchParams({ limit: String(PAGE_SIZE) });
  if (params.search) query.set("search", params.search);
  if (params.status) query.set("status", params.status);
  if (params.cursor) query.set("cursor", params.cursor);

  const result = await serverGet<CounterpartyList>(`/counterparties?${query.toString()}`);
  const filters = { search: params.search ?? "", status: params.status ?? "" };

  return (
    <div className="mx-auto max-w-[1320px] space-y-6">
      <header className="flex flex-wrap items-end justify-between gap-4">
        <div>
          <div className="flex items-center gap-3">
            <span className="eyebrow">CRM</span>
            <Badge variant="secondary">Counterparties</Badge>
          </div>
          <h1 className="mt-3 font-display text-[28px] leading-tight tracking-tight text-mist-100">
            Customers &amp; suppliers
          </h1>
          <p className="mt-2 max-w-2xl text-[13px] leading-relaxed text-mist-500">
            Every record belongs to the active company only. Reads are available to all roles;
            changes require the trader permission.
          </p>
        </div>
        <CounterpartyForm csrfToken={state.session.session.csrf_token} canWrite={canWrite} />
      </header>

      <form
        action="/crm"
        method="get"
        className="panel flex flex-wrap items-end gap-3 rounded-xl p-4"
      >
        <div className="min-w-[220px] flex-1 space-y-1.5">
          <label
            htmlFor="crm-search"
            className="block text-[10.5px] uppercase tracking-[0.16em] text-mist-500"
          >
            Search by name
          </label>
          <Input
            id="crm-search"
            name="search"
            defaultValue={filters.search}
            placeholder="Acme"
            maxLength={160}
          />
        </div>
        <div className="space-y-1.5">
          <label
            htmlFor="crm-status"
            className="block text-[10.5px] uppercase tracking-[0.16em] text-mist-500"
          >
            Status
          </label>
          <Select id="crm-status" name="status" defaultValue={filters.status}>
            <option value="">All</option>
            <option value="active">Active</option>
            <option value="archived">Archived</option>
          </Select>
        </div>
        <Button type="submit" size="sm" variant="outline">
          <Search className="size-3.5" aria-hidden />
          Filter
        </Button>
        {filters.search || filters.status ? (
          <Link
            href="/crm"
            className="text-[11.5px] text-mist-500 underline-offset-4 hover:text-mist-300 hover:underline"
          >
            Clear filters
          </Link>
        ) : null}
      </form>

      {!result.ok ? (
        <Alert variant="danger" title="Counterparties unavailable">
          {result.message}
          {result.requestId ? (
            <span className="ml-1 font-mono text-[11px]">({result.requestId})</span>
          ) : null}
        </Alert>
      ) : result.data.items.length === 0 ? (
        <div className="panel rounded-xl p-10 text-center">
          <p className="font-display text-lg text-mist-200">No counterparties yet</p>
          <p className="mx-auto mt-2 max-w-md text-[12.5px] leading-relaxed text-mist-500">
            Create the first customer or supplier to start linking deals. Nothing is pre-seeded;
            every row here comes from the API.
          </p>
        </div>
      ) : (
        <Table>
          <TableHeader>
            <TableRow>
              <TableHead>Name</TableHead>
              <TableHead>Type</TableHead>
              <TableHead>Country</TableHead>
              <TableHead>Contact</TableHead>
              <TableHead>Status</TableHead>
              <TableHead className="text-right">Updated</TableHead>
            </TableRow>
          </TableHeader>
          <TableBody>
            {result.data.items.map((counterparty) => (
              <TableRow key={counterparty.id}>
                <TableCell>
                  <span className="block text-[13px] text-mist-100">{counterparty.name}</span>
                  {counterparty.email ? (
                    <span className="mt-0.5 block text-[11px] text-mist-600">
                      {counterparty.email}
                    </span>
                  ) : null}
                </TableCell>
                <TableCell className="capitalize">{counterparty.type}</TableCell>
                <TableCell>{counterparty.country ?? "—"}</TableCell>
                <TableCell>{counterparty.contact_name ?? "—"}</TableCell>
                <TableCell>
                  <Badge variant={counterparty.status === "active" ? "success" : "outline"}>
                    {counterparty.status}
                  </Badge>
                </TableCell>
                <TableCell className="text-right text-[11.5px] text-mist-500">
                  {formatTimestamp(counterparty.updated_at)}
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
              href={withQuery("/crm", filters)}
              className="text-[11.5px] text-mist-500 hover:text-mist-300"
            >
              First page
            </Link>
          ) : null}
          {result.ok && result.data.has_more && result.data.next_cursor ? (
            <Button asChild variant="outline" size="sm">
              <Link href={withQuery("/crm", { ...filters, cursor: result.data.next_cursor })}>
                Next page
              </Link>
            </Button>
          ) : null}
        </div>
      </div>
    </div>
  );
}

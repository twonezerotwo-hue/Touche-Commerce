import Link from "next/link";
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
import { SourcingStatusBadge } from "@/components/sourcing/status-badge";
import { serverGet } from "@/lib/api/server";
import { loadSession } from "@/lib/auth/session";
import { formatPercent } from "@/lib/sourcing/format";
import { SCENARIO_STATUSES, type PricingScenarioList } from "@/lib/sourcing/types";
import { formatMoney, formatTimestamp, withQuery } from "@/lib/trade/format";

export const dynamic = "force-dynamic";
export const metadata = { title: "Pricing scenarios" };

const PAGE_SIZE = 25;

export default async function PricingListPage({
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

  const result = await serverGet<PricingScenarioList>(`/pricing-scenarios?${query.toString()}`);
  const filters = { status: params.status ?? "" };

  return (
    <div className="mx-auto max-w-[1360px] space-y-5">
      <PageHeader
        eyebrow="Sourcing"
        meta={<Badge variant="secondary">Pricing</Badge>}
        title="Landed-cost scenarios"
        description="Each scenario stores its inputs and its rounded results. A price agreed today does not change because tomorrow's freight invoice arrived — recalculating is an explicit, audited action."
      />

      <div className="panel overflow-hidden">
        <form action="/pricing" method="get" className="flex flex-wrap items-end gap-2 px-4 py-3">
          <div className="space-y-1">
            <label htmlFor="pricing-filter-status" className="eyebrow">
              Status
            </label>
            <Select
              id="pricing-filter-status"
              name="status"
              defaultValue={filters.status}
              className="h-8 w-[180px] text-[12px]"
            >
              <option value="">All statuses</option>
              {SCENARIO_STATUSES.map((status) => (
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
              <Link href="/pricing">Clear</Link>
            </Button>
          ) : null}
        </form>

        <div className="hairline" />

        {!result.ok ? (
          <div className="p-4">
            <Alert variant="danger" title="Scenarios unavailable">
              {result.message}
            </Alert>
          </div>
        ) : result.data.items.length === 0 ? (
          <div className="p-4">
            <EmptyState
              title="No pricing scenarios yet"
              description="Open a received supplier quote and calculate its landed cost."
              className="border-dashed bg-transparent py-10"
            />
          </div>
        ) : null}

        {result.ok && result.data.items.length > 0 ? (
          <Table bare>
            <TableHeader>
              <TableRow>
                <TableHead className="pl-4">Deal / RFQ</TableHead>
                <TableHead>Supplier</TableHead>
                <TableHead>Status</TableHead>
                <TableHead className="text-right">Landed</TableHead>
                <TableHead className="text-right">Sales</TableHead>
                <TableHead className="text-right">Margin</TableHead>
                <TableHead className="pr-4 text-right">Updated</TableHead>
              </TableRow>
            </TableHeader>
            <TableBody>
              {result.data.items.map((scenario) => (
                <TableRow key={scenario.id}>
                  <TableCell className="pl-4">
                    <Link
                      href={`/pricing/${scenario.id}`}
                      className="font-mono text-[11.5px] text-accent-200 transition-colors hover:text-accent-100"
                    >
                      {scenario.deal_reference} · {scenario.rfq_reference}
                    </Link>
                  </TableCell>
                  <TableCell className="max-w-[200px] truncate text-[12px] text-mist-100">
                    {scenario.supplier_name}
                  </TableCell>
                  <TableCell>
                    <SourcingStatusBadge status={scenario.status} />
                  </TableCell>
                  <TableCell className="text-right whitespace-nowrap text-[12px] text-mist-200">
                    {formatMoney(scenario.landed_total, scenario.target_currency)}
                  </TableCell>
                  <TableCell className="text-right whitespace-nowrap text-[12px] text-mist-200">
                    {formatMoney(scenario.sales_total, scenario.target_currency)}
                  </TableCell>
                  <TableCell className="text-right text-[12px] text-mist-300">
                    {formatPercent(scenario.gross_margin_pct)}
                  </TableCell>
                  <TableCell className="pr-4 text-right font-mono text-[10.5px] whitespace-nowrap text-mist-600">
                    {formatTimestamp(scenario.updated_at)}
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
                <Link href={withQuery("/pricing", filters)}>First page</Link>
              </Button>
            ) : null}
            {result.ok && result.data.has_more && result.data.next_cursor ? (
              <Button asChild variant="outline" size="sm">
                <Link href={withQuery("/pricing", { ...filters, cursor: result.data.next_cursor })}>
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

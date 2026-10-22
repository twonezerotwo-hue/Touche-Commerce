import Link from "next/link";
import {
  ArrowUpRight,
  CircleAlert,
  Database,
  Handshake,
  Package,
  Server,
  Users,
} from "lucide-react";

import { DealStatusBadge } from "@/components/trade/status-badge";
import { Alert } from "@/components/ui/alert";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import {
  Table,
  TableBody,
  TableCell,
  TableHead,
  TableHeader,
  TableRow,
} from "@/components/ui/table";
import { fetchContract, fetchLiveness, fetchReadiness } from "@/lib/api/client";
import { serverGet } from "@/lib/api/server";
import { API_URLS } from "@/lib/api/config";
import { loadSession } from "@/lib/auth/session";
import { formatMoney, formatTimestamp } from "@/lib/trade/format";
import type { DashboardSummary } from "@/lib/trade/types";

export const dynamic = "force-dynamic";
export const metadata = { title: "Command Center" };

export default async function CommandCenterPage() {
  const state = await loadSession();
  if (state.status !== "authenticated") return null;

  const { user, session } = state.session;
  const company = session.company;
  const canWrite = company?.permissions.includes("trade.write") ?? false;

  const [summary, live, readiness, contract] = await Promise.all([
    serverGet<DashboardSummary>("/dashboard/summary"),
    fetchLiveness(),
    fetchReadiness(),
    fetchContract(),
  ]);

  const issues: string[] = [];
  if (!live.ok) issues.push(`API unreachable: ${live.message}`);
  if (live.ok && !readiness.ok) issues.push(`Database not ready: ${readiness.message}`);
  if (!contract.ok) issues.push(`OpenAPI contract unavailable: ${contract.message}`);

  return (
    <div className="mx-auto max-w-[1320px] space-y-7">
      <header className="flex flex-wrap items-end justify-between gap-5">
        <div className="max-w-2xl">
          <div className="flex items-center gap-3">
            <span className="eyebrow">Command Center</span>
            <Badge variant="default">Stage 1B</Badge>
          </div>
          <h1 className="mt-3 font-display text-[30px] leading-[1.12] tracking-tight text-mist-100 lg:text-[36px]">
            {greeting()}, {user.display_name.split(" ")[0]}
          </h1>
          <p className="mt-3 max-w-xl text-[13.5px] leading-relaxed text-mist-500">
            Live trade position for {company?.name ?? "your company"}: deals, pipeline, CRM and
            catalogue. Every number below comes from the API for this company only.
          </p>
        </div>
        <div className="flex flex-wrap items-center gap-2">
          <Button asChild variant="outline" size="sm">
            <Link href="/crm">CRM</Link>
          </Button>
          <Button asChild variant="outline" size="sm">
            <Link href="/products">Products</Link>
          </Button>
          <Button asChild size="sm">
            <Link href="/deals">
              <Handshake className="size-3.5" aria-hidden />
              Deals
            </Link>
          </Button>
        </div>
      </header>

      {issues.length > 0 ? (
        <Alert variant="warning" title="Platform attention required">
          <ul className="list-inside list-disc space-y-1">
            {issues.map((issue) => (
              <li key={issue}>{issue}</li>
            ))}
          </ul>
        </Alert>
      ) : null}

      {!summary.ok ? (
        <Alert variant="danger" title="Dashboard unavailable">
          {summary.message}
          {summary.requestId ? (
            <span className="ml-1 font-mono text-[11px]">({summary.requestId})</span>
          ) : null}
        </Alert>
      ) : (
        <DashboardBody summary={summary.data} canWrite={canWrite} />
      )}

      <footer className="flex flex-wrap items-center gap-x-6 gap-y-2 pb-2 text-[11px] text-mist-600">
        <span className="inline-flex items-center gap-1.5">
          <Server className="size-3.5" aria-hidden />
          API {API_URLS.base}
        </span>
        <span className="inline-flex items-center gap-1.5">
          <Database className="size-3.5" aria-hidden />
          PostgreSQL 17 · schema <span className="font-mono text-mist-500">touche</span>
        </span>
        <Link href="/status" className="inline-flex items-center gap-1.5 hover:text-mist-400">
          <ArrowUpRight className="size-3.5" aria-hidden />
          Public status page
        </Link>
      </footer>
    </div>
  );
}

function greeting(): string {
  const hour = new Date().getUTCHours();
  if (hour < 12) return "Good morning";
  if (hour < 18) return "Good afternoon";
  return "Good evening";
}

function DashboardBody({ summary, canWrite }: { summary: DashboardSummary; canWrite: boolean }) {
  const openStatuses = new Set(["DRAFT", "OPEN", "NEGOTIATION"]);
  const openDeals = summary.status_counts
    .filter((item) => openStatuses.has(item.status))
    .reduce((total, item) => total + item.deal_count, 0);

  return (
    <>
      <section className="grid gap-3 sm:grid-cols-2 xl:grid-cols-4">
        <KpiCard
          eyebrow="Deals"
          value={String(summary.deals_total)}
          detail={`${openDeals} open · ${summary.deals_total - openDeals} closed`}
          icon={<Handshake className="size-4 text-gold-400" aria-hidden />}
        />
        <KpiCard
          eyebrow="Open pipeline"
          value={
            summary.pipeline.length === 0
              ? "—"
              : summary.pipeline
                  .map((item) => formatMoney(item.total_value, item.currency))
                  .join(" · ")
          }
          detail={
            summary.pipeline.length === 0
              ? "No open deals"
              : `${summary.pipeline.reduce((total, item) => total + item.deal_count, 0)} deals`
          }
          icon={<CircleAlert className="size-4 text-jade-400" aria-hidden />}
        />
        <KpiCard
          eyebrow="Counterparties"
          value={String(summary.counterparties_total)}
          detail={`${summary.counterparties_active} active`}
          icon={<Users className="size-4 text-mist-300" aria-hidden />}
        />
        <KpiCard
          eyebrow="Products"
          value={String(summary.products_total)}
          detail={`${summary.products_active} active`}
          icon={<Package className="size-4 text-mist-300" aria-hidden />}
        />
      </section>

      <section className="grid gap-5 lg:grid-cols-[minmax(0,2fr)_minmax(0,1fr)]">
        <div className="space-y-5">
          <div className="panel rounded-xl p-6">
            <div className="flex flex-wrap items-center justify-between gap-3">
              <div>
                <span className="eyebrow">Recent deals</span>
                <h2 className="mt-1 font-display text-lg text-mist-100">Latest activity</h2>
              </div>
              <Button asChild variant="outline" size="sm">
                <Link href="/deals">All deals</Link>
              </Button>
            </div>
            <div className="mt-4">
              {summary.recent_deals.length === 0 ? (
                <div className="rounded-lg border border-dashed border-white/10 px-4 py-8 text-center">
                  <p className="text-[12.5px] text-mist-400">No deals yet in this company.</p>
                  <p className="mt-1 text-[11.5px] text-mist-600">
                    {canWrite
                      ? "Create the first deal to start tracking pipeline."
                      : "A trader can create the first deal."}
                  </p>
                  {canWrite ? (
                    <Button asChild size="sm" className="mt-3">
                      <Link href="/deals/new">New deal</Link>
                    </Button>
                  ) : null}
                </div>
              ) : (
                <Table>
                  <TableHeader>
                    <TableRow>
                      <TableHead>Reference</TableHead>
                      <TableHead>Title</TableHead>
                      <TableHead>Status</TableHead>
                      <TableHead className="text-right">Value</TableHead>
                    </TableRow>
                  </TableHeader>
                  <TableBody>
                    {summary.recent_deals.map((deal) => (
                      <TableRow key={deal.id}>
                        <TableCell>
                          <Link
                            href={`/deals/${deal.id}`}
                            className="font-mono text-[12px] text-gold-200 hover:text-gold-100"
                          >
                            {deal.reference}
                          </Link>
                        </TableCell>
                        <TableCell className="max-w-[240px] truncate text-mist-100">
                          {deal.title}
                        </TableCell>
                        <TableCell>
                          <DealStatusBadge status={deal.status} />
                        </TableCell>
                        <TableCell className="text-right">
                          {formatMoney(deal.total_value, deal.currency)}
                        </TableCell>
                      </TableRow>
                    ))}
                  </TableBody>
                </Table>
              )}
            </div>
          </div>

          <div className="panel rounded-xl p-6">
            <span className="eyebrow">Status distribution</span>
            <ul className="mt-4 space-y-2.5">
              {summary.status_counts.map((item) => (
                <li key={item.status} className="flex items-center justify-between gap-3">
                  <span className="flex items-center gap-2.5">
                    <DealStatusBadge status={item.status} />
                    <span className="text-[11.5px] text-mist-500">{item.deal_count} deals</span>
                  </span>
                  <span className="text-[12px] text-mist-300">
                    {formatMoney(item.total_value, summary.pipeline[0]?.currency ?? "USD")}
                  </span>
                </li>
              ))}
            </ul>
            <p className="mt-4 text-[10.5px] leading-relaxed text-mist-600">
              Totals are computed per deal in the database. Mixed-currency companies see each
              currency separately in the pipeline card above.
            </p>
          </div>
        </div>

        <aside className="panel h-fit rounded-xl p-6">
          <span className="eyebrow">Audit activity</span>
          <ol className="mt-4 space-y-4">
            {summary.recent_activity.length === 0 ? (
              <li className="text-[12px] text-mist-500">No audit rows yet for this company.</li>
            ) : (
              summary.recent_activity.map((entry, index) => (
                <li
                  key={`${entry.action}-${entry.occurred_at}-${index}`}
                  className="border-l border-white/10 pl-4"
                >
                  <p className="font-mono text-[11px] text-mist-300">{entry.action}</p>
                  <p className="mt-0.5 text-[10.5px] text-mist-600">
                    {entry.outcome} · {formatTimestamp(entry.occurred_at)}
                  </p>
                </li>
              ))
            )}
          </ol>
          <p className="mt-5 text-[10.5px] leading-relaxed text-mist-600">
            Read-only view of the append-only audit trail. Rows cannot be edited or deleted by the
            application role.
          </p>
        </aside>
      </section>
    </>
  );
}

function KpiCard({
  eyebrow,
  value,
  detail,
  icon,
}: {
  eyebrow: string;
  value: string;
  detail: string;
  icon: React.ReactNode;
}) {
  return (
    <div className="panel rounded-xl p-5">
      <div className="flex items-center justify-between gap-3">
        <span className="eyebrow">{eyebrow}</span>
        {icon}
      </div>
      <p className="mt-3 font-display text-[22px] leading-tight text-mist-100">{value}</p>
      <p className="mt-1 text-[11px] text-mist-600">{detail}</p>
    </div>
  );
}

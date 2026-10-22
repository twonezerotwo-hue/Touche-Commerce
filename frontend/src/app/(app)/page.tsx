import Link from "next/link";
import type { ReactNode } from "react";
import {
  ArrowRight,
  ArrowUpRight,
  Banknote,
  ClipboardCheck,
  Database,
  Handshake,
  Package,
  Server,
  ShieldCheck,
  Truck,
  Users,
} from "lucide-react";

import { DealStatusBadge } from "@/components/trade/status-badge";
import { Alert } from "@/components/ui/alert";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { Meter } from "@/components/ui/meter";
import { PageHeader } from "@/components/ui/page-header";
import { Stat } from "@/components/ui/stat";
import {
  Table,
  TableBody,
  TableCell,
  TableHead,
  TableHeader,
  TableRow,
} from "@/components/ui/table";
import {
  fetchContract,
  fetchLiveness,
  fetchReadiness,
  type ApiResult,
  type HealthLive,
  type HealthReadiness,
  type OpenApiContract,
} from "@/lib/api/client";
import { API_URLS } from "@/lib/api/config";
import { serverGet } from "@/lib/api/server";
import { loadSession } from "@/lib/auth/session";
import type { OperationsSummary } from "@/lib/operations/types";
import { formatDate, formatMoney, formatTimestamp } from "@/lib/trade/format";
import type { DashboardSummary } from "@/lib/trade/types";
import { cn } from "@/lib/utils";

export const dynamic = "force-dynamic";
export const metadata = { title: "Command Center" };

const OPEN_STATUSES = new Set(["DRAFT", "OPEN", "NEGOTIATION"]);

export default async function CommandCenterPage() {
  const state = await loadSession();
  if (state.status !== "authenticated") return null;

  const { user, session } = state.session;
  const company = session.company;
  const canWrite = company?.permissions.includes("trade.write") ?? false;

  const [summary, operations, live, readiness, contract] = await Promise.all([
    serverGet<DashboardSummary>("/dashboard/summary"),
    serverGet<OperationsSummary>("/operations/summary"),
    fetchLiveness(),
    fetchReadiness(),
    fetchContract(),
  ]);

  const issues: string[] = [];
  if (!live.ok) issues.push(`API unreachable: ${live.message}`);
  if (live.ok && !readiness.ok) issues.push(`Database not ready: ${readiness.message}`);
  if (!contract.ok) issues.push(`OpenAPI contract unavailable: ${contract.message}`);

  const firstName = user.display_name.split(" ")[0];

  return (
    <div className="mx-auto max-w-[1360px] space-y-6">
      <PageHeader
        eyebrow="Command Center"
        meta={
          <>
            <Badge variant="info" dot>
              Live data
            </Badge>
            {summary.ok ? (
              <span className="font-mono text-[10px] text-mist-600">
                {formatTimestamp(summary.data.generated_at)}
              </span>
            ) : null}
          </>
        }
        title={
          <>
            {greeting()}, <span className="text-accent-200">{firstName}</span>
          </>
        }
        description={
          <>
            Live trade position for {company?.name ?? "your company"}. Every figure is read from the
            platform database, scoped to your membership — nothing is inferred in the browser.
          </>
        }
        actions={
          <>
            <Button asChild variant="outline" size="sm">
              <Link href="/crm">
                <Users className="size-3.5" aria-hidden />
                CRM
              </Link>
            </Button>
            <Button asChild variant="outline" size="sm">
              <Link href="/products">
                <Package className="size-3.5" aria-hidden />
                Products
              </Link>
            </Button>
            <Button asChild size="sm">
              <Link href="/deals">
                <Handshake className="size-3.5" aria-hidden />
                Deals
              </Link>
            </Button>
          </>
        }
      />

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

      <OperationsStrip operations={operations} />

      <PlatformHealth live={live} readiness={readiness} contract={contract} />

      <footer className="flex flex-wrap items-center gap-x-6 gap-y-2 pb-2 text-[10.5px] text-mist-600">
        <span className="inline-flex items-center gap-1.5">
          <Server className="size-3.5" aria-hidden />
          API <span className="font-mono">{API_URLS.base}</span>
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
  const openDealCount = summary.status_counts
    .filter((item) => OPEN_STATUSES.has(item.status))
    .reduce((total, item) => total + item.deal_count, 0);
  const closedDealCount = summary.deals_total - openDealCount;
  const pipelineDeals = summary.pipeline.reduce((total, item) => total + item.deal_count, 0);
  const primaryPipeline = summary.pipeline[0];

  return (
    <div className="space-y-4">
      <section className="animate-enter grid gap-3 sm:grid-cols-2 xl:grid-cols-4">
        <Stat
          label="Deals"
          value={summary.deals_total}
          detail={`${openDealCount} open · ${closedDealCount} closed`}
          share={summary.deals_total === 0 ? 0 : (openDealCount / summary.deals_total) * 100}
          icon={<Handshake className="size-3.5" aria-hidden />}
        />
        <Stat
          label="Open pipeline"
          value={
            !primaryPipeline
              ? "—"
              : summary.pipeline.length === 1
                ? formatMoney(primaryPipeline.total_value, primaryPipeline.currency)
                : `${summary.pipeline.length} currencies`
          }
          detail={
            !primaryPipeline
              ? "No open deals yet"
              : `${pipelineDeals} open ${pipelineDeals === 1 ? "deal" : "deals"}${
                  summary.pipeline.length > 1 ? ` across ${summary.pipeline.length} currencies` : ""
                }`
          }
          share={
            summary.deals_total === 0 ? 0 : (pipelineDeals / Math.max(summary.deals_total, 1)) * 100
          }
          tone="accent"
          icon={<Banknote className="size-3.5" aria-hidden />}
        />
        <Stat
          label="Counterparties"
          value={summary.counterparties_total}
          detail={`${summary.counterparties_active} active in CRM`}
          share={
            summary.counterparties_total === 0
              ? 0
              : (summary.counterparties_active / summary.counterparties_total) * 100
          }
          tone="jade"
          icon={<Users className="size-3.5" aria-hidden />}
        />
        <Stat
          label="Products"
          value={summary.products_total}
          detail={`${summary.products_active} active SKUs`}
          share={
            summary.products_total === 0
              ? 0
              : (summary.products_active / summary.products_total) * 100
          }
          tone="neutral"
          icon={<Package className="size-3.5" aria-hidden />}
        />
      </section>

      <section className="grid gap-4 xl:grid-cols-[minmax(0,1.65fr)_minmax(0,1fr)]">
        <div className="panel animate-enter-late flex flex-col overflow-hidden">
          <div className="flex flex-wrap items-end justify-between gap-3 px-5 pt-4.5 pb-4">
            <div>
              <p className="eyebrow">Recent deals</p>
              <h2 className="mt-1.5 text-[14px] font-medium text-mist-100">
                Newest in this workspace
              </h2>
            </div>
            <Link
              href="/deals"
              className="inline-flex items-center gap-1.5 text-[11px] text-mist-500 transition-colors hover:text-accent-200"
            >
              All deals
              <ArrowRight className="size-3.5" aria-hidden />
            </Link>
          </div>
          <div className="hairline" />
          {summary.recent_deals.length === 0 ? (
            <div className="flex flex-1 flex-col items-center justify-center px-6 py-12 text-center">
              <span className="mb-3 flex size-10 items-center justify-center rounded-full border border-white/10 bg-white/[0.03]">
                <Handshake className="size-4 text-mist-500" aria-hidden />
              </span>
              <p className="text-[12.5px] text-mist-300">No deals yet in this company</p>
              <p className="mt-1 max-w-xs text-[11px] leading-relaxed text-mist-600">
                {canWrite
                  ? "Create the first deal to start a recorded, auditable pipeline."
                  : "A member with trade.write can create the first deal."}
              </p>
              {canWrite ? (
                <Button asChild size="sm" className="mt-4">
                  <Link href="/deals/new">New deal</Link>
                </Button>
              ) : null}
            </div>
          ) : (
            <div className="flex-1">
              <Table bare>
                <TableHeader>
                  <TableRow>
                    <TableHead className="pl-5">Reference</TableHead>
                    <TableHead>Counterparty</TableHead>
                    <TableHead>Status</TableHead>
                    <TableHead>Close</TableHead>
                    <TableHead className="pr-5 text-right">Value</TableHead>
                  </TableRow>
                </TableHeader>
                <TableBody>
                  {summary.recent_deals.map((deal) => (
                    <TableRow key={deal.id}>
                      <TableCell className="pl-5">
                        <Link
                          href={`/deals/${deal.id}`}
                          className="font-mono text-[11.5px] text-accent-200 transition-colors hover:text-accent-100"
                        >
                          {deal.reference}
                        </Link>
                      </TableCell>
                      <TableCell className="max-w-[220px]">
                        <span className="block truncate text-[12px] text-mist-100">
                          {deal.title}
                        </span>
                        <span className="mt-0.5 block truncate text-[10.5px] text-mist-600">
                          {deal.counterparty_name}
                        </span>
                      </TableCell>
                      <TableCell>
                        <DealStatusBadge status={deal.status} />
                      </TableCell>
                      <TableCell className="text-[11.5px] whitespace-nowrap text-mist-500">
                        {formatDate(deal.expected_close_date)}
                      </TableCell>
                      <TableCell className="pr-5 text-right text-[12px] whitespace-nowrap text-mist-200">
                        <span className="data-value">
                          {formatMoney(deal.total_value, deal.currency)}
                        </span>
                      </TableCell>
                    </TableRow>
                  ))}
                </TableBody>
              </Table>
            </div>
          )}
        </div>

        <div className="space-y-4">
          <PipelineCard summary={summary} />
          <StatusCard summary={summary} />
        </div>
      </section>

      <ActivityCard summary={summary} />
    </div>
  );
}

function PipelineCard({ summary }: { summary: DashboardSummary }) {
  const totalDeals = summary.pipeline.reduce((total, item) => total + item.deal_count, 0);

  return (
    <div className="panel overflow-hidden">
      <div className="flex items-start justify-between gap-3 px-5 pt-4.5 pb-1">
        <div>
          <p className="eyebrow">Open pipeline</p>
          <h2 className="mt-1.5 text-[14px] font-medium text-mist-100">Value by currency</h2>
        </div>
        <Badge variant="secondary">{totalDeals} deals</Badge>
      </div>

      {summary.pipeline.length === 0 ? (
        <p className="px-5 py-5 text-[11.5px] leading-relaxed text-mist-600">
          No draft, open or negotiating deal carries value yet.
        </p>
      ) : (
        <ul className="space-y-4 px-5 py-4">
          {summary.pipeline.map((item) => {
            const share = totalDeals === 0 ? 0 : (item.deal_count / totalDeals) * 100;
            return (
              <li key={item.currency}>
                <div className="flex items-baseline justify-between gap-3">
                  <span className="font-mono text-[10.5px] tracking-[0.12em] text-mist-500">
                    {item.currency}
                  </span>
                  <span className="data-value text-[14px] text-mist-100">
                    {formatMoney(item.total_value, item.currency)}
                  </span>
                </div>
                <Meter value={share} tone="accent" className="mt-2" />
                <div className="mt-1.5 flex items-center justify-between text-[10px] text-mist-600">
                  <span>
                    {item.deal_count} {item.deal_count === 1 ? "deal" : "deals"}
                  </span>
                  <span className="data-value">{share.toFixed(0)}% of open deals</span>
                </div>
              </li>
            );
          })}
        </ul>
      )}

      <div className="border-t border-white/[0.06] px-5 py-2.5">
        <p className="text-[10px] leading-relaxed text-mist-600">
          Currencies are never summed together — each row is its own total.
        </p>
      </div>
    </div>
  );
}

function StatusCard({ summary }: { summary: DashboardSummary }) {
  return (
    <div className="panel overflow-hidden">
      <div className="flex items-start justify-between gap-3 px-5 pt-4.5 pb-3">
        <div>
          <p className="eyebrow">Status distribution</p>
          <h2 className="mt-1.5 text-[14px] font-medium text-mist-100">Where deals stand</h2>
        </div>
        <span className="data-value text-[11px] text-mist-500">{summary.deals_total} total</span>
      </div>
      <div className="hairline" />
      <ul className="space-y-3 px-5 py-4">
        {summary.status_counts.map((item) => {
          const share =
            summary.deals_total === 0 ? 0 : (item.deal_count / summary.deals_total) * 100;
          const tone =
            item.status === "WON"
              ? "jade"
              : item.status === "LOST" || item.status === "CANCELLED"
                ? "crimson"
                : item.status === "NEGOTIATION"
                  ? "amber"
                  : "accent";
          return (
            <li key={item.status}>
              <div className="flex items-center justify-between gap-3">
                <DealStatusBadge status={item.status} />
                <span className="data-value text-[11.5px] text-mist-300">{item.deal_count}</span>
              </div>
              <Meter value={share} tone={tone} className="mt-2 h-0.5" />
            </li>
          );
        })}
      </ul>
      <div className="border-t border-white/[0.06] px-5 py-2.5">
        <p className="text-[10px] leading-relaxed text-mist-600">
          Counts only. Per-status values are omitted because a company may trade in several
          currencies.
        </p>
      </div>
    </div>
  );
}

function ActivityCard({ summary }: { summary: DashboardSummary }) {
  return (
    <div className="panel overflow-hidden">
      <div className="flex flex-wrap items-center justify-between gap-3 px-5 pt-4.5 pb-3">
        <div>
          <p className="eyebrow">Audit trail</p>
          <h2 className="mt-1.5 text-[14px] font-medium text-mist-100">Recent activity</h2>
        </div>
        <Badge variant="secondary">{summary.recent_activity.length} events</Badge>
      </div>
      <div className="hairline" />
      {summary.recent_activity.length === 0 ? (
        <p className="px-5 py-6 text-[11.5px] text-mist-600">
          No audit rows yet. Every write records one, so this list fills as the team works.
        </p>
      ) : (
        <ol className="divide-y divide-white/[0.045]">
          {summary.recent_activity.map((entry, index) => (
            <li
              key={`${entry.action}-${entry.occurred_at}-${index}`}
              className="flex flex-wrap items-start gap-x-4 gap-y-1 px-5 py-3 transition-colors hover:bg-white/[0.018]"
            >
              <span
                className={cn(
                  "status-dot mt-1.5 shrink-0",
                  entry.outcome === "success" ? "bg-jade-400" : "bg-amber-400",
                )}
                aria-hidden
              />
              <div className="min-w-0 flex-1">
                <p className="truncate font-mono text-[11px] text-mist-200">{entry.action}</p>
                <p className="mt-0.5 truncate text-[10px] text-mist-600">
                  {entry.resource_type ?? "platform"}
                  {entry.resource_id ? ` · ${entry.resource_id.slice(0, 8)}` : ""}
                </p>
              </div>
              <div className="text-right">
                <p className="text-[10.5px] text-mist-400">{entry.outcome}</p>
                <p className="data-value mt-0.5 font-mono text-[9.5px] text-mist-600">
                  {formatTimestamp(entry.occurred_at)}
                </p>
              </div>
            </li>
          ))}
        </ol>
      )}
      <div className="border-t border-white/[0.06] px-5 py-2.5">
        <p className="text-[10px] leading-relaxed text-mist-600">
          Read-only view of the append-only audit log. Application roles cannot edit or delete rows.
        </p>
      </div>
    </div>
  );
}

function PlatformHealth({
  live,
  readiness,
  contract,
}: {
  live: ApiResult<HealthLive>;
  readiness: ApiResult<HealthReadiness>;
  contract: ApiResult<OpenApiContract>;
}) {
  return (
    <section className="panel overflow-hidden">
      <div className="flex flex-wrap items-center justify-between gap-3 px-5 pt-4.5 pb-3">
        <div>
          <p className="eyebrow">Platform health</p>
          <h2 className="mt-1.5 text-[14px] font-medium text-mist-100">Observed on this request</h2>
        </div>
        <span className="inline-flex items-center gap-1.5 text-[10px] tracking-[0.08em] text-mist-500 uppercase">
          <ShieldCheck className="size-3 text-jade-400" aria-hidden />
          Probed live
        </span>
      </div>
      <div className="hairline" />
      <div className="grid divide-y divide-white/[0.05] sm:grid-cols-3 sm:divide-x sm:divide-y-0">
        <HealthCell
          ok={live.ok}
          label="API liveness"
          detail={live.ok ? `Responded in ${live.latencyMs} ms` : live.message}
          endpoint="GET /api/v1/health/live"
        />
        <HealthCell
          ok={readiness.ok}
          label="Database readiness"
          detail={
            readiness.ok
              ? `PostgreSQL probe passed in ${readiness.latencyMs} ms`
              : readiness.message
          }
          endpoint="GET /api/v1/health/ready"
        />
        <HealthCell
          ok={contract.ok}
          label="OpenAPI contract"
          detail={
            contract.ok
              ? `${contract.data.operationCount} operations · OpenAPI ${contract.data.version ?? "3"}`
              : contract.message
          }
          endpoint="GET /api/v1/openapi.json"
        />
      </div>
    </section>
  );
}

function HealthCell({
  ok,
  label,
  detail,
  endpoint,
}: {
  ok: boolean;
  label: string;
  detail: string;
  endpoint: string;
}) {
  return (
    <div className="flex items-start gap-3 px-5 py-4">
      <span
        className={cn("status-dot mt-1.5 shrink-0", ok ? "bg-jade-400" : "bg-crimson-400")}
        aria-hidden
      />
      <div className="min-w-0 flex-1">
        <p className="text-[12px] text-mist-200">{label}</p>
        <p className="mt-0.5 text-[10.5px] leading-relaxed text-mist-500">{detail}</p>
        <p className="mt-1.5 truncate font-mono text-[9.5px] text-mist-600">{endpoint}</p>
      </div>
      <span
        className={cn(
          "shrink-0 rounded-full px-1.5 py-px text-[9px] tracking-[0.1em] uppercase",
          ok ? "bg-jade-400/10 text-jade-400" : "bg-crimson-400/10 text-crimson-400",
        )}
      >
        {ok ? "ok" : "fail"}
      </span>
    </div>
  );
}

function OperationsStrip({ operations }: { operations: ApiResult<OperationsSummary> }) {
  if (!operations.ok) {
    return (
      <Alert variant="warning" title="Operations summary unavailable">
        {operations.message}
      </Alert>
    );
  }

  const data = operations.data;
  const primary = data.order_value_by_currency[0];

  return (
    <section className="panel animate-enter overflow-hidden">
      <div className="flex flex-wrap items-center justify-between gap-3 px-5 pt-4.5 pb-3">
        <div>
          <p className="eyebrow">Execution</p>
          <h2 className="mt-1.5 text-[14px] font-medium text-mist-100">
            Orders, shipments and documents
          </h2>
        </div>
        <div className="flex flex-wrap items-center gap-3 text-[10.5px]">
          <Link href="/orders" className="text-accent-200 hover:text-accent-100">
            Orders
          </Link>
          <Link href="/shipments" className="text-accent-200 hover:text-accent-100">
            Shipments
          </Link>
          <Link href="/documents" className="text-accent-200 hover:text-accent-100">
            Documents
          </Link>
          <span className="font-mono text-mist-600">{formatTimestamp(data.generated_at)}</span>
        </div>
      </div>
      <div className="hairline" />
      <div className="grid divide-y divide-white/[0.05] sm:grid-cols-2 xl:grid-cols-5 sm:divide-x sm:divide-y-0">
        <OperationsCell
          label="Orders created"
          value={data.orders_total}
          detail={
            primary
              ? `${formatMoney(primary.total_value, primary.currency)}${data.order_value_by_currency.length > 1 ? ` +${data.order_value_by_currency.length - 1} currencies` : ""}`
              : "No orders yet"
          }
          href="/orders"
          icon={<ClipboardCheck className="size-3.5" aria-hidden />}
        />
        <OperationsCell
          label="In fulfillment"
          value={data.orders_in_fulfillment}
          detail={`${data.orders_confirmed} confirmed · ${data.orders_fulfilled} fulfilled`}
          href="/orders"
          icon={<Package className="size-3.5" aria-hidden />}
        />
        <OperationsCell
          label="Active shipments"
          value={data.active_shipments}
          detail={`${data.delivered_shipments} delivered`}
          href="/shipments"
          icon={<Truck className="size-3.5" aria-hidden />}
        />
        <OperationsCell
          label="Delayed shipments"
          value={data.delayed_shipments}
          detail="Documented ETA has passed"
          href="/shipments"
          tone={data.delayed_shipments > 0 ? "danger" : "neutral"}
        />
        <OperationsCell
          label="Missing evidence"
          value={data.delivered_shipments_without_evidence}
          detail={`${data.documents_total} active documents on file`}
          href="/documents"
          tone={data.delivered_shipments_without_evidence > 0 ? "warning" : "neutral"}
        />
      </div>
    </section>
  );
}

function OperationsCell({
  label,
  value,
  detail,
  href,
  tone = "neutral",
  icon,
}: {
  label: string;
  value: number;
  detail: string;
  href: string;
  tone?: "neutral" | "warning" | "danger";
  icon?: ReactNode;
}) {
  return (
    <div className="px-5 py-4">
      <p className="flex items-center gap-1.5 text-[10px] tracking-[0.08em] text-mist-500 uppercase">
        {icon}
        {label}
      </p>
      <p
        className={cn(
          "data-value mt-1.5 text-[22px] font-medium",
          tone === "danger"
            ? "text-crimson-400"
            : tone === "warning"
              ? "text-amber-400"
              : "text-mist-100",
        )}
      >
        {value}
      </p>
      <p className="mt-1 text-[10.5px] leading-relaxed text-mist-500">{detail}</p>
      <Link
        href={href}
        className="mt-2 inline-flex items-center gap-1 text-[10.5px] text-accent-200 hover:text-accent-100"
      >
        Open
        <ArrowRight className="size-3" aria-hidden />
      </Link>
    </div>
  );
}

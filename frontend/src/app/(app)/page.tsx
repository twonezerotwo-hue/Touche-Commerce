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
import { getServerT, type ServerTranslator } from "@/lib/i18n/server";
import type { OperationsSummary } from "@/lib/operations/types";
import { formatDate, formatMoney, formatTimestamp } from "@/lib/trade/format";
import type { DashboardSummary } from "@/lib/trade/types";
import { cn } from "@/lib/utils";

export const dynamic = "force-dynamic";
export const metadata = { title: "Command Center" };

type T = ServerTranslator["t"];

const OPEN_STATUSES = new Set(["DRAFT", "OPEN", "NEGOTIATION"]);

export default async function CommandCenterPage() {
  const state = await loadSession();
  if (state.status !== "authenticated") return null;
  const { t } = await getServerT();

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
  if (!live.ok) issues.push(t("dashIssueApi", { message: live.message }));
  if (live.ok && !readiness.ok) issues.push(t("dashIssueDatabase", { message: readiness.message }));
  if (!contract.ok) issues.push(t("dashIssueContract", { message: contract.message }));

  const firstName = user.display_name.split(" ")[0];

  return (
    <div className="mx-auto max-w-[1360px] space-y-6">
      <PageHeader
        eyebrow={t("dashEyebrow")}
        meta={
          <>
            <Badge variant="info" dot>
              {t("dashLive")}
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
            {greeting(t)}, <span className="text-accent-200">{firstName}</span>
          </>
        }
        description={t("dashDescription", { company: company?.name ?? t("dashYourCompany") })}
        actions={
          <>
            <Button asChild variant="outline" size="sm">
              <Link href="/crm">
                <Users className="size-3.5" aria-hidden />
                {t("dashActionCrm")}
              </Link>
            </Button>
            <Button asChild variant="outline" size="sm">
              <Link href="/products">
                <Package className="size-3.5" aria-hidden />
                {t("dashActionProducts")}
              </Link>
            </Button>
            <Button asChild size="sm">
              <Link href="/deals">
                <Handshake className="size-3.5" aria-hidden />
                {t("dashActionDeals")}
              </Link>
            </Button>
          </>
        }
      />

      {issues.length > 0 ? (
        <Alert variant="warning" title={t("dashAttention")}>
          <ul className="list-inside list-disc space-y-1">
            {issues.map((issue) => (
              <li key={issue}>{issue}</li>
            ))}
          </ul>
        </Alert>
      ) : null}

      {!summary.ok ? (
        <Alert variant="danger" title={t("dashUnavailable")}>
          {summary.message}
          {summary.requestId ? (
            <span className="ml-1 font-mono text-[11px]">({summary.requestId})</span>
          ) : null}
        </Alert>
      ) : (
        <DashboardBody summary={summary.data} canWrite={canWrite} t={t} />
      )}

      <OperationsStrip operations={operations} t={t} />

      <PlatformHealth live={live} readiness={readiness} contract={contract} t={t} />

      <footer className="flex flex-wrap items-center gap-x-6 gap-y-2 pb-2 text-[10.5px] text-mist-600">
        <span className="inline-flex items-center gap-1.5">
          <Server className="size-3.5" aria-hidden />
          API <span className="font-mono">{API_URLS.base}</span>
        </span>
        <span className="inline-flex items-center gap-1.5">
          <Database className="size-3.5" aria-hidden />
          {t("dashFooterSchema")} <span className="font-mono text-mist-500">touche</span>
        </span>
        <Link href="/status" className="inline-flex items-center gap-1.5 hover:text-mist-400">
          <ArrowUpRight className="size-3.5" aria-hidden />
          {t("dashPublicStatus")}
        </Link>
      </footer>
    </div>
  );
}

function greeting(t: T): string {
  const hour = new Date().getUTCHours();
  if (hour < 12) return t("dashGreetingMorning");
  if (hour < 18) return t("dashGreetingAfternoon");
  return t("dashGreetingEvening");
}

function DashboardBody({
  summary,
  canWrite,
  t,
}: {
  summary: DashboardSummary;
  canWrite: boolean;
  t: T;
}) {
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
          label={t("statDeals")}
          value={summary.deals_total}
          detail={t("statDealsDetail", { open: openDealCount, closed: closedDealCount })}
          share={summary.deals_total === 0 ? 0 : (openDealCount / summary.deals_total) * 100}
          icon={<Handshake className="size-3.5" aria-hidden />}
        />
        <Stat
          label={t("statPipeline")}
          value={
            !primaryPipeline
              ? "—"
              : summary.pipeline.length === 1
                ? formatMoney(primaryPipeline.total_value, primaryPipeline.currency)
                : t("statCurrencies", { count: summary.pipeline.length })
          }
          detail={
            !primaryPipeline
              ? t("statNoOpen")
              : summary.pipeline.length > 1
                ? t("statAcross", {
                    detail:
                      pipelineDeals === 1
                        ? t("statOpenDealOne")
                        : t("statOpenDealMany", { count: pipelineDeals }),
                    count: summary.pipeline.length,
                  })
                : pipelineDeals === 1
                  ? t("statOpenDealOne")
                  : t("statOpenDealMany", { count: pipelineDeals })
          }
          share={
            summary.deals_total === 0 ? 0 : (pipelineDeals / Math.max(summary.deals_total, 1)) * 100
          }
          tone="accent"
          icon={<Banknote className="size-3.5" aria-hidden />}
        />
        <Stat
          label={t("statCounterparties")}
          value={summary.counterparties_total}
          detail={t("statActiveCrm", { count: summary.counterparties_active })}
          share={
            summary.counterparties_total === 0
              ? 0
              : (summary.counterparties_active / summary.counterparties_total) * 100
          }
          tone="jade"
          icon={<Users className="size-3.5" aria-hidden />}
        />
        <Stat
          label={t("statProducts")}
          value={summary.products_total}
          detail={t("statActiveSkus", { count: summary.products_active })}
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
              <p className="eyebrow">{t("dashRecentEyebrow")}</p>
              <h2 className="mt-1.5 text-[14px] font-medium text-mist-100">
                {t("dashRecentTitle")}
              </h2>
            </div>
            <Link
              href="/deals"
              className="inline-flex items-center gap-1.5 text-[11px] text-mist-500 transition-colors hover:text-accent-200"
            >
              {t("dashAllDeals")}
              <ArrowRight className="size-3.5" aria-hidden />
            </Link>
          </div>
          <div className="hairline" />
          {summary.recent_deals.length === 0 ? (
            <div className="flex flex-1 flex-col items-center justify-center px-6 py-12 text-center">
              <span className="mb-3 flex size-10 items-center justify-center rounded-full border border-white/10 bg-white/[0.03]">
                <Handshake className="size-4 text-mist-500" aria-hidden />
              </span>
              <p className="text-[12.5px] text-mist-300">{t("dashNoDeals")}</p>
              <p className="mt-1 max-w-xs text-[11px] leading-relaxed text-mist-600">
                {canWrite ? t("dashNoDealsWrite") : t("dashNoDealsRead")}
              </p>
              {canWrite ? (
                <Button asChild size="sm" className="mt-4">
                  <Link href="/deals/new">{t("dashNewDeal")}</Link>
                </Button>
              ) : null}
            </div>
          ) : (
            <div className="flex-1">
              <Table bare>
                <TableHeader>
                  <TableRow>
                    <TableHead className="pl-5">{t("columnReference")}</TableHead>
                    <TableHead>{t("dashColCounterparty")}</TableHead>
                    <TableHead>{t("columnStatus")}</TableHead>
                    <TableHead>{t("dashColClose")}</TableHead>
                    <TableHead className="pr-5 text-right">{t("dashColValue")}</TableHead>
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
          <PipelineCard summary={summary} t={t} />
          <StatusCard summary={summary} t={t} />
        </div>
      </section>

      <ActivityCard summary={summary} t={t} />
    </div>
  );
}

function PipelineCard({ summary, t }: { summary: DashboardSummary; t: T }) {
  const totalDeals = summary.pipeline.reduce((total, item) => total + item.deal_count, 0);

  return (
    <div className="panel overflow-hidden">
      <div className="flex items-start justify-between gap-3 px-5 pt-4.5 pb-1">
        <div>
          <p className="eyebrow">{t("pipeEyebrow")}</p>
          <h2 className="mt-1.5 text-[14px] font-medium text-mist-100">{t("pipeTitle")}</h2>
        </div>
        <Badge variant="secondary">
          {t(totalDeals === 1 ? "dealCountOne" : "dealCountMany", { count: totalDeals })}
        </Badge>
      </div>

      {summary.pipeline.length === 0 ? (
        <p className="px-5 py-5 text-[11.5px] leading-relaxed text-mist-600">{t("pipeEmpty")}</p>
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
                    {t(item.deal_count === 1 ? "dealCountOne" : "dealCountMany", {
                      count: item.deal_count,
                    })}
                  </span>
                  <span className="data-value">
                    {t("pipeShare", { percent: share.toFixed(0) })}
                  </span>
                </div>
              </li>
            );
          })}
        </ul>
      )}

      <div className="border-t border-white/[0.06] px-5 py-2.5">
        <p className="text-[10px] leading-relaxed text-mist-600">{t("pipeNote")}</p>
      </div>
    </div>
  );
}

function StatusCard({ summary, t }: { summary: DashboardSummary; t: T }) {
  return (
    <div className="panel overflow-hidden">
      <div className="flex items-start justify-between gap-3 px-5 pt-4.5 pb-3">
        <div>
          <p className="eyebrow">{t("statusEyebrow")}</p>
          <h2 className="mt-1.5 text-[14px] font-medium text-mist-100">{t("statusTitle")}</h2>
        </div>
        <span className="data-value text-[11px] text-mist-500">
          {t("statusTotal", { count: summary.deals_total })}
        </span>
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
        <p className="text-[10px] leading-relaxed text-mist-600">{t("statusNote")}</p>
      </div>
    </div>
  );
}

function ActivityCard({ summary, t }: { summary: DashboardSummary; t: T }) {
  return (
    <div className="panel overflow-hidden">
      <div className="flex flex-wrap items-center justify-between gap-3 px-5 pt-4.5 pb-3">
        <div>
          <p className="eyebrow">{t("actEyebrow")}</p>
          <h2 className="mt-1.5 text-[14px] font-medium text-mist-100">{t("actTitle")}</h2>
        </div>
        <Badge variant="secondary">
          {t("actEvents", { count: summary.recent_activity.length })}
        </Badge>
      </div>
      <div className="hairline" />
      {summary.recent_activity.length === 0 ? (
        <p className="px-5 py-6 text-[11.5px] text-mist-600">{t("actEmpty")}</p>
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
                  {entry.resource_type ?? t("actPlatform")}
                  {entry.resource_id ? ` · ${entry.resource_id.slice(0, 8)}` : ""}
                </p>
              </div>
              <div className="text-right">
                <p className="text-[10.5px] text-mist-400">{outcomeLabel(t, entry.outcome)}</p>
                <p className="data-value mt-0.5 font-mono text-[9.5px] text-mist-600">
                  {formatTimestamp(entry.occurred_at)}
                </p>
              </div>
            </li>
          ))}
        </ol>
      )}
      <div className="border-t border-white/[0.06] px-5 py-2.5">
        <p className="text-[10px] leading-relaxed text-mist-600">{t("actNote")}</p>
      </div>
    </div>
  );
}

function outcomeLabel(t: T, outcome: string): string {
  if (outcome === "success") return t("actOutcomeSuccess");
  if (outcome === "failure") return t("actOutcomeFailure");
  return outcome;
}

function PlatformHealth({
  live,
  readiness,
  contract,
  t,
}: {
  live: ApiResult<HealthLive>;
  readiness: ApiResult<HealthReadiness>;
  contract: ApiResult<OpenApiContract>;
  t: T;
}) {
  return (
    <section className="panel overflow-hidden">
      <div className="flex flex-wrap items-center justify-between gap-3 px-5 pt-4.5 pb-3">
        <div>
          <p className="eyebrow">{t("healthEyebrow")}</p>
          <h2 className="mt-1.5 text-[14px] font-medium text-mist-100">{t("healthTitle")}</h2>
        </div>
        <span className="inline-flex items-center gap-1.5 text-[10px] tracking-[0.08em] text-mist-500 uppercase">
          <ShieldCheck className="size-3 text-jade-400" aria-hidden />
          {t("healthProbed")}
        </span>
      </div>
      <div className="hairline" />
      <div className="grid divide-y divide-white/[0.05] sm:grid-cols-3 sm:divide-x sm:divide-y-0">
        <HealthCell
          ok={live.ok}
          label={t("healthApi")}
          detail={live.ok ? t("healthApiOk", { ms: live.latencyMs }) : live.message}
          endpoint="GET /api/v1/health/live"
          t={t}
        />
        <HealthCell
          ok={readiness.ok}
          label={t("healthDatabase")}
          detail={
            readiness.ok ? t("healthDatabaseOk", { ms: readiness.latencyMs }) : readiness.message
          }
          endpoint="GET /api/v1/health/ready"
          t={t}
        />
        <HealthCell
          ok={contract.ok}
          label={t("healthContract")}
          detail={
            contract.ok
              ? t("healthContractOk", {
                  count: contract.data.operationCount,
                  version: contract.data.version ?? "3",
                })
              : contract.message
          }
          endpoint="GET /api/v1/openapi.json"
          t={t}
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
  t,
}: {
  ok: boolean;
  label: string;
  detail: string;
  endpoint: string;
  t: T;
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
        {ok ? t("healthOk") : t("healthFail")}
      </span>
    </div>
  );
}

function OperationsStrip({ operations, t }: { operations: ApiResult<OperationsSummary>; t: T }) {
  if (!operations.ok) {
    return (
      <Alert variant="warning" title={t("opsUnavailable")}>
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
          <p className="eyebrow">{t("opsEyebrow")}</p>
          <h2 className="mt-1.5 text-[14px] font-medium text-mist-100">{t("opsTitle")}</h2>
        </div>
        <div className="flex flex-wrap items-center gap-3 text-[10.5px]">
          <Link href="/orders" className="text-accent-200 hover:text-accent-100">
            {t("opsOrders")}
          </Link>
          <Link href="/shipments" className="text-accent-200 hover:text-accent-100">
            {t("opsShipments")}
          </Link>
          <Link href="/documents" className="text-accent-200 hover:text-accent-100">
            {t("opsDocuments")}
          </Link>
          <span className="font-mono text-mist-600">{formatTimestamp(data.generated_at)}</span>
        </div>
      </div>
      <div className="hairline" />
      <div className="grid divide-y divide-white/[0.05] sm:grid-cols-2 xl:grid-cols-5 sm:divide-x sm:divide-y-0">
        <OperationsCell
          label={t("opsOrdersCreated")}
          value={data.orders_total}
          detail={
            primary
              ? `${formatMoney(primary.total_value, primary.currency)}${data.order_value_by_currency.length > 1 ? ` ${t("opsMoreCurrencies", { count: data.order_value_by_currency.length - 1 })}` : ""}`
              : t("opsNoOrders")
          }
          href="/orders"
          openLabel={t("opsOpen")}
          icon={<ClipboardCheck className="size-3.5" aria-hidden />}
        />
        <OperationsCell
          label={t("opsInFulfillment")}
          value={data.orders_in_fulfillment}
          detail={t("opsFulfillmentDetail", {
            confirmed: data.orders_confirmed,
            fulfilled: data.orders_fulfilled,
          })}
          href="/orders"
          openLabel={t("opsOpen")}
          icon={<Package className="size-3.5" aria-hidden />}
        />
        <OperationsCell
          label={t("opsActiveShipments")}
          value={data.active_shipments}
          detail={t("opsDelivered", { count: data.delivered_shipments })}
          href="/shipments"
          openLabel={t("opsOpen")}
          icon={<Truck className="size-3.5" aria-hidden />}
        />
        <OperationsCell
          label={t("opsDelayed")}
          value={data.delayed_shipments}
          detail={t("opsDelayedDetail")}
          href="/shipments"
          openLabel={t("opsOpen")}
          tone={data.delayed_shipments > 0 ? "danger" : "neutral"}
        />
        <OperationsCell
          label={t("opsMissingEvidence")}
          value={data.delivered_shipments_without_evidence}
          detail={t("opsDocsOnFile", { count: data.documents_total })}
          href="/documents"
          openLabel={t("opsOpen")}
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
  openLabel,
}: {
  label: string;
  value: number;
  detail: string;
  href: string;
  tone?: "neutral" | "warning" | "danger";
  icon?: ReactNode;
  openLabel: string;
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
        {openLabel}
        <ArrowRight className="size-3" aria-hidden />
      </Link>
    </div>
  );
}

import Link from "next/link";

import { ClassificationBadge } from "@/components/finance/reconciliation-status-badge";
import { Alert } from "@/components/ui/alert";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import {
  Card,
  CardContent,
  CardDescription,
  CardHeader,
  CardHeading,
  CardTitle,
} from "@/components/ui/card";
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
import { serverGet } from "@/lib/api/server";
import { loadSession } from "@/lib/auth/session";
import { formatReconciliationMoney, formatReconciliationPercent } from "@/lib/finance/format";
import type { OrderFinance } from "@/lib/finance/reconciliation";
import { getServerT, titleFor } from "@/lib/i18n/server";
import {
  discrepancyCodeText,
  operationsStatusText,
  severityText,
  fulfilmentModelText,
  costStageText,
  costTypeText,
  reconciliationStatusText,
} from "@/lib/i18n/value-labels";
import { formatTimestamp } from "@/lib/trade/format";

export const dynamic = "force-dynamic";
export const generateMetadata = () => titleFor("finOrderFinanceView");

export default async function OrderFinancePage({ params }: { params: Promise<{ id: string }> }) {
  const state = await loadSession();
  if (state.status !== "authenticated") return null;
  const { t, locale } = await getServerT();
  const { id } = await params;
  const result = await serverGet<OrderFinance>(`/finance/orders/${id}`);
  if (!result.ok) {
    return (
      <div className="mx-auto max-w-[1100px] space-y-4">
        <PageHeader
          eyebrow={t("finEyebrowOrder")}
          back={{ href: "/finance/reconciliation", label: t("finBackReconciliation") }}
          title={t("ofUnavailable")}
        />
        <Alert variant="danger" title={t("ofLoadFailed")}>
          {result.message}
        </Alert>
      </div>
    );
  }
  const data = result.data;
  const currency = data.order.currency;
  const money = (value: string | null | undefined, code: string = currency): string =>
    formatReconciliationMoney(value, code, t("finNotAvailable"), locale);
  const percent = (value: string | null | undefined): string =>
    formatReconciliationPercent(value, t("finNotAvailable"), locale);
  return (
    <div className="mx-auto max-w-[1360px] space-y-5">
      <PageHeader
        eyebrow={t("finEyebrowOrder")}
        back={{ href: "/finance/reconciliation", label: t("finBackReconciliation") }}
        meta={
          <div className="flex flex-wrap items-center gap-2">
            <Badge variant="outline">{operationsStatusText(t, data.order.status)}</Badge>
            <Badge variant="secondary">{fulfilmentModelText(t, data.order.fulfilment_model)}</Badge>
            {data.latest_run_status ? (
              <Badge variant="outline">
                {t("ofRunStatus", { status: reconciliationStatusText(t, data.latest_run_status) })}
              </Badge>
            ) : (
              <Badge variant="outline">{t("ofNoRun")}</Badge>
            )}
          </div>
        }
        title={data.order.order_number}
        description={t("ofDescription", { customer: data.order.customer_name, currency })}
        actions={
          <div className="flex flex-wrap gap-2">
            {data.latest_run_id ? (
              <Button asChild size="sm">
                <Link href={`/finance/reconciliation/${data.latest_run_id}`}>
                  {t("ofOpenLatest")}
                </Link>
              </Button>
            ) : null}
            <Button asChild size="sm" variant="outline">
              <Link href={`/finance/reconciliation?order_id=${data.order.sales_order_id}`}>
                {t("ofRunsForOrder")}
              </Link>
            </Button>
            <Button asChild size="sm" variant="ghost">
              <Link href={`/orders/${data.order.sales_order_id}`}>{t("finCommerceOrder")}</Link>
            </Button>
          </div>
        }
      />

      {!data.latest_run_id ? (
        <Alert variant="warning" title={t("ofNoSnapshotTitle")}>
          {t("ofNoSnapshotBody")}
        </Alert>
      ) : null}

      <div className="grid gap-3 sm:grid-cols-2 xl:grid-cols-4">
        <Stat
          label={t("recAcceptedValue")}
          value={money(data.metrics.accepted_sales_order_value)}
          detail={<ClassificationBadge value={data.classifications.accepted_sales_order_value} />}
        />
        <Stat
          label={t("recCommitments")}
          value={money(data.metrics.purchase_commitments_total)}
          detail={<ClassificationBadge value={data.classifications.purchase_commitments_total} />}
          tone="amber"
        />
        <Stat
          label={t("recStatLanded")}
          value={money(data.metrics.estimated_landed_cost)}
          detail={<ClassificationBadge value={data.classifications.estimated_landed_cost} />}
        />
        <Stat
          label={t("recStatRecorded")}
          value={money(data.metrics.recorded_operational_costs)}
          detail={<ClassificationBadge value={data.classifications.recorded_operational_costs} />}
        />
        <Stat
          label={t("recStatVariance")}
          value={money(data.metrics.estimate_vs_recorded_variance)}
          detail={
            <ClassificationBadge value={data.classifications.estimate_vs_recorded_variance} />
          }
          tone="neutral"
        />
        <Stat
          label={t("recCommitmentMargin")}
          value={money(data.metrics.commitment_based_margin)}
          detail={
            <span>
              <ClassificationBadge value={data.classifications.commitment_based_margin} /> ·{" "}
              {percent(data.metrics.commitment_based_margin_pct)}
            </span>
          }
          tone="jade"
        />
        <Stat
          label={t("recStatDocMargin")}
          value={t("finNotAvailable")}
          detail={<ClassificationBadge value={data.classifications.document_supported_margin} />}
          tone="neutral"
        />
        <Stat
          label={t("ofCompleteness")}
          value={percent(data.metrics.completeness_score)}
          detail={t("ofCompletenessDetail")}
          share={Number.parseFloat(data.metrics.completeness_score)}
        />
      </div>

      <div className="grid grid-cols-1 gap-4 lg:grid-cols-2">
        <Card>
          <CardHeader>
            <CardHeading>
              <CardTitle>{t("ofAcceptedCard")}</CardTitle>
              <CardDescription>{t("ofAcceptedCardBody")}</CardDescription>
            </CardHeading>
            <Badge variant="success">{t("ofDocumented")}</Badge>
          </CardHeader>
          <CardContent className="grid gap-3 sm:grid-cols-2">
            <div>
              <p className="eyebrow">{t("ofOrderValue")}</p>
              <p className="mt-1 font-mono text-[13px] text-mist-100">
                {money(data.order.order_total)}
              </p>
            </div>
            <div>
              <p className="eyebrow">{t("ofConfirmed")}</p>
              <p className="mt-1 text-[12px] text-mist-200">
                {formatTimestamp(data.order.confirmed_at, locale)}
              </p>
            </div>
            <div>
              <p className="eyebrow">{t("ofCurrency")}</p>
              <p className="mt-1 text-[12px] text-mist-200">{data.order.currency}</p>
            </div>
            <div>
              <p className="eyebrow">{t("ofLatestRun")}</p>
              <p className="mt-1 text-[12px] text-mist-200">
                {data.latest_run_at ? formatTimestamp(data.latest_run_at, locale) : t("ofNotRun")}
              </p>
            </div>
          </CardContent>
        </Card>
        <Card>
          <CardHeader>
            <CardHeading>
              <CardTitle>{t("recCommitments")}</CardTitle>
              <CardDescription>{t("ofCommitmentsBody")}</CardDescription>
            </CardHeading>
            <Badge variant="warning">{t("ofCommitted")}</Badge>
          </CardHeader>
          <CardContent>
            {data.purchase_orders.length === 0 ? (
              <p className="text-[11.5px] text-mist-500">{t("ofNoPo")}</p>
            ) : (
              <Table>
                <TableHeader>
                  <TableRow>
                    <TableHead>{t("ofColPo")}</TableHead>
                    <TableHead>{t("recColStatus")}</TableHead>
                    <TableHead className="text-right">{t("recColAmount")}</TableHead>
                  </TableRow>
                </TableHeader>
                <TableBody>
                  {data.purchase_orders.map((po) => (
                    <TableRow key={po.purchase_order_id}>
                      <TableCell className="font-mono text-[10.5px] text-mist-200">
                        {po.po_number}
                      </TableCell>
                      <TableCell>
                        <Badge variant={po.is_committed ? "success" : "outline"}>
                          {operationsStatusText(t, po.status)}
                        </Badge>
                      </TableCell>
                      <TableCell className="text-right font-mono text-[11px]">
                        {money(po.total_cost, po.currency)}
                      </TableCell>
                    </TableRow>
                  ))}
                </TableBody>
              </Table>
            )}
          </CardContent>
        </Card>
      </div>

      <div className="panel overflow-hidden">
        <div className="px-4 py-3">
          <p className="eyebrow">{t("ofCostsTitle")}</p>
          <p className="mt-1 text-[11px] text-mist-500">{t("ofCostsNote")}</p>
        </div>
        <div className="hairline" />
        {data.shipments.length === 0 ? (
          <p className="px-4 py-4 text-[11.5px] text-mist-500">{t("ofNoShipment")}</p>
        ) : (
          <Table>
            <TableHeader>
              <TableRow>
                <TableHead className="pl-4">{t("ofColShipment")}</TableHead>
                <TableHead>{t("recColStatus")}</TableHead>
                <TableHead>{t("ofColCostType")}</TableHead>
                <TableHead>{t("ofColReference")}</TableHead>
                <TableHead className="text-right">{t("recColAmount")}</TableHead>
              </TableRow>
            </TableHeader>
            <TableBody>
              {data.shipments.flatMap((shipment) =>
                shipment.costs.length === 0
                  ? [
                      <TableRow key={shipment.shipment_id}>
                        <TableCell className="pl-4 font-mono text-[10.5px] text-mist-200">
                          {shipment.shipment_number}
                        </TableCell>
                        <TableCell>
                          <Badge variant="outline">
                            {operationsStatusText(t, shipment.status)}
                          </Badge>
                        </TableCell>
                        <TableCell colSpan={3} className="text-[10.5px] text-amber-400">
                          {t("ofNoCost")}
                        </TableCell>
                      </TableRow>,
                    ]
                  : shipment.costs.map((cost) => (
                      <TableRow key={cost.cost_id}>
                        <TableCell className="pl-4 font-mono text-[10.5px] text-mist-200">
                          {shipment.shipment_number}
                        </TableCell>
                        <TableCell>
                          <Badge variant="outline">
                            {operationsStatusText(t, shipment.status)}
                          </Badge>
                        </TableCell>
                        <TableCell className="text-[10.5px] text-mist-300">
                          {costTypeText(t, cost.cost_type)} · {costStageText(t, cost.stage)}
                        </TableCell>
                        <TableCell className="max-w-[220px] truncate text-[10px] text-mist-600">
                          {cost.reference}
                        </TableCell>
                        <TableCell className="text-right font-mono text-[11px]">
                          {money(cost.amount, cost.currency)}
                        </TableCell>
                      </TableRow>
                    )),
              )}
            </TableBody>
          </Table>
        )}
      </div>

      <div className="grid grid-cols-1 gap-4 lg:grid-cols-[minmax(0,1.5fr)_minmax(0,1fr)]">
        <div className="panel p-4">
          <p className="eyebrow">{t("ofGapsTitle")}</p>
          {data.missing_evidence.length === 0 ? (
            <p className="mt-2 text-[11.5px] text-mist-500">{t("ofNoGaps")}</p>
          ) : (
            <ul className="mt-3 space-y-2">
              {data.missing_evidence.map((gap, index) => (
                <li key={`${gap.code}-${index}`} className="panel-inset p-3">
                  <div className="flex flex-wrap items-center gap-2">
                    <Badge variant="outline">{discrepancyCodeText(t, gap.code)}</Badge>
                    <Badge variant="secondary">{severityText(t, gap.severity)}</Badge>
                  </div>
                  <p className="mt-1.5 text-[11px] text-mist-200">{gap.title}</p>
                  <p className="mt-1 text-[10.5px] leading-relaxed text-mist-500">{gap.detail}</p>
                </li>
              ))}
            </ul>
          )}
        </div>
        <Alert variant="info" title={t("ofMarginTitle")}>
          {t("ofMarginPre")} <strong>{t("ofMarginStrong")}</strong>
          {t("ofMarginPost")}
        </Alert>
      </div>
    </div>
  );
}

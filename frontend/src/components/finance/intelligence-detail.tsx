"use client";

import { CheckCircle2, CircleAlert } from "lucide-react";
import Link from "next/link";
import * as React from "react";

import { IntelligenceExceptionsTable } from "@/components/finance/intelligence-exceptions";
import {
  ClassificationBadge,
  ReconciliationStatusBadge,
} from "@/components/finance/reconciliation-status-badge";
import { Signed } from "@/components/finance/signed";
import { Alert } from "@/components/ui/alert";
import { Badge } from "@/components/ui/badge";
import {
  Card,
  CardContent,
  CardDescription,
  CardHeader,
  CardHeading,
  CardTitle,
} from "@/components/ui/card";
import { Stat } from "@/components/ui/stat";
import {
  Table,
  TableBody,
  TableCell,
  TableHead,
  TableHeader,
  TableRow,
} from "@/components/ui/table";
import { formatReconciliationMoney, formatReconciliationPercent } from "@/lib/finance/format";
import type { OrderIntelligenceDetail } from "@/lib/finance/intelligence";
import {
  basisWord,
  costTypeWord,
  decisionWord,
  sourceTypeWord,
  stageWord,
  statusWord,
  verificationWord,
} from "@/lib/finance/intelligence-text";
import { useLocale } from "@/lib/i18n/locale-provider";
import { operationsStatusText } from "@/lib/i18n/value-labels";
import { formatDate, formatMoney, formatQuantity, formatTimestamp } from "@/lib/trade/format";

function Section({
  title,
  description,
  children,
}: {
  title: string;
  description?: string;
  children: React.ReactNode;
}) {
  return (
    <Card>
      <CardHeader>
        <CardHeading>
          <CardTitle>{title}</CardTitle>
          {description ? <CardDescription>{description}</CardDescription> : null}
        </CardHeading>
      </CardHeader>
      <CardContent className="overflow-x-auto px-0">{children}</CardContent>
    </Card>
  );
}

function None({ children }: { children: React.ReactNode }) {
  return <p className="px-5 py-3 text-[11px] text-mist-600">{children}</p>;
}

/** A badge may only name a kind for a figure that is actually shown. */
function kindOf(value: string | null | undefined, kind: string | undefined): string {
  return value === null || value === undefined ? "UNAVAILABLE" : (kind ?? "UNAVAILABLE");
}

/** Margin percentage next to a profit figure; nothing when the profit itself is unavailable. */
function Margin({
  amount,
  percent,
}: {
  amount: string | null | undefined;
  percent: string | null | undefined;
}) {
  const { t, locale } = useLocale();
  if (amount === null || amount === undefined) return null;
  return (
    <>
      {t("oiMarginSuffix", {
        pct: formatReconciliationPercent(percent, t("intNotAvailable"), locale),
      })}
    </>
  );
}

export function IntelligenceDetail({
  detail,
  csrfToken,
  canReview,
}: {
  detail: OrderIntelligenceDetail;
  csrfToken: string;
  canReview: boolean;
}) {
  const { t, locale } = useLocale();
  const { order } = detail;
  const currency = order.currency;
  const classes = order.classifications;
  const money = (value: string | null | undefined, code: string = currency): string =>
    formatReconciliationMoney(value, code, t("intNotAvailable"), locale);
  const plainMoney = (value: string, code: string): string => formatMoney(value, code, locale);

  return (
    <div className="space-y-5">
      <div className="grid grid-cols-1 gap-3 sm:grid-cols-2 xl:grid-cols-3">
        <Stat
          label={t("oiSalesValue")}
          value={money(order.sales_value)}
          detail={<ClassificationBadge value={kindOf(order.sales_value, classes.sales_value)} />}
        />
        <Stat
          label={t("oiEstProfit")}
          value={
            <Signed value={order.estimated_gross_profit}>
              {money(order.estimated_gross_profit)}
            </Signed>
          }
          detail={
            <span className="flex flex-wrap items-center gap-2">
              <ClassificationBadge
                value={kindOf(order.estimated_gross_profit, classes.estimated_gross_profit)}
              />
              <Signed value={order.estimated_gross_margin_pct}>
                <Margin
                  amount={order.estimated_gross_profit}
                  percent={order.estimated_gross_margin_pct ?? null}
                />
              </Signed>
            </span>
          }
        />
        <Stat
          label={t("oiCommittedProfit")}
          value={
            <Signed value={order.committed_gross_profit}>
              {money(order.committed_gross_profit)}
            </Signed>
          }
          detail={
            <span className="flex flex-wrap items-center gap-2">
              <ClassificationBadge
                value={kindOf(order.committed_gross_profit, classes.committed_gross_profit)}
              />
              <Signed value={order.committed_gross_margin_pct}>
                <Margin
                  amount={order.committed_gross_profit}
                  percent={order.committed_gross_margin_pct ?? null}
                />
              </Signed>
            </span>
          }
          tone="amber"
        />
        <Stat
          label={t("oiDocOpCost")}
          value={money(order.documented_operational_cost)}
          detail={
            <span className="flex flex-wrap items-center gap-2">
              <ClassificationBadge
                value={kindOf(
                  order.documented_operational_cost,
                  classes.documented_operational_cost,
                )}
              />
              <span>
                {t("oiTotalWithPurchases", { amount: money(order.documented_total_cost) })}
              </span>
            </span>
          }
        />
        <Stat
          label={t("oiCostVariance")}
          value={money(order.cost_variance)}
          detail={
            <span className="flex flex-wrap items-center gap-2">
              <ClassificationBadge value={kindOf(order.cost_variance, classes.cost_variance)} />
              {order.cost_variance_pct ? (
                <span>
                  {t("oiOfEstimate", {
                    pct: formatReconciliationPercent(
                      order.cost_variance_pct,
                      t("intNotAvailable"),
                      locale,
                    ),
                  })}
                </span>
              ) : null}
            </span>
          }
        />
        <Stat
          label={t("oiActualProfit")}
          value={t("intNotAvailable")}
          detail={<ClassificationBadge value={classes.actual_profit ?? "UNAVAILABLE"} />}
        />
      </div>

      <div className="grid grid-cols-1 gap-4 lg:grid-cols-2">
        <Section title={t("oiChecksTitle")} description={t("oiChecksDesc")}>
          <ul className="divide-y divide-white/[0.05]">
            {detail.checks.map((check) => (
              <li key={check.key} className="flex items-start gap-3 px-5 py-2.5">
                {check.satisfied ? (
                  <CheckCircle2 className="mt-0.5 size-4 shrink-0 text-jade-400" aria-hidden />
                ) : (
                  <CircleAlert className="mt-0.5 size-4 shrink-0 text-amber-400" aria-hidden />
                )}
                <div>
                  <p className="text-[11.5px] text-mist-200">
                    {check.label}
                    <span className="sr-only">
                      {check.satisfied ? t("oiSatisfied") : t("oiNotSatisfied")}
                    </span>
                  </p>
                  <p className="mt-0.5 text-[10.5px] leading-relaxed text-mist-500">
                    {check.detail}
                  </p>
                </div>
              </li>
            ))}
          </ul>
        </Section>

        <Section title={t("oiLimitationsTitle")} description={t("oiLimitationsDesc")}>
          {detail.limitations.length === 0 ? (
            <None>{t("oiNoLimitations")}</None>
          ) : (
            <ul className="list-disc space-y-1.5 pr-5 pl-9 text-[11px] leading-relaxed text-mist-400">
              {detail.limitations.map((item) => (
                <li key={item}>{item}</li>
              ))}
            </ul>
          )}
        </Section>
      </div>

      <Section title={t("oiCostLinesTitle")} description={t("oiCostLinesDesc")}>
        {detail.cost_lines.length === 0 ? (
          <None>{t("oiNoCostLines")}</None>
        ) : (
          <Table>
            <TableHeader>
              <TableRow>
                <TableHead className="pl-5">{t("oiColCost")}</TableHead>
                <TableHead className="text-right">{t("oiColOriginal")}</TableHead>
                <TableHead className="text-right">{t("oiColIn", { currency })}</TableHead>
                <TableHead>{t("oiColFx")}</TableHead>
                <TableHead>{t("oiColBasis")}</TableHead>
                <TableHead>{t("oiColVerification")}</TableHead>
                <TableHead className="pr-5">{t("oiColExpense")}</TableHead>
              </TableRow>
            </TableHeader>
            <TableBody>
              {detail.cost_lines.map((line, index) => (
                <TableRow key={`${line.cost_type}-${line.source_reference}-${index}`}>
                  <TableCell className="pl-5">
                    <span className="text-[11px] text-mist-200">
                      {costTypeWord(t, locale, line.cost_type)}
                    </span>
                    <span className="block font-mono text-[10px] text-mist-600">
                      {line.source_reference}
                    </span>
                  </TableCell>
                  <TableCell className="text-right font-mono text-[11px]">
                    {money(line.original_amount, line.original_currency)}
                  </TableCell>
                  <TableCell className="text-right font-mono text-[11px]">
                    {money(line.converted_amount, line.target_currency)}
                  </TableCell>
                  <TableCell className="font-mono text-[10.5px] text-mist-400">
                    {line.fx_rate ?? "—"}
                  </TableCell>
                  <TableCell className="text-[10.5px] text-mist-400">
                    {basisWord(t, locale, line.basis)}
                  </TableCell>
                  <TableCell>
                    <Badge variant="outline">
                      {verificationWord(t, locale, line.verification_status)}
                    </Badge>
                  </TableCell>
                  <TableCell className="pr-5">
                    <Badge variant={line.is_expense ? "secondary" : "outline"}>
                      {line.is_expense ? t("oiYes") : t("oiNo")}
                    </Badge>
                  </TableCell>
                </TableRow>
              ))}
            </TableBody>
          </Table>
        )}
      </Section>

      {detail.fx_assumptions.length > 0 ? (
        <Section title={t("oiFxTitle")} description={t("oiFxDesc")}>
          <Table>
            <TableHeader>
              <TableRow>
                <TableHead className="pl-5">{t("oiColPair")}</TableHead>
                <TableHead className="text-right">{t("oiColRate")}</TableHead>
                <TableHead>{t("oiColEffective")}</TableHead>
                <TableHead className="pr-5">{t("oiColSource")}</TableHead>
              </TableRow>
            </TableHeader>
            <TableBody>
              {detail.fx_assumptions.map((fx) => (
                <TableRow key={fx.snapshot_id}>
                  <TableCell className="pl-5 font-mono text-[11px]">
                    {fx.base_currency}/{fx.quote_currency}
                  </TableCell>
                  <TableCell className="text-right font-mono text-[11px]">{fx.rate}</TableCell>
                  <TableCell className="text-[10.5px] whitespace-nowrap text-mist-400">
                    {formatTimestamp(fx.effective_at, locale)}
                  </TableCell>
                  <TableCell className="pr-5 text-[10.5px] text-mist-400">{fx.source}</TableCell>
                </TableRow>
              ))}
            </TableBody>
          </Table>
        </Section>
      ) : null}

      <div className="grid grid-cols-1 gap-4 xl:grid-cols-2">
        <Section title={t("oiPosTitle")} description={t("oiPosDesc")}>
          {detail.purchase_orders.length === 0 ? (
            <None>{t("oiNoPos")}</None>
          ) : (
            <Table>
              <TableHeader>
                <TableRow>
                  <TableHead className="pl-5">{t("oiColPo")}</TableHead>
                  <TableHead>{t("intColStatus")}</TableHead>
                  <TableHead className="text-right">{t("oiColTotal")}</TableHead>
                  <TableHead className="pr-5">{t("oiColClass")}</TableHead>
                </TableRow>
              </TableHeader>
              <TableBody>
                {detail.purchase_orders.map((po) => (
                  <TableRow key={po.purchase_order_id}>
                    <TableCell className="pl-5">
                      <Link
                        href={`/purchase-orders/${po.purchase_order_id}`}
                        className="font-mono text-[11px] text-accent-200 hover:text-accent-100"
                      >
                        {po.po_number}
                      </Link>
                      <span className="block text-[10px] text-mist-600">
                        {po.supplier_name ?? t("oiSupplierNotRecorded")}
                      </span>
                    </TableCell>
                    <TableCell>
                      <Badge variant="outline">{statusWord(t, locale, po.status)}</Badge>
                    </TableCell>
                    <TableCell className="text-right font-mono text-[11px]">
                      {plainMoney(po.total_cost, po.currency)}
                    </TableCell>
                    <TableCell className="pr-5">
                      <ClassificationBadge value={po.classification} />
                    </TableCell>
                  </TableRow>
                ))}
              </TableBody>
            </Table>
          )}
        </Section>

        <Section title={t("oiShipTitle")} description={t("oiShipDesc")}>
          {detail.shipments.length === 0 ? (
            <None>{t("oiNoShipments")}</None>
          ) : (
            <div className="space-y-3">
              {detail.shipments.map((shipment) => (
                <div key={shipment.shipment_id}>
                  <div className="flex items-center justify-between gap-3 px-5 pb-1">
                    <Link
                      href={`/shipments/${shipment.shipment_id}`}
                      className="font-mono text-[11px] text-accent-200 hover:text-accent-100"
                    >
                      {shipment.shipment_number}
                    </Link>
                    <Badge variant="outline">{statusWord(t, locale, shipment.status)}</Badge>
                  </div>
                  {shipment.costs.length === 0 ? (
                    <None>{t("oiNoShipmentCost")}</None>
                  ) : (
                    <Table>
                      <TableBody>
                        {shipment.costs.map((cost) => (
                          <TableRow key={cost.cost_id}>
                            <TableCell className="pl-5 text-[11px] text-mist-300">
                              {costTypeWord(t, locale, cost.cost_type)}
                              <span className="block font-mono text-[10px] text-mist-600">
                                {cost.reference}
                              </span>
                            </TableCell>
                            <TableCell>
                              <Badge variant="outline">{stageWord(t, locale, cost.stage)}</Badge>
                            </TableCell>
                            <TableCell className="text-right font-mono text-[11px]">
                              {plainMoney(cost.amount, cost.currency)}
                            </TableCell>
                            <TableCell className="pr-5">
                              <ClassificationBadge value={cost.classification} />
                            </TableCell>
                          </TableRow>
                        ))}
                      </TableBody>
                    </Table>
                  )}
                </div>
              ))}
            </div>
          )}
        </Section>
      </div>

      <Section
        title={t("oiQuoteTitle", {
          number: detail.quote.quote_number,
          revision: detail.quote.revision,
        })}
        description={t("oiQuoteDesc", {
          incoterm: detail.quote.incoterm,
          place: detail.quote.named_delivery_place,
          terms: detail.quote.payment_terms,
          date: formatDate(detail.quote.valid_until, locale),
        })}
      >
        <Table>
          <TableHeader>
            <TableRow>
              <TableHead className="pl-5">{t("oiColDescription")}</TableHead>
              <TableHead className="text-right">{t("oiColQuantity")}</TableHead>
              <TableHead className="text-right">{t("oiColUnitPrice")}</TableHead>
              <TableHead className="pr-5 text-right">{t("oiColLineTotal")}</TableHead>
            </TableRow>
          </TableHeader>
          <TableBody>
            {detail.quote.lines.map((line) => (
              <TableRow key={`${line.product_id}-${line.description}`}>
                <TableCell className="pl-5 text-[11px] text-mist-200">{line.description}</TableCell>
                <TableCell className="text-right font-mono text-[11px]">
                  {formatQuantity(line.quantity, line.unit, locale)}
                </TableCell>
                <TableCell className="text-right font-mono text-[11px]">
                  {plainMoney(line.unit_price, detail.quote.currency)}
                </TableCell>
                <TableCell className="pr-5 text-right font-mono text-[11px]">
                  {plainMoney(line.line_total, detail.quote.currency)}
                </TableCell>
              </TableRow>
            ))}
          </TableBody>
        </Table>
      </Section>

      <div className="grid grid-cols-1 gap-4 xl:grid-cols-2">
        <Section title={t("oiRunsTitle")} description={t("oiRunsDesc")}>
          {detail.runs.length === 0 ? (
            <None>{t("oiNoRuns")}</None>
          ) : (
            <Table>
              <TableHeader>
                <TableRow>
                  <TableHead className="pl-5">{t("oiColRun")}</TableHead>
                  <TableHead>{t("intColStatus")}</TableHead>
                  <TableHead className="text-right">{t("oiColEvidence")}</TableHead>
                  <TableHead className="pr-5 text-right">{t("intColOpen")}</TableHead>
                </TableRow>
              </TableHeader>
              <TableBody>
                {detail.runs.map((run) => (
                  <TableRow key={run.run_id}>
                    <TableCell className="pl-5">
                      <Link
                        href={`/finance/reconciliation/${run.run_id}`}
                        className="font-mono text-[11px] text-accent-200 hover:text-accent-100"
                      >
                        {formatDate(run.as_of, locale)}
                      </Link>
                      <span className="block text-[10px] text-mist-600">
                        {run.latest_decision
                          ? `${decisionWord(t, locale, run.latest_decision)} · ${formatTimestamp(run.latest_review_at ?? null, locale)}`
                          : t("oiNotReviewed")}
                      </span>
                    </TableCell>
                    <TableCell>
                      <ReconciliationStatusBadge status={run.status} />
                    </TableCell>
                    <TableCell className="text-right font-mono text-[11px]">
                      {run.evidence_count}
                    </TableCell>
                    <TableCell className="pr-5 text-right font-mono text-[11px]">
                      {run.open_discrepancy_count}
                    </TableCell>
                  </TableRow>
                ))}
              </TableBody>
            </Table>
          )}
        </Section>

        <Section title={t("oiEvidenceTitle")} description={t("oiEvidenceDesc")}>
          {detail.evidence.length === 0 ? (
            <None>{t("oiNoEvidence")}</None>
          ) : (
            <Table>
              <TableHeader>
                <TableRow>
                  <TableHead className="pl-5">{t("oiColReference")}</TableHead>
                  <TableHead className="text-right">{t("oiColAmount")}</TableHead>
                  <TableHead className="pr-5">{t("oiColVerification")}</TableHead>
                </TableRow>
              </TableHeader>
              <TableBody>
                {detail.evidence.map((item) => (
                  <TableRow key={item.id}>
                    <TableCell className="pl-5">
                      <span className="font-mono text-[11px] text-mist-200">
                        {item.finance_source_reference}
                      </span>
                      <span className="block text-[10px] text-mist-600">
                        {t("oiEvidenceThrough", {
                          type: sourceTypeWord(t, locale, item.finance_source_type),
                          date: formatDate(item.data_through ?? null, locale),
                        })}
                      </span>
                    </TableCell>
                    <TableCell className="text-right font-mono text-[11px]">
                      {plainMoney(item.amount, item.currency)}
                    </TableCell>
                    <TableCell className="pr-5">
                      <Badge
                        variant={
                          item.verification_status === "VERIFIED"
                            ? "success"
                            : item.verification_status === "REJECTED"
                              ? "danger"
                              : "outline"
                        }
                      >
                        {locale === "tr"
                          ? operationsStatusText(t, item.verification_status)
                          : item.verification_status}
                      </Badge>
                    </TableCell>
                  </TableRow>
                ))}
              </TableBody>
            </Table>
          )}
        </Section>
      </div>

      <div className="panel overflow-hidden">
        <div className="px-4 py-3">
          <p className="eyebrow">{t("oiExceptionsTitle")}</p>
          <p className="mt-1 text-[11px] text-mist-500">{t("oiExceptionsNote")}</p>
        </div>
        <div className="hairline" />
        <IntelligenceExceptionsTable
          items={detail.discrepancies}
          csrfToken={csrfToken}
          canReview={canReview}
        />
      </div>

      <Alert variant="info" title={t("oiHowToReadTitle")}>
        {t("oiHowToRead")}
      </Alert>
    </div>
  );
}

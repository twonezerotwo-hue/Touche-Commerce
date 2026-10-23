import { CheckCircle2, CircleAlert } from "lucide-react";
import Link from "next/link";
import * as React from "react";

import { IntelligenceExceptionsTable } from "@/components/finance/intelligence-exceptions";
import {
  ClassificationBadge,
  ReconciliationStatusBadge,
} from "@/components/finance/reconciliation-status-badge";
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
import { humanize, type OrderIntelligenceDetail } from "@/lib/finance/intelligence";
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

/** Margin percentage next to a profit figure; nothing when the profit itself is unavailable. */
function Margin({
  amount,
  percent,
}: {
  amount: string | null | undefined;
  percent: string | null | undefined;
}) {
  if (amount === null || amount === undefined) return null;
  return <>{formatReconciliationPercent(percent)} margin</>;
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
  const { order } = detail;
  const currency = order.currency;
  const classes = order.classifications;

  return (
    <div className="space-y-5">
      <div className="grid gap-3 sm:grid-cols-2 xl:grid-cols-3">
        <Stat
          label="Sales value"
          value={formatReconciliationMoney(order.sales_value, currency)}
          detail={<ClassificationBadge value={classes.sales_value} />}
        />
        <Stat
          label="Estimated gross profit"
          value={formatReconciliationMoney(order.estimated_gross_profit, currency)}
          detail={
            <span className="flex flex-wrap items-center gap-2">
              <ClassificationBadge value={classes.estimated_gross_profit} />
              <Margin
                amount={order.estimated_gross_profit}
                percent={order.estimated_gross_margin_pct ?? null}
              />
            </span>
          }
        />
        <Stat
          label="Committed gross profit"
          value={formatReconciliationMoney(order.committed_gross_profit, currency)}
          detail={
            <span className="flex flex-wrap items-center gap-2">
              <ClassificationBadge value={classes.committed_gross_profit} />
              <Margin
                amount={order.committed_gross_profit}
                percent={order.committed_gross_margin_pct ?? null}
              />
            </span>
          }
          tone="amber"
        />
        <Stat
          label="Documented cost"
          value={formatReconciliationMoney(order.documented_total_cost, currency)}
          detail={<ClassificationBadge value={classes.documented_operational_cost} />}
        />
        <Stat
          label="Cost variance"
          value={formatReconciliationMoney(order.cost_variance, currency)}
          detail={
            <span className="flex flex-wrap items-center gap-2">
              <ClassificationBadge value={classes.cost_variance} />
              {formatReconciliationPercent(order.cost_variance_pct ?? null)} of estimate
            </span>
          }
        />
        <Stat
          label="Actual profit"
          value="Not available"
          detail={<ClassificationBadge value={classes.actual_profit ?? "UNAVAILABLE"} />}
        />
      </div>

      <div className="grid gap-4 lg:grid-cols-2">
        <Section
          title="Completion checks"
          description="Each check is a fact about the stored data, not an opinion."
        >
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
                      {check.satisfied ? " — satisfied" : " — not satisfied"}
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

        <Section
          title="Limitations"
          description="What this analysis does not claim, stated by the calculation itself."
        >
          {detail.limitations.length === 0 ? (
            <None>No limitations were recorded for this order.</None>
          ) : (
            <ul className="list-disc space-y-1.5 pr-5 pl-9 text-[11px] leading-relaxed text-mist-400">
              {detail.limitations.map((item) => (
                <li key={item}>{item}</li>
              ))}
            </ul>
          )}
        </Section>
      </div>

      <Section
        title="Estimated cost lines"
        description="The Stage 3 landed-cost scenario in the order currency. Non-expense lines (such as recoverable VAT) are marked and excluded."
      >
        {detail.cost_lines.length === 0 ? (
          <None>No pricing scenario with cost lines is linked to this order.</None>
        ) : (
          <Table>
            <TableHeader>
              <TableRow>
                <TableHead className="pl-5">Cost</TableHead>
                <TableHead className="text-right">Original</TableHead>
                <TableHead className="text-right">In {currency}</TableHead>
                <TableHead>FX rate</TableHead>
                <TableHead>Basis</TableHead>
                <TableHead>Verification</TableHead>
                <TableHead className="pr-5">Counts as expense</TableHead>
              </TableRow>
            </TableHeader>
            <TableBody>
              {detail.cost_lines.map((line, index) => (
                <TableRow key={`${line.cost_type}-${line.source_reference}-${index}`}>
                  <TableCell className="pl-5">
                    <span className="text-[11px] text-mist-200">{humanize(line.cost_type)}</span>
                    <span className="block font-mono text-[10px] text-mist-600">
                      {line.source_reference}
                    </span>
                  </TableCell>
                  <TableCell className="text-right font-mono text-[11px]">
                    {formatReconciliationMoney(line.original_amount, line.original_currency)}
                  </TableCell>
                  <TableCell className="text-right font-mono text-[11px]">
                    {formatReconciliationMoney(line.converted_amount, line.target_currency)}
                  </TableCell>
                  <TableCell className="font-mono text-[10.5px] text-mist-400">
                    {line.fx_rate ?? "—"}
                  </TableCell>
                  <TableCell className="text-[10.5px] text-mist-400">
                    {humanize(line.basis)}
                  </TableCell>
                  <TableCell>
                    <Badge variant="outline">{humanize(line.verification_status)}</Badge>
                  </TableCell>
                  <TableCell className="pr-5">
                    <Badge variant={line.is_expense ? "secondary" : "outline"}>
                      {line.is_expense ? "Yes" : "No"}
                    </Badge>
                  </TableCell>
                </TableRow>
              ))}
            </TableBody>
          </Table>
        )}
      </Section>

      {detail.fx_assumptions.length > 0 ? (
        <Section
          title="FX assumptions"
          description="Stored snapshots only. No current market rate is ever borrowed."
        >
          <Table>
            <TableHeader>
              <TableRow>
                <TableHead className="pl-5">Pair</TableHead>
                <TableHead className="text-right">Rate</TableHead>
                <TableHead>Effective</TableHead>
                <TableHead className="pr-5">Source</TableHead>
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
                    {formatTimestamp(fx.effective_at)}
                  </TableCell>
                  <TableCell className="pr-5 text-[10.5px] text-mist-400">{fx.source}</TableCell>
                </TableRow>
              ))}
            </TableBody>
          </Table>
        </Section>
      ) : null}

      <div className="grid gap-4 xl:grid-cols-2">
        <Section
          title="Purchase orders"
          description="Only approved-or-later purchase orders are treated as committed."
        >
          {detail.purchase_orders.length === 0 ? (
            <None>No purchase order is linked to this order.</None>
          ) : (
            <Table>
              <TableHeader>
                <TableRow>
                  <TableHead className="pl-5">PO</TableHead>
                  <TableHead>Status</TableHead>
                  <TableHead className="text-right">Total</TableHead>
                  <TableHead className="pr-5">Class</TableHead>
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
                        {po.supplier_name ?? "Supplier not recorded"}
                      </span>
                    </TableCell>
                    <TableCell>
                      <Badge variant="outline">{humanize(po.status)}</Badge>
                    </TableCell>
                    <TableCell className="text-right font-mono text-[11px]">
                      {formatMoney(po.total_cost, po.currency)}
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

        <Section
          title="Shipments and recorded costs"
          description="QUOTED and ESTIMATED costs are forecasts; only INCURRED and DOCUMENTED enter the documented basis."
        >
          {detail.shipments.length === 0 ? (
            <None>No shipment has been planned for this order.</None>
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
                    <Badge variant="outline">{humanize(shipment.status)}</Badge>
                  </div>
                  {shipment.costs.length === 0 ? (
                    <None>No cost recorded for this shipment.</None>
                  ) : (
                    <Table>
                      <TableBody>
                        {shipment.costs.map((cost) => (
                          <TableRow key={cost.cost_id}>
                            <TableCell className="pl-5 text-[11px] text-mist-300">
                              {humanize(cost.cost_type)}
                              <span className="block font-mono text-[10px] text-mist-600">
                                {cost.reference}
                              </span>
                            </TableCell>
                            <TableCell>
                              <Badge variant="outline">{cost.stage}</Badge>
                            </TableCell>
                            <TableCell className="text-right font-mono text-[11px]">
                              {formatMoney(cost.amount, cost.currency)}
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
        title={`Accepted quote ${detail.quote.quote_number} · revision ${detail.quote.revision}`}
        description={`${detail.quote.incoterm} ${detail.quote.named_delivery_place} · ${detail.quote.payment_terms} · valid until ${formatDate(detail.quote.valid_until)}`}
      >
        <Table>
          <TableHeader>
            <TableRow>
              <TableHead className="pl-5">Description</TableHead>
              <TableHead className="text-right">Quantity</TableHead>
              <TableHead className="text-right">Unit price</TableHead>
              <TableHead className="pr-5 text-right">Line total</TableHead>
            </TableRow>
          </TableHeader>
          <TableBody>
            {detail.quote.lines.map((line) => (
              <TableRow key={`${line.product_id}-${line.description}`}>
                <TableCell className="pl-5 text-[11px] text-mist-200">{line.description}</TableCell>
                <TableCell className="text-right font-mono text-[11px]">
                  {formatQuantity(line.quantity, line.unit)}
                </TableCell>
                <TableCell className="text-right font-mono text-[11px]">
                  {formatMoney(line.unit_price, detail.quote.currency)}
                </TableCell>
                <TableCell className="pr-5 text-right font-mono text-[11px]">
                  {formatMoney(line.line_total, detail.quote.currency)}
                </TableCell>
              </TableRow>
            ))}
          </TableBody>
        </Table>
      </Section>

      <div className="grid gap-4 xl:grid-cols-2">
        <Section
          title="Reconciliation timeline"
          description="Every Stage 5D snapshot for this order, newest first."
        >
          {detail.runs.length === 0 ? (
            <None>No reconciliation run exists for this order.</None>
          ) : (
            <Table>
              <TableHeader>
                <TableRow>
                  <TableHead className="pl-5">Run</TableHead>
                  <TableHead>Status</TableHead>
                  <TableHead className="text-right">Evidence</TableHead>
                  <TableHead className="pr-5 text-right">Open</TableHead>
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
                        {formatDate(run.as_of)}
                      </Link>
                      <span className="block text-[10px] text-mist-600">
                        {run.latest_decision
                          ? `${humanize(run.latest_decision)} · ${formatTimestamp(run.latest_review_at ?? null)}`
                          : "Not reviewed"}
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

        <Section
          title="Finance evidence"
          description="Operator-linked Finance source references. A link is evidence, not an accounting entry."
        >
          {detail.evidence.length === 0 ? (
            <None>No Finance source has been linked to this order.</None>
          ) : (
            <Table>
              <TableHeader>
                <TableRow>
                  <TableHead className="pl-5">Reference</TableHead>
                  <TableHead className="text-right">Amount</TableHead>
                  <TableHead className="pr-5">Verification</TableHead>
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
                        {humanize(item.finance_source_type)} · through{" "}
                        {formatDate(item.data_through ?? null)}
                      </span>
                    </TableCell>
                    <TableCell className="text-right font-mono text-[11px]">
                      {formatMoney(item.amount, item.currency)}
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
                        {item.verification_status}
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
          <p className="eyebrow">Exceptions for this order</p>
          <p className="mt-1 text-[11px] text-mist-500">
            Resolving an item records a note; it never changes Finance.
          </p>
        </div>
        <div className="hairline" />
        <IntelligenceExceptionsTable
          items={detail.discrepancies}
          csrfToken={csrfToken}
          canReview={canReview}
        />
      </div>

      <Alert variant="info" title="How to read this page">
        Estimated, committed and documented values are separate bases. A missing input keeps a
        figure “Not available” rather than becoming zero, and nothing here is converted at a rate
        that was not stored with the order.
      </Alert>
    </div>
  );
}

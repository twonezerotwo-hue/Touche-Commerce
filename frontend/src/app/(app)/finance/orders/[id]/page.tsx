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
import { formatTimestamp } from "@/lib/trade/format";

export const dynamic = "force-dynamic";
export const metadata = { title: "Order finance" };

export default async function OrderFinancePage({ params }: { params: Promise<{ id: string }> }) {
  const state = await loadSession();
  if (state.status !== "authenticated") return null;
  const { id } = await params;
  const result = await serverGet<OrderFinance>(`/finance/orders/${id}`);
  if (!result.ok) {
    return (
      <div className="mx-auto max-w-[1100px] space-y-4">
        <PageHeader
          eyebrow="Finance · Order view"
          back={{ href: "/finance/reconciliation", label: "Reconciliation" }}
          title="Order finance unavailable"
        />
        <Alert variant="danger" title="Could not load the order finance view">
          {result.message}
        </Alert>
      </div>
    );
  }
  const data = result.data;
  const currency = data.order.currency;
  return (
    <div className="mx-auto max-w-[1360px] space-y-5">
      <PageHeader
        eyebrow="Finance · Order view"
        back={{ href: "/finance/reconciliation", label: "Reconciliation" }}
        meta={
          <div className="flex flex-wrap items-center gap-2">
            <Badge variant="outline">{data.order.status.replaceAll("_", " ")}</Badge>
            <Badge variant="secondary">{data.order.fulfilment_model.replaceAll("_", " ")}</Badge>
            {data.latest_run_status ? (
              <Badge variant="outline">Run {data.latest_run_status}</Badge>
            ) : (
              <Badge variant="outline">No reconciliation run</Badge>
            )}
          </div>
        }
        title={data.order.order_number}
        description={`${data.order.customer_name} · ${currency}. Accepted commercial facts, commitments and costs stay separate from Finance observations.`}
        actions={
          <div className="flex flex-wrap gap-2">
            {data.latest_run_id ? (
              <Button asChild size="sm">
                <Link href={`/finance/reconciliation/${data.latest_run_id}`}>Open latest run</Link>
              </Button>
            ) : null}
            <Button asChild size="sm" variant="outline">
              <Link href={`/finance/reconciliation?order_id=${data.order.sales_order_id}`}>
                Runs for this order
              </Link>
            </Button>
            <Button asChild size="sm" variant="ghost">
              <Link href={`/orders/${data.order.sales_order_id}`}>Commerce order</Link>
            </Button>
          </div>
        }
      />

      {!data.latest_run_id ? (
        <Alert variant="warning" title="No reconciliation snapshot">
          No Finance source has been linked to this order. Commerce shows only its own accepted and
          operational facts; it does not infer an invoice or payment.
        </Alert>
      ) : null}

      <div className="grid gap-3 sm:grid-cols-2 xl:grid-cols-4">
        <Stat
          label="Accepted order value"
          value={formatReconciliationMoney(data.metrics.accepted_sales_order_value, currency)}
          detail={<ClassificationBadge value={data.classifications.accepted_sales_order_value} />}
        />
        <Stat
          label="Purchase commitments"
          value={formatReconciliationMoney(data.metrics.purchase_commitments_total, currency)}
          detail={<ClassificationBadge value={data.classifications.purchase_commitments_total} />}
          tone="amber"
        />
        <Stat
          label="Estimated landed cost"
          value={formatReconciliationMoney(data.metrics.estimated_landed_cost, currency)}
          detail={<ClassificationBadge value={data.classifications.estimated_landed_cost} />}
        />
        <Stat
          label="Recorded costs"
          value={formatReconciliationMoney(data.metrics.recorded_operational_costs, currency)}
          detail={<ClassificationBadge value={data.classifications.recorded_operational_costs} />}
        />
        <Stat
          label="Estimate vs recorded"
          value={formatReconciliationMoney(data.metrics.estimate_vs_recorded_variance, currency)}
          detail={
            <ClassificationBadge value={data.classifications.estimate_vs_recorded_variance} />
          }
          tone="neutral"
        />
        <Stat
          label="Commitment-based margin"
          value={formatReconciliationMoney(data.metrics.commitment_based_margin, currency)}
          detail={
            <span>
              <ClassificationBadge value={data.classifications.commitment_based_margin} /> ·{" "}
              {formatReconciliationPercent(data.metrics.commitment_based_margin_pct)}
            </span>
          }
          tone="jade"
        />
        <Stat
          label="Document-supported margin"
          value="Not available"
          detail={<ClassificationBadge value={data.classifications.document_supported_margin} />}
          tone="neutral"
        />
        <Stat
          label="Completeness"
          value={formatReconciliationPercent(data.metrics.completeness_score)}
          detail="Commerce source checks"
          share={Number.parseFloat(data.metrics.completeness_score)}
        />
      </div>

      <div className="grid gap-4 lg:grid-cols-2">
        <Card>
          <CardHeader>
            <CardHeading>
              <CardTitle>Accepted commercial order</CardTitle>
              <CardDescription>
                Captured at conversion; the accepted terms are not reconstructed later.
              </CardDescription>
            </CardHeading>
            <Badge variant="success">Documented</Badge>
          </CardHeader>
          <CardContent className="grid gap-3 sm:grid-cols-2">
            <div>
              <p className="eyebrow">Order value</p>
              <p className="mt-1 font-mono text-[13px] text-mist-100">
                {formatReconciliationMoney(data.order.order_total, currency)}
              </p>
            </div>
            <div>
              <p className="eyebrow">Confirmed</p>
              <p className="mt-1 text-[12px] text-mist-200">
                {formatTimestamp(data.order.confirmed_at)}
              </p>
            </div>
            <div>
              <p className="eyebrow">Currency</p>
              <p className="mt-1 text-[12px] text-mist-200">{data.order.currency}</p>
            </div>
            <div>
              <p className="eyebrow">Latest run</p>
              <p className="mt-1 text-[12px] text-mist-200">
                {data.latest_run_at ? formatTimestamp(data.latest_run_at) : "Not run"}
              </p>
            </div>
          </CardContent>
        </Card>
        <Card>
          <CardHeader>
            <CardHeading>
              <CardTitle>Purchase commitments</CardTitle>
              <CardDescription>
                Approved or recorded purchase orders only. Drafts are not commitments.
              </CardDescription>
            </CardHeading>
            <Badge variant="warning">Committed</Badge>
          </CardHeader>
          <CardContent>
            {data.purchase_orders.length === 0 ? (
              <p className="text-[11.5px] text-mist-500">No purchase order is attached.</p>
            ) : (
              <Table>
                <TableHeader>
                  <TableRow>
                    <TableHead>PO</TableHead>
                    <TableHead>Status</TableHead>
                    <TableHead className="text-right">Amount</TableHead>
                  </TableRow>
                </TableHeader>
                <TableBody>
                  {data.purchase_orders.map((po) => (
                    <TableRow key={po.purchase_order_id}>
                      <TableCell className="font-mono text-[10.5px] text-mist-200">
                        {po.po_number}
                      </TableCell>
                      <TableCell>
                        <Badge variant={po.is_committed ? "success" : "outline"}>{po.status}</Badge>
                      </TableCell>
                      <TableCell className="text-right font-mono text-[11px]">
                        {formatReconciliationMoney(po.total_cost, po.currency)}
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
          <p className="eyebrow">Recorded operational costs</p>
          <p className="mt-1 text-[11px] text-mist-500">
            Stage 4 shipment cost records. Missing costs remain unavailable, not zero.
          </p>
        </div>
        <div className="hairline" />
        {data.shipments.length === 0 ? (
          <p className="px-4 py-4 text-[11.5px] text-mist-500">No shipment has been planned.</p>
        ) : (
          <Table>
            <TableHeader>
              <TableRow>
                <TableHead className="pl-4">Shipment</TableHead>
                <TableHead>Status</TableHead>
                <TableHead>Cost type</TableHead>
                <TableHead>Reference</TableHead>
                <TableHead className="text-right">Amount</TableHead>
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
                          <Badge variant="outline">{shipment.status}</Badge>
                        </TableCell>
                        <TableCell colSpan={3} className="text-[10.5px] text-amber-400">
                          No recorded cost — operational evidence incomplete
                        </TableCell>
                      </TableRow>,
                    ]
                  : shipment.costs.map((cost) => (
                      <TableRow key={cost.cost_id}>
                        <TableCell className="pl-4 font-mono text-[10.5px] text-mist-200">
                          {shipment.shipment_number}
                        </TableCell>
                        <TableCell>
                          <Badge variant="outline">{shipment.status}</Badge>
                        </TableCell>
                        <TableCell className="text-[10.5px] text-mist-300">
                          {cost.cost_type.replaceAll("_", " ")} · {cost.stage}
                        </TableCell>
                        <TableCell className="max-w-[220px] truncate text-[10px] text-mist-600">
                          {cost.reference}
                        </TableCell>
                        <TableCell className="text-right font-mono text-[11px]">
                          {formatReconciliationMoney(cost.amount, cost.currency)}
                        </TableCell>
                      </TableRow>
                    )),
              )}
            </TableBody>
          </Table>
        )}
      </div>

      <div className="grid gap-4 lg:grid-cols-[1.5fr_1fr]">
        <div className="panel p-4">
          <p className="eyebrow">Missing evidence and gaps</p>
          {data.missing_evidence.length === 0 ? (
            <p className="mt-2 text-[11.5px] text-mist-500">
              No deterministic gaps are currently supported.
            </p>
          ) : (
            <ul className="mt-3 space-y-2">
              {data.missing_evidence.map((gap, index) => (
                <li key={`${gap.code}-${index}`} className="panel-inset p-3">
                  <div className="flex flex-wrap items-center gap-2">
                    <Badge variant="outline">{gap.code}</Badge>
                    <Badge variant="secondary">{gap.severity}</Badge>
                  </div>
                  <p className="mt-1.5 text-[11px] text-mist-200">{gap.title}</p>
                  <p className="mt-1 text-[10.5px] leading-relaxed text-mist-500">{gap.detail}</p>
                </li>
              ))}
            </ul>
          )}
        </div>
        <Alert variant="info" title="Margin interpretation">
          Commitment-based margin is an operational interpretation of accepted value minus committed
          purchase orders and recorded costs. Document-supported margin and actual profit are{" "}
          <strong>Unavailable</strong>. VAT is not assumed to be an expense, and no currency is
          converted. A verified Finance link is evidence, not a journal entry.
        </Alert>
      </div>
    </div>
  );
}

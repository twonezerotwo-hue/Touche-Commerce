import Link from "next/link";

import { PurchaseOrderActions } from "@/components/operations/purchase-order-actions";
import { OperationsStatusBadge } from "@/components/operations/status-badge";
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
import { PageHeader } from "@/components/ui/page-header";
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
import type { PurchaseOrder } from "@/lib/operations/types";
import { formatDate, formatMoney, formatTimestamp } from "@/lib/trade/format";

export const dynamic = "force-dynamic";

export default async function PurchaseOrderDetailPage({
  params,
}: {
  params: Promise<{ id: string }>;
}) {
  const state = await loadSession();
  if (state.status !== "authenticated") return null;
  const { id } = await params;

  const result = await serverGet<PurchaseOrder>(`/purchase-orders/${id}`);
  if (!result.ok) {
    return (
      <div className="mx-auto max-w-[900px] space-y-4">
        <PageHeader
          eyebrow="Purchase order"
          back={{ href: "/purchase-orders", label: "Purchase orders" }}
          title="Purchase order unavailable"
        />
        <Alert variant="danger">{result.message}</Alert>
      </div>
    );
  }

  const po = result.data;
  const permissions = state.session.session.company?.permissions ?? [];
  const canWrite = permissions.includes("trade.write");
  const canApprove = permissions.includes("finance.approve");

  return (
    <div className="mx-auto max-w-[1180px] space-y-5">
      <PageHeader
        eyebrow="Purchase order"
        back={{ href: "/purchase-orders", label: "Purchase orders" }}
        meta={
          <div className="flex flex-wrap items-center gap-2">
            <OperationsStatusBadge status={po.status} />
            <span className="font-mono text-[10px] text-mist-600">v{po.version}</span>
          </div>
        }
        title={`${po.po_number} · ${formatMoney(po.total_cost, po.currency)}`}
        description={`${po.supplier_name} · ${po.incoterm} ${po.named_delivery_place} · ${po.payment_terms}`}
      />

      <div className="grid gap-4 lg:grid-cols-[1.6fr_1fr]">
        <div className="space-y-4">
          <Card>
            <CardHeader>
              <CardHeading>
                <CardTitle>Ordered from the supplier</CardTitle>
                <CardDescription>
                  Costs are purchase costs, separate from the customer-facing sales price.
                </CardDescription>
              </CardHeading>
              <Badge variant="outline">{po.currency}</Badge>
            </CardHeader>
            <CardContent>
              <Table bare>
                <TableHeader>
                  <TableRow>
                    <TableHead>SKU</TableHead>
                    <TableHead>Description</TableHead>
                    <TableHead className="text-right">Quantity</TableHead>
                    <TableHead className="text-right">Unit cost</TableHead>
                    <TableHead className="text-right">Line total</TableHead>
                  </TableRow>
                </TableHeader>
                <TableBody>
                  {po.items.map((item) => (
                    <TableRow key={item.id}>
                      <TableCell className="font-mono text-[11.5px] text-accent-200">
                        {item.sku}
                      </TableCell>
                      <TableCell className="text-[12px] text-mist-200">
                        {item.description}
                      </TableCell>
                      <TableCell className="text-right text-[12px] whitespace-nowrap text-mist-200">
                        {item.quantity} {item.unit}
                      </TableCell>
                      <TableCell className="text-right text-[12px] text-mist-300">
                        {formatMoney(item.unit_cost, po.currency)}
                      </TableCell>
                      <TableCell className="text-right text-[12px] text-mist-100">
                        {formatMoney(item.line_total, po.currency)}
                      </TableCell>
                    </TableRow>
                  ))}
                </TableBody>
              </Table>
            </CardContent>
          </Card>

          <Card>
            <CardHeader>
              <CardHeading>
                <CardTitle>History and evidence</CardTitle>
                <CardDescription>
                  Every transition keeps its own evidence reference.
                </CardDescription>
              </CardHeading>
            </CardHeader>
            <CardContent className="space-y-2">
              {po.transitions.map((transition, index) => (
                <div
                  key={`${transition.to_status}-${index}`}
                  className="rounded-lg border border-white/[0.06] px-3 py-2"
                >
                  <div className="flex items-center justify-between gap-2">
                    <span className="text-[11.5px] text-mist-200">
                      {transition.from_status ?? "—"} → {transition.to_status}
                    </span>
                    <span className="font-mono text-[9.5px] text-mist-600">
                      v{transition.version_after}
                    </span>
                  </div>
                  <p className="text-[10px] text-mist-500">
                    {formatTimestamp(transition.occurred_at)}
                    {transition.reason ? ` · ${transition.reason}` : ""}
                    {transition.evidence_reference
                      ? ` · evidence ${transition.evidence_reference}`
                      : ""}
                  </p>
                </div>
              ))}
            </CardContent>
          </Card>
        </div>
        <div className="space-y-4">
          <Card>
            <CardHeader>
              <CardHeading>
                <CardTitle>Procurement workflow</CardTitle>
                <CardDescription>
                  Approval is financial; recording a send is evidence, not an action by TOUCHE.
                </CardDescription>
              </CardHeading>
            </CardHeader>
            <CardContent>
              <PurchaseOrderActions
                purchaseOrder={po}
                csrfToken={state.session.session.csrf_token}
                canWrite={canWrite}
                canApprove={canApprove}
              />
            </CardContent>
          </Card>

          <Card>
            <CardHeader>
              <CardHeading>
                <CardTitle>Facts</CardTitle>
              </CardHeading>
            </CardHeader>
            <CardContent>
              <dl className="space-y-2 text-[11.5px]">
                <div className="flex justify-between gap-3">
                  <dt className="eyebrow">Sales order</dt>
                  <dd>
                    <Link
                      href={`/orders/${po.sales_order_id}`}
                      className="font-mono text-[10.5px] text-accent-200"
                    >
                      {po.order_number}
                    </Link>
                  </dd>
                </div>
                <div className="flex justify-between gap-3">
                  <dt className="eyebrow">Supplier quote</dt>
                  <dd className="font-mono text-[10px] text-mist-400">
                    {po.supplier_quote_id ?? "—"}
                  </dd>
                </div>
                <div className="flex justify-between gap-3">
                  <dt className="eyebrow">Expected dispatch</dt>
                  <dd className="text-mist-300">{formatDate(po.expected_dispatch_date)}</dd>
                </div>
                <div className="flex justify-between gap-3">
                  <dt className="eyebrow">Expected delivery</dt>
                  <dd className="text-mist-300">{formatDate(po.expected_delivery_date)}</dd>
                </div>
                <div className="flex justify-between gap-3">
                  <dt className="eyebrow">Approved</dt>
                  <dd className="text-mist-300">{formatTimestamp(po.approved_at)}</dd>
                </div>
                <div className="flex justify-between gap-3">
                  <dt className="eyebrow">Dispatch channel</dt>
                  <dd className="text-mist-300">{po.dispatch_channel ?? "—"}</dd>
                </div>
                <div className="flex justify-between gap-3">
                  <dt className="eyebrow">Dispatch reference</dt>
                  <dd className="max-w-[180px] truncate text-mist-300">
                    {po.dispatch_reference ?? "—"}
                  </dd>
                </div>
                <div className="flex justify-between gap-3">
                  <dt className="eyebrow">Supplier confirmation</dt>
                  <dd className="max-w-[180px] truncate text-mist-300">
                    {po.supplier_confirmation_reference ?? "—"}
                  </dd>
                </div>
                {po.cancellation_reason ? (
                  <div className="flex justify-between gap-3">
                    <dt className="eyebrow">Cancellation</dt>
                    <dd className="max-w-[200px] text-right text-crimson-400">
                      {po.cancellation_reason}
                    </dd>
                  </div>
                ) : null}
              </dl>
            </CardContent>
          </Card>
        </div>
      </div>
    </div>
  );
}

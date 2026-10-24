import Link from "next/link";

import { DocumentActions } from "@/components/operations/document-actions";
import { DocumentUpload } from "@/components/operations/document-upload";
import { OrderActions } from "@/components/operations/order-actions";
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
import { Meter } from "@/components/ui/meter";
import { PageHeader } from "@/components/ui/page-header";
import {
  Table,
  TableBody,
  TableCell,
  TableHead,
  TableHeader,
  TableRow,
} from "@/components/ui/table";
import { BROWSER_API_PREFIX } from "@/lib/api/config";
import { serverGet } from "@/lib/api/server";
import { loadSession } from "@/lib/auth/session";
import { DocumentDownloads } from "@/components/documents/document-downloads";
import { canGenerateDocuments } from "@/lib/documents/access";
import { completionPercent, documentTypeLabel, formatBytes } from "@/lib/operations/format";
import type {
  DocumentList,
  DocumentPreview,
  FulfilmentSummary,
  SalesOrder,
  ShipmentList,
} from "@/lib/operations/types";
import { formatMoney, formatQuantity, formatTimestamp } from "@/lib/trade/format";

export const dynamic = "force-dynamic";

export default async function OrderDetailPage({ params }: { params: Promise<{ id: string }> }) {
  const state = await loadSession();
  if (state.status !== "authenticated") return null;
  const { id } = await params;

  const orderResult = await serverGet<SalesOrder>(`/sales-orders/${id}`);
  if (!orderResult.ok) {
    return (
      <div className="mx-auto max-w-[900px] space-y-4">
        <PageHeader
          eyebrow="Sales order"
          back={{ href: "/orders", label: "Sales orders" }}
          title="Order unavailable"
        />
        <Alert variant="danger" title="Could not load this order">
          {orderResult.message}
        </Alert>
      </div>
    );
  }

  const order = orderResult.data;
  const [fulfilment, shipments, documents, preview] = await Promise.all([
    serverGet<FulfilmentSummary>(`/sales-orders/${order.id}/fulfilment`),
    serverGet<ShipmentList>(`/shipments?sales_order_id=${order.id}&limit=50`),
    serverGet<DocumentList>(
      `/documents?linked_entity_type=SALES_ORDER&linked_entity_id=${order.id}&limit=50`,
    ),
    serverGet<DocumentPreview>(
      `/sales-orders/${order.id}/documents/preview?kind=commercial_invoice`,
    ),
  ]);

  const permissions = state.session.session.company?.permissions ?? [];
  const canWrite = permissions.includes("trade.write");
  const completion = fulfilment.ok ? completionPercent(fulfilment.data.completion_ratio) : "—";

  return (
    <div className="mx-auto max-w-[1240px] space-y-5">
      <PageHeader
        eyebrow="Sales order"
        back={{ href: "/orders", label: "Sales orders" }}
        meta={
          <div className="flex flex-wrap items-center gap-2">
            <OperationsStatusBadge status={order.status} />
            <Badge variant="outline">{order.fulfilment_model.replaceAll("_", " ")}</Badge>
            <span className="font-mono text-[10px] text-mist-600">v{order.version}</span>
          </div>
        }
        title={`${order.order_number} · ${formatMoney(order.order_total, order.currency)}`}
        description={`${order.customer_name} · accepted quote ${order.quote_number} r${order.sales_quote_revision} · ${order.incoterm} ${order.named_delivery_place}`}
      />
      {canGenerateDocuments(state.session.session.company) ? (
        <DocumentDownloads
          documents={[
            { kind: "order_confirmation", entityId: order.id },
            { kind: "proforma_invoice", entityId: order.id },
            { kind: "commercial_invoice", entityId: order.id },
          ]}
        />
      ) : null}

      <div className="grid gap-4 lg:grid-cols-[1.65fr_1fr]">
        <div className="space-y-4">
          <Card>
            <CardHeader>
              <CardHeading>
                <CardTitle>Accepted lines</CardTitle>
                <CardDescription>
                  Frozen when the deal was won. Later catalogue or quote changes do not touch them.
                </CardDescription>
              </CardHeading>
              <Badge variant="outline">{order.currency}</Badge>
            </CardHeader>
            <CardContent>
              <Table bare>
                <TableHeader>
                  <TableRow>
                    <TableHead>SKU</TableHead>
                    <TableHead>Description</TableHead>
                    <TableHead className="text-right">Quantity</TableHead>
                    <TableHead className="text-right">Unit price</TableHead>
                    <TableHead className="text-right">Line total</TableHead>
                  </TableRow>
                </TableHeader>
                <TableBody>
                  {order.items.map((line) => (
                    <TableRow key={line.id}>
                      <TableCell className="font-mono text-[11.5px] text-accent-200">
                        {line.sku}
                      </TableCell>
                      <TableCell className="max-w-[280px] text-[12px] text-mist-200">
                        {line.description}
                      </TableCell>
                      <TableCell className="text-right text-[12px] whitespace-nowrap text-mist-200">
                        {formatQuantity(line.quantity, line.unit)}
                      </TableCell>
                      <TableCell className="text-right text-[12px] whitespace-nowrap text-mist-300">
                        {formatMoney(line.unit_price, order.currency)}
                      </TableCell>
                      <TableCell className="text-right text-[12px] whitespace-nowrap text-mist-100">
                        {formatMoney(line.line_total, order.currency)}
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
                <CardTitle>Fulfilment</CardTitle>
                <CardDescription>
                  Derived from delivered shipment quantities, not from the order status.
                </CardDescription>
              </CardHeading>
              <Badge
                variant={fulfilment.ok && fulfilment.data.fully_delivered ? "success" : "secondary"}
              >
                {completion}
              </Badge>
            </CardHeader>
            <CardContent className="space-y-3">
              {fulfilment.ok ? (
                <>
                  <Meter value={Number.parseFloat(fulfilment.data.completion_ratio) || 0} />
                  <Table bare>
                    <TableHeader>
                      <TableRow>
                        <TableHead>SKU</TableHead>
                        <TableHead className="text-right">Ordered</TableHead>
                        <TableHead className="text-right">Allocated</TableHead>
                        <TableHead className="text-right">Delivered</TableHead>
                        <TableHead className="text-right">Remaining</TableHead>
                      </TableRow>
                    </TableHeader>
                    <TableBody>
                      {fulfilment.data.lines.map((line) => (
                        <TableRow key={line.sales_order_item_id}>
                          <TableCell className="font-mono text-[11px] text-mist-300">
                            {line.sku}
                          </TableCell>
                          <TableCell className="text-right text-[11.5px] text-mist-200">
                            {line.ordered} {line.unit}
                          </TableCell>
                          <TableCell className="text-right text-[11.5px] text-mist-300">
                            {line.allocated}
                          </TableCell>
                          <TableCell className="text-right text-[11.5px] text-jade-400">
                            {line.delivered}
                          </TableCell>
                          <TableCell className="text-right text-[11.5px] text-mist-200">
                            {line.remaining}
                          </TableCell>
                        </TableRow>
                      ))}
                    </TableBody>
                  </Table>
                </>
              ) : (
                <Alert variant="danger">{fulfilment.message}</Alert>
              )}
            </CardContent>
          </Card>

          <Card>
            <CardHeader>
              <CardHeading>
                <CardTitle>Shipments</CardTitle>
                <CardDescription>
                  A partial shipment never fulfils the order; the remaining quantity stays visible.
                </CardDescription>
              </CardHeading>
              <Badge variant="outline">{shipments.ok ? shipments.data.items.length : 0}</Badge>
            </CardHeader>
            <CardContent className="space-y-2">
              {shipments.ok && shipments.data.items.length > 0 ? (
                shipments.data.items.map((shipment) => (
                  <div
                    key={shipment.id}
                    className="flex flex-wrap items-center justify-between gap-2 rounded-lg border border-white/[0.06] px-3 py-2"
                  >
                    <div>
                      <Link
                        href={`/shipments/${shipment.id}`}
                        className="font-mono text-[11.5px] text-accent-200 hover:text-accent-100"
                      >
                        {shipment.shipment_number}
                      </Link>
                      <p className="text-[10.5px] text-mist-500">
                        {shipment.origin} → {shipment.destination} · {shipment.transport_mode}
                      </p>
                    </div>
                    <div className="flex items-center gap-2">
                      {shipment.is_delayed ? <Badge variant="danger">Delayed</Badge> : null}
                      <OperationsStatusBadge status={shipment.status} />
                    </div>
                  </div>
                ))
              ) : (
                <p className="text-[11.5px] text-mist-500">
                  No shipment yet. Use the shipments planner to allocate part of this order.
                </p>
              )}
            </CardContent>
          </Card>

          <Card>
            <CardHeader>
              <CardHeading>
                <CardTitle>Trade documents</CardTitle>
                <CardDescription>
                  Private by default. Downloads are authorised against this company and this order.
                </CardDescription>
              </CardHeading>
            </CardHeader>
            <CardContent className="space-y-3">
              {documents.ok && documents.data.items.length > 0 ? (
                documents.data.items.map((document) => (
                  <div
                    key={document.id}
                    className="flex flex-wrap items-center justify-between gap-2 rounded-lg border border-white/[0.06] px-3 py-2"
                  >
                    <div>
                      <p className="text-[12px] text-mist-100">
                        {document.title} <span className="text-mist-600">v{document.version}</span>
                      </p>
                      <p className="text-[10.5px] text-mist-500">
                        {documentTypeLabel(document.document_type)} ·{" "}
                        {formatBytes(document.size_bytes)} · {document.verification_status}
                      </p>
                    </div>
                    <div className="flex items-center gap-2">
                      <a
                        href={`${BROWSER_API_PREFIX}${document.download_path}`}
                        className="text-[11px] text-accent-200 hover:text-accent-100"
                      >
                        Download
                      </a>
                      <DocumentActions
                        document={document}
                        csrfToken={state.session.session.csrf_token}
                        canWrite={canWrite}
                      />
                    </div>
                  </div>
                ))
              ) : (
                <p className="text-[11.5px] text-mist-500">
                  No documents attached to this order yet.
                </p>
              )}

              <DocumentUpload
                csrfToken={state.session.session.csrf_token}
                canWrite={canWrite}
                maxBytes={documents.ok ? documents.data.max_upload_bytes : 10 * 1024 * 1024}
                entityType="SALES_ORDER"
                entityId={order.id}
                entityLabel={`order ${order.order_number}`}
              />
            </CardContent>
          </Card>
        </div>
        <div className="space-y-4">
          <Card>
            <CardHeader>
              <CardHeading>
                <CardTitle>Workflow</CardTitle>
                <CardDescription>
                  Cancellation and closing are recorded; fulfilment is derived from deliveries.
                </CardDescription>
              </CardHeading>
            </CardHeader>
            <CardContent>
              <OrderActions
                order={order}
                csrfToken={state.session.session.csrf_token}
                canWrite={canWrite}
              />
            </CardContent>
          </Card>

          <Card>
            <CardHeader>
              <CardHeading>
                <CardTitle>Accepted commercial facts</CardTitle>
                <CardDescription>
                  The order keeps its own copy; the quote may be superseded later.
                </CardDescription>
              </CardHeading>
            </CardHeader>
            <CardContent>
              <dl className="space-y-2.5 text-[11.5px]">
                <div className="flex items-baseline justify-between gap-3">
                  <dt className="eyebrow">Customer</dt>
                  <dd className="text-right text-mist-200">{order.customer_name}</dd>
                </div>
                <div className="flex items-baseline justify-between gap-3">
                  <dt className="eyebrow">Quote</dt>
                  <dd className="text-right font-mono text-[10.5px] text-mist-300">
                    {order.quote_number} r{order.sales_quote_revision}
                  </dd>
                </div>
                <div className="flex items-baseline justify-between gap-3">
                  <dt className="eyebrow">Incoterm</dt>
                  <dd className="text-right text-mist-200">
                    {order.incoterm} {order.named_delivery_place}
                  </dd>
                </div>
                <div className="flex items-baseline justify-between gap-3">
                  <dt className="eyebrow">Payment terms</dt>
                  <dd className="text-right text-mist-200">{order.payment_terms_snapshot}</dd>
                </div>
                <div className="flex items-baseline justify-between gap-3">
                  <dt className="eyebrow">Acceptance evidence</dt>
                  <dd className="text-right font-mono text-[10px] text-mist-400">
                    {order.acceptance_evidence_id}
                  </dd>
                </div>
                <div className="flex items-baseline justify-between gap-3">
                  <dt className="eyebrow">Confirmed</dt>
                  <dd className="text-right text-mist-300">
                    {formatTimestamp(order.confirmed_at)}
                  </dd>
                </div>
                {order.cancelled_at ? (
                  <div className="flex items-baseline justify-between gap-3">
                    <dt className="eyebrow">Cancelled</dt>
                    <dd className="text-right text-crimson-400">
                      {formatTimestamp(order.cancelled_at)}
                    </dd>
                  </div>
                ) : null}
              </dl>
            </CardContent>
          </Card>

          <Card>
            <CardHeader>
              <CardHeading>
                <CardTitle>Draft invoice preview</CardTitle>
                <CardDescription>Generated from the accepted order snapshot.</CardDescription>
              </CardHeading>
              <Badge variant="warning">Draft</Badge>
            </CardHeader>
            <CardContent className="space-y-2">
              {preview.ok ? (
                <>
                  <Alert variant="warning" title="Not a legal document">
                    {preview.data.header.legal_notice}
                  </Alert>
                  <dl className="space-y-1.5 text-[11.5px]">
                    <div className="flex justify-between gap-3">
                      <dt className="eyebrow">Draft number</dt>
                      <dd className="font-mono text-[10.5px] text-mist-300">
                        {preview.data.header.document_number}
                      </dd>
                    </div>
                    <div className="flex justify-between gap-3">
                      <dt className="eyebrow">Buyer</dt>
                      <dd className="text-mist-200">{preview.data.header.buyer.name}</dd>
                    </div>
                    <div className="flex justify-between gap-3">
                      <dt className="eyebrow">Total</dt>
                      <dd className="text-mist-100">
                        {formatMoney(preview.data.header.order_total, preview.data.header.currency)}
                      </dd>
                    </div>
                  </dl>
                </>
              ) : (
                <Alert variant="danger">{preview.message}</Alert>
              )}
            </CardContent>
          </Card>

          <Card>
            <CardHeader>
              <CardHeading>
                <CardTitle>History</CardTitle>
                <CardDescription>Append-only transitions and amendments.</CardDescription>
              </CardHeading>
            </CardHeader>
            <CardContent className="space-y-2">
              {order.transitions.map((transition, index) => (
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
                  </p>
                </div>
              ))}
              {order.amendments.map((amendment, index) => (
                <div
                  key={`amendment-${index}`}
                  className="rounded-lg border border-amber-400/20 bg-amber-400/[0.04] px-3 py-2"
                >
                  <p className="text-[11.5px] text-amber-300">Amendment</p>
                  <p className="text-[10px] text-mist-400">
                    {amendment.reason} · {formatTimestamp(amendment.created_at)}
                  </p>
                </div>
              ))}
            </CardContent>
          </Card>
        </div>
      </div>
    </div>
  );
}

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
import { DocumentDownloads } from "@/components/documents/document-downloads";
import { canGenerateDocuments } from "@/lib/documents/access";
import { getServerT, titleFor } from "@/lib/i18n/server";
import { operationsStatusText } from "@/lib/i18n/value-labels";
import type { PurchaseOrder } from "@/lib/operations/types";
import { formatDate, formatMoney, formatQuantity, formatTimestamp } from "@/lib/trade/format";

export const dynamic = "force-dynamic";
export const generateMetadata = () => titleFor("poEyebrow");

export default async function PurchaseOrderDetailPage({
  params,
}: {
  params: Promise<{ id: string }>;
}) {
  const state = await loadSession();
  if (state.status !== "authenticated") return null;
  const { t, locale } = await getServerT();
  const { id } = await params;

  const result = await serverGet<PurchaseOrder>(`/purchase-orders/${id}`);
  if (!result.ok) {
    return (
      <div className="mx-auto max-w-[900px] space-y-4">
        <PageHeader
          eyebrow={t("poEyebrow")}
          back={{ href: "/purchase-orders", label: t("poBreadcrumb") }}
          title={t("poDetailUnavailable")}
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
        eyebrow={t("poEyebrow")}
        back={{ href: "/purchase-orders", label: t("poBreadcrumb") }}
        meta={
          <div className="flex flex-wrap items-center gap-2">
            <OperationsStatusBadge status={po.status} />
            <span className="font-mono text-[10px] text-mist-600">v{po.version}</span>
          </div>
        }
        title={`${po.po_number} · ${formatMoney(po.total_cost, po.currency, locale)}`}
        description={`${po.supplier_name} · ${po.incoterm} ${po.named_delivery_place} · ${po.payment_terms}`}
      />
      {canGenerateDocuments(state.session.session.company) ? (
        <DocumentDownloads documents={[{ kind: "purchase_order", entityId: po.id }]} />
      ) : null}

      <div className="grid grid-cols-1 gap-4 lg:grid-cols-[minmax(0,1.6fr)_minmax(0,1fr)]">
        <div className="space-y-4">
          <Card>
            <CardHeader>
              <CardHeading>
                <CardTitle>{t("poOrderedTitle")}</CardTitle>
                <CardDescription>{t("poOrderedDesc")}</CardDescription>
              </CardHeading>
              <Badge variant="outline">{po.currency}</Badge>
            </CardHeader>
            <CardContent>
              <Table bare>
                <TableHeader>
                  <TableRow>
                    <TableHead>{t("columnSku")}</TableHead>
                    <TableHead>{t("ordColDescription")}</TableHead>
                    <TableHead className="text-right">{t("lgColQuantity")}</TableHead>
                    <TableHead className="text-right">{t("poColUnitCost")}</TableHead>
                    <TableHead className="text-right">{t("poColLineTotal")}</TableHead>
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
                        {formatQuantity(item.quantity, item.unit, locale)}
                      </TableCell>
                      <TableCell className="text-right text-[12px] text-mist-300">
                        {formatMoney(item.unit_cost, po.currency, locale)}
                      </TableCell>
                      <TableCell className="text-right text-[12px] text-mist-100">
                        {formatMoney(item.line_total, po.currency, locale)}
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
                <CardTitle>{t("poHistoryTitle")}</CardTitle>
                <CardDescription>{t("poHistoryDesc")}</CardDescription>
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
                      {transition.from_status
                        ? operationsStatusText(t, transition.from_status)
                        : "—"}{" "}
                      → {operationsStatusText(t, transition.to_status)}
                    </span>
                    <span className="font-mono text-[9.5px] text-mist-600">
                      v{transition.version_after}
                    </span>
                  </div>
                  <p className="text-[10px] text-mist-500">
                    {formatTimestamp(transition.occurred_at, locale)}
                    {transition.reason ? ` · ${transition.reason}` : ""}
                    {transition.evidence_reference
                      ? ` · ${t("lgEvidence", { reference: transition.evidence_reference })}`
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
                <CardTitle>{t("poWorkflowTitle")}</CardTitle>
                <CardDescription>{t("poWorkflowDesc")}</CardDescription>
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
                <CardTitle>{t("lgFacts")}</CardTitle>
              </CardHeading>
            </CardHeader>
            <CardContent>
              <dl className="space-y-2 text-[11.5px]">
                <div className="flex justify-between gap-3">
                  <dt className="eyebrow">{t("lgSalesOrder")}</dt>
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
                  <dt className="eyebrow">{t("poSupplierQuote")}</dt>
                  <dd className="font-mono text-[10px] text-mist-400">
                    {po.supplier_quote_id ?? "—"}
                  </dd>
                </div>
                <div className="flex justify-between gap-3">
                  <dt className="eyebrow">{t("poColExpectedDispatch")}</dt>
                  <dd className="text-mist-300">{formatDate(po.expected_dispatch_date, locale)}</dd>
                </div>
                <div className="flex justify-between gap-3">
                  <dt className="eyebrow">{t("poExpectedDelivery")}</dt>
                  <dd className="text-mist-300">{formatDate(po.expected_delivery_date, locale)}</dd>
                </div>
                <div className="flex justify-between gap-3">
                  <dt className="eyebrow">{t("poApproved")}</dt>
                  <dd className="text-mist-300">{formatTimestamp(po.approved_at, locale)}</dd>
                </div>
                <div className="flex justify-between gap-3">
                  <dt className="eyebrow">{t("poDispatchChannel")}</dt>
                  <dd className="text-mist-300">{po.dispatch_channel ?? "—"}</dd>
                </div>
                <div className="flex justify-between gap-3">
                  <dt className="eyebrow">{t("poDispatchReference")}</dt>
                  <dd className="max-w-[180px] truncate text-mist-300">
                    {po.dispatch_reference ?? "—"}
                  </dd>
                </div>
                <div className="flex justify-between gap-3">
                  <dt className="eyebrow">{t("poSupplierConfirmation")}</dt>
                  <dd className="max-w-[180px] truncate text-mist-300">
                    {po.supplier_confirmation_reference ?? "—"}
                  </dd>
                </div>
                {po.cancellation_reason ? (
                  <div className="flex justify-between gap-3">
                    <dt className="eyebrow">{t("lgCancellation")}</dt>
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

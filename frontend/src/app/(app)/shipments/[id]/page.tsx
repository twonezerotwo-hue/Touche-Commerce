import Link from "next/link";

import { DocumentActions } from "@/components/operations/document-actions";
import { DocumentUpload } from "@/components/operations/document-upload";
import { ShipmentActions } from "@/components/operations/shipment-actions";
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
import { BROWSER_API_PREFIX } from "@/lib/api/config";
import { serverGet } from "@/lib/api/server";
import { loadSession } from "@/lib/auth/session";
import { DocumentDownloads } from "@/components/documents/document-downloads";
import { canGenerateDocuments } from "@/lib/documents/access";
import { getServerT, titleFor } from "@/lib/i18n/server";
import {
  costStageText,
  costTypeText,
  documentTypeText,
  provenanceText,
  referenceTypeText,
  shipmentEventText,
  transportModeText,
} from "@/lib/i18n/value-labels";
import { formatBytes } from "@/lib/operations/format";
import type { DocumentList, Shipment } from "@/lib/operations/types";
import { formatMoney, formatQuantity, formatTimestamp } from "@/lib/trade/format";

export const dynamic = "force-dynamic";
export const generateMetadata = () => titleFor("shpEyebrow");

export default async function ShipmentDetailPage({ params }: { params: Promise<{ id: string }> }) {
  const state = await loadSession();
  if (state.status !== "authenticated") return null;
  const { t, locale } = await getServerT();
  const { id } = await params;

  const result = await serverGet<Shipment>(`/shipments/${id}`);
  if (!result.ok) {
    return (
      <div className="mx-auto max-w-[900px] space-y-4">
        <PageHeader
          eyebrow={t("shpEyebrow")}
          back={{ href: "/shipments", label: t("shpTitle") }}
          title={t("shpDetailUnavailable")}
        />
        <Alert variant="danger">{result.message}</Alert>
      </div>
    );
  }

  const shipment = result.data;
  const documents = await serverGet<DocumentList>(
    `/documents?linked_entity_type=SHIPMENT&linked_entity_id=${shipment.id}&limit=50`,
  );
  const permissions = state.session.session.company?.permissions ?? [];
  const canWrite = permissions.includes("trade.write");

  return (
    <div className="mx-auto max-w-[1200px] space-y-5">
      <PageHeader
        eyebrow={t("shpEyebrow")}
        back={{ href: "/shipments", label: t("shpTitle") }}
        meta={
          <div className="flex flex-wrap items-center gap-2">
            <OperationsStatusBadge status={shipment.status} />
            {shipment.is_delayed ? <Badge variant="danger">{t("shpPastEta")}</Badge> : null}
            <span className="font-mono text-[10px] text-mist-600">v{shipment.version}</span>
          </div>
        }
        title={`${shipment.shipment_number} · ${transportModeText(t, shipment.transport_mode)}`}
        description={t("shpDetailDescription", {
          route: `${shipment.origin} → ${shipment.destination}`,
          order: shipment.order_number,
          carrier: shipment.carrier ?? t("shpNoCarrierInline"),
          forwarder: shipment.forwarder ?? t("shpNoForwarderInline"),
        })}
      />
      {canGenerateDocuments(state.session.session.company) ? (
        <DocumentDownloads documents={[{ kind: "packing_list", entityId: shipment.id }]} />
      ) : null}

      <div className="grid gap-4 lg:grid-cols-[1.6fr_1fr]">
        <div className="space-y-4">
          <Card>
            <CardHeader>
              <CardHeading>
                <CardTitle>{t("shpAllocTitle")}</CardTitle>
                <CardDescription>{t("shpAllocDesc")}</CardDescription>
              </CardHeading>
            </CardHeader>
            <CardContent>
              <Table bare>
                <TableHeader>
                  <TableRow>
                    <TableHead>{t("columnSku")}</TableHead>
                    <TableHead>{t("ordColDescription")}</TableHead>
                    <TableHead className="text-right">{t("shpColInShipment")}</TableHead>
                    <TableHead className="text-right">{t("ordDelivered")}</TableHead>
                  </TableRow>
                </TableHeader>
                <TableBody>
                  {shipment.items.map((item) => (
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
                      <TableCell className="text-right text-[12px] whitespace-nowrap text-jade-400">
                        {formatQuantity(item.delivered_quantity, item.unit, locale)}
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
                <CardTitle>{t("shpTimelineTitle")}</CardTitle>
                <CardDescription>{t("shpTimelineDesc")}</CardDescription>
              </CardHeading>
            </CardHeader>
            <CardContent className="space-y-2">
              {shipment.events.map((event) => (
                <div key={event.id} className="rounded-lg border border-white/[0.06] px-3 py-2">
                  <div className="flex items-center justify-between gap-2">
                    <span className="text-[11.5px] text-mist-200">
                      {shipmentEventText(t, event.event_type)}
                    </span>
                    <span className="font-mono text-[9.5px] text-mist-600">
                      {formatTimestamp(event.occurred_at, locale)}
                    </span>
                  </div>
                  <p className="text-[10px] text-mist-500">
                    {event.location ?? t("shpLocationNone")}
                    {event.notes ? ` · ${event.notes}` : ""}
                    {event.evidence_reference
                      ? ` · ${t("lgEvidence", { reference: event.evidence_reference })}`
                      : ""}
                    {` · ${provenanceText(t, event.tracking_source)}`}
                  </p>
                </div>
              ))}
            </CardContent>
          </Card>

          <Card>
            <CardHeader>
              <CardHeading>
                <CardTitle>{t("shpCostsTitle")}</CardTitle>
                <CardDescription>{t("shpCostsDesc")}</CardDescription>
              </CardHeading>
              <Badge variant="outline">{shipment.costs.length}</Badge>
            </CardHeader>
            <CardContent className="space-y-2">
              {shipment.costs.length === 0 ? (
                <p className="text-[11.5px] text-mist-500">{t("shpNoCosts")}</p>
              ) : (
                shipment.costs.map((cost) => (
                  <div
                    key={cost.id}
                    className="flex flex-wrap items-center justify-between gap-2 rounded-lg border border-white/[0.06] px-3 py-2"
                  >
                    <div>
                      <p className="text-[11.5px] text-mist-200">
                        {costTypeText(t, cost.cost_type)} · {costStageText(t, cost.stage)}
                      </p>
                      <p className="text-[10px] text-mist-500">
                        {cost.reference} · {formatTimestamp(cost.recorded_at, locale)}
                      </p>
                    </div>
                    <span className="text-[12px] text-mist-100">
                      {formatMoney(cost.amount, cost.currency, locale)}
                    </span>
                  </div>
                ))
              )}
            </CardContent>
          </Card>

          <Card>
            <CardHeader>
              <CardHeading>
                <CardTitle>{t("shpRefsTitle")}</CardTitle>
                <CardDescription>{t("shpRefsDesc")}</CardDescription>
              </CardHeading>
            </CardHeader>
            <CardContent className="space-y-2">
              {shipment.references.length === 0 ? (
                <p className="text-[11.5px] text-mist-500">{t("shpNoRefs")}</p>
              ) : (
                shipment.references.map((reference) => (
                  <div
                    key={reference.id}
                    className="flex items-center justify-between gap-2 rounded-lg border border-white/[0.06] px-3 py-2 text-[11.5px]"
                  >
                    <span className="text-mist-300">
                      {referenceTypeText(t, reference.reference_type)}
                    </span>
                    <span className="font-mono text-[10.5px] text-accent-200">
                      {reference.reference_value}
                    </span>
                    <span className="text-[10px] text-mist-500">
                      {provenanceText(t, reference.provenance)}
                    </span>
                  </div>
                ))
              )}
            </CardContent>
          </Card>
        </div>
        <div className="space-y-4">
          <Card>
            <CardHeader>
              <CardHeading>
                <CardTitle>{t("shpMilestonesTitle")}</CardTitle>
                <CardDescription>{t("shpMilestonesDesc")}</CardDescription>
              </CardHeading>
            </CardHeader>
            <CardContent>
              <ShipmentActions
                shipment={shipment}
                csrfToken={state.session.session.csrf_token}
                canWrite={canWrite}
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
                  <dt className="eyebrow">{t("lgOrder")}</dt>
                  <dd>
                    <Link
                      href={`/orders/${shipment.sales_order_id}`}
                      className="font-mono text-[10.5px] text-accent-200"
                    >
                      {shipment.order_number}
                    </Link>
                  </dd>
                </div>
                <div className="flex justify-between gap-3">
                  <dt className="eyebrow">{t("lgPlannedDispatch")}</dt>
                  <dd className="text-mist-300">
                    {formatTimestamp(shipment.planned_dispatch_at, locale)}
                  </dd>
                </div>
                <div className="flex justify-between gap-3">
                  <dt className="eyebrow">{t("shpActualDispatch")}</dt>
                  <dd className="text-mist-300">
                    {formatTimestamp(shipment.actual_dispatch_at, locale)}
                  </dd>
                </div>
                <div className="flex justify-between gap-3">
                  <dt className="eyebrow">{t("shpEtaDocumented")}</dt>
                  <dd className="text-mist-300">
                    {formatTimestamp(shipment.estimated_arrival_at, locale)}
                  </dd>
                </div>
                <div className="flex justify-between gap-3">
                  <dt className="eyebrow">{t("shpActualArrival")}</dt>
                  <dd className="text-mist-300">
                    {formatTimestamp(shipment.actual_arrival_at, locale)}
                  </dd>
                </div>
                <div className="flex justify-between gap-3">
                  <dt className="eyebrow">{t("ordDelivered")}</dt>
                  <dd className="text-mist-200">
                    {formatTimestamp(shipment.delivered_at, locale)}
                  </dd>
                </div>
                <div className="flex justify-between gap-3">
                  <dt className="eyebrow">{t("shpTracking")}</dt>
                  <dd className="max-w-[170px] truncate font-mono text-[10px] text-mist-300">
                    {shipment.tracking_reference ?? "—"}
                  </dd>
                </div>
                <div className="flex justify-between gap-3">
                  <dt className="eyebrow">{t("shpTrackingProvenance")}</dt>
                  <dd className="text-mist-300">{provenanceText(t, shipment.tracking_source)}</dd>
                </div>
                <div className="flex justify-between gap-3">
                  <dt className="eyebrow">{t("shpDeliveryEvidence")}</dt>
                  <dd className="max-w-[170px] truncate text-mist-300">
                    {shipment.delivery_evidence_reference ?? "—"}
                  </dd>
                </div>
                {shipment.cancellation_reason ? (
                  <div className="flex justify-between gap-3">
                    <dt className="eyebrow">{t("lgCancellation")}</dt>
                    <dd className="max-w-[200px] text-right text-crimson-400">
                      {shipment.cancellation_reason}
                    </dd>
                  </div>
                ) : null}
              </dl>
            </CardContent>
          </Card>

          <Card>
            <CardHeader>
              <CardHeading>
                <CardTitle>{t("shpDocsTitle")}</CardTitle>
                <CardDescription>{t("shpDocsDesc")}</CardDescription>
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
                      <p className="text-[11.5px] text-mist-100">
                        {document.title} <span className="text-mist-600">v{document.version}</span>
                      </p>
                      <p className="text-[10px] text-mist-500">
                        {documentTypeText(t, document.document_type)} ·{" "}
                        {formatBytes(document.size_bytes, locale)}
                      </p>
                    </div>
                    <div className="flex items-center gap-2">
                      <a
                        href={`${BROWSER_API_PREFIX}${document.download_path}`}
                        className="text-[11px] text-accent-200 hover:text-accent-100"
                      >
                        {t("actionDownload")}
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
                <p className="text-[11.5px] text-mist-500">{t("shpNoDocs")}</p>
              )}

              <DocumentUpload
                csrfToken={state.session.session.csrf_token}
                canWrite={canWrite}
                maxBytes={documents.ok ? documents.data.max_upload_bytes : 10 * 1024 * 1024}
                entityType="SHIPMENT"
                entityId={shipment.id}
                entityLabel={t("shpEntityLabel", { number: shipment.shipment_number })}
              />
            </CardContent>
          </Card>
        </div>
      </div>
    </div>
  );
}

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
  documentTypeText,
  provenanceText,
  referenceTypeText,
  shipmentCostTypeText,
  shipmentEventText,
  transportModeText,
} from "@/lib/i18n/value-labels";
import { formatBytes } from "@/lib/operations/format";
import type { DocumentList, Shipment } from "@/lib/operations/types";
import { formatMoney, formatQuantity, formatTimestamp } from "@/lib/trade/format";

export const dynamic = "force-dynamic";
export const generateMetadata = () => titleFor("shipEyebrow");

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
          eyebrow={t("shipEyebrow")}
          back={{ href: "/shipments", label: t("shipPageTitle") }}
          title={t("shipUnavailableTitle")}
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
        eyebrow={t("shipEyebrow")}
        back={{ href: "/shipments", label: t("shipPageTitle") }}
        meta={
          <div className="flex flex-wrap items-center gap-2">
            <OperationsStatusBadge status={shipment.status} />
            {shipment.is_delayed ? <Badge variant="danger">{t("shipPastEta")}</Badge> : null}
            <span className="font-mono text-[10px] text-mist-600">v{shipment.version}</span>
          </div>
        }
        title={`${shipment.shipment_number} · ${transportModeText(t, shipment.transport_mode)}`}
        description={t("shipHeaderDescription", {
          origin: shipment.origin,
          destination: shipment.destination,
          order: shipment.order_number,
          carrier: shipment.carrier ?? t("logNoCarrier"),
          forwarder: shipment.forwarder ?? t("logNoForwarder"),
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
                <CardTitle>{t("shipAllocated")}</CardTitle>
                <CardDescription>{t("shipAllocatedHint")}</CardDescription>
              </CardHeading>
            </CardHeader>
            <CardContent>
              <Table bare>
                <TableHeader>
                  <TableRow>
                    <TableHead>{t("logSku")}</TableHead>
                    <TableHead>{t("logDescription")}</TableHead>
                    <TableHead className="text-right">{t("shipInThis")}</TableHead>
                    <TableHead className="text-right">{t("shipDelivered")}</TableHead>
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
                <CardTitle>{t("shipTimeline")}</CardTitle>
                <CardDescription>{t("shipTimelineHint")}</CardDescription>
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
                    {event.location ?? t("shipLocationNotRecorded")}
                    {event.notes ? ` · ${event.notes}` : ""}
                    {event.evidence_reference
                      ? ` · ${t("logEvidenceSuffix", { ref: event.evidence_reference })}`
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
                <CardTitle>{t("shipCosts")}</CardTitle>
                <CardDescription>{t("shipCostsHint")}</CardDescription>
              </CardHeading>
              <Badge variant="outline">{shipment.costs.length}</Badge>
            </CardHeader>
            <CardContent className="space-y-2">
              {shipment.costs.length === 0 ? (
                <p className="text-[11.5px] text-mist-500">{t("shipNoCosts")}</p>
              ) : (
                shipment.costs.map((cost) => (
                  <div
                    key={cost.id}
                    className="flex flex-wrap items-center justify-between gap-2 rounded-lg border border-white/[0.06] px-3 py-2"
                  >
                    <div>
                      <p className="text-[11.5px] text-mist-200">
                        {shipmentCostTypeText(t, cost.cost_type)} · {costStageText(t, cost.stage)}
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
                <CardTitle>{t("shipReferences")}</CardTitle>
                <CardDescription>{t("shipReferencesHint")}</CardDescription>
              </CardHeading>
            </CardHeader>
            <CardContent className="space-y-2">
              {shipment.references.length === 0 ? (
                <p className="text-[11.5px] text-mist-500">{t("shipNoReferences")}</p>
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
                <CardTitle>{t("shipMilestones")}</CardTitle>
                <CardDescription>{t("shipMilestonesHint")}</CardDescription>
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
                <CardTitle>{t("logFacts")}</CardTitle>
              </CardHeading>
            </CardHeader>
            <CardContent>
              <dl className="space-y-2 text-[11.5px]">
                <div className="flex justify-between gap-3">
                  <dt className="eyebrow">{t("logOrder")}</dt>
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
                  <dt className="eyebrow">{t("shipPlannedDispatch")}</dt>
                  <dd className="text-mist-300">
                    {formatTimestamp(shipment.planned_dispatch_at, locale)}
                  </dd>
                </div>
                <div className="flex justify-between gap-3">
                  <dt className="eyebrow">{t("shipActualDispatch")}</dt>
                  <dd className="text-mist-300">
                    {formatTimestamp(shipment.actual_dispatch_at, locale)}
                  </dd>
                </div>
                <div className="flex justify-between gap-3">
                  <dt className="eyebrow">{t("shipEtaDocumented")}</dt>
                  <dd className="text-mist-300">
                    {formatTimestamp(shipment.estimated_arrival_at, locale)}
                  </dd>
                </div>
                <div className="flex justify-between gap-3">
                  <dt className="eyebrow">{t("shipActualArrival")}</dt>
                  <dd className="text-mist-300">
                    {formatTimestamp(shipment.actual_arrival_at, locale)}
                  </dd>
                </div>
                <div className="flex justify-between gap-3">
                  <dt className="eyebrow">{t("shipDeliveredAt")}</dt>
                  <dd className="text-mist-200">
                    {formatTimestamp(shipment.delivered_at, locale)}
                  </dd>
                </div>
                <div className="flex justify-between gap-3">
                  <dt className="eyebrow">{t("shipTracking")}</dt>
                  <dd className="max-w-[170px] truncate font-mono text-[10px] text-mist-300">
                    {shipment.tracking_reference ?? "—"}
                  </dd>
                </div>
                <div className="flex justify-between gap-3">
                  <dt className="eyebrow">{t("shipTrackingProvenance")}</dt>
                  <dd className="text-mist-300">{provenanceText(t, shipment.tracking_source)}</dd>
                </div>
                <div className="flex justify-between gap-3">
                  <dt className="eyebrow">{t("shipDeliveryEvidence")}</dt>
                  <dd className="max-w-[170px] truncate text-mist-300">
                    {shipment.delivery_evidence_reference ?? "—"}
                  </dd>
                </div>
                {shipment.cancellation_reason ? (
                  <div className="flex justify-between gap-3">
                    <dt className="eyebrow">{t("logCancellation")}</dt>
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
                <CardTitle>{t("shipDocuments")}</CardTitle>
                <CardDescription>{t("shipDocumentsHint")}</CardDescription>
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
                        {formatBytes(document.size_bytes)}
                      </p>
                    </div>
                    <div className="flex items-center gap-2">
                      <a
                        href={`${BROWSER_API_PREFIX}${document.download_path}`}
                        className="text-[11px] text-accent-200 hover:text-accent-100"
                      >
                        {t("logDownload")}
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
                <p className="text-[11.5px] text-mist-500">{t("shipNoDocuments")}</p>
              )}

              <DocumentUpload
                csrfToken={state.session.session.csrf_token}
                canWrite={canWrite}
                maxBytes={documents.ok ? documents.data.max_upload_bytes : 10 * 1024 * 1024}
                entityType="SHIPMENT"
                entityId={shipment.id}
                entityLabel={t("shipEntityLabel", { number: shipment.shipment_number })}
              />
            </CardContent>
          </Card>
        </div>
      </div>
    </div>
  );
}

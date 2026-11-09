import Link from "next/link";

import { DocumentActions } from "@/components/operations/document-actions";
import { DocumentUpload } from "@/components/operations/document-upload";
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
import { EmptyState } from "@/components/ui/empty-state";
import { PageHeader } from "@/components/ui/page-header";
import { Select } from "@/components/ui/select";
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
import { getServerT, titleFor } from "@/lib/i18n/server";
import { documentTypeText, linkedEntityText, operationsStatusText } from "@/lib/i18n/value-labels";
import { formatBytes } from "@/lib/operations/format";
import {
  DOCUMENT_TYPES,
  type DocumentList,
  type DocumentPreview,
  type LinkedEntityType,
  type SalesOrderList,
  type ShipmentList,
} from "@/lib/operations/types";
import { formatMoney, formatQuantity, formatTimestamp } from "@/lib/trade/format";

export const dynamic = "force-dynamic";
export const generateMetadata = () => titleFor("documentsTitle");

export default async function DocumentsPage({
  searchParams,
}: {
  searchParams: Promise<{
    document_type?: string;
    status?: string;
    entity_type?: string;
    entity_id?: string;
    entity?: string;
    preview_order?: string;
    preview_kind?: string;
  }>;
}) {
  const state = await loadSession();
  if (state.status !== "authenticated") return null;
  const { t, locale } = await getServerT();
  const params = await searchParams;

  const query = new URLSearchParams({ limit: "50" });
  if (params.document_type) query.set("document_type", params.document_type);
  if (params.status) query.set("status", params.status);

  const [documents, orders, shipments] = await Promise.all([
    serverGet<DocumentList>(`/documents?${query.toString()}`),
    serverGet<SalesOrderList>("/sales-orders?limit=20"),
    serverGet<ShipmentList>("/shipments?limit=20"),
  ]);

  const permissions = state.session.session.company?.permissions ?? [];
  const canWrite = permissions.includes("trade.write");

  const entityOptions: { type: LinkedEntityType; id: string; label: string }[] = [
    ...(orders.ok
      ? orders.data.items.map((order) => ({
          type: "SALES_ORDER" as const,
          id: order.id,
          label: `${order.order_number} · ${order.customer_name}`,
        }))
      : []),
    ...(shipments.ok
      ? shipments.data.items.map((shipment) => ({
          type: "SHIPMENT" as const,
          id: shipment.id,
          label: `${shipment.shipment_number} · ${shipment.origin} → ${shipment.destination}`,
        }))
      : []),
  ];
  const requestedEntity = params.entity ?? null;
  const [requestedType, requestedId] = requestedEntity
    ? (requestedEntity.split(":") as [string, string])
    : [params.entity_type ?? "", params.entity_id ?? ""];
  const selectedEntity =
    entityOptions.find((option) => option.type === requestedType && option.id === requestedId) ??
    entityOptions[0];

  const defaultOrderId = orders.ok ? orders.data.items[0]?.id : undefined;
  const previewOrderId = params.preview_order ?? defaultOrderId;
  const previewKind =
    params.preview_kind === "packing_list" ? "packing_list" : "commercial_invoice";
  const preview = previewOrderId
    ? await serverGet<DocumentPreview>(
        `/sales-orders/${previewOrderId}/documents/preview?kind=${previewKind}`,
      )
    : null;

  return (
    <div className="mx-auto max-w-[1300px] space-y-5">
      <PageHeader
        eyebrow={t("documentsTitle")}
        meta={<Badge variant="secondary">{t("dregBadge")}</Badge>}
        title={t("dregTitle")}
        description={t("dregDescription")}
      />

      <div className="grid grid-cols-1 gap-4 lg:grid-cols-2">
        <Card>
          <CardHeader>
            <CardHeading>
              <CardTitle>{t("dregUploadTitle")}</CardTitle>
              <CardDescription>{t("dregUploadDesc")}</CardDescription>
            </CardHeading>
          </CardHeader>
          <CardContent className="space-y-3">
            {entityOptions.length === 0 ? (
              <Alert variant="info" title={t("dregNothingTitle")}>
                {t("dregNothingBody")}
              </Alert>
            ) : (
              <>
                <form action="/documents" method="get" className="flex flex-wrap items-end gap-2">
                  <div className="w-full space-y-1 sm:w-auto">
                    <label htmlFor="entity-select" className="eyebrow">
                      {t("dregAttachTo")}
                    </label>
                    <Select
                      id="entity-select"
                      name="entity"
                      defaultValue={`${selectedEntity?.type}:${selectedEntity?.id}`}
                      className="h-8 w-full text-[12px] sm:w-[320px]"
                    >
                      {entityOptions.map((option) => (
                        <option
                          key={`${option.type}:${option.id}`}
                          value={`${option.type}:${option.id}`}
                        >
                          {option.label}
                        </option>
                      ))}
                    </Select>
                  </div>
                  <Button type="submit" size="sm" variant="subtle">
                    {t("dregSelect")}
                  </Button>
                </form>
                {selectedEntity ? (
                  <DocumentUpload
                    csrfToken={state.session.session.csrf_token}
                    canWrite={canWrite}
                    maxBytes={documents.ok ? documents.data.max_upload_bytes : 10 * 1024 * 1024}
                    entityType={selectedEntity.type}
                    entityId={selectedEntity.id}
                    entityLabel={selectedEntity.label}
                  />
                ) : null}
              </>
            )}
          </CardContent>
        </Card>

        <Card>
          <CardHeader>
            <CardHeading>
              <CardTitle>{t("dregPreviewTitle")}</CardTitle>
              <CardDescription>{t("dregPreviewDesc")}</CardDescription>
            </CardHeading>
            <Badge variant="warning">{t("dregDraftOnly")}</Badge>
          </CardHeader>
          <CardContent className="space-y-3">
            <form action="/documents" method="get" className="flex flex-wrap items-end gap-2">
              <div className="w-full space-y-1 sm:w-auto">
                <label htmlFor="preview-order" className="eyebrow">
                  {t("lgSalesOrder")}
                </label>
                <Select
                  id="preview-order"
                  name="preview_order"
                  defaultValue={previewOrderId ?? ""}
                  className="h-8 w-full text-[12px] sm:w-[250px]"
                >
                  {(orders.ok ? orders.data.items : []).map((order) => (
                    <option key={order.id} value={order.id}>
                      {order.order_number} · {order.customer_name}
                    </option>
                  ))}
                </Select>
              </div>
              <div className="w-full space-y-1 sm:w-auto">
                <label htmlFor="preview-kind" className="eyebrow">
                  {t("dregKind")}
                </label>
                <Select
                  id="preview-kind"
                  name="preview_kind"
                  defaultValue={previewKind}
                  className="h-8 w-full text-[12px] sm:w-[180px]"
                >
                  <option value="commercial_invoice">{t("docTypeCommercialInvoice")}</option>
                  <option value="packing_list">{t("docTypePackingList")}</option>
                </Select>
              </div>
              <Button type="submit" size="sm" variant="subtle">
                {t("dregPreview")}
              </Button>
            </form>

            {preview ? (
              preview.ok ? (
                <>
                  <Alert variant="warning" title={t("ordNotLegal")}>
                    {preview.data.header.legal_notice}
                  </Alert>
                  <div className="rounded-lg border border-white/[0.07] p-3">
                    <p className="text-[12px] text-mist-100">
                      {preview.data.header.document_label}
                    </p>
                    <p className="font-mono text-[10px] text-mist-500">
                      {preview.data.header.document_number} · {preview.data.header.document_date}
                    </p>
                    <p className="mt-1 text-[11px] text-mist-300">
                      {preview.data.header.seller.name} → {preview.data.header.buyer.name}
                    </p>
                    <p className="text-[11px] text-mist-400">
                      {preview.data.header.incoterm} {preview.data.header.named_delivery_place} ·{" "}
                      {formatMoney(
                        preview.data.header.order_total,
                        preview.data.header.currency,
                        locale,
                      )}
                    </p>
                    <div className="mt-2 space-y-1">
                      {preview.data.lines.map((line) => (
                        <div key={line.sku} className="flex justify-between text-[10.5px]">
                          <span className="text-mist-400">
                            {line.sku} · {formatQuantity(line.quantity, line.unit, locale)}
                          </span>
                          <span className="text-mist-200">
                            {formatMoney(line.line_total, preview.data.header.currency, locale)}
                          </span>
                        </div>
                      ))}
                    </div>
                  </div>
                </>
              ) : (
                <Alert variant="danger">{preview.message}</Alert>
              )
            ) : (
              <Alert variant="info" title={t("dregNoOrderTitle")}>
                {t("dregNoOrderBody")}
              </Alert>
            )}
          </CardContent>
        </Card>
      </div>

      <div className="panel overflow-hidden">
        <form action="/documents" method="get" className="flex flex-wrap items-end gap-2 px-4 py-3">
          <div className="w-full space-y-1 sm:w-auto">
            <label htmlFor="doc-type-filter" className="eyebrow">
              {t("columnType")}
            </label>
            <Select
              id="doc-type-filter"
              name="document_type"
              defaultValue={params.document_type ?? ""}
              className="h-8 w-full text-[12px] sm:w-[240px]"
            >
              <option value="">{t("dregAllTypes")}</option>
              {DOCUMENT_TYPES.map((value) => (
                <option key={value} value={value}>
                  {documentTypeText(t, value)}
                </option>
              ))}
            </Select>
          </div>
          <div className="w-full space-y-1 sm:w-auto">
            <label htmlFor="doc-status-filter" className="eyebrow">
              {t("columnStatus")}
            </label>
            <Select
              id="doc-status-filter"
              name="status"
              defaultValue={params.status ?? ""}
              className="h-8 w-full text-[12px] sm:w-[160px]"
            >
              <option value="">{t("dregAll")}</option>
              <option value="ACTIVE">{t("statusActive")}</option>
              <option value="ARCHIVED">{t("statusArchived")}</option>
            </Select>
          </div>
          <Button type="submit" size="sm" variant="subtle">
            {t("actionApply")}
          </Button>
          {params.document_type || params.status ? (
            <Button asChild size="sm" variant="ghost">
              <Link href="/documents">{t("actionClear")}</Link>
            </Button>
          ) : null}
        </form>

        <div className="hairline" />

        {!documents.ok ? (
          <div className="p-4">
            <Alert variant="danger" title={t("dregUnavailable")}>
              {documents.message}
            </Alert>
          </div>
        ) : documents.data.items.length === 0 ? (
          <div className="p-4">
            <EmptyState title={t("dregNone")} description={t("dregNoneHint")} />
          </div>
        ) : (
          <Table bare>
            <TableHeader>
              <TableRow>
                <TableHead className="pl-4">{t("dregColDocument")}</TableHead>
                <TableHead>{t("columnType")}</TableHead>
                <TableHead>{t("dregColAttached")}</TableHead>
                <TableHead>{t("columnStatus")}</TableHead>
                <TableHead className="text-right">{t("dregColSize")}</TableHead>
                <TableHead>{t("dregColUploaded")}</TableHead>
                <TableHead className="pr-4 text-right">{t("dregColActions")}</TableHead>
              </TableRow>
            </TableHeader>
            <TableBody>
              {documents.data.items.map((document) => (
                <TableRow key={document.id}>
                  <TableCell className="pl-4">
                    <p className="text-[12px] text-mist-100">{document.title}</p>
                    <p className="font-mono text-[9.5px] text-mist-600">
                      v{document.version} · {document.sha256.slice(0, 12)}… ·{" "}
                      {document.original_filename}
                    </p>
                  </TableCell>
                  <TableCell className="text-[11px] text-mist-300">
                    {documentTypeText(t, document.document_type)}
                  </TableCell>
                  <TableCell className="text-[10.5px] text-mist-500">
                    {linkedEntityText(t, document.linked_entity_type)}
                    <span className="block font-mono text-[9px] text-mist-600">
                      {document.linked_entity_id.slice(0, 8)}…
                    </span>
                  </TableCell>
                  <TableCell>
                    <div className="flex flex-wrap gap-1">
                      <Badge variant={document.status === "ACTIVE" ? "secondary" : "outline"}>
                        {operationsStatusText(t, document.status)}
                      </Badge>
                      <Badge
                        variant={
                          document.verification_status === "VERIFIED"
                            ? "success"
                            : document.verification_status === "REJECTED"
                              ? "danger"
                              : "outline"
                        }
                      >
                        {operationsStatusText(t, document.verification_status)}
                      </Badge>
                    </div>
                  </TableCell>
                  <TableCell className="text-right text-[11px] text-mist-400">
                    {formatBytes(document.size_bytes, locale)}
                  </TableCell>
                  <TableCell className="text-[10.5px] text-mist-500">
                    {formatTimestamp(document.uploaded_at, locale)}
                  </TableCell>
                  <TableCell className="pr-4">
                    <div className="flex flex-wrap items-center justify-end gap-2">
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
                  </TableCell>
                </TableRow>
              ))}
            </TableBody>
          </Table>
        )}

        <div className="border-t border-white/[0.06] px-4 py-3">
          <p className="text-[10.5px] leading-relaxed text-mist-600">{t("dregFooter")}</p>
        </div>
      </div>
    </div>
  );
}

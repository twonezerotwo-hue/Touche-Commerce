/**
 * Browser client for sales orders, procurement, shipments and documents.
 *
 * Same contract as the sourcing client: same-origin proxy, CSRF on every write,
 * a fresh `Idempotency-Key` per action and `If-Match` for updates. Multipart
 * uploads let the browser set the content type so the boundary is correct, and
 * the API remains the only authority on file type and size.
 */

import { parseErrorEnvelope } from "@/lib/api/client";
import { BROWSER_API_PREFIX } from "@/lib/api/config";
import { newIdempotencyKey } from "@/lib/sourcing/client";

import type { PurchaseOrder, SalesOrder, Shipment, TradeDocument } from "./types";

export type OperationsResult<T> =
  | { ok: true; data: T; etag: string | null }
  | { ok: false; code: string; message: string; requestId: string | null };

interface JsonOptions {
  method: "POST" | "PATCH";
  path: string;
  body?: unknown;
  csrfToken: string;
  ifMatch?: string | null;
  idempotencyKey?: string;
}

async function requestJson<T>({
  method,
  path,
  body,
  csrfToken,
  ifMatch,
  idempotencyKey,
}: JsonOptions): Promise<OperationsResult<T>> {
  const headers: Record<string, string> = {
    accept: "application/json",
    "X-CSRF-Token": csrfToken,
    "Idempotency-Key": idempotencyKey ?? newIdempotencyKey(),
  };
  if (body !== undefined) headers["content-type"] = "application/json";
  if (ifMatch) headers["If-Match"] = ifMatch;

  try {
    const response = await fetch(`${BROWSER_API_PREFIX}${path}`, {
      method,
      headers,
      body: body === undefined ? undefined : JSON.stringify(body),
      credentials: "same-origin",
      cache: "no-store",
    });
    return await readResult<T>(response);
  } catch {
    return unreachable();
  }
}

async function readResult<T>(response: Response): Promise<OperationsResult<T>> {
  const payload: unknown = await response.json().catch(() => null);
  const requestId = response.headers.get("x-request-id");

  if (!response.ok) {
    const envelope = parseErrorEnvelope(payload);
    return {
      ok: false,
      code: envelope?.error.code ?? `HTTP_${response.status}`,
      message: envelope?.error.message ?? "The request could not be completed.",
      requestId: envelope?.error.request_id ?? requestId,
    };
  }

  return { ok: true, data: payload as T, etag: response.headers.get("etag") };
}

function unreachable(): OperationsResult<never> {
  return {
    ok: false,
    code: "UNREACHABLE",
    message: "Cannot reach the API. Confirm the service is running and try again.",
    requestId: null,
  };
}

export interface AcceptancePayload {
  channel: string;
  accepted_at: string;
  accepted_by_name: string;
  evidence_reference: string;
  evidence_document_id?: string | null;
  notes?: string | null;
}

export function recordCustomerAcceptance(
  dealId: string,
  payload: AcceptancePayload,
  csrfToken: string,
): Promise<OperationsResult<{ id: string }>> {
  return requestJson({
    method: "POST",
    path: `/deals/${dealId}/customer-acceptance`,
    body: payload,
    csrfToken,
  });
}

export interface ConversionPayload {
  sales_quote_id: string;
  acceptance_evidence_id?: string;
  fulfilment_model?: "PURCHASE_RESALE" | "BROKERAGE";
  expected_total?: string;
  notes?: string | null;
}

export function convertDealToOrder(
  dealId: string,
  payload: ConversionPayload,
  csrfToken: string,
  idempotencyKey?: string,
): Promise<OperationsResult<SalesOrder>> {
  return requestJson({
    method: "POST",
    path: `/deals/${dealId}/sales-order`,
    body: payload,
    csrfToken,
    idempotencyKey,
  });
}

export function transitionSalesOrder(
  id: string,
  target: string,
  reason: string | null,
  csrfToken: string,
  etag: string,
): Promise<OperationsResult<SalesOrder>> {
  return requestJson({
    method: "POST",
    path: `/sales-orders/${id}/transitions`,
    body: { target, reason },
    csrfToken,
    ifMatch: etag,
  });
}

export function amendSalesOrder(
  id: string,
  payload: {
    reason: string;
    payment_terms?: string;
    named_delivery_place?: string;
    expected_delivery_date?: string;
    notes?: string;
    lines?: { item_id: string; quantity: string }[];
  },
  csrfToken: string,
  etag: string,
): Promise<OperationsResult<SalesOrder>> {
  return requestJson({
    method: "POST",
    path: `/sales-orders/${id}/amendments`,
    body: payload,
    csrfToken,
    ifMatch: etag,
  });
}

export interface PurchaseOrderPayload {
  sales_order_id: string;
  supplier_id: string;
  supplier_quote_id?: string | null;
  incoterm: string;
  named_delivery_place: string;
  payment_terms: string;
  expected_dispatch_date?: string | null;
  expected_delivery_date?: string | null;
  notes?: string | null;
  items: {
    product_id: string;
    description?: string | null;
    quantity: string;
    unit: string;
    unit_cost: string;
  }[];
}

export function createPurchaseOrder(
  payload: PurchaseOrderPayload,
  csrfToken: string,
): Promise<OperationsResult<PurchaseOrder>> {
  return requestJson({ method: "POST", path: "/purchase-orders", body: payload, csrfToken });
}

export interface PurchaseOrderTransitionPayload {
  target: string;
  reason?: string | null;
  dispatched_at?: string | null;
  dispatch_channel?: string | null;
  dispatch_reference?: string | null;
  supplier_confirmation_reference?: string | null;
  evidence_reference?: string | null;
}

export function transitionPurchaseOrder(
  id: string,
  payload: PurchaseOrderTransitionPayload,
  csrfToken: string,
  etag: string,
): Promise<OperationsResult<PurchaseOrder>> {
  return requestJson({
    method: "POST",
    path: `/purchase-orders/${id}/transitions`,
    body: payload,
    csrfToken,
    ifMatch: etag,
  });
}

export interface ShipmentPayload {
  sales_order_id: string;
  purchase_order_id?: string | null;
  transport_mode: string;
  origin: string;
  destination: string;
  carrier?: string | null;
  forwarder?: string | null;
  planned_dispatch_at?: string | null;
  estimated_arrival_at?: string | null;
  tracking_reference?: string | null;
  tracking_source?: "MANUAL" | "DOCUMENT_EVIDENCE" | null;
  notes?: string | null;
  items: { sales_order_item_id: string; quantity: string }[];
}

export function planShipment(
  payload: ShipmentPayload,
  csrfToken: string,
): Promise<OperationsResult<Shipment>> {
  return requestJson({ method: "POST", path: "/shipments", body: payload, csrfToken });
}

export interface ShipmentTransitionPayload {
  target: string;
  occurred_at?: string | null;
  location?: string | null;
  notes?: string | null;
  reason?: string | null;
  tracking_reference?: string | null;
  tracking_source?: "MANUAL" | "DOCUMENT_EVIDENCE" | null;
  evidence_reference?: string | null;
  delivery_evidence_reference?: string | null;
}

export function transitionShipment(
  id: string,
  payload: ShipmentTransitionPayload,
  csrfToken: string,
  etag: string,
): Promise<OperationsResult<Shipment>> {
  return requestJson({
    method: "POST",
    path: `/shipments/${id}/transitions`,
    body: payload,
    csrfToken,
    ifMatch: etag,
  });
}

export function recordShipmentEvent(
  id: string,
  payload: {
    event_type: "IN_TRANSIT" | "DELAY_RECORDED";
    occurred_at: string;
    location?: string | null;
    notes?: string | null;
    evidence_reference?: string | null;
    tracking_source?: "MANUAL" | "DOCUMENT_EVIDENCE" | null;
  },
  csrfToken: string,
): Promise<OperationsResult<Shipment>> {
  return requestJson({ method: "POST", path: `/shipments/${id}/events`, body: payload, csrfToken });
}

export function recordShipmentCost(
  id: string,
  payload: {
    cost_type: string;
    stage: string;
    amount: string;
    currency: string;
    reference: string;
    notes?: string | null;
  },
  csrfToken: string,
): Promise<OperationsResult<Shipment>> {
  return requestJson({ method: "POST", path: `/shipments/${id}/costs`, body: payload, csrfToken });
}

export function addShipmentReference(
  id: string,
  payload: {
    reference_type: string;
    reference_value: string;
    provenance: "MANUAL" | "DOCUMENT_EVIDENCE";
  },
  csrfToken: string,
): Promise<OperationsResult<Shipment>> {
  return requestJson({
    method: "POST",
    path: `/shipments/${id}/references`,
    body: payload,
    csrfToken,
  });
}

export function uploadDocument(
  form: FormData,
  csrfToken: string,
  idempotencyKey?: string,
): Promise<OperationsResult<TradeDocument>> {
  return requestMultipart<TradeDocument>("/documents", form, csrfToken, idempotencyKey);
}

async function requestMultipart<T>(
  path: string,
  form: FormData,
  csrfToken: string,
  idempotencyKey?: string,
): Promise<OperationsResult<T>> {
  try {
    const response = await fetch(`${BROWSER_API_PREFIX}${path}`, {
      method: "POST",
      headers: {
        accept: "application/json",
        "X-CSRF-Token": csrfToken,
        "Idempotency-Key": idempotencyKey ?? newIdempotencyKey(),
      },
      body: form,
      credentials: "same-origin",
      cache: "no-store",
    });
    return await readResult<T>(response);
  } catch {
    return unreachable();
  }
}

export function archiveDocument(
  id: string,
  reason: string | null,
  csrfToken: string,
): Promise<OperationsResult<TradeDocument>> {
  return requestJson({
    method: "POST",
    path: `/documents/${id}/archive`,
    body: { reason },
    csrfToken,
  });
}

export function verifyDocument(
  id: string,
  status: "VERIFIED" | "REJECTED",
  note: string | null,
  csrfToken: string,
): Promise<OperationsResult<TradeDocument>> {
  return requestJson({
    method: "POST",
    path: `/documents/${id}/verification`,
    body: { verification_status: status, note },
    csrfToken,
  });
}

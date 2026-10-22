/**
 * Presentation helpers for Stage 4 statuses, document types and evidence.
 *
 * The UI never renders a raw enum, and it never invents a tone for a status it
 * does not know: unknown values fall back to the neutral badge.
 */

import type { BadgeTone } from "@/lib/trade/format";

const STATUS_LABELS: Record<string, string> = {
  CONFIRMED: "Confirmed",
  IN_FULFILLMENT: "In fulfillment",
  FULFILLED: "Fulfilled",
  CLOSED: "Closed",
  CANCELLED: "Cancelled",
  DRAFT: "Draft",
  APPROVED: "Approved",
  RECORDED_SENT: "Sent (recorded)",
  SUPPLIER_CONFIRMED: "Supplier confirmed",
  RECEIVED: "Received",
  PLANNED: "Planned",
  BOOKED: "Booked",
  DISPATCHED: "Dispatched",
  IN_TRANSIT: "In transit",
  ARRIVED: "Arrived",
  DELIVERED: "Delivered",
  ACTIVE: "Active",
  ARCHIVED: "Archived",
  UNVERIFIED: "Unverified",
  VERIFIED: "Verified",
  REJECTED: "Rejected",
  MANUAL: "Manual entry",
  DOCUMENT_EVIDENCE: "Document evidence",
  VERIFIED_EXTERNAL: "Verified externally",
};

const STATUS_TONES: Record<string, BadgeTone> = {
  CONFIRMED: "default",
  IN_FULFILLMENT: "warning",
  FULFILLED: "success",
  CLOSED: "outline",
  CANCELLED: "outline",
  DRAFT: "secondary",
  APPROVED: "success",
  RECORDED_SENT: "warning",
  SUPPLIER_CONFIRMED: "success",
  RECEIVED: "success",
  PLANNED: "secondary",
  BOOKED: "default",
  DISPATCHED: "warning",
  IN_TRANSIT: "warning",
  ARRIVED: "success",
  DELIVERED: "success",
  ACTIVE: "default",
  ARCHIVED: "outline",
  UNVERIFIED: "secondary",
  VERIFIED: "success",
  REJECTED: "danger",
};

export function operationsStatusLabel(status: string): string {
  return STATUS_LABELS[status] ?? status;
}

export function operationsStatusTone(status: string): BadgeTone {
  return STATUS_TONES[status] ?? "secondary";
}

const DOCUMENT_TYPE_LABELS: Record<string, string> = {
  COMMERCIAL_INVOICE: "Commercial invoice",
  PROFORMA_INVOICE: "Proforma invoice",
  PACKING_LIST: "Packing list",
  BILL_OF_LADING: "Bill of lading",
  AIR_WAYBILL: "Air waybill",
  CMR_CONSIGNMENT_NOTE: "CMR consignment note",
  CERTIFICATE_OF_ORIGIN: "Certificate of origin",
  INSURANCE_CERTIFICATE: "Insurance certificate",
  QUALITY_INSPECTION_CERTIFICATE: "Quality / inspection certificate",
  CUSTOMS_DECLARATION: "Customs declaration",
  PURCHASE_ORDER: "Purchase order",
  SALES_ORDER: "Sales order",
  DELIVERY_CONFIRMATION: "Delivery confirmation",
  OTHER: "Supporting document",
};

export function documentTypeLabel(value: string): string {
  return DOCUMENT_TYPE_LABELS[value] ?? value;
}

export function transportModeLabel(value: string): string {
  return value === "MULTIMODAL" ? "Multimodal" : value.charAt(0) + value.slice(1).toLowerCase();
}

export function costStageLabel(value: string): string {
  const labels: Record<string, string> = {
    ESTIMATED: "Estimated",
    QUOTED: "Quoted",
    INCURRED: "Incurred",
    DOCUMENTED: "Documented",
  };
  return labels[value] ?? value;
}

/** Human file size without pretending to more precision than there is. */
export function formatBytes(bytes: number): string {
  if (!Number.isFinite(bytes) || bytes < 0) return "—";
  if (bytes < 1024) return `${bytes} B`;
  if (bytes < 1024 * 1024) return `${(bytes / 1024).toFixed(1)} KB`;
  return `${(bytes / (1024 * 1024)).toFixed(1)} MB`;
}

/** Completion ratio (`0.4000`) rendered as a whole percentage. */
export function completionPercent(value: string): string {
  const parsed = Number.parseFloat(value);
  if (!Number.isFinite(parsed)) return "—";
  return `${Math.round(parsed * 100)}%`;
}

/** A shipment is late only when the API says its documented ETA has passed. */
export function delayLabel(isDelayed: boolean, estimatedArrival: string | null): string {
  if (isDelayed) return "Past the documented ETA";
  if (!estimatedArrival) return "No ETA recorded";
  return "Within the documented ETA";
}

export function evidenceProvenanceLabel(value: string | null): string {
  if (!value) return "No tracking provenance recorded";
  return STATUS_LABELS[value] ?? value;
}

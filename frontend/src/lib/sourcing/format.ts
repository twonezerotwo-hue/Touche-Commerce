/**
 * Presentation helpers for sourcing statuses and percentages.
 *
 * Statuses are enum values from the API (`PENDING_APPROVAL`); the UI never
 * renders a raw enum, and it never invents a tone for a status it does not know.
 */

import type { BadgeTone } from "@/lib/trade/format";

const STATUS_LABELS: Record<string, string> = {
  DRAFT: "Draft",
  PREPARED: "Prepared",
  SENT: "Sent",
  RESPONDED: "Responded",
  CLOSED: "Closed",
  CANCELLED: "Cancelled",
  RECEIVED: "Received",
  WITHDRAWN: "Withdrawn",
  INCOMPLETE: "Incomplete",
  ESTIMATED: "Estimated",
  VERIFIED_INPUTS: "Verified inputs",
  PENDING_APPROVAL: "Pending approval",
  APPROVED: "Approved",
  REJECTED: "Rejected",
};

const STATUS_TONES: Record<string, BadgeTone> = {
  DRAFT: "secondary",
  PREPARED: "default",
  SENT: "warning",
  RESPONDED: "success",
  CLOSED: "outline",
  CANCELLED: "outline",
  RECEIVED: "success",
  WITHDRAWN: "outline",
  INCOMPLETE: "danger",
  ESTIMATED: "warning",
  VERIFIED_INPUTS: "success",
  PENDING_APPROVAL: "warning",
  APPROVED: "success",
  REJECTED: "danger",
};

export function statusLabel(status: string): string {
  return STATUS_LABELS[status] ?? status;
}

export function statusTone(status: string): BadgeTone {
  return STATUS_TONES[status] ?? "secondary";
}

/** Render a stored percentage (`20.0000`) without trailing zeros. */
export function formatPercent(value: string | null | undefined): string {
  if (value === null || value === undefined || value === "") return "—";
  const parsed = Number.parseFloat(value);
  if (!Number.isFinite(parsed)) return value;
  return `${new Intl.NumberFormat("en-GB", { maximumFractionDigits: 2 }).format(parsed)}%`;
}

/** A shared `ETag: "v{n}"` header value for an optimistic update. */
export function etagFor(version: number): string {
  return `"v${version}"`;
}

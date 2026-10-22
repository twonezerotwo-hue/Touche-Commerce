/**
 * Presentation helpers for trade values.
 *
 * The API sends decimals as strings so no binary floating point ever touches a
 * price. These helpers parse only for display, and fall back to the raw string
 * when a value is not numeric rather than showing `NaN`.
 */

import type { DealStatus } from "./types";

export type BadgeTone = "default" | "secondary" | "success" | "warning" | "danger" | "outline";

const STATUS_LABELS: Record<DealStatus, string> = {
  DRAFT: "Draft",
  OPEN: "Open",
  NEGOTIATION: "Negotiation",
  WON: "Won",
  LOST: "Lost",
  CANCELLED: "Cancelled",
};

const STATUS_TONES: Record<DealStatus, BadgeTone> = {
  DRAFT: "secondary",
  OPEN: "default",
  NEGOTIATION: "warning",
  WON: "success",
  LOST: "danger",
  CANCELLED: "outline",
};

export function statusLabel(status: DealStatus): string {
  return STATUS_LABELS[status] ?? status;
}

export function statusTone(status: DealStatus): BadgeTone {
  return STATUS_TONES[status] ?? "secondary";
}

const CURRENCY_FORMATTERS = new Map<string, Intl.NumberFormat>();

function formatterFor(currency: string): Intl.NumberFormat {
  const key = currency || "USD";
  const existing = CURRENCY_FORMATTERS.get(key);
  if (existing) return existing;
  const formatter = new Intl.NumberFormat("en-GB", {
    style: "currency",
    currency: key,
    maximumFractionDigits: 2,
  });
  CURRENCY_FORMATTERS.set(key, formatter);
  return formatter;
}

/** Format a decimal string as money; invalid values are returned unchanged. */
export function formatMoney(value: string, currency = "USD"): string {
  const parsed = Number.parseFloat(value);
  if (!Number.isFinite(parsed)) return value;
  try {
    return formatterFor(currency).format(parsed);
  } catch {
    return `${value} ${currency}`;
  }
}

/** Format a decimal string without inventing precision. */
export function formatQuantity(value: string, unit?: string): string {
  const parsed = Number.parseFloat(value);
  if (!Number.isFinite(parsed)) return value;
  const formatted = new Intl.NumberFormat("en-GB", { maximumFractionDigits: 3 }).format(parsed);
  return unit ? `${formatted} ${unit}` : formatted;
}

/** Multiply two decimal strings with cent rounding, without float drift. */
export function lineTotal(quantity: string, unitPrice: string): string {
  const q = Number.parseFloat(quantity);
  const p = Number.parseFloat(unitPrice);
  if (!Number.isFinite(q) || !Number.isFinite(p) || q <= 0 || p < 0) return "0.00";
  return (Math.round(q * p * 100) / 100).toFixed(2);
}

export function sumTotals(values: readonly string[]): string {
  const cents = values.reduce((total, value) => {
    const parsed = Number.parseFloat(value);
    return total + (Number.isFinite(parsed) ? Math.round(parsed * 100) : 0);
  }, 0);
  return (cents / 100).toFixed(2);
}

export function formatDate(value: string | null): string {
  if (!value) return "—";
  const date = new Date(value);
  if (Number.isNaN(date.getTime())) return value;
  return new Intl.DateTimeFormat("en-GB", {
    day: "2-digit",
    month: "short",
    year: "numeric",
  }).format(date);
}

export function formatTimestamp(value: string | null): string {
  if (!value) return "—";
  const date = new Date(value);
  if (Number.isNaN(date.getTime())) return value;
  return new Intl.DateTimeFormat("en-GB", {
    day: "2-digit",
    month: "short",
    year: "numeric",
    hour: "2-digit",
    minute: "2-digit",
    timeZone: "UTC",
  }).format(date);
}

/** Build a same-page URL keeping only meaningful query parameters. */
export function withQuery(base: string, params: Record<string, string | null | undefined>): string {
  const search = new URLSearchParams();
  for (const [key, value] of Object.entries(params)) {
    if (value !== null && value !== undefined && value !== "") search.set(key, value);
  }
  const rendered = search.toString();
  return rendered ? `${base}?${rendered}` : base;
}

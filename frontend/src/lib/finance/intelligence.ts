/** Stage 5E financial intelligence types and pure helpers (generated OpenAPI contract). */

import type { components } from "@/lib/api/schema";
import { formatMoney } from "@/lib/trade/format";

type Schemas = components["schemas"];

export type IntelligenceSummary = Schemas["IntelligenceSummaryResponse"];
export type IntelligenceMetric = Schemas["IntelligenceMetricResponse"];
export type IntelligenceCoverage = Schemas["CoverageResponse"];
export type IntelligenceFilterOptions = Schemas["FilterOptionsResponse"];
export type OrderProfitability = Schemas["OrderProfitabilityResponse"];
export type OrderIntelligenceList = Schemas["OrderIntelligenceListResponse"];
export type CostVarianceList = Schemas["CostVarianceListResponse"];
export type OrderIntelligenceDetail = Schemas["OrderIntelligenceDetailResponse"];
export type FinancialException = Schemas["FinancialExceptionResponse"];
export type FinancialExceptionList = Schemas["FinancialExceptionListResponse"];
export type MonthlyCommitment = Schemas["MonthlyCommitmentResponse"];
export type CostComparison = Schemas["CostComparisonResponse"];
export type MarginBucket = Schemas["MarginBucketResponse"];
export type CategoryCount = Schemas["CategoryCountResponse"];
export type CompletenessCount = Schemas["CompletenessCountResponse"];
export type Completeness = Schemas["IntelligenceMetricResponse"]["completeness"];

export const INTELLIGENCE_ANALYSIS_NOTICE =
  "Operational financial analysis only. It is not a statutory financial statement and not accounting profit; actual profit stays unavailable because Finance exposes no transaction-level invoice or payment source.";

/** The only query keys the intelligence screens read, forward or serialise. */
export const INTELLIGENCE_FILTER_KEYS = [
  "from",
  "to",
  "currency",
  "fulfilment_model",
  "order_status",
  "customer_id",
  "supplier_id",
  "reconciliation_status",
  "completeness",
] as const;

export type IntelligenceFilterKey = (typeof INTELLIGENCE_FILTER_KEYS)[number];
export type IntelligenceFilters = Partial<Record<IntelligenceFilterKey, string>>;

const DATE_PATTERN = /^\d{4}-\d{2}-\d{2}$/;
const CURRENCY_PATTERN = /^[A-Za-z]{3}$/;
const UUID_PATTERN = /^[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}$/i;
const TOKEN_PATTERN = /^[A-Z][A-Z_]{0,31}$/;

function firstValue(value: string | string[] | undefined): string {
  return (Array.isArray(value) ? value[0] : value)?.trim() ?? "";
}

function normalise(key: IntelligenceFilterKey, raw: string): string | null {
  if (!raw) return null;
  switch (key) {
    case "from":
    case "to":
      return DATE_PATTERN.test(raw) ? raw : null;
    case "currency":
      return CURRENCY_PATTERN.test(raw) ? raw.toUpperCase() : null;
    case "customer_id":
    case "supplier_id":
      return UUID_PATTERN.test(raw) ? raw.toLowerCase() : null;
    default: {
      const token = raw.toUpperCase();
      return TOKEN_PATTERN.test(token) ? token : null;
    }
  }
}

/** Keep only known, well-formed filters; anything else is dropped silently. */
export function parseIntelligenceFilters(
  params: Record<string, string | string[] | undefined>,
): IntelligenceFilters {
  const filters: IntelligenceFilters = {};
  for (const key of INTELLIGENCE_FILTER_KEYS) {
    const value = normalise(key, firstValue(params[key]));
    if (value !== null) filters[key] = value;
  }
  return filters;
}

/** Query string for the intelligence API (filters plus optional paging). */
export function intelligenceQuery(
  filters: IntelligenceFilters,
  extra: Record<string, string | number | null | undefined> = {},
): string {
  const search = new URLSearchParams();
  for (const key of INTELLIGENCE_FILTER_KEYS) {
    const value = filters[key];
    if (value) search.set(key, value);
  }
  for (const [key, value] of Object.entries(extra)) {
    if (value !== null && value !== undefined && value !== "") search.set(key, String(value));
  }
  return search.toString();
}

export function hasActiveFilters(filters: IntelligenceFilters): boolean {
  return INTELLIGENCE_FILTER_KEYS.some((key) => Boolean(filters[key]));
}

export function humanize(value: string): string {
  return value.replaceAll("_", " ");
}

/**
 * File name for a downloaded export: the server's `Content-Disposition` name when
 * it is a plain file name, otherwise a dated fallback. Never trusts a path.
 */
export function exportFilename(disposition: string | null, fallback: string): string {
  const match = /filename="?([^";]+)"?/i.exec(disposition ?? "");
  const name = match?.[1]?.trim();
  return name && /^[\w.-]+$/.test(name) ? name : fallback;
}

export const COMPLETENESS_LABELS: Record<Completeness, string> = {
  COMPLETE: "COMPLETE",
  PARTIAL: "PARTIAL",
  MISSING: "MISSING",
  UNAVAILABLE: "UNAVAILABLE",
};

export function completenessTone(
  value: Completeness,
): "success" | "warning" | "danger" | "outline" {
  switch (value) {
    case "COMPLETE":
      return "success";
    case "PARTIAL":
      return "warning";
    case "MISSING":
      return "danger";
    default:
      return "outline";
  }
}

/** True for a decimal string below zero; a missing or unparsable value is not a loss. */
export function isNegative(value: string | null | undefined): boolean {
  const parsed = Number.parseFloat(value ?? "");
  return Number.isFinite(parsed) && parsed < 0;
}

export interface MetricLine {
  /** Currency the line is denominated in; null for counts. */
  currency: string | null;
  text: string;
  /** Below zero (a loss); the text keeps its minus sign, colour only reinforces it. */
  negative: boolean;
}

/**
 * Lines to render for one metric. Money and percentages stay one line per
 * currency — nothing is summed across currencies — and an unavailable metric
 * has no lines at all, so it can never be shown as zero.
 */
export function metricLines(metric: IntelligenceMetric): MetricLine[] {
  if (!metric.available) return [];
  switch (metric.kind) {
    case "MONEY":
      return metric.money.map((item) => ({
        currency: item.currency,
        text: formatMoney(item.amount, item.currency),
        negative: isNegative(item.amount),
      }));
    case "PERCENT": {
      if (metric.percentages.length > 0) {
        return metric.percentages.map((item) => ({
          currency: item.currency,
          text: `${item.value}%`,
          negative: isNegative(item.value),
        }));
      }
      return metric.percentage
        ? [
            {
              currency: null,
              text: `${metric.percentage}%`,
              negative: isNegative(metric.percentage),
            },
          ]
        : [];
    }
    default:
      return typeof metric.count === "number"
        ? [{ currency: null, text: String(metric.count), negative: false }]
        : [];
  }
}

/**
 * Bar length as a 0–100 share of the largest absolute value. Only used to size
 * a mark; the figure shown to the reader is always the backend's decimal string.
 */
export function barShare(value: string | null | undefined, maximum: number): number {
  if (value === null || value === undefined || !(maximum > 0)) return 0;
  const parsed = Number.parseFloat(value);
  if (!Number.isFinite(parsed)) return 0;
  return Math.min(100, (Math.abs(parsed) / maximum) * 100);
}

export function maxAbs(values: ReadonlyArray<string | null | undefined>): number {
  let maximum = 0;
  for (const value of values) {
    if (value === null || value === undefined) continue;
    const parsed = Number.parseFloat(value);
    if (Number.isFinite(parsed)) maximum = Math.max(maximum, Math.abs(parsed));
  }
  return maximum;
}

export type TooltipAlign = "start" | "center" | "end";

/** Keep a tooltip inside its chart: marks in the first or last third anchor to that edge. */
export function tooltipAlign(index: number, count: number): TooltipAlign {
  if (count < 5) return "center";
  const edge = Math.ceil(count / 3);
  if (index < edge) return "start";
  if (index >= count - edge) return "end";
  return "center";
}

/** Group rows by currency, preserving first-seen currency order. */
export function groupByCurrency<T extends { currency: string }>(
  rows: readonly T[],
): Array<{ currency: string; rows: T[] }> {
  const groups = new Map<string, T[]>();
  for (const row of rows) {
    const bucket = groups.get(row.currency);
    if (bucket) bucket.push(row);
    else groups.set(row.currency, [row]);
  }
  return [...groups].map(([currency, grouped]) => ({ currency, rows: grouped }));
}

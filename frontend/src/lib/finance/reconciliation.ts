/** Stage 5D reconciliation types derived from the generated OpenAPI contract. */

import type { components } from "@/lib/api/schema";

export type ReconciliationRun = components["schemas"]["ReconciliationRunResponse"];
export type ReconciliationRunSummary = components["schemas"]["ReconciliationRunSummaryResponse"];
export type ReconciliationList = components["schemas"]["ReconciliationListResponse"];
export type ReconciliationMetrics = components["schemas"]["ReconciliationMetricsResponse"];
export type ReconciliationDiscrepancy = components["schemas"]["DiscrepancyResponse"];
export type ReconciliationDiscrepancyList = components["schemas"]["DiscrepancyListResponse"];
export type ReconciliationEvidence = components["schemas"]["EvidenceLinkResponse"];
export type ReconciliationReview = components["schemas"]["ReviewResponse"];
export type ReconciliationSourceReference = components["schemas"]["SourceReferenceResponse"];
export type OrderFinance = components["schemas"]["OrderFinanceResponse"];
export type OrderFinanceEvidenceGap = components["schemas"]["OrderFinanceEvidenceGap"];

export const RECONCILIATION_STATUS_LABELS = {
  INCOMPLETE: "INCOMPLETE",
  UNMATCHED: "UNMATCHED",
  POTENTIAL_MATCH: "POTENTIAL MATCH",
  MATCHED_EVIDENCE: "MATCHED EVIDENCE",
  VERIFIED: "VERIFIED",
  DISPUTED: "DISPUTED",
} as const;

export function reconciliationStatusLabel(status: ReconciliationRun["status"]): string {
  return RECONCILIATION_STATUS_LABELS[status] ?? status;
}

export function reconciliationStatusTone(
  status: ReconciliationRun["status"],
): "success" | "warning" | "danger" | "secondary" | "outline" | "default" {
  switch (status) {
    case "VERIFIED":
      return "success";
    case "MATCHED_EVIDENCE":
      return "default";
    case "POTENTIAL_MATCH":
      return "warning";
    case "DISPUTED":
      return "danger";
    case "INCOMPLETE":
      return "danger";
    default:
      return "outline";
  }
}

export function discrepancyTone(
  severity: ReconciliationDiscrepancy["severity"],
): "success" | "warning" | "danger" | "secondary" | "outline" {
  switch (severity) {
    case "BLOCKING":
    case "ERROR":
      return "danger";
    case "WARNING":
      return "warning";
    case "INFO":
      return "outline";
    default:
      return "secondary";
  }
}

export function classificationLabel(value: string | undefined): string {
  switch (value) {
    case "ESTIMATED":
      return "ESTIMATED";
    case "COMMITTED":
      return "COMMITTED";
    case "DOCUMENTED":
      return "DOCUMENTED";
    case "FINANCE_OBSERVED":
      return "FINANCE OBSERVED";
    case "VERIFIED":
      return "VERIFIED";
    default:
      return "UNAVAILABLE";
  }
}

export function isOpenDiscrepancy(item: ReconciliationDiscrepancy): boolean {
  return item.status === "OPEN";
}

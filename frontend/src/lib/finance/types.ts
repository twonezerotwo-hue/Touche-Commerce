/** Stage 5C Finance types derived from the generated OpenAPI contract. */

import type { components } from "@/lib/api/schema";

export type FinanceStatus = components["schemas"]["FinanceStatusResponse"];
export type FinanceCapabilities = components["schemas"]["FinanceCapabilitiesResponse"];
export type FinanceSummary = components["schemas"]["FinanceSummaryResponse"];
export type FinanceAccounts = components["schemas"]["FinanceAccountsResponse"];
export type FinanceAging = components["schemas"]["FinanceAgingResponse"];
export type FinanceMoney = components["schemas"]["FinanceMoney"];

export const FINANCE_VIEWS = ["overview", "accounts", "receivables", "payables"] as const;
export type FinanceView = (typeof FINANCE_VIEWS)[number];

export const FINANCE_STATE_LABELS: Record<FinanceStatus["state"], string> = {
  not_configured: "NOT_CONFIGURED",
  disabled: "DISABLED",
  connected: "CONNECTED",
  degraded: "DEGRADED",
  unavailable: "UNAVAILABLE",
  auth_error: "AUTH_ERROR",
};

export function financeStateLabel(state: FinanceStatus["state"]): string {
  return FINANCE_STATE_LABELS[state] ?? state.toUpperCase();
}

export function financeStateTone(
  state: FinanceStatus["state"],
): "success" | "warning" | "danger" | "secondary" | "outline" {
  switch (state) {
    case "connected":
      return "success";
    case "degraded":
      return "warning";
    case "auth_error":
    case "unavailable":
      return "danger";
    case "not_configured":
      return "outline";
    default:
      return "secondary";
  }
}

export function parseFinanceView(value: string | undefined): FinanceView {
  return FINANCE_VIEWS.includes(value as FinanceView) ? (value as FinanceView) : "overview";
}

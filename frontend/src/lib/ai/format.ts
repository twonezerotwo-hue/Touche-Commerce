/** Pure presentation helpers for the AI Office (no network, no React). */

import type { AiBasis, AiEvidence, AiRunStatus, AiToolCallStatus } from "@/lib/ai/types";

export type Tone = "default" | "secondary" | "success" | "warning" | "danger" | "info" | "outline";

export const BASIS_META: Record<AiBasis, { label: string; tone: Tone; meaning: string }> = {
  CONFIRMED_SOURCE: {
    label: "Confirmed source",
    tone: "success",
    meaning: "Backed by a stored record returned by a tool.",
  },
  ESTIMATED: {
    label: "Estimated",
    tone: "info",
    meaning: "Backed by a stored estimate or scenario, not a confirmed fact.",
  },
  INCOMPLETE: {
    label: "Incomplete",
    tone: "warning",
    meaning: "The source record is partial; some inputs are missing.",
  },
  AI_INFERENCE: {
    label: "AI inference",
    tone: "default",
    meaning: "The assistant's own reasoning. No stored record supports it.",
  },
  NOT_AVAILABLE: {
    label: "Not available",
    tone: "outline",
    meaning: "The data does not exist in the records.",
  },
};

export const RUN_STATUS_META: Record<AiRunStatus, { label: string; tone: Tone }> = {
  RUNNING: { label: "Working", tone: "info" },
  COMPLETED: { label: "Completed", tone: "success" },
  FAILED: { label: "Failed", tone: "danger" },
  CANCELLED: { label: "Cancelled", tone: "secondary" },
};

export const TOOL_STATUS_META: Record<AiToolCallStatus, { label: string; tone: Tone }> = {
  OK: { label: "Read", tone: "success" },
  DENIED: { label: "Denied", tone: "danger" },
  INVALID: { label: "Rejected input", tone: "warning" },
  ERROR: { label: "No result", tone: "warning" },
  LIMITED: { label: "Limit reached", tone: "warning" },
};

export const MODE_META = {
  DISABLED: { label: "Disabled", tone: "danger" },
  MOCK: { label: "Offline test provider", tone: "warning" },
  REAL: { label: "Live provider", tone: "success" },
} as const satisfies Record<string, { label: string; tone: Tone }>;

const ERROR_TEXT: Record<string, string> = {
  AI_DISABLED: "The AI Office is switched off for this deployment.",
  AI_PROVIDER_UNAVAILABLE: "The AI provider is unavailable right now. Nothing was changed.",
  AI_PROVIDER_TIMEOUT: "The AI provider did not answer in time. Try again in a moment.",
  AI_PROVIDER_RATE_LIMITED: "The AI provider is rate limiting requests. Try again shortly.",
  AI_PROVIDER_AUTH_FAILED: "The server's AI credential was rejected. An administrator must fix it.",
  AI_PROVIDER_QUOTA_EXCEEDED: "The AI provider account has no remaining quota.",
  AI_PROVIDER_BAD_RESPONSE: "The AI provider returned something unusable. Nothing was changed.",
  AI_BUDGET_EXCEEDED: "The AI usage budget was reached, so the request was stopped.",
  AI_TOO_MANY_RUNS: "Too many AI requests are running. Wait a moment and try again.",
  AI_INPUT_TOO_LARGE: "That message is too large for the AI Office.",
  AI_RUN_CANCELLED: "The request was cancelled.",
  AI_RUN_ABANDONED: "The request was interrupted before it finished.",
  AI_PROPOSAL_STATE_INVALID: "This proposal was already decided or cannot be changed.",
  AI_ACTION_NOT_SUPPORTED: "This kind of action cannot be executed by the AI Office.",
  VERSION_CONFLICT: "Someone changed this proposal. Reload to see the latest version.",
  FORBIDDEN: "Your role does not allow this action.",
  INTERNAL_ERROR: "The request failed unexpectedly. Nothing was changed.",
};

/** A calm sentence for an error code; falls back to the server's own message. */
export function describeError(code: string | null | undefined, fallback?: string | null): string {
  if (code && ERROR_TEXT[code]) return ERROR_TEXT[code];
  return fallback || "The request could not be completed.";
}

const WARNING_TEXT: Record<string, string> = {
  UNVERIFIED_NUMBER:
    "A figure in this text did not come from any record the assistant read. Treat it as unverified.",
  UNVERIFIED_FIGURE_REMOVED: "A figure with no matching record was removed.",
  UNKNOWN_EVIDENCE_REMOVED: "A citation that does not exist was removed.",
  NO_SOURCE_EVIDENCE: "No stored record supports this, so it is shown as an inference.",
  BASIS_DOWNGRADED:
    "Labelled more weakly because one of its sources is only an estimate or partial.",
  BASIS_INVALID: "The assistant used an unknown label; shown as an inference.",
  UNKNOWN_TARGET_REMOVED: "The record this refers to was not found and was removed.",
  RESPONSE_NOT_STRUCTURED: "The assistant answered in plain text, so nothing could be verified.",
  EDITED_BY_USER: "Edited by a person after the assistant wrote it.",
};

export function describeWarning(code: string): string {
  return WARNING_TEXT[code] ?? code.replaceAll("_", " ").toLowerCase();
}

export function humanTool(name: string): string {
  const spaced = name.replaceAll("_", " ");
  return spaced.charAt(0).toUpperCase() + spaced.slice(1);
}

export function isRunFinished(status: AiRunStatus): boolean {
  return status !== "RUNNING";
}

/** Only application-internal paths are ever linked; anything else is shown as text. */
export function safeSourceHref(evidence: Pick<AiEvidence, "href">): string | null {
  const href = evidence.href;
  if (!href || !href.startsWith("/") || href.startsWith("//") || href.includes("\\")) return null;
  return href;
}

export function formatTokens(value: number): string {
  if (value >= 1_000_000) return `${(value / 1_000_000).toFixed(1)}M`;
  if (value >= 10_000) return `${Math.round(value / 1000)}k`;
  if (value >= 1000) return `${(value / 1000).toFixed(1)}k`;
  return String(value);
}

export function formatUsd(value: string): string {
  const parsed = Number.parseFloat(value);
  if (!Number.isFinite(parsed)) return "$0.00";
  return parsed > 0 && parsed < 0.01 ? "<$0.01" : `$${parsed.toFixed(2)}`;
}

export function budgetPercent(used: number, budget: number): number {
  if (!Number.isFinite(budget) || budget <= 0) return 0;
  return Math.min(100, (used / budget) * 100);
}

export const DRAFT_KIND_LABEL: Record<string, string> = {
  RFQ_EMAIL: "RFQ e-mail",
  SUPPLIER_FOLLOW_UP: "Supplier follow-up",
  CUSTOMER_UPDATE: "Customer update",
  OTHER: "Draft",
};

export const PRIORITY_TONE: Record<string, Tone> = {
  HIGH: "danger",
  MEDIUM: "warning",
  LOW: "secondary",
};

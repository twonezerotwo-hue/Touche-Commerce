"use client";

import { parseErrorEnvelope } from "@/lib/api/client";
import { BROWSER_API_PREFIX } from "@/lib/api/config";
import { newIdempotencyKey } from "@/lib/sourcing/client";
import type { ReconciliationDiscrepancy, ReconciliationRun } from "@/lib/finance/reconciliation";

export type FinanceActionResult<T> =
  | { ok: true; data: T; etag: string | null }
  | { ok: false; code: string; message: string; requestId: string | null };

async function postJson<T>({
  path,
  body,
  csrfToken,
  ifMatch,
}: {
  path: string;
  body: unknown;
  csrfToken: string;
  ifMatch?: string;
}): Promise<FinanceActionResult<T>> {
  const headers: Record<string, string> = {
    accept: "application/json",
    "content-type": "application/json",
    "X-CSRF-Token": csrfToken,
    "Idempotency-Key": newIdempotencyKey(),
  };
  if (ifMatch) headers["If-Match"] = ifMatch;

  try {
    const response = await fetch(`${BROWSER_API_PREFIX}${path}`, {
      method: "POST",
      headers,
      body: JSON.stringify(body),
      credentials: "same-origin",
      cache: "no-store",
    });
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
    return {
      ok: true,
      data: payload as T,
      etag: response.headers.get("etag"),
    };
  } catch {
    return {
      ok: false,
      code: "UNREACHABLE",
      message: "Cannot reach the API. Confirm the service is running and try again.",
      requestId: null,
    };
  }
}

export function createReconciliationRun(
  payload: { sales_order_id: string; currency: string; as_of: string },
  csrfToken: string,
): Promise<FinanceActionResult<ReconciliationRun>> {
  return postJson({
    path: "/finance/reconciliation/runs",
    body: payload,
    csrfToken,
  });
}

export function linkReconciliationEvidence(
  payload: {
    run_id: string;
    source_entity_type: "SALES_ORDER" | "PURCHASE_ORDER" | "SHIPMENT_COST";
    source_entity_id: string;
    finance_source_reference_id: string;
    notes?: string | null;
  },
  csrfToken: string,
  etag: string,
): Promise<FinanceActionResult<ReconciliationRun>> {
  return postJson({
    path: "/finance/evidence-links",
    body: payload,
    csrfToken,
    ifMatch: etag,
  });
}

export function reviewReconciliation(
  payload: {
    run_id: string;
    decision: "CONFIRM" | "DISPUTE" | "REQUEST_CHANGES";
    notes: string;
  },
  csrfToken: string,
  etag: string,
): Promise<FinanceActionResult<ReconciliationRun>> {
  return postJson({
    path: "/finance/reviews",
    body: payload,
    csrfToken,
    ifMatch: etag,
  });
}

export function resolveReconciliationDiscrepancy(
  discrepancyId: string,
  notes: string,
  csrfToken: string,
  etag: string,
): Promise<FinanceActionResult<ReconciliationDiscrepancy>> {
  return postJson({
    path: `/finance/discrepancies/${discrepancyId}/resolve`,
    body: { notes },
    csrfToken,
    ifMatch: etag,
  });
}

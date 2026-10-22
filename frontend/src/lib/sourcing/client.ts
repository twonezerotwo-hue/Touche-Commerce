/**
 * Browser-side sourcing client.
 *
 * Same conventions as the trade client: same-origin proxy, CSRF header on every
 * mutation, a fresh `Idempotency-Key` per action, and `If-Match` for anything
 * that changes an existing row. A 409 is surfaced with its stable error code so
 * the UI can explain what the user has to do instead of showing a generic error.
 */

import { parseErrorEnvelope } from "@/lib/api/client";
import { BROWSER_API_PREFIX } from "@/lib/api/config";

import type {
  PricingScenario,
  PricingScenarioRequest,
  Rfq,
  RfqCreate,
  RfqTransitionRequest,
  SalesQuote,
  SalesQuoteCreate,
  SupplierQuote,
  SupplierQuoteCreate,
} from "./types";

export type SourcingResult<T> =
  | { ok: true; data: T; etag: string | null }
  | { ok: false; code: string; message: string; requestId: string | null };

interface RequestOptions {
  method: "POST" | "PUT" | "PATCH";
  path: string;
  body?: unknown;
  csrfToken: string;
  ifMatch?: string | null;
}

export function newIdempotencyKey(): string {
  if (typeof crypto !== "undefined" && typeof crypto.randomUUID === "function") {
    return crypto.randomUUID();
  }
  return `key-${Date.now().toString(36)}-${Math.random().toString(36).slice(2, 12)}`;
}

async function request<T>({
  method,
  path,
  body,
  csrfToken,
  ifMatch,
}: RequestOptions): Promise<SourcingResult<T>> {
  const headers: Record<string, string> = {
    accept: "application/json",
    "X-CSRF-Token": csrfToken,
    "Idempotency-Key": newIdempotencyKey(),
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

type RfqBatch = { items: Rfq[] };

export function createRfqs(
  payload: RfqCreate,
  csrfToken: string,
): Promise<SourcingResult<RfqBatch>> {
  return request<RfqBatch>({ method: "POST", path: "/rfqs", body: payload, csrfToken });
}

export function transitionRfq(
  id: string,
  payload: RfqTransitionRequest,
  csrfToken: string,
  etag?: string | null,
): Promise<SourcingResult<Rfq>> {
  return request<Rfq>({
    method: "POST",
    path: `/rfqs/${id}/transitions`,
    body: payload,
    csrfToken,
    ifMatch: etag ?? null,
  });
}

export function recordSupplierQuote(
  rfqId: string,
  payload: SupplierQuoteCreate,
  csrfToken: string,
): Promise<SourcingResult<SupplierQuote>> {
  return request<SupplierQuote>({
    method: "POST",
    path: `/rfqs/${rfqId}/quotes`,
    body: payload,
    csrfToken,
  });
}

export function createPricingScenario(
  payload: PricingScenarioRequest,
  csrfToken: string,
): Promise<SourcingResult<PricingScenario>> {
  return request<PricingScenario>({
    method: "POST",
    path: "/pricing-scenarios",
    body: payload,
    csrfToken,
  });
}

export function createSalesQuote(
  payload: SalesQuoteCreate,
  csrfToken: string,
): Promise<SourcingResult<SalesQuote>> {
  return request<SalesQuote>({
    method: "POST",
    path: "/sales-quotes",
    body: payload,
    csrfToken,
  });
}

export type SalesQuoteAction = "submit" | "approve" | "reject" | "withdraw" | "revisions";

export function actOnSalesQuote(
  id: string,
  action: SalesQuoteAction,
  payload: Record<string, unknown> | null,
  csrfToken: string,
  etag: string,
): Promise<SourcingResult<SalesQuote>> {
  return request<SalesQuote>({
    method: "POST",
    path: `/sales-quotes/${id}/${action}`,
    body: payload ?? {},
    csrfToken,
    ifMatch: etag,
  });
}

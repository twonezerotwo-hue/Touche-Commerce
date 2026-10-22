/**
 * Browser-side trade client.
 *
 * Every call goes to the same-origin proxy so the HttpOnly session cookie is
 * first-party. Mutations send the CSRF token from the server-rendered session,
 * a fresh `Idempotency-Key` (so a network retry cannot duplicate a deal or a
 * transition) and, for updates, the `If-Match` version returned by the last read.
 */

import { parseErrorEnvelope } from "@/lib/api/client";
import { BROWSER_API_PREFIX } from "@/lib/api/config";

import type {
  Counterparty,
  CounterpartyCreate,
  CounterpartyUpdate,
  Deal,
  DealCreate,
  DealTransitionRequest,
  DealUpdate,
  Product,
  ProductCreate,
  ProductUpdate,
} from "./types";

export type TradeResult<T> =
  | { ok: true; data: T; etag: string | null }
  | { ok: false; code: string; message: string; requestId: string | null };

interface RequestOptions {
  method: "POST" | "PATCH";
  path: string;
  body?: unknown;
  csrfToken: string;
  requireIdempotency?: boolean;
  ifMatch?: string | null;
}

/** Browser-safe unique key; falls back only where WebCrypto is unavailable. */
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
  requireIdempotency = true,
  ifMatch,
}: RequestOptions): Promise<TradeResult<T>> {
  const headers: Record<string, string> = {
    accept: "application/json",
    "X-CSRF-Token": csrfToken,
  };
  if (body !== undefined) headers["content-type"] = "application/json";
  if (requireIdempotency) headers["Idempotency-Key"] = newIdempotencyKey();
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

export function createCounterparty(
  payload: CounterpartyCreate,
  csrfToken: string,
): Promise<TradeResult<Counterparty>> {
  return request<Counterparty>({
    method: "POST",
    path: "/counterparties",
    body: payload,
    csrfToken,
  });
}

export function updateCounterparty(
  id: string,
  payload: CounterpartyUpdate,
  csrfToken: string,
  etag: string,
): Promise<TradeResult<Counterparty>> {
  return request<Counterparty>({
    method: "PATCH",
    path: `/counterparties/${id}`,
    body: payload,
    csrfToken,
    ifMatch: etag,
  });
}

export function createProduct(
  payload: ProductCreate,
  csrfToken: string,
): Promise<TradeResult<Product>> {
  return request<Product>({ method: "POST", path: "/products", body: payload, csrfToken });
}

export function updateProduct(
  id: string,
  payload: ProductUpdate,
  csrfToken: string,
  etag: string,
): Promise<TradeResult<Product>> {
  return request<Product>({
    method: "PATCH",
    path: `/products/${id}`,
    body: payload,
    csrfToken,
    ifMatch: etag,
  });
}

export function createDeal(payload: DealCreate, csrfToken: string): Promise<TradeResult<Deal>> {
  return request<Deal>({ method: "POST", path: "/deals", body: payload, csrfToken });
}

export function updateDeal(
  id: string,
  payload: DealUpdate,
  csrfToken: string,
  etag: string,
): Promise<TradeResult<Deal>> {
  return request<Deal>({
    method: "PATCH",
    path: `/deals/${id}`,
    body: payload,
    csrfToken,
    ifMatch: etag,
  });
}

export function transitionDeal(
  id: string,
  payload: DealTransitionRequest,
  csrfToken: string,
  etag?: string | null,
): Promise<TradeResult<Deal>> {
  return request<Deal>({
    method: "POST",
    path: `/deals/${id}/transitions`,
    body: payload,
    csrfToken,
    ifMatch: etag ?? null,
  });
}

/** Trade DTOs generated from the backend OpenAPI document (single source of truth). */

import type { components } from "@/lib/api/schema";

export type Counterparty = components["schemas"]["CounterpartyResponse"];
export type CounterpartyList = components["schemas"]["CounterpartyListResponse"];
export type CounterpartyCreate = components["schemas"]["CounterpartyCreateRequest"];
export type CounterpartyUpdate = components["schemas"]["CounterpartyUpdateRequest"];

export type Product = components["schemas"]["ProductResponse"];
export type ProductList = components["schemas"]["ProductListResponse"];
export type ProductCreate = components["schemas"]["ProductCreateRequest"];
export type ProductUpdate = components["schemas"]["ProductUpdateRequest"];

export type Deal = components["schemas"]["DealResponse"];
export type DealSummary = components["schemas"]["DealSummaryResponse"];
export type DealList = components["schemas"]["DealListResponse"];
export type DealCreate = components["schemas"]["DealCreateRequest"];
export type DealUpdate = components["schemas"]["DealUpdateRequest"];
export type DealStatus = Deal["status"];
export type DealItem = components["schemas"]["DealItemResponse"];
export type DealTransition = components["schemas"]["DealTransitionResponse"];
export type DealTransitionRequest = components["schemas"]["DealTransitionRequest"];

export type DashboardSummary = components["schemas"]["DashboardSummaryResponse"];

export const DEAL_STATUSES: readonly DealStatus[] = [
  "DRAFT",
  "OPEN",
  "NEGOTIATION",
  "WON",
  "LOST",
  "CANCELLED",
] as const;

export const PRODUCT_UNITS = ["kg", "mt", "lb", "unit", "l", "m3"] as const;
export const COUNTERPARTY_TYPES = ["buyer", "supplier", "both"] as const;

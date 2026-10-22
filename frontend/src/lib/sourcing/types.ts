/** Stage 3 sourcing DTOs generated from the backend OpenAPI document. */

import type { components } from "@/lib/api/schema";

export type FxRate = components["schemas"]["FxRateResponse"];
export type FxRateList = components["schemas"]["FxRateListResponse"];

export type Rfq = components["schemas"]["RfqResponse"];
export type RfqSummary = components["schemas"]["RfqSummaryResponse"];
export type RfqList = components["schemas"]["RfqListResponse"];
export type RfqCreate = components["schemas"]["RfqCreateRequest"];
export type RfqItem = components["schemas"]["RfqItemResponse"];
export type RfqQuoteSummary = components["schemas"]["RfqQuoteSummaryResponse"];
export type RfqTransitionRequest = components["schemas"]["RfqTransitionRequest"];
export type RfqStatus = Rfq["status"];

export type SupplierQuote = components["schemas"]["SupplierQuoteResponse"];
export type SupplierQuoteSummary = components["schemas"]["SupplierQuoteSummaryResponse"];
export type SupplierQuoteList = components["schemas"]["SupplierQuoteListResponse"];
export type SupplierQuoteCreate = components["schemas"]["SupplierQuoteCreateRequest"];
export type SupplierQuoteItem = components["schemas"]["SupplierQuoteItemResponse"];
export type SupplierQuoteStatus = SupplierQuote["status"];

export type PricingScenario = components["schemas"]["PricingScenarioResponse"];
export type PricingScenarioSummary = components["schemas"]["PricingScenarioSummaryResponse"];
export type PricingScenarioList = components["schemas"]["PricingScenarioListResponse"];
export type PricingScenarioRequest = components["schemas"]["PricingScenarioRequest"];
export type PricingComponent = components["schemas"]["PricingCostComponentResponse"];
export type PricingComponentRequest = components["schemas"]["PricingCostComponentRequest"];
export type ScenarioStatus = PricingScenario["status"];

export type SalesQuote = components["schemas"]["SalesQuoteResponse"];
export type SalesQuoteSummary = components["schemas"]["SalesQuoteSummaryResponse"];
export type SalesQuoteList = components["schemas"]["SalesQuoteListResponse"];
export type SalesQuoteCreate = components["schemas"]["SalesQuoteCreateRequest"];
export type SalesQuoteStatus = SalesQuote["status"];

export const RFQ_STATUSES: readonly RfqStatus[] = [
  "DRAFT",
  "PREPARED",
  "SENT",
  "RESPONDED",
  "CLOSED",
  "CANCELLED",
] as const;

export const SUPPLIER_QUOTE_STATUSES: readonly SupplierQuoteStatus[] = [
  "RECEIVED",
  "WITHDRAWN",
] as const;

export const SCENARIO_STATUSES: readonly ScenarioStatus[] = [
  "INCOMPLETE",
  "ESTIMATED",
  "VERIFIED_INPUTS",
] as const;

export const SALES_QUOTE_STATUSES: readonly SalesQuoteStatus[] = [
  "DRAFT",
  "PENDING_APPROVAL",
  "APPROVED",
  "REJECTED",
  "WITHDRAWN",
] as const;

export const INCOTERMS = [
  "EXW",
  "FCA",
  "FAS",
  "FOB",
  "CFR",
  "CIF",
  "CPT",
  "CIP",
  "DAP",
  "DPU",
  "DDP",
] as const;

export const COST_TYPES = [
  "FREIGHT",
  "DOMESTIC_TRANSPORT",
  "INSURANCE",
  "CUSTOMS_DUTY",
  "CUSTOMS_BROKERAGE",
  "QUALITY_INSPECTION",
  "BANKING_FINANCE",
  "OTHER",
  "CONTINGENCY",
  "VAT_CASHFLOW",
] as const;

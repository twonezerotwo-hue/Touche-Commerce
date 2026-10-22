/**
 * Stage 4 operational types.
 *
 * Decimal money and quantities arrive as strings (the API never sends binary
 * floats), every workflow state is a string enum, and `version` is the value
 * behind `If-Match`. Nothing here is derived data: the API is the only source.
 */

export const SALES_ORDER_STATUSES = [
  "CONFIRMED",
  "IN_FULFILLMENT",
  "FULFILLED",
  "CLOSED",
  "CANCELLED",
] as const;

export const PURCHASE_ORDER_STATUSES = [
  "DRAFT",
  "APPROVED",
  "RECORDED_SENT",
  "SUPPLIER_CONFIRMED",
  "IN_FULFILLMENT",
  "RECEIVED",
  "CANCELLED",
] as const;

export const SHIPMENT_STATUSES = [
  "PLANNED",
  "BOOKED",
  "DISPATCHED",
  "IN_TRANSIT",
  "ARRIVED",
  "DELIVERED",
  "CANCELLED",
] as const;

export const TRANSPORT_MODES = ["SEA", "AIR", "ROAD", "RAIL", "MULTIMODAL"] as const;

export const DOCUMENT_TYPES = [
  "COMMERCIAL_INVOICE",
  "PROFORMA_INVOICE",
  "PACKING_LIST",
  "BILL_OF_LADING",
  "AIR_WAYBILL",
  "CMR_CONSIGNMENT_NOTE",
  "CERTIFICATE_OF_ORIGIN",
  "INSURANCE_CERTIFICATE",
  "QUALITY_INSPECTION_CERTIFICATE",
  "CUSTOMS_DECLARATION",
  "PURCHASE_ORDER",
  "SALES_ORDER",
  "DELIVERY_CONFIRMATION",
  "OTHER",
] as const;

export const LINKED_ENTITY_TYPES = [
  "DEAL",
  "SALES_ORDER",
  "PURCHASE_ORDER",
  "SHIPMENT",
  "CUSTOMER_ACCEPTANCE",
] as const;

export const COST_STAGES = ["ESTIMATED", "QUOTED", "INCURRED", "DOCUMENTED"] as const;
export const SHIPMENT_COST_TYPES = [
  "FREIGHT",
  "INSURANCE",
  "HANDLING",
  "CUSTOMS_BROKERAGE",
  "DOMESTIC_TRANSPORT",
  "OTHER",
] as const;
export const SHIPMENT_REFERENCE_TYPES = [
  "BOOKING",
  "CONTAINER",
  "BILL_OF_LADING",
  "AIR_WAYBILL",
  "CMR",
  "TRACKING",
  "OTHER",
] as const;

export type SalesOrderStatus = (typeof SALES_ORDER_STATUSES)[number];
export type PurchaseOrderStatus = (typeof PURCHASE_ORDER_STATUSES)[number];
export type ShipmentStatus = (typeof SHIPMENT_STATUSES)[number];
export type TransportMode = (typeof TRANSPORT_MODES)[number];
export type DocumentType = (typeof DOCUMENT_TYPES)[number];
export type LinkedEntityType = (typeof LINKED_ENTITY_TYPES)[number];

export interface SalesOrderItem {
  id: string;
  product_id: string;
  sku: string;
  name: string;
  description: string;
  quantity: string;
  unit: string;
  unit_price: string;
  line_total: string;
}

export interface SalesOrderTransition {
  from_status: string | null;
  to_status: string;
  reason: string | null;
  actor_id: string;
  occurred_at: string;
  version_after: number;
}

export interface OrderAmendment {
  reason: string;
  changes: Record<string, unknown>;
  actor_id: string;
  created_at: string;
  version_after: number;
}

export interface SalesOrder {
  id: string;
  company_id: string;
  order_number: string;
  deal_id: string;
  deal_reference: string;
  sales_quote_id: string;
  quote_number: string;
  sales_quote_revision: number;
  acceptance_evidence_id: string;
  customer_id: string;
  customer_name: string;
  currency: string;
  incoterm: string;
  named_delivery_place: string;
  payment_terms_snapshot: string;
  fulfilment_model: string;
  order_total: string;
  status: string;
  expected_delivery_date: string | null;
  notes: string | null;
  confirmed_at: string;
  cancelled_at: string | null;
  cancellation_reason: string | null;
  version: number;
  created_by: string;
  created_at: string;
  updated_at: string;
  items: SalesOrderItem[];
  transitions: SalesOrderTransition[];
  amendments: OrderAmendment[];
  accepted_terms: Record<string, unknown>;
  allowed_transitions: string[];
}

export interface SalesOrderSummary {
  id: string;
  company_id: string;
  order_number: string;
  deal_id: string;
  deal_reference: string;
  sales_quote_id: string;
  quote_number: string;
  sales_quote_revision: number;
  customer_id: string;
  customer_name: string;
  currency: string;
  incoterm: string;
  named_delivery_place: string;
  fulfilment_model: string;
  order_total: string;
  status: string;
  confirmed_at: string;
  expected_delivery_date: string | null;
  version: number;
  updated_at: string;
}

export interface SalesOrderList {
  items: SalesOrderSummary[];
  next_cursor: string | null;
  has_more: boolean;
}

export interface CustomerAcceptance {
  id: string;
  company_id: string;
  deal_id: string;
  sales_quote_id: string;
  sales_quote_revision: number;
  channel: string;
  accepted_at: string;
  accepted_by_name: string;
  evidence_reference: string;
  evidence_document_id: string | null;
  notes: string | null;
  recorded_by: string;
  recorded_at: string;
}

export interface SalesQuoteOption {
  id: string;
  quote_number: string;
  revision: number;
  status: string;
  currency: string;
  total_value: string;
  customer_name: string;
  deal_id: string;
  approved_at: string | null;
}

export interface SalesQuoteOptionList {
  items: SalesQuoteOption[];
}

export interface FulfilmentLine {
  sales_order_item_id: string;
  sku: string;
  unit: string;
  ordered: string;
  allocated: string;
  delivered: string;
  remaining: string;
}

export interface FulfilmentSummary {
  sales_order_id: string;
  order_number: string;
  order_status: string;
  lines: FulfilmentLine[];
  completion_ratio: string;
  fully_delivered: boolean;
  delivered_any: boolean;
}

export interface PurchaseOrderItem {
  id: string;
  product_id: string;
  sku: string;
  description: string;
  quantity: string;
  unit: string;
  unit_cost: string;
  line_total: string;
}

export interface PurchaseOrderTransition {
  from_status: string | null;
  to_status: string;
  reason: string | null;
  evidence_reference: string | null;
  actor_id: string;
  occurred_at: string;
  version_after: number;
}

export interface PurchaseOrder {
  id: string;
  company_id: string;
  po_number: string;
  sales_order_id: string;
  order_number: string;
  supplier_id: string;
  supplier_name: string;
  supplier_quote_id: string | null;
  currency: string;
  incoterm: string;
  named_delivery_place: string;
  payment_terms: string;
  total_cost: string;
  status: string;
  expected_dispatch_date: string | null;
  expected_delivery_date: string | null;
  dispatch_channel: string | null;
  dispatched_at: string | null;
  dispatch_reference: string | null;
  supplier_confirmation_reference: string | null;
  supplier_confirmed_at: string | null;
  approved_by: string | null;
  approved_at: string | null;
  notes: string | null;
  cancelled_at: string | null;
  cancellation_reason: string | null;
  version: number;
  created_at: string;
  updated_at: string;
  items: PurchaseOrderItem[];
  transitions: PurchaseOrderTransition[];
  allowed_transitions: string[];
}

export interface PurchaseOrderSummary {
  id: string;
  company_id: string;
  po_number: string;
  sales_order_id: string;
  order_number: string;
  supplier_id: string;
  supplier_name: string;
  currency: string;
  total_cost: string;
  status: string;
  expected_dispatch_date: string | null;
  expected_delivery_date: string | null;
  approved_at: string | null;
  version: number;
  updated_at: string;
}

export interface PurchaseOrderList {
  items: PurchaseOrderSummary[];
  next_cursor: string | null;
  has_more: boolean;
}

export interface ShipmentItem {
  id: string;
  sales_order_item_id: string;
  product_id: string;
  sku: string;
  description: string;
  quantity: string;
  unit: string;
  delivered_quantity: string;
}

export interface ShipmentEvent {
  id: string;
  event_type: string;
  occurred_at: string;
  location: string | null;
  notes: string | null;
  evidence_reference: string | null;
  tracking_source: string | null;
  recorded_by: string;
  recorded_at: string;
}

export interface ShipmentReference {
  id: string;
  reference_type: string;
  reference_value: string;
  provenance: string;
  created_at: string;
}

export interface ShipmentCost {
  id: string;
  cost_type: string;
  stage: string;
  amount: string;
  currency: string;
  reference: string;
  notes: string | null;
  recorded_at: string;
}

export interface Shipment {
  id: string;
  company_id: string;
  shipment_number: string;
  sales_order_id: string;
  order_number: string;
  purchase_order_id: string | null;
  transport_mode: string;
  origin: string;
  destination: string;
  carrier: string | null;
  forwarder: string | null;
  planned_dispatch_at: string | null;
  actual_dispatch_at: string | null;
  estimated_arrival_at: string | null;
  actual_arrival_at: string | null;
  delivered_at: string | null;
  status: string;
  tracking_reference: string | null;
  tracking_source: string | null;
  delivery_evidence_reference: string | null;
  delay_reason: string | null;
  cancellation_reason: string | null;
  notes: string | null;
  version: number;
  created_at: string;
  updated_at: string;
  items: ShipmentItem[];
  events: ShipmentEvent[];
  references: ShipmentReference[];
  costs: ShipmentCost[];
  is_delayed: boolean;
  allowed_transitions: string[];
}

export interface ShipmentSummary {
  id: string;
  company_id: string;
  shipment_number: string;
  sales_order_id: string;
  order_number: string;
  transport_mode: string;
  origin: string;
  destination: string;
  carrier: string | null;
  forwarder: string | null;
  status: string;
  estimated_arrival_at: string | null;
  actual_dispatch_at: string | null;
  delivered_at: string | null;
  tracking_reference: string | null;
  version: number;
  updated_at: string;
  is_delayed: boolean;
}

export interface ShipmentList {
  items: ShipmentSummary[];
  next_cursor: string | null;
  has_more: boolean;
}

export interface TradeDocument {
  id: string;
  company_id: string;
  document_type: string;
  linked_entity_type: string;
  linked_entity_id: string;
  title: string;
  original_filename: string;
  mime_type: string;
  size_bytes: number;
  sha256: string;
  version: number;
  supersedes_document_id: string | null;
  status: string;
  verification_status: string;
  is_draft: boolean;
  uploaded_by: string;
  uploaded_at: string;
  archived_at: string | null;
  download_path: string;
}

export interface DocumentList {
  items: TradeDocument[];
  max_upload_bytes: number;
}

export interface DocumentHistory {
  items: TradeDocument[];
}

export interface PreviewLine {
  sku: string;
  description: string;
  quantity: string;
  unit: string;
  unit_price: string;
  line_total: string;
  shipment_quantity: string | null;
}

export interface DocumentPreview {
  header: {
    kind: string;
    is_draft: boolean;
    legal_notice: string;
    document_label: string;
    document_number: string;
    document_date: string;
    sales_order_id: string;
    order_number: string;
    sales_quote_revision: number;
    seller: Record<string, string>;
    buyer: Record<string, string>;
    currency: string;
    incoterm: string;
    named_delivery_place: string;
    payment_terms: string;
    order_total: string;
    shipment_id: string | null;
    shipment_number: string | null;
    generated_at: string;
  };
  lines: PreviewLine[];
}

export interface CurrencyOrderValue {
  currency: string;
  order_count: number;
  total_value: string;
}

export interface OperationsSummary {
  orders_total: number;
  orders_confirmed: number;
  orders_in_fulfillment: number;
  orders_fulfilled: number;
  orders_closed: number;
  orders_cancelled: number;
  order_value_by_currency: CurrencyOrderValue[];
  purchase_orders_total: number;
  purchase_orders_open: number;
  active_shipments: number;
  delayed_shipments: number;
  delivered_shipments: number;
  documents_total: number;
  delivered_shipments_without_evidence: number;
  generated_at: string;
}

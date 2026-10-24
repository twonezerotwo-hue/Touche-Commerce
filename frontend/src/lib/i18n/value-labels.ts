import type { MessageKey } from "./messages";

type TFn = (key: MessageKey) => string;

const RECORD_STATUS: Record<string, MessageKey> = {
  active: "statusActive",
  archived: "statusArchived",
  inactive: "statusInactive",
};

const COUNTERPARTY_TYPE: Record<string, MessageKey> = {
  buyer: "typeBuyer",
  supplier: "typeSupplier",
  both: "typeBoth",
};

/** Words the API stores in English ("active", "buyer"), shown in the reader's language. */
export function recordStatusLabel(t: TFn, status: string): string {
  const key = RECORD_STATUS[status];
  return key ? t(key) : status;
}

export function counterpartyTypeLabel(t: TFn, type: string): string {
  const key = COUNTERPARTY_TYPE[type];
  return key ? t(key) : type;
}

const DEAL_STATUS: Record<string, MessageKey> = {
  DRAFT: "dealStatusDraft",
  OPEN: "dealStatusOpen",
  NEGOTIATION: "dealStatusNegotiation",
  WON: "dealStatusWon",
  LOST: "dealStatusLost",
  CANCELLED: "dealStatusCancelled",
};

/** Deal status codes ("OPEN") in the reader's language; unknown codes are shown as they are. */
export function dealStatusLabel(t: TFn, status: string): string {
  const key = DEAL_STATUS[status];
  return key ? t(key) : status;
}

const OPERATIONS_STATUS: Record<string, MessageKey> = {
  CONFIRMED: "opStatusConfirmed",
  IN_FULFILLMENT: "opStatusInFulfillment",
  FULFILLED: "opStatusFulfilled",
  CLOSED: "opStatusClosed",
  CANCELLED: "opStatusCancelled",
  DRAFT: "opStatusDraft",
  APPROVED: "opStatusApproved",
  RECORDED_SENT: "opStatusRecordedSent",
  SUPPLIER_CONFIRMED: "opStatusSupplierConfirmed",
  RECEIVED: "opStatusReceived",
  PLANNED: "opStatusPlanned",
  BOOKED: "opStatusBooked",
  DISPATCHED: "opStatusDispatched",
  IN_TRANSIT: "opStatusInTransit",
  ARRIVED: "opStatusArrived",
  DELIVERED: "opStatusDelivered",
  ACTIVE: "opStatusActive",
  ARCHIVED: "opStatusArchived",
  UNVERIFIED: "opStatusUnverified",
  VERIFIED: "opStatusVerified",
  REJECTED: "opStatusRejected",
  MANUAL: "opStatusManual",
  DOCUMENT_EVIDENCE: "opStatusDocumentEvidence",
  VERIFIED_EXTERNAL: "opStatusVerifiedExternal",
};

const DOCUMENT_TYPE: Record<string, MessageKey> = {
  COMMERCIAL_INVOICE: "docTypeCommercialInvoice",
  PROFORMA_INVOICE: "docTypeProformaInvoice",
  PACKING_LIST: "docTypePackingList",
  BILL_OF_LADING: "docTypeBillOfLading",
  AIR_WAYBILL: "docTypeAirWaybill",
  CMR_CONSIGNMENT_NOTE: "docTypeCmr",
  CERTIFICATE_OF_ORIGIN: "docTypeOrigin",
  INSURANCE_CERTIFICATE: "docTypeInsurance",
  QUALITY_INSPECTION_CERTIFICATE: "docTypeQuality",
  CUSTOMS_DECLARATION: "docTypeCustoms",
  PURCHASE_ORDER: "docTypePurchaseOrder",
  SALES_ORDER: "docTypeSalesOrder",
  DELIVERY_CONFIRMATION: "docTypeDelivery",
  OTHER: "docTypeOther",
};

const TRANSPORT_MODE: Record<string, MessageKey> = {
  SEA: "transportSea",
  AIR: "transportAir",
  ROAD: "transportRoad",
  RAIL: "transportRail",
  MULTIMODAL: "transportMultimodal",
};

const FULFILMENT_MODEL: Record<string, MessageKey> = {
  PURCHASE_RESALE: "modelPurchaseResale",
  BROKERAGE: "modelBrokerage",
};

const ACCEPTANCE_CHANNEL: Record<string, MessageKey> = {
  SIGNED_QUOTE: "channelSignedQuote",
  PURCHASE_ORDER: "channelPurchaseOrder",
  EMAIL: "channelEmail",
  PORTAL: "channelPortal",
  OTHER: "channelOther",
};

function lookup(t: TFn, table: Record<string, MessageKey>, code: string): string {
  const key = table[code];
  return key ? t(key) : code.replaceAll("_", " ");
}

/** Order, purchase-order, shipment and document statuses in the reader's language. */
export const operationsStatusText = (t: TFn, code: string): string =>
  lookup(t, OPERATIONS_STATUS, code);
export const documentTypeText = (t: TFn, code: string): string => lookup(t, DOCUMENT_TYPE, code);
export const transportModeText = (t: TFn, code: string): string => lookup(t, TRANSPORT_MODE, code);
export const fulfilmentModelText = (t: TFn, code: string): string =>
  lookup(t, FULFILMENT_MODEL, code);
export const acceptanceChannelText = (t: TFn, code: string): string =>
  lookup(t, ACCEPTANCE_CHANNEL, code);

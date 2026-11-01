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

const SOURCING_STATUS: Record<string, MessageKey> = {
  DRAFT: "srcStDraft",
  PREPARED: "srcStPrepared",
  SENT: "srcStSent",
  RESPONDED: "srcStResponded",
  CLOSED: "srcStClosed",
  CANCELLED: "srcStCancelled",
  RECEIVED: "srcStReceived",
  WITHDRAWN: "srcStWithdrawn",
  INCOMPLETE: "srcStIncomplete",
  ESTIMATED: "srcStEstimated",
  VERIFIED_INPUTS: "srcStVerifiedInputs",
  PENDING_APPROVAL: "srcStPendingApproval",
  APPROVED: "srcStApproved",
  REJECTED: "srcStRejected",
};

/** RFQ, supplier-quote, pricing-scenario and sales-quote status codes as words. */
export function sourcingStatusText(t: TFn, status: string): string {
  const key = SOURCING_STATUS[status];
  return key ? t(key) : status;
}

const COST_TYPE: Record<string, MessageKey> = {
  FREIGHT: "costFreight",
  DOMESTIC_TRANSPORT: "costDomesticTransport",
  INSURANCE: "costInsurance",
  CUSTOMS_DUTY: "costCustomsDuty",
  CUSTOMS_BROKERAGE: "costCustomsBrokerage",
  QUALITY_INSPECTION: "costQualityInspection",
  BANKING_FINANCE: "costBankingFinance",
  OTHER: "costOther",
  CONTINGENCY: "costContingency",
  VAT_CASHFLOW: "costVatCashflow",
};

/** A landed-cost component type ("CUSTOMS_DUTY") in the reader's language. */
export function costTypeText(t: TFn, type: string): string {
  const key = COST_TYPE[type];
  return key ? t(key) : type.replaceAll("_", " ");
}

/** How a cost is spread: the whole order or one product line. */
export function costBasisText(t: TFn, basis: string): string {
  if (basis === "ORDER") return t("prcBasisOrder");
  if (basis === "LINE") return t("prcBasisLine");
  return basis;
}

/** Whether a cost is an estimate or backed by a document. */
export function verificationText(t: TFn, status: string): string {
  if (status === "VERIFIED") return t("prcVerified");
  if (status === "ESTIMATED") return t("prcEstimated");
  return status;
}

const SHIPMENT_EVENT: Record<string, MessageKey> = {
  PLANNED: "evPlanned",
  BOOKED: "evBooked",
  DISPATCHED: "evDispatched",
  IN_TRANSIT: "evInTransit",
  ARRIVED: "evArrived",
  DELIVERED: "evDelivered",
  DELAY_RECORDED: "evDelayRecorded",
  CANCELLED: "evCancelled",
};

const SHIPMENT_COST_TYPE: Record<string, MessageKey> = {
  FREIGHT: "shipCostFreight",
  INSURANCE: "shipCostInsurance",
  HANDLING: "shipCostHandling",
  CUSTOMS_BROKERAGE: "shipCostCustomsBrokerage",
  DOMESTIC_TRANSPORT: "shipCostDomesticTransport",
  OTHER: "shipCostOther",
};

const COST_STAGE: Record<string, MessageKey> = {
  ESTIMATED: "stageEstimated",
  QUOTED: "stageQuoted",
  INCURRED: "stageIncurred",
  DOCUMENTED: "stageDocumented",
};

const REFERENCE_TYPE: Record<string, MessageKey> = {
  BOOKING: "refBooking",
  CONTAINER: "refContainer",
  BILL_OF_LADING: "refBillOfLading",
  AIR_WAYBILL: "refAirWaybill",
  CMR: "refCmr",
  TRACKING: "refTracking",
  OTHER: "refOther",
};

const ENTITY_TYPE: Record<string, MessageKey> = {
  DEAL: "entDeal",
  SALES_ORDER: "entSalesOrder",
  PURCHASE_ORDER: "entPurchaseOrder",
  SHIPMENT: "entShipment",
  CUSTOMER_ACCEPTANCE: "entCustomerAcceptance",
};

/** A shipment milestone ("IN_TRANSIT") in the reader's language. */
export const shipmentEventText = (t: TFn, code: string): string => lookup(t, SHIPMENT_EVENT, code);
export const shipmentCostTypeText = (t: TFn, code: string): string =>
  lookup(t, SHIPMENT_COST_TYPE, code);
/** The certainty of a logistics cost: estimated, quoted, incurred or documented. */
export const costStageText = (t: TFn, code: string): string => lookup(t, COST_STAGE, code);
export const referenceTypeText = (t: TFn, code: string): string => lookup(t, REFERENCE_TYPE, code);
/** The kind of record a document is attached to. */
export const entityTypeText = (t: TFn, code: string): string => lookup(t, ENTITY_TYPE, code);

/** Where a tracking fact came from (manual entry, document evidence, external verification). */
export function provenanceText(t: TFn, value: string | null): string {
  if (!value) return t("provenanceNone");
  return operationsStatusText(t, value);
}

/** A shipment is late only when the API says so; an ETA alone never makes it late or arrived. */
export function delayText(t: TFn, isDelayed: boolean, estimatedArrival: string | null): string {
  if (isDelayed) return t("delayLate");
  if (!estimatedArrival) return t("delayNoEta");
  return t("delayOk");
}

"""Request/response schemas for sales orders, procurement, logistics and documents.

Money and quantities stay ``Decimal`` on the wire (serialised as JSON strings),
workflow state is never part of a create body, and every request forbids unknown
fields so a typo cannot silently change a commercial fact.
"""

from __future__ import annotations

from datetime import date, datetime
from decimal import Decimal
from typing import Any, Literal
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field, model_validator

SalesOrderStatusValue = Literal[
    "CONFIRMED", "IN_FULFILLMENT", "FULFILLED", "CLOSED", "CANCELLED"
]
PurchaseOrderStatusValue = Literal[
    "DRAFT",
    "APPROVED",
    "RECORDED_SENT",
    "SUPPLIER_CONFIRMED",
    "IN_FULFILLMENT",
    "RECEIVED",
    "CANCELLED",
]
ShipmentStatusValue = Literal[
    "PLANNED", "BOOKED", "DISPATCHED", "IN_TRANSIT", "ARRIVED", "DELIVERED", "CANCELLED"
]
TransportModeValue = Literal["SEA", "AIR", "ROAD", "RAIL", "MULTIMODAL"]
AcceptanceChannelValue = Literal["SIGNED_QUOTE", "PURCHASE_ORDER", "EMAIL", "PORTAL", "OTHER"]
FulfilmentModelValue = Literal["PURCHASE_RESALE", "BROKERAGE"]
TrackingSourceValue = Literal["MANUAL", "DOCUMENT_EVIDENCE"]
ShipmentEventTypeValue = Literal["IN_TRANSIT", "DELAY_RECORDED"]
DocumentTypeValue = Literal[
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
]
LinkedEntityTypeValue = Literal[
    "DEAL", "SALES_ORDER", "PURCHASE_ORDER", "SHIPMENT", "CUSTOMER_ACCEPTANCE"
]
DocumentStatusValue = Literal["ACTIVE", "ARCHIVED"]
VerificationStatusValue = Literal["UNVERIFIED", "VERIFIED", "REJECTED"]
CostStageValue = Literal["ESTIMATED", "QUOTED", "INCURRED", "DOCUMENTED"]
ShipmentCostTypeValue = Literal[
    "FREIGHT", "INSURANCE", "HANDLING", "CUSTOMS_BROKERAGE", "DOMESTIC_TRANSPORT", "OTHER"
]
ShipmentReferenceTypeValue = Literal[
    "BOOKING", "CONTAINER", "BILL_OF_LADING", "AIR_WAYBILL", "CMR", "TRACKING", "OTHER"
]
UnitValue = Literal["kg", "mt", "lb", "unit", "l", "m3"]
IncotermValue = Literal[
    "EXW", "FCA", "FAS", "FOB", "CFR", "CIF", "CPT", "CIP", "DAP", "DPU", "DDP"
]


class CustomerAcceptanceRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    channel: AcceptanceChannelValue
    accepted_at: datetime
    accepted_by_name: str = Field(min_length=2, max_length=160)
    evidence_reference: str = Field(min_length=3, max_length=500)
    evidence_document_id: UUID | None = None
    notes: str | None = Field(default=None, max_length=2000)


class CustomerAcceptanceResponse(BaseModel):
    id: UUID
    company_id: UUID
    deal_id: UUID
    sales_quote_id: UUID
    sales_quote_revision: int
    channel: str
    accepted_at: datetime
    accepted_by_name: str
    evidence_reference: str
    evidence_document_id: UUID | None
    notes: str | None
    recorded_by: UUID
    recorded_at: datetime


class CustomerAcceptanceListResponse(BaseModel):
    items: list[CustomerAcceptanceResponse]


class OrderConversionRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    sales_quote_id: UUID
    acceptance_evidence_id: UUID | None = None
    customer_acceptance: CustomerAcceptanceRequest | None = None
    fulfilment_model: FulfilmentModelValue = "PURCHASE_RESALE"
    expected_delivery_date: date | None = None
    expected_total: Decimal | None = Field(default=None, ge=0)
    order_number: str | None = Field(default=None, min_length=3, max_length=40)
    notes: str | None = Field(default=None, max_length=2000)

    @model_validator(mode="after")
    def _one_acceptance_source(self) -> OrderConversionRequest:
        if (self.acceptance_evidence_id is None) == (self.customer_acceptance is None):
            raise ValueError(
                "Provide either acceptance_evidence_id or customer_acceptance, not both."
            )
        return self


class SalesOrderItemResponse(BaseModel):
    id: UUID
    product_id: UUID
    sku: str
    name: str
    description: str
    quantity: Decimal
    unit: str
    unit_price: Decimal
    line_total: Decimal


class SalesOrderTransitionResponse(BaseModel):
    from_status: str | None
    to_status: str
    reason: str | None
    actor_id: UUID
    occurred_at: datetime
    version_after: int


class OrderAmendmentLineResponse(BaseModel):
    item_id: str
    sku: str
    previous_quantity: str
    new_quantity: str


class OrderAmendmentResponse(BaseModel):
    reason: str
    changes: dict[str, Any]
    actor_id: UUID
    created_at: datetime
    version_after: int


class SalesOrderResponse(BaseModel):
    id: UUID
    company_id: UUID
    order_number: str
    deal_id: UUID
    deal_reference: str
    sales_quote_id: UUID
    quote_number: str
    sales_quote_revision: int
    acceptance_evidence_id: UUID
    customer_id: UUID
    customer_name: str
    currency: str
    incoterm: str
    named_delivery_place: str
    payment_terms_snapshot: str
    fulfilment_model: str
    order_total: Decimal
    status: str
    expected_delivery_date: date | None
    notes: str | None
    confirmed_at: datetime
    cancelled_at: datetime | None
    cancellation_reason: str | None
    version: int
    created_by: UUID
    created_at: datetime
    updated_at: datetime
    items: list[SalesOrderItemResponse]
    transitions: list[SalesOrderTransitionResponse]
    amendments: list[OrderAmendmentResponse]
    accepted_terms: dict[str, Any]
    allowed_transitions: list[str]


class SalesOrderSummaryResponse(BaseModel):
    id: UUID
    company_id: UUID
    order_number: str
    deal_id: UUID
    deal_reference: str
    sales_quote_id: UUID
    quote_number: str
    sales_quote_revision: int
    customer_id: UUID
    customer_name: str
    currency: str
    incoterm: str
    named_delivery_place: str
    fulfilment_model: str
    order_total: Decimal
    status: str
    confirmed_at: datetime
    expected_delivery_date: date | None
    version: int
    updated_at: datetime


class SalesOrderListResponse(BaseModel):
    items: list[SalesOrderSummaryResponse]
    next_cursor: str | None
    has_more: bool


class OrderTransitionRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    target: SalesOrderStatusValue
    reason: str | None = Field(default=None, max_length=500)


class AmendmentLineRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    item_id: UUID
    quantity: Decimal = Field(gt=0, max_digits=18, decimal_places=3)


class OrderAmendmentRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    reason: str = Field(min_length=3, max_length=500)
    payment_terms: str | None = Field(default=None, min_length=2, max_length=200)
    named_delivery_place: str | None = Field(default=None, min_length=2, max_length=160)
    expected_delivery_date: date | None = None
    notes: str | None = Field(default=None, max_length=2000)
    lines: list[AmendmentLineRequest] = Field(default_factory=list)

    @model_validator(mode="after")
    def _at_least_one_change(self) -> OrderAmendmentRequest:
        if (
            self.payment_terms is None
            and self.named_delivery_place is None
            and self.expected_delivery_date is None
            and self.notes is None
            and not self.lines
        ):
            raise ValueError("Provide at least one change to amend.")
        return self


class FulfilmentLineResponse(BaseModel):
    sales_order_item_id: UUID
    sku: str
    unit: str
    ordered: Decimal
    allocated: Decimal
    delivered: Decimal
    remaining: Decimal


class FulfilmentSummaryResponse(BaseModel):
    sales_order_id: UUID
    order_number: str
    order_status: str
    lines: list[FulfilmentLineResponse]
    completion_ratio: Decimal
    fully_delivered: bool
    delivered_any: bool


class PurchaseOrderItemResponse(BaseModel):
    id: UUID
    product_id: UUID
    sku: str
    description: str
    quantity: Decimal
    unit: str
    unit_cost: Decimal
    line_total: Decimal


class PurchaseOrderTransitionResponse(BaseModel):
    from_status: str | None
    to_status: str
    reason: str | None
    evidence_reference: str | None
    actor_id: UUID
    occurred_at: datetime
    version_after: int


class PurchaseOrderResponse(BaseModel):
    id: UUID
    company_id: UUID
    po_number: str
    sales_order_id: UUID
    order_number: str
    supplier_id: UUID
    supplier_name: str
    supplier_quote_id: UUID | None
    currency: str
    incoterm: str
    named_delivery_place: str
    payment_terms: str
    total_cost: Decimal
    status: str
    expected_dispatch_date: date | None
    expected_delivery_date: date | None
    dispatch_channel: str | None
    dispatched_at: datetime | None
    dispatch_reference: str | None
    supplier_confirmation_reference: str | None
    supplier_confirmed_at: datetime | None
    approved_by: UUID | None
    approved_at: datetime | None
    notes: str | None
    cancelled_at: datetime | None
    cancellation_reason: str | None
    version: int
    created_at: datetime
    updated_at: datetime
    items: list[PurchaseOrderItemResponse]
    transitions: list[PurchaseOrderTransitionResponse]
    allowed_transitions: list[str]


class PurchaseOrderSummaryResponse(BaseModel):
    id: UUID
    company_id: UUID
    po_number: str
    sales_order_id: UUID
    order_number: str
    supplier_id: UUID
    supplier_name: str
    currency: str
    total_cost: Decimal
    status: str
    expected_dispatch_date: date | None
    expected_delivery_date: date | None
    approved_at: datetime | None
    version: int
    updated_at: datetime


class PurchaseOrderListResponse(BaseModel):
    items: list[PurchaseOrderSummaryResponse]
    next_cursor: str | None
    has_more: bool


class PurchaseOrderItemRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    product_id: UUID
    description: str | None = Field(default=None, max_length=1000)
    quantity: Decimal = Field(gt=0, max_digits=18, decimal_places=3)
    unit: UnitValue | None = None
    unit_cost: Decimal = Field(ge=0, max_digits=18, decimal_places=4)


class PurchaseOrderCreateRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    sales_order_id: UUID
    supplier_id: UUID
    supplier_quote_id: UUID | None = None
    incoterm: IncotermValue
    named_delivery_place: str = Field(min_length=2, max_length=160)
    payment_terms: str = Field(min_length=2, max_length=200)
    expected_dispatch_date: date | None = None
    expected_delivery_date: date | None = None
    notes: str | None = Field(default=None, max_length=2000)
    items: list[PurchaseOrderItemRequest] = Field(min_length=1)

    @model_validator(mode="after")
    def _unique_products(self) -> PurchaseOrderCreateRequest:
        product_ids = [item.product_id for item in self.items]
        if len(set(product_ids)) != len(product_ids):
            raise ValueError("Each product may appear only once.")
        return self


class PurchaseOrderTransitionRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    target: PurchaseOrderStatusValue
    reason: str | None = Field(default=None, max_length=500)
    dispatched_at: datetime | None = None
    dispatch_channel: str | None = Field(default=None, max_length=32)
    dispatch_reference: str | None = Field(default=None, max_length=200)
    supplier_confirmation_reference: str | None = Field(default=None, max_length=200)
    evidence_reference: str | None = Field(default=None, max_length=500)


class ShipmentItemResponse(BaseModel):
    id: UUID
    sales_order_item_id: UUID
    product_id: UUID
    sku: str
    description: str
    quantity: Decimal
    unit: str
    delivered_quantity: Decimal


class ShipmentEventResponse(BaseModel):
    id: UUID
    event_type: str
    occurred_at: datetime
    location: str | None
    notes: str | None
    evidence_reference: str | None
    tracking_source: str | None
    recorded_by: UUID
    recorded_at: datetime


class ShipmentReferenceResponse(BaseModel):
    id: UUID
    reference_type: str
    reference_value: str
    provenance: str
    created_at: datetime


class ShipmentCostResponse(BaseModel):
    id: UUID
    cost_type: str
    stage: str
    amount: Decimal
    currency: str
    reference: str
    notes: str | None
    recorded_at: datetime


class ShipmentResponse(BaseModel):
    id: UUID
    company_id: UUID
    shipment_number: str
    sales_order_id: UUID
    order_number: str
    purchase_order_id: UUID | None
    transport_mode: str
    origin: str
    destination: str
    carrier: str | None
    forwarder: str | None
    planned_dispatch_at: datetime | None
    actual_dispatch_at: datetime | None
    estimated_arrival_at: datetime | None
    actual_arrival_at: datetime | None
    delivered_at: datetime | None
    status: str
    tracking_reference: str | None
    tracking_source: str | None
    delivery_evidence_reference: str | None
    delay_reason: str | None
    cancellation_reason: str | None
    notes: str | None
    version: int
    created_at: datetime
    updated_at: datetime
    items: list[ShipmentItemResponse]
    events: list[ShipmentEventResponse]
    references: list[ShipmentReferenceResponse]
    costs: list[ShipmentCostResponse]
    is_delayed: bool
    allowed_transitions: list[str]


class ShipmentSummaryResponse(BaseModel):
    id: UUID
    company_id: UUID
    shipment_number: str
    sales_order_id: UUID
    order_number: str
    transport_mode: str
    origin: str
    destination: str
    carrier: str | None
    forwarder: str | None
    status: str
    estimated_arrival_at: datetime | None
    actual_dispatch_at: datetime | None
    delivered_at: datetime | None
    tracking_reference: str | None
    version: int
    updated_at: datetime
    is_delayed: bool


class ShipmentListResponse(BaseModel):
    items: list[ShipmentSummaryResponse]
    next_cursor: str | None
    has_more: bool


class ShipmentLineRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    sales_order_item_id: UUID
    quantity: Decimal = Field(gt=0, max_digits=18, decimal_places=3)


class ShipmentCreateRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    sales_order_id: UUID
    purchase_order_id: UUID | None = None
    transport_mode: TransportModeValue
    origin: str = Field(min_length=2, max_length=160)
    destination: str = Field(min_length=2, max_length=160)
    carrier: str | None = Field(default=None, max_length=160)
    forwarder: str | None = Field(default=None, max_length=160)
    planned_dispatch_at: datetime | None = None
    estimated_arrival_at: datetime | None = None
    tracking_reference: str | None = Field(default=None, max_length=200)
    tracking_source: TrackingSourceValue | None = None
    notes: str | None = Field(default=None, max_length=2000)
    items: list[ShipmentLineRequest] = Field(min_length=1)

    @model_validator(mode="after")
    def _unique_lines(self) -> ShipmentCreateRequest:
        ids = [line.sales_order_item_id for line in self.items]
        if len(set(ids)) != len(ids):
            raise ValueError("Each order line may appear only once.")
        return self


class ShipmentTransitionRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    target: ShipmentStatusValue
    occurred_at: datetime | None = None
    location: str | None = Field(default=None, max_length=160)
    notes: str | None = Field(default=None, max_length=2000)
    reason: str | None = Field(default=None, max_length=500)
    tracking_reference: str | None = Field(default=None, max_length=200)
    tracking_source: TrackingSourceValue | None = None
    evidence_reference: str | None = Field(default=None, max_length=500)
    delivery_evidence_reference: str | None = Field(default=None, max_length=500)


class ShipmentEventRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    event_type: ShipmentEventTypeValue
    occurred_at: datetime
    location: str | None = Field(default=None, max_length=160)
    notes: str | None = Field(default=None, max_length=2000)
    evidence_reference: str | None = Field(default=None, max_length=500)
    tracking_source: TrackingSourceValue | None = None


class ShipmentCostRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    cost_type: ShipmentCostTypeValue
    stage: CostStageValue
    amount: Decimal = Field(ge=0, max_digits=18, decimal_places=2)
    currency: str = Field(min_length=3, max_length=3, pattern=r"^[A-Za-z]{3}$")
    reference: str = Field(min_length=2, max_length=200)
    notes: str | None = Field(default=None, max_length=2000)


class ShipmentReferenceRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    reference_type: ShipmentReferenceTypeValue
    reference_value: str = Field(min_length=2, max_length=120)
    provenance: TrackingSourceValue


class DocumentResponse(BaseModel):
    id: UUID
    company_id: UUID
    document_type: str
    linked_entity_type: str
    linked_entity_id: UUID
    title: str
    original_filename: str
    mime_type: str
    size_bytes: int
    sha256: str
    version: int
    supersedes_document_id: UUID | None
    status: str
    verification_status: str
    is_draft: bool
    uploaded_by: UUID
    uploaded_at: datetime
    archived_at: datetime | None
    download_path: str


class DocumentListResponse(BaseModel):
    items: list[DocumentResponse]
    max_upload_bytes: int


class DocumentHistoryResponse(BaseModel):
    items: list[DocumentResponse]


class DocumentArchiveRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    reason: str | None = Field(default=None, max_length=500)


class DocumentVerifyRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    verification_status: Literal["VERIFIED", "REJECTED"]
    note: str | None = Field(default=None, max_length=500)


class PreviewHeaderResponse(BaseModel):
    kind: str
    is_draft: bool
    legal_notice: str
    document_label: str
    document_number: str
    document_date: str
    sales_order_id: str
    order_number: str
    sales_quote_revision: int
    seller: dict[str, str]
    buyer: dict[str, str]
    currency: str
    incoterm: str
    named_delivery_place: str
    payment_terms: str
    order_total: str
    shipment_id: str | None
    shipment_number: str | None
    generated_at: str


class PreviewLineResponse(BaseModel):
    sku: str
    description: str
    quantity: str
    unit: str
    unit_price: str
    line_total: str
    shipment_quantity: str | None


class DocumentPreviewResponse(BaseModel):
    header: PreviewHeaderResponse
    lines: list[PreviewLineResponse]


class CurrencyOrderValueResponse(BaseModel):
    currency: str
    order_count: int
    total_value: Decimal


class OperationsSummaryResponse(BaseModel):
    orders_total: int
    orders_confirmed: int
    orders_in_fulfillment: int
    orders_fulfilled: int
    orders_closed: int
    orders_cancelled: int
    order_value_by_currency: list[CurrencyOrderValueResponse]
    purchase_orders_total: int
    purchase_orders_open: int
    active_shipments: int
    delayed_shipments: int
    delivered_shipments: int
    documents_total: int
    delivered_shipments_without_evidence: int
    generated_at: datetime

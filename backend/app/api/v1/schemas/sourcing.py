"""Request/response schemas for FX snapshots, RFQs, quotes, pricing and sales.

Money and quantities remain ``Decimal`` end to end (rendered as JSON strings), and
every request model forbids unknown fields. Workflow state is never part of a
create or update body: it changes only through the explicit transition endpoints,
which keeps a ``PATCH`` from silently approving a quote.
"""

from __future__ import annotations

from datetime import date, datetime
from decimal import Decimal
from typing import Any, Literal
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field, model_validator

ProductUnitValue = Literal["kg", "mt", "lb", "unit", "l", "m3"]
IncotermValue = Literal[
    "EXW", "FCA", "FAS", "FOB", "CFR", "CIF", "CPT", "CIP", "DAP", "DPU", "DDP"
]
CostTypeValue = Literal[
    "PURCHASE",
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
]
CostBasisValue = Literal["ORDER", "LINE"]
VerificationStatusValue = Literal["ESTIMATED", "VERIFIED"]
RfqStatusValue = Literal["DRAFT", "PREPARED", "SENT", "RESPONDED", "CLOSED", "CANCELLED"]
SupplierQuoteStatusValue = Literal["RECEIVED", "WITHDRAWN"]
ScenarioStatusValue = Literal["INCOMPLETE", "ESTIMATED", "VERIFIED_INPUTS"]
SalesQuoteStatusValue = Literal["DRAFT", "PENDING_APPROVAL", "APPROVED", "REJECTED", "WITHDRAWN"]

_CURRENCY = r"^[A-Za-z]{3}$"
_PERCENT = Decimal("100")


class FxRateResponse(BaseModel):
    id: UUID
    company_id: UUID
    base_currency: str
    quote_currency: str
    rate: Decimal
    effective_at: datetime
    source: str
    recorded_by: UUID
    recorded_at: datetime


class FxRateListResponse(BaseModel):
    items: list[FxRateResponse]
    next_cursor: str | None
    has_more: bool


class FxRateCreateRequest(BaseModel):
    model_config = ConfigDict(
        extra="forbid",
        json_schema_extra={
            "example": {
                "base_currency": "EUR",
                "quote_currency": "USD",
                "rate": "1.0875000000",
                "effective_at": "2026-10-22T00:00:00Z",
                "source": "ECB reference rate 2026-10-22",
            }
        },
    )

    base_currency: str = Field(pattern=_CURRENCY, description="ISO 4217 base currency.")
    quote_currency: str = Field(pattern=_CURRENCY, description="ISO 4217 quote currency.")
    rate: Decimal = Field(gt=0, max_digits=20, decimal_places=10)
    effective_at: datetime
    source: str = Field(min_length=3, max_length=160)

    @model_validator(mode="after")
    def _distinct_currencies(self) -> FxRateCreateRequest:
        if self.base_currency.upper() == self.quote_currency.upper():
            raise ValueError("The base and quote currency must differ.")
        return self


class RfqItemRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    product_id: UUID
    description: str = Field(min_length=1, max_length=500)
    quantity: Decimal = Field(gt=0, max_digits=18, decimal_places=3)
    unit: ProductUnitValue
    notes: str | None = Field(default=None, max_length=500)


class RfqCreateRequest(BaseModel):
    model_config = ConfigDict(
        extra="forbid",
        json_schema_extra={
            "example": {
                "deal_id": "7f7b0a54-0f43-4d7d-9a1b-3f5f3f0f0a11",
                "supplier_ids": ["0f6a1f43-2b61-4a4d-9ad6-5a1f1a1f1a11"],
                "requested_currency": "USD",
                "delivery_location": "Rotterdam, NL",
                "response_due_date": "2026-11-05",
                "items": [
                    {
                        "product_id": "0f6a1f43-2b61-4a4d-9ad6-5a1f1a1f1a12",
                        "description": "Almond kernels, 25 kg bags",
                        "quantity": "1000.000",
                        "unit": "kg",
                    }
                ],
            }
        },
    )

    deal_id: UUID
    supplier_ids: list[UUID] = Field(
        min_length=1,
        max_length=10,
        description="One RFQ is created per supplier in a single transaction.",
    )
    requested_currency: str = Field(pattern=_CURRENCY)
    requested_delivery_terms: str | None = Field(default=None, min_length=3, max_length=40)
    delivery_location: str = Field(min_length=2, max_length=160)
    response_due_date: date | None = None
    notes: str | None = Field(default=None, max_length=2000)
    items: list[RfqItemRequest] = Field(min_length=1, max_length=50)

    @model_validator(mode="after")
    def _unique_children(self) -> RfqCreateRequest:
        if len(set(self.supplier_ids)) != len(self.supplier_ids):
            raise ValueError("Each supplier may be selected only once.")
        product_ids = [item.product_id for item in self.items]
        if len(set(product_ids)) != len(product_ids):
            raise ValueError("Each product may appear only once per RFQ.")
        return self


class RfqUpdateRequest(BaseModel):
    """Header/lines update. ``status`` is intentionally absent."""

    model_config = ConfigDict(extra="forbid")

    requested_currency: str | None = Field(default=None, pattern=_CURRENCY)
    requested_delivery_terms: str | None = Field(default=None, min_length=3, max_length=40)
    delivery_location: str | None = Field(default=None, min_length=2, max_length=160)
    response_due_date: date | None = None
    notes: str | None = Field(default=None, max_length=2000)
    items: list[RfqItemRequest] | None = Field(default=None, min_length=1, max_length=50)

    @model_validator(mode="after")
    def _at_least_one_field(self) -> RfqUpdateRequest:
        if not self.model_fields_set:
            raise ValueError("Provide at least one field to update.")
        if self.items is not None:
            product_ids = [item.product_id for item in self.items]
            if len(set(product_ids)) != len(product_ids):
                raise ValueError("Each product may appear only once per RFQ.")
        return self


class RfqTransitionRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    to: RfqStatusValue
    channel: str | None = Field(
        default=None, max_length=40, description="Required to send: for example 'email'."
    )
    evidence: str | None = Field(
        default=None,
        max_length=500,
        description="Required to send: message id, thread or file proving dispatch.",
    )
    reason: str | None = Field(
        default=None, max_length=500, description="Required (3-500 characters) to cancel."
    )



class RfqItemResponse(BaseModel):
    id: UUID
    product_id: UUID
    sku: str
    name: str
    unit: ProductUnitValue
    description: str
    quantity: Decimal
    notes: str | None


class RfqQuoteSummaryResponse(BaseModel):
    id: UUID
    revision: int
    status: SupplierQuoteStatusValue
    currency: str
    total_value: Decimal
    valid_until: date
    received_at: datetime


class RfqRevisionResponse(BaseModel):
    revision: int
    reason: str | None
    actor_id: UUID
    created_at: datetime


class RfqRevisionDetailResponse(RfqRevisionResponse):
    snapshot: dict[str, Any]


class RfqSummaryResponse(BaseModel):
    id: UUID
    company_id: UUID
    deal_id: UUID
    deal_reference: str
    supplier_counterparty_id: UUID
    supplier_name: str
    reference_number: str
    requested_currency: str
    response_due_date: date | None
    status: RfqStatusValue
    revision: int
    version: int
    item_count: int
    quote_count: int
    created_at: datetime
    updated_at: datetime


class RfqResponse(BaseModel):
    id: UUID
    company_id: UUID
    deal_id: UUID
    deal_reference: str
    supplier_counterparty_id: UUID
    supplier_name: str
    reference_number: str
    requested_currency: str
    requested_delivery_terms: str | None
    delivery_location: str
    response_due_date: date | None
    notes: str | None
    status: RfqStatusValue
    revision: int
    version: int = Field(description="Optimistic concurrency version; also sent as ETag.")
    sent_channel: str | None
    sent_at: datetime | None
    sent_evidence: str | None
    created_by: UUID
    created_at: datetime
    updated_at: datetime
    items: list[RfqItemResponse]
    quotes: list[RfqQuoteSummaryResponse]
    revisions: list[RfqRevisionResponse]
    allowed_transitions: list[RfqStatusValue]
    is_editable: bool


class RfqListResponse(BaseModel):
    items: list[RfqSummaryResponse]
    next_cursor: str | None
    has_more: bool


class RfqBatchResponse(BaseModel):
    """One row per supplier that was asked, created in one transaction."""

    items: list[RfqResponse]


class SupplierQuoteItemRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    product_id: UUID
    quantity: Decimal = Field(gt=0, max_digits=18, decimal_places=3)
    unit_price: Decimal = Field(ge=0, max_digits=18, decimal_places=4)
    moq: Decimal | None = Field(default=None, gt=0, max_digits=18, decimal_places=3)
    notes: str | None = Field(default=None, max_length=500)


class SupplierQuoteCreateRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    supplier_reference: str | None = Field(default=None, max_length=80)
    currency: str = Field(pattern=_CURRENCY, description="Currency the supplier quoted in.")
    incoterm: IncotermValue
    named_delivery_place: str = Field(min_length=2, max_length=160)
    payment_terms: str = Field(min_length=2, max_length=200)
    shipping_conditions: str | None = Field(default=None, max_length=500)
    lead_time_days: int = Field(ge=0, le=3650)
    valid_until: date
    source_reference: str = Field(
        min_length=3,
        max_length=200,
        description="Email, file or portal message the quote was taken from.",
    )
    notes: str | None = Field(default=None, max_length=2000)
    received_at: datetime | None = Field(
        default=None, description="When the supplier's reply arrived; defaults to now."
    )
    items: list[SupplierQuoteItemRequest] = Field(min_length=1, max_length=50)

    @model_validator(mode="after")
    def _unique_products(self) -> SupplierQuoteCreateRequest:
        product_ids = [item.product_id for item in self.items]
        if len(set(product_ids)) != len(product_ids):
            raise ValueError("Each product may appear only once per quote.")
        return self


class SupplierQuoteReviseRequest(SupplierQuoteCreateRequest):
    reason: str | None = Field(
        default=None, max_length=500, description="Why a new revision was recorded."
    )


class SupplierQuoteWithdrawRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    reason: str = Field(min_length=3, max_length=500)



class SupplierQuoteItemResponse(BaseModel):
    id: UUID
    product_id: UUID
    sku: str
    name: str
    unit: ProductUnitValue
    description: str
    quantity: Decimal
    unit_price: Decimal
    moq: Decimal | None
    notes: str | None
    line_total: Decimal


class SupplierQuoteRevisionResponse(BaseModel):
    revision: int
    reason: str | None
    actor_id: UUID
    created_at: datetime


class SupplierQuoteRevisionDetailResponse(SupplierQuoteRevisionResponse):
    snapshot: dict[str, Any]


class SupplierQuoteSummaryResponse(BaseModel):
    id: UUID
    company_id: UUID
    rfq_id: UUID
    rfq_reference: str
    deal_id: UUID
    deal_reference: str
    supplier_counterparty_id: UUID
    supplier_name: str
    supplier_reference: str | None
    currency: str
    incoterm: IncotermValue
    valid_until: date
    status: SupplierQuoteStatusValue
    revision: int
    received_at: datetime
    superseded_by_quote_id: UUID | None
    version: int
    item_count: int
    total_value: Decimal
    created_at: datetime
    updated_at: datetime


class SupplierQuoteResponse(BaseModel):
    id: UUID
    company_id: UUID
    rfq_id: UUID
    rfq_reference: str
    deal_id: UUID
    deal_reference: str
    supplier_counterparty_id: UUID
    supplier_name: str
    supplier_reference: str | None
    currency: str
    incoterm: IncotermValue
    named_delivery_place: str
    payment_terms: str
    shipping_conditions: str | None
    lead_time_days: int
    valid_until: date
    status: SupplierQuoteStatusValue
    revision: int
    source_reference: str
    notes: str | None
    received_at: datetime
    supersedes_quote_id: UUID | None
    superseded_by_quote_id: UUID | None
    version: int = Field(description="Optimistic concurrency version; also sent as ETag.")
    created_by: UUID
    created_at: datetime
    updated_at: datetime
    items: list[SupplierQuoteItemResponse]
    revisions: list[SupplierQuoteRevisionResponse]
    total_value: Decimal
    is_active: bool


class SupplierQuoteListResponse(BaseModel):
    items: list[SupplierQuoteSummaryResponse]
    next_cursor: str | None
    has_more: bool


class PricingCostComponentRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    cost_type: CostTypeValue
    amount: Decimal = Field(ge=0, max_digits=18, decimal_places=2)
    currency: str = Field(pattern=_CURRENCY)
    basis: CostBasisValue = "ORDER"
    source_reference: str = Field(min_length=3, max_length=200)
    verification_status: VerificationStatusValue
    fx_rate_snapshot_id: UUID | None = Field(
        default=None, description="Required when the currency differs from the target."
    )
    product_id: UUID | None = Field(
        default=None, description="Required for LINE basis, forbidden for ORDER."
    )
    notes: str | None = Field(default=None, max_length=500)

    @model_validator(mode="after")
    def _line_product(self) -> PricingCostComponentRequest:
        if (self.basis == "LINE") != (self.product_id is not None):
            raise ValueError("A LINE cost must name its product; an ORDER cost must not.")
        return self



class PricingScenarioRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    supplier_quote_id: UUID
    target_currency: str = Field(pattern=_CURRENCY)
    sales_incoterm: IncotermValue | None = None
    sales_named_place: str | None = Field(default=None, min_length=2, max_length=160)
    margin_pct: Decimal = Field(default=Decimal("0"), ge=0, lt=_PERCENT)
    markup_pct: Decimal = Field(default=Decimal("0"), ge=0, lt=_PERCENT)
    fx_rate_snapshot_id: UUID | None = Field(
        default=None, description="Required when the quote currency differs from the target."
    )
    components: list[PricingCostComponentRequest] = Field(default_factory=list, max_length=50)

    @model_validator(mode="after")
    def _single_pricing_method(self) -> PricingScenarioRequest:
        if self.margin_pct > 0 and self.markup_pct > 0:
            raise ValueError("Use either margin_pct or markup_pct, never both.")
        return self


class PricingCostComponentResponse(BaseModel):
    id: UUID
    cost_type: CostTypeValue
    amount: Decimal
    currency: str
    basis: CostBasisValue
    source_reference: str
    verification_status: VerificationStatusValue
    fx_rate_snapshot_id: UUID | None
    product_id: UUID | None
    product_sku: str | None
    product_name: str | None
    notes: str | None


class PricingScenarioSummaryResponse(BaseModel):
    id: UUID
    company_id: UUID
    deal_id: UUID
    deal_reference: str
    supplier_quote_id: UUID
    rfq_reference: str
    supplier_name: str
    target_currency: str
    status: ScenarioStatusValue
    landed_total: Decimal
    sales_total: Decimal
    gross_margin: Decimal
    gross_margin_pct: Decimal
    version: int
    created_at: datetime
    updated_at: datetime


class PricingScenarioResponse(BaseModel):
    id: UUID
    company_id: UUID
    deal_id: UUID
    deal_reference: str
    supplier_quote_id: UUID
    rfq_id: UUID
    rfq_reference: str
    supplier_counterparty_id: UUID
    supplier_name: str
    quote_currency: str
    quote_revision: int
    target_currency: str
    sales_incoterm: IncotermValue | None
    sales_named_place: str | None
    status: ScenarioStatusValue
    calculation_version: str
    pricing_inputs: dict[str, Any]
    calculated_results: dict[str, Any]
    completeness: dict[str, Any]
    version: int = Field(description="Optimistic concurrency version; also sent as ETag.")
    created_by: UUID
    created_at: datetime
    updated_at: datetime
    components: list[PricingCostComponentResponse]


class PricingScenarioListResponse(BaseModel):
    items: list[PricingScenarioSummaryResponse]
    next_cursor: str | None
    has_more: bool


class SalesQuoteCreateRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    scenario_id: UUID
    customer_id: UUID
    valid_until: date
    incoterm: IncotermValue
    named_delivery_place: str = Field(min_length=2, max_length=160)
    payment_terms: str = Field(min_length=2, max_length=200)
    notes: str | None = Field(default=None, max_length=2000)


class SalesQuoteApproveRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    note: str | None = Field(default=None, max_length=500)


class SalesQuoteRejectRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    reason: str = Field(min_length=3, max_length=500)


class SalesQuoteWithdrawRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    reason: str | None = Field(default=None, max_length=500)


class SalesQuoteReviseRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    valid_until: date
    notes: str | None = Field(default=None, max_length=2000)
    reason: str | None = Field(default=None, max_length=500)



class SalesQuoteItemResponse(BaseModel):
    id: UUID
    product_id: UUID
    sku: str
    name: str
    unit: ProductUnitValue
    description: str
    quantity: Decimal
    unit_price: Decimal
    line_total: Decimal


class SalesQuoteRevisionResponse(BaseModel):
    revision: int
    reason: str | None
    actor_id: UUID
    created_at: datetime


class SalesQuoteRevisionDetailResponse(SalesQuoteRevisionResponse):
    snapshot: dict[str, Any]


class SalesQuoteSummaryResponse(BaseModel):
    id: UUID
    company_id: UUID
    deal_id: UUID
    deal_reference: str
    quote_number: str
    revision: int
    scenario_id: UUID
    scenario_status: ScenarioStatusValue
    customer_id: UUID
    customer_name: str
    currency: str
    valid_until: date
    status: SalesQuoteStatusValue
    total_value: Decimal
    version: int
    approved_at: datetime | None = Field(
        default=None,
        description="When the internal approval was recorded; acceptance must follow it.",
    )
    created_at: datetime
    updated_at: datetime


class SalesQuoteResponse(BaseModel):
    id: UUID
    company_id: UUID
    deal_id: UUID
    deal_reference: str
    quote_number: str
    revision: int
    scenario_id: UUID
    scenario_status: ScenarioStatusValue
    customer_id: UUID
    customer_name: str
    currency: str
    valid_until: date
    incoterm: IncotermValue
    named_delivery_place: str
    payment_terms: str
    status: SalesQuoteStatusValue
    notes: str | None
    approved_by: UUID | None
    approved_at: datetime | None
    rejection_reason: str | None
    submitted_by: UUID | None
    submitted_at: datetime | None
    supersedes_sales_quote_id: UUID | None
    superseded_by_sales_quote_id: UUID | None
    version: int = Field(description="Optimistic concurrency version; also sent as ETag.")
    created_by: UUID
    created_at: datetime
    updated_at: datetime
    items: list[SalesQuoteItemResponse]
    revisions: list[SalesQuoteRevisionResponse]
    total_value: Decimal
    allowed_transitions: list[SalesQuoteStatusValue]
    can_submit: bool


class SalesQuoteListResponse(BaseModel):
    items: list[SalesQuoteSummaryResponse]
    next_cursor: str | None
    has_more: bool


__all__ = [
    "CostBasisValue",
    "CostTypeValue",
    "FxRateCreateRequest",
    "FxRateListResponse",
    "FxRateResponse",
    "IncotermValue",
    "PricingCostComponentRequest",
    "PricingCostComponentResponse",
    "PricingScenarioListResponse",
    "PricingScenarioRequest",
    "PricingScenarioResponse",
    "PricingScenarioSummaryResponse",
    "ProductUnitValue",
    "RfqBatchResponse",
    "RfqCreateRequest",
    "RfqItemRequest",
    "RfqItemResponse",
    "RfqListResponse",
    "RfqQuoteSummaryResponse",
    "RfqResponse",
    "RfqRevisionDetailResponse",
    "RfqRevisionResponse",
    "RfqStatusValue",
    "RfqSummaryResponse",
    "RfqTransitionRequest",
    "RfqUpdateRequest",
    "SalesQuoteApproveRequest",
    "SalesQuoteCreateRequest",
    "SalesQuoteItemResponse",
    "SalesQuoteListResponse",
    "SalesQuoteRejectRequest",
    "SalesQuoteResponse",
    "SalesQuoteReviseRequest",
    "SalesQuoteRevisionDetailResponse",
    "SalesQuoteRevisionResponse",
    "SalesQuoteStatusValue",
    "SalesQuoteSummaryResponse",
    "SalesQuoteWithdrawRequest",
    "ScenarioStatusValue",
    "SupplierQuoteCreateRequest",
    "SupplierQuoteItemRequest",
    "SupplierQuoteItemResponse",
    "SupplierQuoteListResponse",
    "SupplierQuoteResponse",
    "SupplierQuoteReviseRequest",
    "SupplierQuoteRevisionDetailResponse",
    "SupplierQuoteRevisionResponse",
    "SupplierQuoteStatusValue",
    "SupplierQuoteSummaryResponse",
    "SupplierQuoteWithdrawRequest",
    "VerificationStatusValue",
]


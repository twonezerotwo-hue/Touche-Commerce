"""Request/response schemas for counterparties, products, deals and the dashboard.

These classes are the OpenAPI source of truth for the Stage 1B trade module.
Two deliberate choices are encoded here:

* update models forbid unknown fields, so ``{"status": "WON"}`` on a ``PATCH``
  is a ``422 VALIDATION_ERROR`` instead of a silent status change — the only way
  to move a deal is ``POST /deals/{id}/transitions`` (ADR-025);
* money and quantities stay ``Decimal`` end to end; JSON renders them as strings
  so no binary floating point ever touches a price.
"""

from __future__ import annotations

from datetime import date, datetime
from decimal import Decimal
from typing import Literal
from uuid import UUID

from pydantic import BaseModel, ConfigDict, EmailStr, Field, model_validator

CounterpartyTypeValue = Literal["buyer", "supplier", "both"]
RecordStatusValue = Literal["active", "archived"]
ProductUnitValue = Literal["kg", "mt", "lb", "unit", "l", "m3"]
DealStatusValue = Literal["DRAFT", "OPEN", "NEGOTIATION", "WON", "LOST", "CANCELLED"]

_COUNTRY = r"^[A-Za-z]{2}$"
_CURRENCY = r"^[A-Za-z]{3}$"
_REFERENCE = r"^[A-Za-z0-9][A-Za-z0-9-]{2,31}$"


class CounterpartyResponse(BaseModel):
    id: UUID
    company_id: UUID
    name: str
    type: CounterpartyTypeValue
    country: str | None
    contact_name: str | None
    email: str | None
    phone: str | None
    notes: str | None
    status: RecordStatusValue
    version: int = Field(description="Optimistic concurrency version; also sent as ETag.")
    created_at: datetime
    updated_at: datetime


class CounterpartyListResponse(BaseModel):
    items: list[CounterpartyResponse]
    next_cursor: str | None = Field(description="Opaque cursor for the next page.")
    has_more: bool


class CounterpartyCreateRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    name: str = Field(min_length=1, max_length=160)
    type: CounterpartyTypeValue = "buyer"
    country: str | None = Field(default=None, pattern=_COUNTRY)
    contact_name: str | None = Field(default=None, max_length=120)
    email: EmailStr | None = None
    phone: str | None = Field(default=None, max_length=40)
    notes: str | None = Field(default=None, max_length=2000)


class CounterpartyUpdateRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    name: str | None = Field(default=None, min_length=1, max_length=160)
    type: CounterpartyTypeValue | None = None
    country: str | None = Field(default=None, pattern=_COUNTRY)
    contact_name: str | None = Field(default=None, max_length=120)
    email: EmailStr | None = None
    phone: str | None = Field(default=None, max_length=40)
    notes: str | None = Field(default=None, max_length=2000)
    status: RecordStatusValue | None = None

    @model_validator(mode="after")
    def _at_least_one_field(self) -> CounterpartyUpdateRequest:
        if not self.model_fields_set:
            raise ValueError("Provide at least one field to update.")
        return self


class ProductResponse(BaseModel):
    id: UUID
    company_id: UUID
    sku: str
    name: str
    unit: ProductUnitValue
    currency: str
    unit_price: Decimal
    status: RecordStatusValue
    version: int
    created_at: datetime
    updated_at: datetime


class ProductListResponse(BaseModel):
    items: list[ProductResponse]
    next_cursor: str | None
    has_more: bool


class ProductCreateRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    sku: str = Field(min_length=1, max_length=40)
    name: str = Field(min_length=1, max_length=160)
    unit: ProductUnitValue
    currency: str = Field(pattern=_CURRENCY, description="ISO 4217 code.")
    unit_price: Decimal = Field(ge=0, max_digits=18, decimal_places=4)


class ProductUpdateRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    sku: str | None = Field(default=None, min_length=1, max_length=40)
    name: str | None = Field(default=None, min_length=1, max_length=160)
    unit: ProductUnitValue | None = None
    currency: str | None = Field(default=None, pattern=_CURRENCY)
    unit_price: Decimal | None = Field(default=None, ge=0, max_digits=18, decimal_places=4)
    status: RecordStatusValue | None = None

    @model_validator(mode="after")
    def _at_least_one_field(self) -> ProductUpdateRequest:
        if not self.model_fields_set:
            raise ValueError("Provide at least one field to update.")
        return self


class DealItemRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    product_id: UUID
    quantity: Decimal = Field(gt=0, max_digits=18, decimal_places=3)
    unit_price: Decimal = Field(ge=0, max_digits=18, decimal_places=4)


class DealCreateRequest(BaseModel):
    model_config = ConfigDict(
        extra="forbid",
        json_schema_extra={
            "example": {
                "title": "50 MT aluminium ingots",
                "counterparty_id": "7f7b0a54-0f43-4d7d-9a1b-3f5f3f0f0a11",
                "currency": "USD",
                "expected_close_date": "2026-11-30",
                "items": [
                    {
                        "product_id": "0f6a1f43-2b61-4a4d-9ad6-5a1f1a1f1a11",
                        "quantity": "50.000",
                        "unit_price": "2450.0000",
                    }
                ],
            }
        },
    )

    title: str = Field(min_length=1, max_length=160)
    counterparty_id: UUID
    currency: str = Field(pattern=_CURRENCY)
    expected_close_date: date | None = None
    notes: str | None = Field(default=None, max_length=2000)
    reference: str | None = Field(
        default=None,
        pattern=_REFERENCE,
        description="Optional human reference; generated when omitted.",
    )
    items: list[DealItemRequest] = Field(min_length=1, max_length=20)

    @model_validator(mode="after")
    def _unique_products(self) -> DealCreateRequest:
        product_ids = [item.product_id for item in self.items]
        if len(set(product_ids)) != len(product_ids):
            raise ValueError("Each product may appear only once per deal.")
        return self


class DealUpdateRequest(BaseModel):
    """Header-only update. ``status`` is intentionally absent (ADR-025)."""

    model_config = ConfigDict(extra="forbid")

    title: str | None = Field(default=None, min_length=1, max_length=160)
    counterparty_id: UUID | None = None
    currency: str | None = Field(default=None, pattern=_CURRENCY)
    expected_close_date: date | None = None
    notes: str | None = Field(default=None, max_length=2000)

    @model_validator(mode="after")
    def _at_least_one_field(self) -> DealUpdateRequest:
        if not self.model_fields_set:
            raise ValueError("Provide at least one field to update.")
        return self



class DealItemResponse(BaseModel):
    id: UUID
    product_id: UUID
    sku: str
    name: str
    unit: ProductUnitValue
    quantity: Decimal
    unit_price: Decimal
    line_total: Decimal


class DealTransitionResponse(BaseModel):
    id: UUID
    from_status: DealStatusValue | None
    to_status: DealStatusValue
    reason: str | None
    actor_id: UUID
    request_id: str | None
    version_after: int
    occurred_at: datetime


class DealSummaryResponse(BaseModel):
    """List projection: no lines or history, only what a table needs."""

    id: UUID
    company_id: UUID
    reference: str
    title: str
    status: DealStatusValue
    counterparty_id: UUID
    counterparty_name: str
    currency: str
    expected_close_date: date | None
    total_value: Decimal
    version: int
    created_at: datetime
    updated_at: datetime


class DealResponse(BaseModel):
    id: UUID
    company_id: UUID
    reference: str
    title: str
    status: DealStatusValue
    counterparty_id: UUID
    counterparty_name: str
    currency: str
    expected_close_date: date | None
    notes: str | None
    total_value: Decimal
    version: int = Field(description="Optimistic concurrency version; also sent as ETag.")
    created_by: UUID
    closed_at: datetime | None
    created_at: datetime
    updated_at: datetime
    items: list[DealItemResponse]
    transitions: list[DealTransitionResponse]
    allowed_transitions: list[DealStatusValue] = Field(
        description="Statuses reachable from the current status; WON is never listed."
    )


class DealListResponse(BaseModel):
    items: list[DealSummaryResponse]
    next_cursor: str | None
    has_more: bool


class DealTransitionRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    to: DealStatusValue
    reason: str | None = Field(
        default=None,
        max_length=500,
        description="Required (3-500 characters) for LOST and CANCELLED.",
    )


class DashboardStatusCount(BaseModel):
    status: DealStatusValue
    deal_count: int
    total_value: Decimal


class DashboardCurrencyTotal(BaseModel):
    currency: str
    deal_count: int
    total_value: Decimal


class DashboardActivity(BaseModel):
    action: str
    outcome: str
    occurred_at: datetime
    resource_type: str | None
    resource_id: str | None


class DashboardSummaryResponse(BaseModel):
    company_id: UUID
    generated_at: datetime
    deals_total: int
    status_counts: list[DashboardStatusCount]
    pipeline: list[DashboardCurrencyTotal]
    counterparties_total: int
    counterparties_active: int
    products_total: int
    products_active: int
    recent_deals: list[DealSummaryResponse]
    recent_activity: list[DashboardActivity]


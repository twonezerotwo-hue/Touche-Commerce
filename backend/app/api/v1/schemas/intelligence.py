"""Stage 5E financial intelligence API schemas.

Amounts and percentages are decimal strings. ``read_only`` and
``accounting_writes_enabled`` are literal response guarantees.
"""

from __future__ import annotations

from datetime import date, datetime
from typing import Any, Literal
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field

CompletenessValue = Literal["COMPLETE", "PARTIAL", "MISSING", "UNAVAILABLE"]
ValueClassification = Literal[
    "ESTIMATED",
    "COMMITTED",
    "DOCUMENTED",
    "FINANCE_OBSERVED",
    "VERIFIED",
    "UNAVAILABLE",
]
MetricKindValue = Literal["MONEY", "PERCENT", "COUNT"]
ReconciliationStatusValue = Literal[
    "INCOMPLETE",
    "UNMATCHED",
    "POTENTIAL_MATCH",
    "MATCHED_EVIDENCE",
    "VERIFIED",
    "DISPUTED",
]


class IntelligenceModel(BaseModel):
    model_config = ConfigDict(extra="ignore")


class MoneyTotalResponse(IntelligenceModel):
    currency: str
    amount: str


class PercentTotalResponse(IntelligenceModel):
    currency: str
    value: str


class IntelligenceMetricResponse(IntelligenceModel):
    key: str
    label: str
    kind: MetricKindValue
    money: list[MoneyTotalResponse]
    percentages: list[PercentTotalResponse]
    percentage: str | None = None
    count: int | None = None
    available: bool
    classification: ValueClassification
    completeness: CompletenessValue
    meaning: str
    as_of: date
    data_through: date | None = None


class MonthlyCommitmentResponse(IntelligenceModel):
    month: str
    currency: str
    accepted_value: str
    purchase_commitments: str
    order_count: int = Field(ge=0)


class CostComparisonResponse(IntelligenceModel):
    currency: str
    estimated_cost: str
    documented_cost: str
    variance: str
    order_count: int = Field(ge=0)


class MarginBucketResponse(IntelligenceModel):
    key: str
    label: str
    count: int = Field(ge=0)


class CategoryCountResponse(IntelligenceModel):
    key: str
    count: int = Field(ge=0)


class CompletenessCountResponse(IntelligenceModel):
    status: CompletenessValue
    count: int = Field(ge=0)


class FilterOptionResponse(IntelligenceModel):
    id: UUID
    name: str


class FilterOptionsResponse(IntelligenceModel):
    currencies: list[str]
    customers: list[FilterOptionResponse]
    suppliers: list[FilterOptionResponse]
    order_statuses: list[str]
    fulfilment_models: list[str]
    reconciliation_statuses: list[str]
    completeness_statuses: list[CompletenessValue]


class OrderProfitabilityResponse(IntelligenceModel):
    sales_order_id: UUID
    order_number: str
    customer_name: str
    status: str
    fulfilment_model: str
    currency: str
    confirmed_at: datetime
    expected_delivery_date: date | None = None
    sales_value: str
    estimated_purchase_cost: str | None = None
    estimated_extra_purchase_cost: str | None = None
    estimated_operational_cost: str | None = None
    estimated_vat_cashflow: str | None = None
    estimated_landed_cost: str | None = None
    scenario_landed_total_including_vat: str | None = None
    committed_purchase_cost: str | None = None
    quoted_operational_cost: str | None = None
    documented_operational_cost: str | None = None
    documented_total_cost: str | None = None
    estimated_gross_profit: str | None = None
    estimated_gross_margin_pct: str | None = None
    estimated_markup_pct: str | None = None
    committed_gross_profit: str | None = None
    committed_gross_margin_pct: str | None = None
    committed_markup_pct: str | None = None
    cost_variance: str | None = None
    cost_variance_pct: str | None = None
    estimate_status: CompletenessValue
    committed_status: CompletenessValue
    completeness: CompletenessValue
    missing_components: list[str]
    classifications: dict[str, str]
    purchase_currency_mismatch: bool
    cost_currency_mismatch: bool
    partial_fulfilment: bool
    cancelled: bool
    reconciliation_status: ReconciliationStatusValue | None = None
    latest_run_id: UUID | None = None
    latest_run_at: datetime | None = None
    data_through: date | None = None
    open_discrepancy_count: int = Field(ge=0)
    blocking_discrepancy_count: int = Field(ge=0)
    run_count: int = Field(ge=0)


class IntelligenceSummaryResponse(IntelligenceModel):
    as_of: date
    data_through: date | None = None
    calculation_version: str
    order_count: int = Field(ge=0)
    active_order_count: int = Field(ge=0)
    cancelled_order_count: int = Field(ge=0)
    metrics: list[IntelligenceMetricResponse]
    monthly_commitments: list[MonthlyCommitmentResponse]
    cost_comparison: list[CostComparisonResponse]
    margin_distribution: list[MarginBucketResponse]
    discrepancy_categories: list[CategoryCountResponse]
    completeness: list[CompletenessCountResponse]
    review_orders: list[OrderProfitabilityResponse]
    filter_options: FilterOptionsResponse
    read_only: Literal[True] = True
    accounting_writes_enabled: Literal[False] = False
    statutory_statements: Literal[False] = False


class OrderIntelligenceListResponse(IntelligenceModel):
    items: list[OrderProfitabilityResponse]
    total: int = Field(ge=0)
    limit: int = Field(ge=1)
    offset: int = Field(ge=0)
    calculation_version: str
    as_of: date
    data_through: date | None = None
    read_only: Literal[True] = True
    accounting_writes_enabled: Literal[False] = False


class CostVarianceListResponse(IntelligenceModel):
    items: list[OrderProfitabilityResponse]
    total: int = Field(ge=0)
    excluded_order_count: int = Field(ge=0)
    limit: int = Field(ge=1)
    offset: int = Field(ge=0)
    calculation_version: str
    read_only: Literal[True] = True
    accounting_writes_enabled: Literal[False] = False


class CoverageResponse(IntelligenceModel):
    as_of: date
    data_through: date | None = None
    order_count: int = Field(ge=0)
    active_order_count: int = Field(ge=0)
    estimate: list[CompletenessCountResponse]
    committed: list[CompletenessCountResponse]
    reconciliation: list[CategoryCountResponse]
    missing_components: list[CategoryCountResponse]
    calculation_version: str
    read_only: Literal[True] = True
    accounting_writes_enabled: Literal[False] = False


class FinancialExceptionResponse(IntelligenceModel):
    id: UUID
    run_id: UUID
    sales_order_id: UUID
    order_number: str
    customer_name: str
    currency: str
    order_status: str
    code: str
    severity: Literal["INFO", "WARNING", "ERROR", "BLOCKING"]
    status: Literal["OPEN", "RESOLVED", "DISMISSED"]
    title: str
    detail: str
    expected: dict[str, Any]
    observed: dict[str, Any]
    source_entity_type: str | None = None
    source_entity_id: UUID | None = None
    finance_source_reference: str | None = None
    reviewer_name: str | None = None
    resolution_notes: str | None = None
    resolved_at: datetime | None = None
    created_at: datetime
    updated_at: datetime
    version: int = Field(ge=1)


class FinancialExceptionListResponse(IntelligenceModel):
    items: list[FinancialExceptionResponse]
    total: int = Field(ge=0)
    limit: int = Field(ge=1)
    offset: int = Field(ge=0)
    read_only: Literal[True] = True
    accounting_writes_enabled: Literal[False] = False


class CompletionCheckResponse(IntelligenceModel):
    key: str
    label: str
    satisfied: bool
    detail: str


class QuoteLineResponse(IntelligenceModel):
    product_id: UUID
    description: str
    quantity: str
    unit: str
    unit_price: str
    line_total: str


class QuoteDetailResponse(IntelligenceModel):
    quote_id: UUID
    quote_number: str
    revision: int = Field(ge=1)
    status: str
    currency: str
    incoterm: str
    named_delivery_place: str
    payment_terms: str
    valid_until: date
    approved_at: datetime | None = None
    lines: list[QuoteLineResponse]


class PurchaseOrderDetailResponse(IntelligenceModel):
    purchase_order_id: UUID
    po_number: str
    status: str
    currency: str
    total_cost: str
    supplier_id: UUID | None = None
    supplier_name: str | None = None
    classification: ValueClassification


class ShipmentCostDetailResponse(IntelligenceModel):
    cost_id: UUID
    cost_type: str
    stage: str
    currency: str
    amount: str
    reference: str
    classification: ValueClassification


class ShipmentDetailResponse(IntelligenceModel):
    shipment_id: UUID
    shipment_number: str
    status: str
    costs: list[ShipmentCostDetailResponse]


class EstimateCostLineResponse(IntelligenceModel):
    cost_type: str
    original_amount: str | None = None
    original_currency: str
    converted_amount: str | None = None
    target_currency: str
    basis: str
    verification_status: str
    source_reference: str
    fx_rate: str | None = None
    fx_snapshot_id: UUID | None = None
    is_expense: bool


class FxAssumptionResponse(IntelligenceModel):
    snapshot_id: UUID
    base_currency: str
    quote_currency: str
    rate: str
    effective_at: datetime
    source: str


class ReconciliationTimelineResponse(IntelligenceModel):
    run_id: UUID
    status: ReconciliationStatusValue
    as_of: date
    data_through: date | None = None
    currency: str
    created_at: datetime
    evidence_count: int = Field(ge=0)
    open_discrepancy_count: int = Field(ge=0)
    latest_decision: Literal["CONFIRM", "DISPUTE", "REQUEST_CHANGES"] | None = None
    latest_review_at: datetime | None = None


class EvidenceReferenceResponse(IntelligenceModel):
    id: UUID
    run_id: UUID
    source_entity_type: str
    source_entity_id: UUID
    finance_source_type: str
    finance_source_reference: str
    currency: str
    amount: str
    as_of: date
    data_through: date | None = None
    verification_status: Literal["UNVERIFIED", "VERIFIED", "REJECTED"]
    created_at: datetime
    verified_at: datetime | None = None


class OrderIntelligenceDetailResponse(IntelligenceModel):
    order: OrderProfitabilityResponse
    quote: QuoteDetailResponse
    purchase_orders: list[PurchaseOrderDetailResponse]
    shipments: list[ShipmentDetailResponse]
    cost_lines: list[EstimateCostLineResponse]
    fx_assumptions: list[FxAssumptionResponse]
    checks: list[CompletionCheckResponse]
    limitations: list[str]
    runs: list[ReconciliationTimelineResponse]
    evidence: list[EvidenceReferenceResponse]
    discrepancies: list[FinancialExceptionResponse]
    read_only: Literal[True] = True
    accounting_writes_enabled: Literal[False] = False
    statutory_statements: Literal[False] = False

"""Stage 5D reconciliation API schemas.

Amounts are decimal strings so no JSON float can alter a financial value.
Every response declares ``read_only=true`` and ``accounting_writes_enabled=false``.
"""

from __future__ import annotations

from datetime import date, datetime
from typing import Any, Literal
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field

ReconciliationStatusValue = Literal[
    "INCOMPLETE",
    "UNMATCHED",
    "POTENTIAL_MATCH",
    "MATCHED_EVIDENCE",
    "VERIFIED",
    "DISPUTED",
]
DiscrepancyCodeValue = Literal[
    "MISSING_EVIDENCE",
    "MISSING_FINANCE_REFERENCE",
    "AMOUNT_MISMATCH",
    "CURRENCY_MISMATCH",
    "DUPLICATE_REFERENCE",
    "INCOMPLETE_COSTS",
    "UNMATCHED_FINANCE_ITEM",
    "SOURCE_STALE",
    "COMPANY_MAPPING_INVALID",
    "MANUAL_REVIEW_REQUIRED",
]
EvidenceSourceEntityValue = Literal["SALES_ORDER", "PURCHASE_ORDER", "SHIPMENT_COST"]


class ReconciliationModel(BaseModel):
    model_config = ConfigDict(extra="ignore")


class CompletenessCheckResponse(ReconciliationModel):
    key: str
    label: str
    satisfied: bool
    detail: str


class ReconciliationMetricsResponse(ReconciliationModel):
    accepted_sales_order_value: str
    purchase_commitments_total: str | None = None
    purchase_commitment_count: int = Field(ge=0)
    estimated_landed_cost: str | None = None
    recorded_operational_costs: str | None = None
    estimate_vs_recorded_variance: str | None = None
    commitment_based_margin: str | None = None
    commitment_based_margin_pct: str | None = None
    document_supported_margin: str | None = None
    completeness_score: str
    completeness_checks: list[CompletenessCheckResponse]


class SourceReferenceResponse(ReconciliationModel):
    id: UUID
    source_type: Literal["AGING_RECEIVABLE", "AGING_PAYABLE", "ACCOUNT", "SUMMARY"]
    source_reference: str
    is_transaction_level: bool
    currency: str
    observed_amount: str | None = None
    as_of: date
    data_through: date | None = None
    content_hash: str
    payload: dict[str, Any]


class EvidenceLinkResponse(ReconciliationModel):
    id: UUID
    source_entity_type: Literal["SALES_ORDER", "PURCHASE_ORDER", "SHIPMENT", "SHIPMENT_COST"]
    source_entity_id: UUID
    finance_source_reference_id: UUID
    finance_source_type: str
    finance_source_reference: str
    currency: str
    amount: str
    as_of: date
    data_through: date | None = None
    provenance: dict[str, Any]
    verification_status: Literal["UNVERIFIED", "VERIFIED", "REJECTED"]
    notes: str | None = None
    created_by: UUID
    created_at: datetime
    verified_by: UUID | None = None
    verified_at: datetime | None = None


class DiscrepancyResponse(ReconciliationModel):
    id: UUID
    run_id: UUID
    code: DiscrepancyCodeValue
    severity: Literal["INFO", "WARNING", "ERROR", "BLOCKING"]
    status: Literal["OPEN", "RESOLVED", "DISMISSED"]
    title: str
    detail: str
    expected: dict[str, Any]
    observed: dict[str, Any]
    source_entity_type: str | None = None
    source_entity_id: UUID | None = None
    finance_source_reference_id: UUID | None = None
    assigned_to: UUID | None = None
    resolution_notes: str | None = None
    resolved_by: UUID | None = None
    resolved_at: datetime | None = None
    created_at: datetime
    updated_at: datetime
    version: int


class ReviewResponse(ReconciliationModel):
    id: UUID
    decision: Literal["CONFIRM", "DISPUTE", "REQUEST_CHANGES"]
    previous_status: ReconciliationStatusValue
    new_status: ReconciliationStatusValue
    notes: str
    reviewer_id: UUID
    reviewer_name: str | None = None
    created_at: datetime


class ReconciliationRunSummaryResponse(ReconciliationModel):
    id: UUID
    sales_order_id: UUID
    order_number: str
    customer_name: str
    currency: str
    as_of: date
    data_through: date | None = None
    status: ReconciliationStatusValue
    version: int
    created_at: datetime
    evidence_count: int
    open_discrepancy_count: int
    blocking_discrepancy_count: int


class ReconciliationRunResponse(ReconciliationRunSummaryResponse):
    company_id: UUID
    finance_company_id: str
    finance_currency: str
    calculation_version: str
    metrics: ReconciliationMetricsResponse
    classifications: dict[str, str]
    limitations: list[str]
    finance_snapshot: dict[str, Any]
    source_references: list[SourceReferenceResponse]
    evidence_links: list[EvidenceLinkResponse]
    discrepancies: list[DiscrepancyResponse]
    reviews: list[ReviewResponse]
    created_by: UUID
    updated_at: datetime
    read_only: Literal[True] = True
    accounting_writes_enabled: Literal[False] = False


class ReconciliationListResponse(ReconciliationModel):
    items: list[ReconciliationRunSummaryResponse]
    total: int = Field(ge=0)
    limit: int = Field(ge=1)
    offset: int = Field(ge=0)
    currency: str | None = None
    status_counts: dict[str, int]
    open_discrepancy_count: int = Field(ge=0)
    blocking_discrepancy_count: int = Field(ge=0)
    read_only: Literal[True] = True
    accounting_writes_enabled: Literal[False] = False


class ReconciliationRunCreateRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    sales_order_id: UUID
    currency: str | None = Field(default=None, max_length=3, pattern=r"^[A-Za-z]{2,3}$")
    as_of: date | None = None


class EvidenceLinkRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    run_id: UUID
    source_entity_type: EvidenceSourceEntityValue
    source_entity_id: UUID
    finance_source_reference_id: UUID
    notes: str | None = Field(default=None, max_length=2000)


class EvidenceLinkListResponse(ReconciliationModel):
    items: list[EvidenceLinkResponse]
    total: int = Field(ge=0)
    limit: int = Field(ge=1)
    offset: int = Field(ge=0)
    read_only: Literal[True] = True
    accounting_writes_enabled: Literal[False] = False


class DiscrepancyListResponse(ReconciliationModel):
    items: list[DiscrepancyResponse]
    total: int = Field(ge=0)
    limit: int = Field(ge=1)
    offset: int = Field(ge=0)
    read_only: Literal[True] = True
    accounting_writes_enabled: Literal[False] = False


class DiscrepancyResolveRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    notes: str = Field(min_length=3, max_length=2000)


class ReviewRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    run_id: UUID
    decision: Literal["CONFIRM", "DISPUTE", "REQUEST_CHANGES"]
    notes: str = Field(min_length=3, max_length=2000)


class OrderFinanceOrder(ReconciliationModel):
    sales_order_id: UUID
    order_number: str
    customer_name: str
    status: str
    fulfilment_model: str
    currency: str
    order_total: str
    confirmed_at: str
    expected_delivery_date: date | None = None


class OrderFinancePurchaseOrder(ReconciliationModel):
    purchase_order_id: UUID
    po_number: str
    status: str
    currency: str
    total_cost: str
    is_committed: bool


class OrderFinanceShipmentCost(ReconciliationModel):
    cost_id: UUID
    cost_type: str
    stage: str
    currency: str
    amount: str
    reference: str


class OrderFinanceShipment(ReconciliationModel):
    shipment_id: UUID
    shipment_number: str
    status: str
    costs: list[OrderFinanceShipmentCost]


class OrderFinanceEvidenceGap(ReconciliationModel):
    code: DiscrepancyCodeValue
    severity: Literal["INFO", "WARNING", "ERROR", "BLOCKING"]
    title: str
    detail: str
    expected: dict[str, Any]
    observed: dict[str, Any]
    source_entity_type: str | None = None
    source_entity_id: UUID | None = None


class OrderFinanceResponse(ReconciliationModel):
    order: OrderFinanceOrder
    purchase_orders: list[OrderFinancePurchaseOrder]
    shipments: list[OrderFinanceShipment]
    metrics: ReconciliationMetricsResponse
    classifications: dict[str, str]
    limitations: list[str]
    missing_evidence: list[OrderFinanceEvidenceGap]
    latest_run_id: UUID | None = None
    latest_run_status: ReconciliationStatusValue | None = None
    latest_run_at: datetime | None = None
    read_only: Literal[True] = True
    accounting_writes_enabled: Literal[False] = False

"""Deterministic Stage 5D financial analysis.

This module contains no I/O. It accepts already-loaded commercial facts and
returns Decimal metrics, explicit classifications and deterministic discrepancy
drafts. Finance remains a separate observation: no company balance is attributed
to an order, and no mixed-currency total is ever produced.

Terminology is deliberately narrow:

* ``ESTIMATED``  â€” a Stage 3 landed-cost scenario;
* ``COMMITTED``  â€” an approved/recorded purchase order;
* ``DOCUMENTED`` â€” a Commerce operational fact or cost;
* ``FINANCE_OBSERVED`` â€” a value Finance itself reported;
* ``VERIFIED``   â€” a human review confirmed linked evidence;
* ``UNAVAILABLE`` â€” the supported contract does not expose the fact.

There is intentionally no ``actual_profit`` field.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import date
from decimal import Decimal
from enum import StrEnum
from uuid import UUID

from app.db.models import (
    DiscrepancyCode,
    DiscrepancySeverity,
    PurchaseOrderStatus,
    SalesOrderStatus,
    ShipmentStatus,
)

CALCULATION_VERSION = "stage5d-1.0.0"
MONEY_QUANTUM = Decimal("0.01")
ZERO = Decimal("0")

_COMMITTED_PO_STATUSES = frozenset(
    {
        PurchaseOrderStatus.APPROVED.value,
        PurchaseOrderStatus.RECORDED_SENT.value,
        PurchaseOrderStatus.SUPPLIER_CONFIRMED.value,
        PurchaseOrderStatus.IN_FULFILLMENT.value,
        PurchaseOrderStatus.RECEIVED.value,
    }
)
_CLOSED_SALES_ORDER_STATUSES = frozenset(
    {SalesOrderStatus.FULFILLED.value, SalesOrderStatus.CLOSED.value}
)
_ACTIVE_SHIPMENT_STATUSES = frozenset(
    status.value for status in ShipmentStatus if status is not ShipmentStatus.CANCELLED
)


class ValueClass(StrEnum):
    ESTIMATED = "ESTIMATED"
    COMMITTED = "COMMITTED"
    DOCUMENTED = "DOCUMENTED"
    FINANCE_OBSERVED = "FINANCE_OBSERVED"
    VERIFIED = "VERIFIED"
    UNAVAILABLE = "UNAVAILABLE"


def canonical_currency(value: str) -> str:
    """Normalise one currency label without converting any amount.

    Finance uses ``TL`` for Turkish lira while Commerce's ISO code is ``TRY``.
    That is a label alias, not an exchange rate: the numeric amount is unchanged.
    Unknown labels are returned upper-cased and must match the supported list.
    """

    normalised = value.strip().upper()
    return "TRY" if normalised == "TL" else normalised


def finance_currency_for(canonical: str, available: tuple[str, ...]) -> str | None:
    """Select the Finance label for a canonical currency, or ``None``."""

    normalised = canonical_currency(canonical)
    if normalised in available:
        return normalised
    if normalised == "TRY" and "TL" in available:
        return "TL"
    return None


def quantize_money(value: Decimal) -> Decimal:
    return value.quantize(MONEY_QUANTUM)


@dataclass(frozen=True, slots=True)
class PurchaseCommitmentFact:
    purchase_order_id: UUID
    po_number: str
    status: str
    currency: str
    total_cost: Decimal

    @property
    def is_committed(self) -> bool:
        return self.status in _COMMITTED_PO_STATUSES


@dataclass(frozen=True, slots=True)
class ShipmentCostFact:
    cost_id: UUID
    cost_type: str
    stage: str
    currency: str
    amount: Decimal
    reference: str


@dataclass(frozen=True, slots=True)
class ShipmentFact:
    shipment_id: UUID
    shipment_number: str
    status: str
    costs: tuple[ShipmentCostFact, ...]

    @property
    def is_active(self) -> bool:
        return self.status in _ACTIVE_SHIPMENT_STATUSES


@dataclass(frozen=True, slots=True)
class PricingEstimateFact:
    scenario_id: UUID
    status: str
    calculation_version: str
    target_currency: str
    landed_total: Decimal | None
    sales_total: Decimal | None


@dataclass(frozen=True, slots=True)
class CommercialFacts:
    sales_order_id: UUID
    order_number: str
    customer_name: str
    status: str
    fulfilment_model: str
    currency: str
    order_total: Decimal
    confirmed_at: str
    expected_delivery_date: date | None
    purchase_orders: tuple[PurchaseCommitmentFact, ...]
    shipments: tuple[ShipmentFact, ...]
    pricing_estimate: PricingEstimateFact | None


@dataclass(frozen=True, slots=True)
class CompletenessCheck:
    key: str
    label: str
    satisfied: bool
    detail: str


@dataclass(frozen=True, slots=True)
class ReconciliationMetrics:
    accepted_sales_order_value: Decimal
    purchase_commitments_total: Decimal | None
    purchase_commitment_count: int
    estimated_landed_cost: Decimal | None
    recorded_operational_costs: Decimal | None
    estimate_vs_recorded_variance: Decimal | None
    commitment_based_margin: Decimal | None
    commitment_based_margin_pct: Decimal | None
    document_supported_margin: Decimal | None
    completeness_checks: tuple[CompletenessCheck, ...]

    @property
    def completeness_score(self) -> Decimal:
        if not self.completeness_checks:
            return ZERO
        satisfied = sum(1 for check in self.completeness_checks if check.satisfied)
        return (
            Decimal(satisfied) * Decimal(100) / Decimal(len(self.completeness_checks))
        ).quantize(MONEY_QUANTUM)

    @property
    def is_complete(self) -> bool:
        return all(check.satisfied for check in self.completeness_checks)


@dataclass(frozen=True, slots=True)
class DiscrepancyDraft:
    code: DiscrepancyCode
    severity: DiscrepancySeverity
    title: str
    detail: str
    expected: dict[str, object]
    observed: dict[str, object]
    source_entity_type: str | None = None
    source_entity_id: UUID | None = None
    finance_source_reference_id: UUID | None = None


@dataclass(frozen=True, slots=True)
class AnalysisResult:
    metrics: ReconciliationMetrics
    discrepancies: tuple[DiscrepancyDraft, ...]
    classifications: dict[str, str]
    limitations: tuple[str, ...]
    status: str


def _money_text(value: Decimal | None) -> str | None:
    return None if value is None else str(quantize_money(value))


def build_metrics(facts: CommercialFacts) -> ReconciliationMetrics:
    """Calculate every supported figure without mixing currencies.

    ``None`` means either the concept is unsupported or the inputs contain a
    currency that cannot be added to the order currency. A caller must display
    it as unavailable, never as zero.
    """

    order_currency = canonical_currency(facts.currency)
    mismatched_po_currencies = {
        canonical_currency(po.currency)
        for po in facts.purchase_orders
        if canonical_currency(po.currency) != order_currency
    }
    committed = tuple(po for po in facts.purchase_orders if po.is_committed)
    committed_currency_ok = not mismatched_po_currencies and all(
        canonical_currency(po.currency) == order_currency for po in committed
    )
    purchase_total: Decimal | None
    if facts.fulfilment_model == "BROKERAGE":
        purchase_total = ZERO if committed_currency_ok else None
    elif committed and committed_currency_ok:
        purchase_total = quantize_money(sum((po.total_cost for po in committed), ZERO))
    else:
        purchase_total = None

    estimate = facts.pricing_estimate
    estimate_currency_ok = (
        estimate is not None
        and estimate.landed_total is not None
        and canonical_currency(estimate.target_currency) == order_currency
    )
    estimated_landed = (
        quantize_money(estimate.landed_total)
        if estimate is not None and estimate.landed_total is not None and estimate_currency_ok
        else None
    )

    active_shipments = tuple(shipment for shipment in facts.shipments if shipment.is_active)
    cost_currency_bad = any(
        canonical_currency(cost.currency) != order_currency
        for shipment in active_shipments
        for cost in shipment.costs
    )
    recorded_costs = (
        quantize_money(
            sum(
                (cost.amount for shipment in active_shipments for cost in shipment.costs),
                ZERO,
            )
        )
        if not cost_currency_bad
        else None
    )
    shipments_without_costs = tuple(shipment for shipment in active_shipments if not shipment.costs)
    costs_complete = not shipments_without_costs and not (
        facts.status in _CLOSED_SALES_ORDER_STATUSES and not active_shipments
    )
    if not costs_complete:
        recorded_costs = None

    variance = (
        quantize_money(estimated_landed - recorded_costs)
        if estimated_landed is not None and recorded_costs is not None
        else None
    )
    margin = (
        quantize_money(facts.order_total - purchase_total - recorded_costs)
        if purchase_total is not None and recorded_costs is not None
        else None
    )
    margin_pct = (
        (margin * Decimal(100) / facts.order_total).quantize(MONEY_QUANTUM)
        if margin is not None and facts.order_total > ZERO
        else None
    )

    pricing_satisfied = estimated_landed is not None
    purchase_satisfied = (
        facts.fulfilment_model == "BROKERAGE" and purchase_total is not None
    ) or bool(committed)
    checks = (
        CompletenessCheck(
            key="accepted_sales_order",
            label="Accepted sales order",
            satisfied=True,
            detail="The order and its accepted terms are stored in Commerce.",
        ),
        CompletenessCheck(
            key="pricing_estimate",
            label="Pricing estimate",
            satisfied=pricing_satisfied,
            detail="A same-currency Stage 3 landed-cost result is available."
            if pricing_satisfied
            else "No supported same-currency landed-cost result is attached.",
        ),
        CompletenessCheck(
            key="purchase_commitment",
            label="Purchase commitment",
            satisfied=purchase_satisfied,
            detail="A committed purchase order exists."
            if purchase_satisfied and facts.fulfilment_model != "BROKERAGE"
            else (
                "Brokerage does not require a purchase commitment."
                if facts.fulfilment_model == "BROKERAGE"
                else "No approved or recorded purchase order exists."
            ),
        ),
        CompletenessCheck(
            key="operational_costs",
            label="Operational costs",
            satisfied=costs_complete,
            detail="Every active shipment has a same-currency recorded cost."
            if costs_complete
            else "At least one shipment cost is missing or in another currency.",
        ),
        CompletenessCheck(
            key="currency_consistency",
            label="Currency consistency",
            satisfied=not mismatched_po_currencies
            and not cost_currency_bad
            and estimate_currency_ok,
            detail="All compared source records use the order currency."
            if not mismatched_po_currencies and not cost_currency_bad and estimate_currency_ok
            else "At least one source record uses a different currency; no conversion was applied.",
        ),
    )

    return ReconciliationMetrics(
        accepted_sales_order_value=quantize_money(facts.order_total),
        purchase_commitments_total=purchase_total,
        purchase_commitment_count=len(committed),
        estimated_landed_cost=estimated_landed,
        recorded_operational_costs=recorded_costs,
        estimate_vs_recorded_variance=variance,
        commitment_based_margin=margin,
        commitment_based_margin_pct=margin_pct,
        document_supported_margin=None,
        completeness_checks=checks,
    )


def detect_discrepancies(
    facts: CommercialFacts,
    metrics: ReconciliationMetrics,
    *,
    as_of: date,
    finance_data_through: date | None,
    duplicate_finance_references: int = 0,
) -> tuple[DiscrepancyDraft, ...]:
    """Return only conclusions the loaded evidence actually supports."""

    drafts: list[DiscrepancyDraft] = []
    currency = canonical_currency(facts.currency)

    if facts.status == SalesOrderStatus.CANCELLED.value:
        drafts.append(
            DiscrepancyDraft(
                code=DiscrepancyCode.MISSING_EVIDENCE,
                severity=DiscrepancySeverity.WARNING,
                title="Cancelled order has no current value to reconcile",
                detail=(
                    "The accepted commercial history is preserved, but a cancelled order "
                    "must not be treated as current revenue or a live commitment."
                ),
                expected={"status": "current order"},
                observed={"status": facts.status},
                source_entity_type="SALES_ORDER",
                source_entity_id=facts.sales_order_id,
            )
        )

    estimate = facts.pricing_estimate
    if estimate is None or estimate.landed_total is None:
        drafts.append(
            DiscrepancyDraft(
                code=DiscrepancyCode.MISSING_EVIDENCE,
                severity=DiscrepancySeverity.WARNING,
                title="No supported landed-cost estimate",
                detail=(
                    "No completed same-currency pricing scenario is attached to the "
                    "accepted quote. Estimated landed cost stays unavailable."
                ),
                expected={"pricing_estimate": "available"},
                observed={"pricing_estimate": "unavailable"},
                source_entity_type="SALES_ORDER",
                source_entity_id=facts.sales_order_id,
            )
        )
    elif canonical_currency(estimate.target_currency) != currency:
        drafts.append(
            DiscrepancyDraft(
                code=DiscrepancyCode.CURRENCY_MISMATCH,
                severity=DiscrepancySeverity.BLOCKING,
                title="Pricing estimate currency differs from the order",
                detail=(
                    "The landed-cost scenario targets a different currency. Commerce "
                    "does not convert it, so no estimate-vs-recorded variance is produced."
                ),
                expected={"currency": currency, "scenario_id": str(estimate.scenario_id)},
                observed={"currency": canonical_currency(estimate.target_currency)},
                source_entity_type="SALES_ORDER",
                source_entity_id=facts.sales_order_id,
            )
        )

    if facts.fulfilment_model == "PURCHASE_RESALE" and metrics.purchase_commitment_count == 0:
        drafts.append(
            DiscrepancyDraft(
                code=DiscrepancyCode.MISSING_EVIDENCE,
                severity=DiscrepancySeverity.WARNING,
                title="No purchase commitment",
                detail=(
                    "This is a purchase-resale order but no approved or recorded "
                    "purchase order supports the commitment."
                ),
                expected={"committed_purchase_orders": "at least one"},
                observed={"committed_purchase_orders": 0},
                source_entity_type="SALES_ORDER",
                source_entity_id=facts.sales_order_id,
            )
        )

    for purchase_order in facts.purchase_orders:
        if canonical_currency(purchase_order.currency) != currency:
            drafts.append(
                DiscrepancyDraft(
                    code=DiscrepancyCode.CURRENCY_MISMATCH,
                    severity=DiscrepancySeverity.BLOCKING,
                    title="Purchase order currency differs from the order",
                    detail=(
                        "A purchase commitment in another currency is not added to the "
                        "order figures. No implicit conversion is performed."
                    ),
                    expected={"currency": currency},
                    observed={"currency": canonical_currency(purchase_order.currency)},
                    source_entity_type="PURCHASE_ORDER",
                    source_entity_id=purchase_order.purchase_order_id,
                )
            )

    for shipment in facts.shipments:
        if not shipment.is_active:
            continue
        if not shipment.costs:
            drafts.append(
                DiscrepancyDraft(
                    code=DiscrepancyCode.INCOMPLETE_COSTS,
                    severity=DiscrepancySeverity.WARNING,
                    title="Shipment has no recorded operational cost",
                    detail=(
                        "The shipment exists, so missing freight/handling cost is a "
                        "Commerce evidence gap. It is not an accounting assertion."
                    ),
                    expected={"recorded_costs": "at least one"},
                    observed={"shipment_number": shipment.shipment_number, "costs": 0},
                    source_entity_type="SHIPMENT",
                    source_entity_id=shipment.shipment_id,
                )
            )
        for cost in shipment.costs:
            if canonical_currency(cost.currency) != currency:
                drafts.append(
                    DiscrepancyDraft(
                        code=DiscrepancyCode.CURRENCY_MISMATCH,
                        severity=DiscrepancySeverity.BLOCKING,
                        title="Shipment cost currency differs from the order",
                        detail=(
                            "The recorded cost is excluded from order totals because "
                            "Commerce never converts currencies implicitly."
                        ),
                        expected={"currency": currency},
                        observed={"currency": canonical_currency(cost.currency)},
                        source_entity_type="SHIPMENT_COST",
                        source_entity_id=cost.cost_id,
                    )
                )

    if facts.status in _CLOSED_SALES_ORDER_STATUSES and not any(
        shipment.is_active for shipment in facts.shipments
    ):
        drafts.append(
            DiscrepancyDraft(
                code=DiscrepancyCode.INCOMPLETE_COSTS,
                severity=DiscrepancySeverity.WARNING,
                title="Fulfilled order has no shipment cost record",
                detail=(
                    "The order is fulfilled or closed but no active shipment carries "
                    "a recorded operational cost."
                ),
                expected={"shipments": "at least one with costs"},
                observed={"active_shipments": 0},
                source_entity_type="SALES_ORDER",
                source_entity_id=facts.sales_order_id,
            )
        )

    if finance_data_through is None:
        drafts.append(
            DiscrepancyDraft(
                code=DiscrepancyCode.SOURCE_STALE,
                severity=DiscrepancySeverity.WARNING,
                title="Finance did not report a data-through date",
                detail=(
                    "The Finance response omitted its ledger watermark, so the "
                    "snapshot's freshness cannot be established."
                ),
                expected={"data_through": "reported"},
                observed={"data_through": None},
            )
        )
    elif finance_data_through < as_of:
        drafts.append(
            DiscrepancyDraft(
                code=DiscrepancyCode.SOURCE_STALE,
                severity=DiscrepancySeverity.WARNING,
                title="Finance data is older than the reconciliation date",
                detail=(
                    "Finance's ledger watermark predates the as-of date. No later "
                    "ledger fact is invented or assumed."
                ),
                expected={"data_through": as_of.isoformat()},
                observed={"data_through": finance_data_through.isoformat()},
            )
        )

    drafts.append(
        DiscrepancyDraft(
            code=DiscrepancyCode.MISSING_FINANCE_REFERENCE,
            severity=DiscrepancySeverity.WARNING,
            title="No Finance source is linked to this order yet",
            detail=(
                "Finance exposes no structured invoice/payment endpoint and no "
                "order-level document reference. This is an unavailable capability "
                "and is not proof that a real invoice is missing. An operator may "
                "link an exposed aging item explicitly; company-wide totals are "
                "never attributed to the order."
            ),
            expected={"order_level_finance_reference": "linked evidence"},
            observed={"order_level_finance_reference": "not linked"},
            source_entity_type="SALES_ORDER",
            source_entity_id=facts.sales_order_id,
        )
    )

    if duplicate_finance_references:
        drafts.append(
            DiscrepancyDraft(
                code=DiscrepancyCode.DUPLICATE_REFERENCE,
                severity=DiscrepancySeverity.BLOCKING,
                title="Finance returned a duplicate source reference",
                detail=(
                    "The same transaction-level source id appeared more than once. "
                    "No automatic allocation semantics are assumed."
                ),
                expected={"unique_source_references": True},
                observed={"duplicate_references": duplicate_finance_references},
            )
        )

    if not metrics.is_complete:
        drafts.append(
            DiscrepancyDraft(
                code=DiscrepancyCode.MANUAL_REVIEW_REQUIRED,
                severity=DiscrepancySeverity.INFO,
                title="Manual financial review required",
                detail=(
                    "At least one required Commerce fact is incomplete; this run "
                    "cannot be treated as fully supported."
                ),
                expected={"completeness": "100.00"},
                observed={"completeness": _money_text(metrics.completeness_score)},
                source_entity_type="SALES_ORDER",
                source_entity_id=facts.sales_order_id,
            )
        )

    return tuple(drafts)


def analyse(
    facts: CommercialFacts,
    *,
    as_of: date,
    finance_data_through: date | None,
    duplicate_finance_references: int = 0,
) -> AnalysisResult:
    metrics = build_metrics(facts)
    drafts = detect_discrepancies(
        facts,
        metrics,
        as_of=as_of,
        finance_data_through=finance_data_through,
        duplicate_finance_references=duplicate_finance_references,
    )
    blocking = any(draft.severity is DiscrepancySeverity.BLOCKING for draft in drafts)
    if blocking or not metrics.is_complete or facts.status == SalesOrderStatus.CANCELLED.value:
        status = "INCOMPLETE"
    else:
        status = "UNMATCHED"
    classifications = {
        "accepted_sales_order_value": ValueClass.DOCUMENTED.value,
        "purchase_commitments_total": (
            ValueClass.COMMITTED.value
            if metrics.purchase_commitments_total is not None
            else ValueClass.UNAVAILABLE.value
        ),
        "estimated_landed_cost": (
            ValueClass.ESTIMATED.value
            if metrics.estimated_landed_cost is not None
            else ValueClass.UNAVAILABLE.value
        ),
        "recorded_operational_costs": (
            ValueClass.DOCUMENTED.value
            if metrics.recorded_operational_costs is not None
            else ValueClass.UNAVAILABLE.value
        ),
        "estimate_vs_recorded_variance": (
            ValueClass.ESTIMATED.value
            if metrics.estimate_vs_recorded_variance is not None
            else ValueClass.UNAVAILABLE.value
        ),
        "commitment_based_margin": (
            ValueClass.COMMITTED.value
            if metrics.commitment_based_margin is not None
            else ValueClass.UNAVAILABLE.value
        ),
        "document_supported_margin": ValueClass.UNAVAILABLE.value,
        "actual_profit": ValueClass.UNAVAILABLE.value,
    }
    limitations = (
        "Finance exposes no structured invoice, payment, counterparty-master or "
        "project-master objects; Commerce does not fabricate them.",
        "No mixed-currency aggregation is performed. TRY/TL is a code alias only, "
        "never an FX conversion.",
        "VAT is not treated as an expense because no accounting treatment is "
        "provided by the exposed Finance contract.",
        "Document-supported margin is unavailable until a supported transaction-level "
        "Finance cost/revenue source exists.",
        "Commitment-based margin is an operational interpretation, not accounting profit.",
    )
    return AnalysisResult(
        metrics=metrics,
        discrepancies=drafts,
        classifications=classifications,
        limitations=limitations,
        status=status,
    )

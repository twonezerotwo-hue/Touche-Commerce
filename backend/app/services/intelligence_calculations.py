"""Deterministic Stage 5E profitability analysis.

This module contains no I/O. It interprets persisted Commerce facts and never
reads Finance directly, never invents an invoice/payment and never converts a
currency without an explicit stored FX snapshot.

Two profitability bases are deliberately kept apart:

* ``ESTIMATED`` — accepted sales value minus the Stage 3 landed-cost scenario.
  ``VAT_CASHFLOW`` is excluded because recoverable VAT is not an expense.
* ``COMMITTED`` / ``DOCUMENTED`` — accepted sales value minus committed purchase
  orders and shipment costs recorded as ``INCURRED`` or ``DOCUMENTED``.

Quoted/estimated shipment costs and the pricing scenario are never added to the
committed basis. There is intentionally no ``actual_profit`` field.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import date, datetime
from decimal import ROUND_HALF_UP, Decimal
from enum import StrEnum
from uuid import UUID

from app.db.models import PurchaseOrderStatus, SalesOrderStatus, ShipmentStatus
from app.services.reconciliation_calculations import (
    ZERO,
    ValueClass,
    canonical_currency,
)

CALCULATION_VERSION = "stage5e-1.0.0"
MONEY_QUANTUM = Decimal("0.01")
PERCENT_QUANTUM = Decimal("0.01")

_COMMITTED_PO_STATUSES = frozenset(
    {
        PurchaseOrderStatus.APPROVED.value,
        PurchaseOrderStatus.RECORDED_SENT.value,
        PurchaseOrderStatus.SUPPLIER_CONFIRMED.value,
        PurchaseOrderStatus.IN_FULFILLMENT.value,
        PurchaseOrderStatus.RECEIVED.value,
    }
)
_FULLY_FULFILLED_STATUSES = frozenset(
    {SalesOrderStatus.FULFILLED.value, SalesOrderStatus.CLOSED.value}
)
_DOCUMENTED_STAGES = frozenset({"INCURRED", "DOCUMENTED"})
_FORECAST_STAGES = frozenset({"QUOTED", "ESTIMATED"})
_ACTIVE_SHIPMENT_STATUSES = frozenset(
    status.value for status in ShipmentStatus if status is not ShipmentStatus.CANCELLED
)
_NON_EXPENSE_COST_TYPES = frozenset({"VAT_CASHFLOW"})


class CompletenessStatus(StrEnum):
    COMPLETE = "COMPLETE"
    PARTIAL = "PARTIAL"
    MISSING = "MISSING"
    UNAVAILABLE = "UNAVAILABLE"


class MetricKind(StrEnum):
    MONEY = "MONEY"
    PERCENT = "PERCENT"
    COUNT = "COUNT"


def money(value: Decimal) -> Decimal:
    """Round a monetary value half-up to cents, matching Stage 3/4 rules."""

    return Decimal(value).quantize(MONEY_QUANTUM, rounding=ROUND_HALF_UP)


def percent(value: Decimal) -> Decimal:
    return Decimal(value).quantize(PERCENT_QUANTUM, rounding=ROUND_HALF_UP)


def safe_ratio(
    numerator: Decimal, denominator: Decimal, *, as_percent: bool = False
) -> Decimal | None:
    """Return a deterministic ratio or ``None`` for an invalid denominator."""

    if denominator <= ZERO:
        return None
    ratio = numerator / denominator
    if as_percent:
        ratio *= Decimal(100)
    return percent(ratio)


@dataclass(frozen=True, slots=True)
class FxFact:
    """A stored, sourced FX observation. Nothing here is inferred or refreshed."""

    snapshot_id: UUID
    base_currency: str
    quote_currency: str
    rate: Decimal
    effective_at: datetime
    source: str


@dataclass(frozen=True, slots=True)
class PricingComponentFact:
    component_id: UUID
    cost_type: str
    amount: Decimal
    currency: str
    basis: str
    verification_status: str
    source_reference: str
    product_id: UUID | None = None
    fx: FxFact | None = None


@dataclass(frozen=True, slots=True)
class PricingScenarioFact:
    scenario_id: UUID
    status: str
    calculation_version: str
    quote_currency: str
    target_currency: str
    purchase_total: Decimal | None
    additional_cost_total: Decimal | None
    landed_total: Decimal | None
    sales_total: Decimal | None
    fx_rate: Decimal | None = None
    fx: FxFact | None = None
    components: tuple[PricingComponentFact, ...] = ()


@dataclass(frozen=True, slots=True)
class PurchaseOrderFact:
    purchase_order_id: UUID
    po_number: str
    status: str
    currency: str
    total_cost: Decimal
    supplier_id: UUID | None = None
    supplier_name: str | None = None

    @property
    def is_committed(self) -> bool:
        return self.status in _COMMITTED_PO_STATUSES

    @property
    def is_cancelled(self) -> bool:
        return self.status == PurchaseOrderStatus.CANCELLED.value


@dataclass(frozen=True, slots=True)
class ShipmentCostFact:
    cost_id: UUID
    cost_type: str
    stage: str
    currency: str
    amount: Decimal
    reference: str

    @property
    def is_documented(self) -> bool:
        return self.stage in _DOCUMENTED_STAGES

    @property
    def is_forecast(self) -> bool:
        return self.stage in _FORECAST_STAGES


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
class OrderFacts:
    sales_order_id: UUID
    order_number: str
    customer_id: UUID
    customer_name: str
    status: str
    fulfilment_model: str
    currency: str
    order_total: Decimal
    confirmed_at: datetime
    expected_delivery_date: date | None
    deal_id: UUID | None = None
    deal_reference: str | None = None
    sales_quote_id: UUID | None = None
    sales_quote_number: str | None = None
    pricing: PricingScenarioFact | None = None
    purchase_orders: tuple[PurchaseOrderFact, ...] = ()
    shipments: tuple[ShipmentFact, ...] = ()
    reconciliation_status: str | None = None
    latest_run_id: UUID | None = None
    latest_run_at: datetime | None = None
    data_through: date | None = None
    open_discrepancy_count: int = 0
    blocking_discrepancy_count: int = 0
    run_count: int = 0


@dataclass(frozen=True, slots=True)
class CompletionCheck:
    key: str
    label: str
    satisfied: bool
    detail: str


@dataclass(frozen=True, slots=True)
class CostLine:
    """One converted estimate component, retaining its original currency."""

    cost_type: str
    original_amount: Decimal | None
    original_currency: str
    converted_amount: Decimal | None
    target_currency: str
    basis: str
    verification_status: str
    source_reference: str
    fx_rate: Decimal | None
    fx_snapshot_id: UUID | None
    is_expense: bool


@dataclass(frozen=True, slots=True)
class ProfitabilityResult:
    sales_order_id: UUID
    currency: str
    sales_value: Decimal
    estimated_purchase_cost: Decimal | None
    estimated_extra_purchase_cost: Decimal | None
    estimated_operational_cost: Decimal | None
    estimated_vat_cashflow: Decimal | None
    estimated_landed_cost: Decimal | None
    scenario_landed_total_including_vat: Decimal | None
    committed_purchase_cost: Decimal | None
    quoted_operational_cost: Decimal | None
    documented_operational_cost: Decimal | None
    documented_total_cost: Decimal | None
    estimated_gross_profit: Decimal | None
    estimated_gross_margin_pct: Decimal | None
    estimated_markup_pct: Decimal | None
    committed_gross_profit: Decimal | None
    committed_gross_margin_pct: Decimal | None
    committed_markup_pct: Decimal | None
    cost_variance: Decimal | None
    cost_variance_pct: Decimal | None
    estimate_status: CompletenessStatus
    committed_status: CompletenessStatus
    completeness: CompletenessStatus
    missing_components: tuple[str, ...]
    checks: tuple[CompletionCheck, ...]
    classifications: dict[str, str]
    cost_lines: tuple[CostLine, ...]
    purchase_currency_mismatch: bool
    cost_currency_mismatch: bool
    partial_fulfilment: bool
    cancelled: bool
    limitations: tuple[str, ...]


def _check(key: str, label: str, satisfied: bool, detail: str) -> CompletionCheck:
    return CompletionCheck(key=key, label=label, satisfied=satisfied, detail=detail)


def _component_rate(
    component: PricingComponentFact, target_currency: str
) -> tuple[Decimal | None, bool]:
    """Return ``(rate, valid)`` without ever borrowing a current market rate."""

    source = canonical_currency(component.currency)
    target = canonical_currency(target_currency)
    if source == target:
        return Decimal("1"), True
    fx = component.fx
    if fx is None:
        return None, False
    if canonical_currency(fx.base_currency) != source:
        return None, False
    if canonical_currency(fx.quote_currency) != target:
        return None, False
    if fx.rate <= ZERO:
        return None, False
    return fx.rate, True


def _convert_components(
    scenario: PricingScenarioFact, order_currency: str
) -> tuple[tuple[CostLine, ...], Decimal | None, Decimal | None, Decimal | None, bool]:
    """Convert stored components exactly once, returning expense buckets.

    A missing/invalid snapshot makes the whole estimate unavailable; a partial
    cost total would be more dangerous than an explicit gap.
    """

    lines: list[CostLine] = []
    purchase_extra = ZERO
    operational = ZERO
    vat = ZERO
    valid = True
    for component in scenario.components:
        rate, component_valid = _component_rate(component, order_currency)
        if not component_valid or rate is None:
            valid = False
            converted = None
        else:
            converted = money(component.amount * rate)
        is_expense = component.cost_type not in _NON_EXPENSE_COST_TYPES
        lines.append(
            CostLine(
                cost_type=component.cost_type,
                original_amount=money(component.amount),
                original_currency=canonical_currency(component.currency),
                converted_amount=converted,
                target_currency=canonical_currency(order_currency),
                basis=component.basis,
                verification_status=component.verification_status,
                source_reference=component.source_reference,
                fx_rate=rate,
                fx_snapshot_id=component.fx.snapshot_id if component.fx else None,
                is_expense=is_expense,
            )
        )
        if converted is None:
            continue
        if component.cost_type == "VAT_CASHFLOW":
            vat += converted
        elif component.cost_type == "PURCHASE":
            purchase_extra += converted
        else:
            operational += converted
    if not scenario.components and scenario.additional_cost_total is not None:
        # An older/incomplete scenario may not have child components. The stored
        # additional total is the only supported figure; VAT treatment is then
        # explicitly unknown and the estimate is not presented as net-of-VAT.
        operational = money(scenario.additional_cost_total)
        valid = True
    return (
        tuple(lines),
        money(purchase_extra),
        money(operational),
        money(vat),
        valid,
    )


def analyse_order(facts: OrderFacts) -> ProfitabilityResult:
    """Calculate one order's supported profitability without mixing bases."""

    currency = canonical_currency(facts.currency)
    sales_value = money(facts.order_total)
    cancelled = facts.status == SalesOrderStatus.CANCELLED.value
    missing: list[str] = []
    checks: list[CompletionCheck] = []
    limitations = (
        "Estimated gross profit is an operational landed-cost estimate, not accounting profit.",
        "Documented gross profit uses committed purchase orders and "
        "incurred/documented shipment costs only.",
        "Quoted shipment costs and the pricing scenario are never added to the documented basis.",
        "Recoverable VAT is not treated as an expense; VAT_CASHFLOW is shown separately.",
        "No currency is converted unless a stored, sourced FX snapshot supports that pair.",
    )

    checks.append(
        _check(
            "accepted_sales_order",
            "Accepted sales order",
            not cancelled,
            "Accepted order value is stored in Commerce."
            if not cancelled
            else "The order is cancelled; accepted history is preserved but "
            "not current profitability.",
        )
    )

    if cancelled:
        missing.append("CANCELLED_ORDER")
        return ProfitabilityResult(
            sales_order_id=facts.sales_order_id,
            currency=currency,
            sales_value=sales_value,
            estimated_purchase_cost=None,
            estimated_extra_purchase_cost=None,
            estimated_operational_cost=None,
            estimated_vat_cashflow=None,
            estimated_landed_cost=None,
            scenario_landed_total_including_vat=None,
            committed_purchase_cost=None,
            quoted_operational_cost=None,
            documented_operational_cost=None,
            documented_total_cost=None,
            estimated_gross_profit=None,
            estimated_gross_margin_pct=None,
            estimated_markup_pct=None,
            committed_gross_profit=None,
            committed_gross_margin_pct=None,
            committed_markup_pct=None,
            cost_variance=None,
            cost_variance_pct=None,
            estimate_status=CompletenessStatus.UNAVAILABLE,
            committed_status=CompletenessStatus.UNAVAILABLE,
            completeness=CompletenessStatus.UNAVAILABLE,
            missing_components=tuple(missing),
            checks=tuple(checks),
            classifications={
                "sales_value": ValueClass.UNAVAILABLE.value,
                "estimated_gross_profit": ValueClass.UNAVAILABLE.value,
                "committed_gross_profit": ValueClass.UNAVAILABLE.value,
                "cost_variance": ValueClass.UNAVAILABLE.value,
            },
            cost_lines=(),
            purchase_currency_mismatch=False,
            cost_currency_mismatch=False,
            partial_fulfilment=False,
            cancelled=True,
            limitations=limitations,
        )

    scenario = facts.pricing
    estimated_purchase: Decimal | None = None
    estimated_extra_purchase: Decimal | None = None
    estimated_operational: Decimal | None = None
    estimated_vat: Decimal | None = None
    estimated_landed: Decimal | None = None
    scenario_landed = scenario.landed_total if scenario is not None else None
    cost_lines: tuple[CostLine, ...] = ()
    estimate_complete = False

    if scenario is None or scenario.landed_total is None:
        missing.append("PRICING_ESTIMATE")
        checks.append(
            _check(
                "pricing_estimate",
                "Pricing estimate",
                False,
                "No completed Stage 3 landed-cost scenario is attached to the accepted quote.",
            )
        )
    elif canonical_currency(scenario.target_currency) != currency:
        missing.append("ESTIMATE_CURRENCY_MISMATCH")
        checks.append(
            _check(
                "pricing_estimate",
                "Pricing estimate",
                False,
                "The scenario targets another currency; Commerce does not "
                "convert or reinterpret it.",
            )
        )
    elif scenario.status == "INCOMPLETE" or scenario.purchase_total is None:
        missing.append("PRICING_ESTIMATE_INCOMPLETE")
        checks.append(
            _check(
                "pricing_estimate",
                "Pricing estimate",
                False,
                "The attached scenario is incomplete or has no stored purchase total.",
            )
        )
    else:
        (
            cost_lines,
            estimated_extra_purchase,
            estimated_operational,
            estimated_vat,
            estimate_valid,
        ) = _convert_components(scenario, currency)
        if not estimate_valid:
            missing.append("ESTIMATE_FX_UNAVAILABLE")
            checks.append(
                _check(
                    "pricing_estimate",
                    "Pricing estimate",
                    False,
                    "At least one scenario component lacks a valid stored FX snapshot.",
                )
            )
        else:
            extra_purchase = (
                estimated_extra_purchase
                if estimated_extra_purchase is not None
                else ZERO
            )
            operational = (
                estimated_operational if estimated_operational is not None else ZERO
            )
            estimated_purchase = money(scenario.purchase_total)
            estimated_landed = money(estimated_purchase + extra_purchase + operational)
            estimate_complete = True
            checks.append(
                _check(
                    "pricing_estimate",
                    "Pricing estimate",
                    True,
                    "A same-currency Stage 3 landed cost is stored with its "
                    "original FX assumptions.",
                )
            )

    estimated_gross_profit = (
        money(sales_value - estimated_landed)
        if estimate_complete and estimated_landed is not None
        else None
    )
    estimated_margin = (
        safe_ratio(estimated_gross_profit, sales_value, as_percent=True)
        if estimated_gross_profit is not None
        else None
    )
    estimated_markup = (
        safe_ratio(estimated_gross_profit, estimated_landed, as_percent=True)
        if estimated_gross_profit is not None and estimated_landed is not None
        else None
    )

    purchase_required = facts.fulfilment_model == "PURCHASE_RESALE"
    active_pos = tuple(po for po in facts.purchase_orders if not po.is_cancelled)
    committed_pos = tuple(po for po in active_pos if po.is_committed)
    uncommitted_pos = tuple(po for po in active_pos if not po.is_committed)
    purchase_currency_mismatch = any(
        canonical_currency(po.currency) != currency for po in committed_pos
    )
    committed_purchase: Decimal | None = None
    purchase_commitment_complete = False
    if purchase_currency_mismatch:
        missing.append("CURRENCY_MISMATCH_PURCHASE")
        checks.append(
            _check(
                "purchase_commitment",
                "Purchase commitment",
                False,
                "A committed purchase order uses another currency; no "
                "conversion was applied.",
            )
        )
    elif purchase_required and not committed_pos and not uncommitted_pos:
        missing.append("PURCHASE_COMMITMENT")
        checks.append(
            _check(
                "purchase_commitment",
                "Purchase commitment",
                False,
                "A purchase-resale order has no approved or recorded purchase order.",
            )
        )
    elif uncommitted_pos:
        committed_purchase = (
            money(sum((po.total_cost for po in committed_pos), ZERO))
            if committed_pos
            else None
        )
        missing.append("PURCHASE_COMMITMENT_INCOMPLETE")
        checks.append(
            _check(
                "purchase_commitment",
                "Purchase commitment",
                False,
                "A non-cancelled purchase order is still a draft; the "
                "committed total is incomplete.",
            )
        )
    else:
        committed_purchase = money(sum((po.total_cost for po in committed_pos), ZERO))
        purchase_commitment_complete = True
        checks.append(
            _check(
                "purchase_commitment",
                "Purchase commitment",
                True,
                "Brokerage has no required supplier purchase."
                if not purchase_required
                else "Every non-cancelled purchase order is committed in the order currency.",
            )
        )

    active_shipments = tuple(shipment for shipment in facts.shipments if shipment.is_active)
    documented_pairs = tuple(
        (shipment, cost)
        for shipment in active_shipments
        for cost in shipment.costs
        if cost.is_documented
    )
    forecast_pairs = tuple(
        (shipment, cost)
        for shipment in active_shipments
        for cost in shipment.costs
        if cost.is_forecast
    )
    cost_currency_mismatch = any(
        canonical_currency(cost.currency) != currency for _, cost in documented_pairs
    )
    documented_known = money(
        sum(
            (
                cost.amount
                for _, cost in documented_pairs
                if canonical_currency(cost.currency) == currency
            ),
            ZERO,
        )
    )
    quoted_known = money(
        sum(
            (
                cost.amount
                for _, cost in forecast_pairs
                if canonical_currency(cost.currency) == currency
            ),
            ZERO,
        )
    )
    shipments_without_documented = tuple(
        shipment
        for shipment in active_shipments
        if not any(cost.is_documented for cost in shipment.costs)
    )
    partial_fulfilment = facts.status not in _FULLY_FULFILLED_STATUSES
    documented_complete = (
        not cost_currency_mismatch
        and not shipments_without_documented
        and bool(active_shipments)
        and not partial_fulfilment
    )

    if cost_currency_mismatch:
        missing.append("CURRENCY_MISMATCH_COST")
        checks.append(
            _check(
                "operational_costs",
                "Operational costs",
                False,
                "A documented shipment cost uses another currency; no conversion was applied.",
            )
        )
    elif not active_shipments:
        missing.append("SHIPMENT_COST_MISSING")
        checks.append(
            _check(
                "operational_costs",
                "Operational costs",
                False,
                "No active shipment carries a documented operational cost.",
            )
        )
    elif shipments_without_documented:
        missing.append("DOCUMENTED_OPERATIONAL_COSTS")
        checks.append(
            _check(
                "operational_costs",
                "Operational costs",
                False,
                "An active shipment has no incurred/documented cost; quoted costs remain forecast.",
            )
        )
    else:
        checks.append(
            _check(
                "operational_costs",
                "Operational costs",
                True,
                "Every active shipment has a documented cost in the order currency.",
            )
        )

    checks.append(
        _check(
            "full_fulfilment",
            "Full fulfilment",
            not partial_fulfilment,
            "The order is fulfilled or closed."
            if not partial_fulfilment
            else "The order is not fully fulfilled; documented costs cover only current activity.",
        )
    )
    if partial_fulfilment:
        missing.append("PARTIAL_FULFILMENT")

    documented_operational: Decimal | None = (
        documented_known
        if documented_pairs and not cost_currency_mismatch
        else None
    )
    quoted_operational: Decimal | None = (
        quoted_known if forecast_pairs and not cost_currency_mismatch else None
    )
    documented_total: Decimal | None = None
    committed_complete = purchase_commitment_complete and documented_complete
    if committed_complete and committed_purchase is not None:
        documented_total = money(committed_purchase + documented_known)

    committed_gross_profit = (
        money(sales_value - documented_total) if documented_total is not None else None
    )
    committed_margin = (
        safe_ratio(committed_gross_profit, sales_value, as_percent=True)
        if committed_gross_profit is not None
        else None
    )
    committed_markup = (
        safe_ratio(committed_gross_profit, documented_total, as_percent=True)
        if committed_gross_profit is not None and documented_total is not None
        else None
    )

    if committed_complete:
        committed_status = CompletenessStatus.COMPLETE
    elif active_pos or committed_purchase is not None or documented_pairs or forecast_pairs:
        committed_status = CompletenessStatus.PARTIAL
    else:
        committed_status = CompletenessStatus.MISSING

    if estimate_complete and committed_complete:
        completeness = CompletenessStatus.COMPLETE
    elif estimate_complete or committed_status is not CompletenessStatus.MISSING:
        completeness = CompletenessStatus.PARTIAL
    else:
        completeness = CompletenessStatus.MISSING

    cost_variance: Decimal | None = None
    cost_variance_pct: Decimal | None = None
    if (
        estimate_complete
        and committed_complete
        and estimated_landed is not None
        and documented_total is not None
    ):
        cost_variance = money(documented_total - estimated_landed)
        cost_variance_pct = safe_ratio(cost_variance, estimated_landed, as_percent=True)

    classifications = {
        "sales_value": ValueClass.DOCUMENTED.value,
        "estimated_landed_cost": ValueClass.ESTIMATED.value
        if estimate_complete
        else ValueClass.UNAVAILABLE.value,
        "estimated_gross_profit": ValueClass.ESTIMATED.value
        if estimated_gross_profit is not None
        else ValueClass.UNAVAILABLE.value,
        "committed_purchase_cost": ValueClass.COMMITTED.value
        if committed_purchase is not None
        else ValueClass.UNAVAILABLE.value,
        "documented_operational_cost": ValueClass.DOCUMENTED.value
        if documented_operational is not None
        else ValueClass.UNAVAILABLE.value,
        "committed_gross_profit": ValueClass.COMMITTED.value
        if committed_gross_profit is not None
        else ValueClass.UNAVAILABLE.value,
        "cost_variance": ValueClass.ESTIMATED.value
        if cost_variance is not None
        else ValueClass.UNAVAILABLE.value,
        "finance_observed_profit": ValueClass.UNAVAILABLE.value,
        "actual_profit": ValueClass.UNAVAILABLE.value,
    }

    return ProfitabilityResult(
        sales_order_id=facts.sales_order_id,
        currency=currency,
        sales_value=sales_value,
        estimated_purchase_cost=estimated_purchase,
        estimated_extra_purchase_cost=estimated_extra_purchase,
        estimated_operational_cost=estimated_operational,
        estimated_vat_cashflow=estimated_vat,
        estimated_landed_cost=estimated_landed,
        scenario_landed_total_including_vat=scenario_landed,
        committed_purchase_cost=committed_purchase,
        quoted_operational_cost=quoted_operational,
        documented_operational_cost=documented_operational,
        documented_total_cost=documented_total,
        estimated_gross_profit=estimated_gross_profit,
        estimated_gross_margin_pct=estimated_margin,
        estimated_markup_pct=estimated_markup,
        committed_gross_profit=committed_gross_profit,
        committed_gross_margin_pct=committed_margin,
        committed_markup_pct=committed_markup,
        cost_variance=cost_variance,
        cost_variance_pct=cost_variance_pct,
        estimate_status=CompletenessStatus.COMPLETE
        if estimate_complete
        else CompletenessStatus.UNAVAILABLE
        if scenario is not None
        else CompletenessStatus.MISSING,
        committed_status=committed_status,
        completeness=completeness,
        missing_components=tuple(dict.fromkeys(missing)),
        checks=tuple(checks),
        classifications=classifications,
        cost_lines=cost_lines,
        purchase_currency_mismatch=purchase_currency_mismatch,
        cost_currency_mismatch=cost_currency_mismatch,
        partial_fulfilment=partial_fulfilment,
        cancelled=False,
        limitations=limitations,
    )


@dataclass(frozen=True, slots=True)
class MoneyTotal:
    currency: str
    amount: Decimal


def sum_by_currency(values: list[tuple[str, Decimal | None]]) -> tuple[MoneyTotal, ...]:
    """Sum only identical currencies; ``None`` is a gap, never zero."""

    buckets: dict[str, Decimal] = {}
    for currency, amount in values:
        if amount is None:
            continue
        code = canonical_currency(currency)
        buckets[code] = buckets.get(code, ZERO) + amount
    return tuple(
        MoneyTotal(currency=code, amount=money(amount)) for code, amount in sorted(buckets.items())
    )


__all__ = [
    "CALCULATION_VERSION",
    "CompletenessStatus",
    "CompletionCheck",
    "CostLine",
    "FxFact",
    "MetricKind",
    "MoneyTotal",
    "OrderFacts",
    "PricingComponentFact",
    "PricingScenarioFact",
    "ProfitabilityResult",
    "PurchaseOrderFact",
    "ShipmentCostFact",
    "ShipmentFact",
    "analyse_order",
    "money",
    "percent",
    "safe_ratio",
    "sum_by_currency",
]

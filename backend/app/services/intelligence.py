"""Stage 5E operational financial intelligence read model.

All data is loaded in one tenant-scoped transaction using bounded, bulk queries.
There is no per-order API waterfall, no Finance write and no direct Finance SQLite
access. Company-wide Finance balances are never attributed to an order.
"""

from __future__ import annotations

import contextlib
from collections import defaultdict
from dataclasses import dataclass
from datetime import UTC, date, datetime, time
from decimal import Decimal
from typing import Any
from uuid import UUID

from sqlalchemy import and_, func, select
from sqlalchemy.orm import Session, aliased

from app.core.errors import BadRequestError, NotFoundError
from app.db.engine import Database
from app.db.models import (
    Counterparty,
    Deal,
    FinanceDiscrepancy,
    FinanceReconciliationEvidence,
    FinanceReconciliationReview,
    FinanceReconciliationRun,
    FinanceSourceReference,
    FulfilmentModel,
    FxRateSnapshot,
    PricingCostComponent,
    PricingScenario,
    PurchaseOrder,
    ReconciliationStatus,
    SalesOrder,
    SalesOrderStatus,
    SalesQuote,
    SalesQuoteItem,
    Shipment,
    ShipmentCost,
    User,
)
from app.db.tenant import apply_company_context
from app.services.intelligence_calculations import (
    CALCULATION_VERSION,
    CompletenessStatus,
    CostLine,
    FxFact,
    MetricKind,
    MoneyTotal,
    OrderFacts,
    PricingComponentFact,
    PricingScenarioFact,
    ProfitabilityResult,
    PurchaseOrderFact,
    ShipmentCostFact,
    ShipmentFact,
    analyse_order,
    money,
    percent,
    safe_ratio,
    sum_by_currency,
)

MAX_ANALYSIS_ORDERS = 5000
MAX_DATE_RANGE_DAYS = 731
_ACTIVE_RECONCILIATION = frozenset({"MATCHED_EVIDENCE", "VERIFIED"})
_CANCELLED = "CANCELLED"


@dataclass(frozen=True)
class IntelligenceFilters:
    from_date: date
    to_date: date
    currency: str | None = None
    fulfilment_model: str | None = None
    order_status: str | None = None
    customer_id: UUID | None = None
    supplier_id: UUID | None = None
    order_id: UUID | None = None
    reconciliation_status: str | None = None
    completeness: str | None = None


@dataclass(frozen=True)
class PercentTotal:
    currency: str
    value: Decimal


@dataclass(frozen=True)
class MetricRecord:
    key: str
    label: str
    kind: MetricKind
    money: tuple[MoneyTotal, ...]
    percentages: tuple[PercentTotal, ...]
    percentage: Decimal | None
    count: int | None
    available: bool
    classification: str
    completeness: str
    meaning: str
    as_of: date
    data_through: date | None


@dataclass(frozen=True)
class MonthlyCommitmentRecord:
    month: str
    currency: str
    accepted_value: Decimal
    purchase_commitments: Decimal
    order_count: int


@dataclass(frozen=True)
class CostComparisonRecord:
    currency: str
    estimated_cost: Decimal
    documented_cost: Decimal
    variance: Decimal
    order_count: int


@dataclass(frozen=True)
class MarginBucketRecord:
    key: str
    label: str
    count: int


@dataclass(frozen=True)
class CategoryCountRecord:
    key: str
    count: int


@dataclass(frozen=True)
class CompletenessCountRecord:
    status: str
    count: int


@dataclass(frozen=True)
class FilterOptionsRecord:
    currencies: tuple[str, ...]
    customers: tuple[tuple[UUID, str], ...]
    suppliers: tuple[tuple[UUID, str], ...]
    order_statuses: tuple[str, ...]
    fulfilment_models: tuple[str, ...]
    reconciliation_statuses: tuple[str, ...]
    completeness_statuses: tuple[str, ...]


@dataclass(frozen=True)
class AnalyzedOrder:
    facts: OrderFacts
    result: ProfitabilityResult

    @property
    def active(self) -> bool:
        return self.facts.status != _CANCELLED


@dataclass(frozen=True)
class SummaryRecord:
    as_of: date
    data_through: date | None
    calculation_version: str
    order_count: int
    active_order_count: int
    cancelled_order_count: int
    metrics: tuple[MetricRecord, ...]
    monthly_commitments: tuple[MonthlyCommitmentRecord, ...]
    cost_comparison: tuple[CostComparisonRecord, ...]
    margin_distribution: tuple[MarginBucketRecord, ...]
    discrepancy_categories: tuple[CategoryCountRecord, ...]
    completeness: tuple[CompletenessCountRecord, ...]
    review_orders: tuple[AnalyzedOrder, ...]
    filter_options: FilterOptionsRecord


@dataclass(frozen=True)
class OrderPage:
    items: tuple[AnalyzedOrder, ...]
    total: int
    limit: int
    offset: int


@dataclass(frozen=True)
class CostVariancePage:
    items: tuple[AnalyzedOrder, ...]
    total: int
    excluded_order_count: int
    limit: int
    offset: int


@dataclass(frozen=True)
class CoverageRecord:
    as_of: date
    data_through: date | None
    order_count: int
    active_order_count: int
    estimate: tuple[CompletenessCountRecord, ...]
    committed: tuple[CompletenessCountRecord, ...]
    reconciliation: tuple[CategoryCountRecord, ...]
    missing_components: tuple[CategoryCountRecord, ...]


@dataclass(frozen=True)
class ExceptionRecord:
    id: UUID
    run_id: UUID
    sales_order_id: UUID
    order_number: str
    customer_name: str
    currency: str
    order_status: str
    code: str
    severity: str
    status: str
    title: str
    detail: str
    expected: dict[str, Any]
    observed: dict[str, Any]
    source_entity_type: str | None
    source_entity_id: UUID | None
    finance_source_reference: str | None
    reviewer_name: str | None
    resolution_notes: str | None
    resolved_at: datetime | None
    created_at: datetime
    updated_at: datetime
    version: int


@dataclass(frozen=True)
class ExceptionPage:
    items: tuple[ExceptionRecord, ...]
    total: int
    limit: int
    offset: int


@dataclass(frozen=True)
class QuoteLineRecord:
    product_id: UUID
    description: str
    quantity: Decimal
    unit: str
    unit_price: Decimal
    line_total: Decimal


@dataclass(frozen=True)
class QuoteDetailRecord:
    quote_id: UUID
    quote_number: str
    revision: int
    status: str
    currency: str
    incoterm: str
    named_delivery_place: str
    payment_terms: str
    valid_until: date
    approved_at: datetime | None
    lines: tuple[QuoteLineRecord, ...]


@dataclass(frozen=True)
class RunTimelineRecord:
    run_id: UUID
    status: str
    as_of: date
    data_through: date | None
    currency: str
    created_at: datetime
    evidence_count: int
    open_discrepancy_count: int
    latest_decision: str | None
    latest_review_at: datetime | None


@dataclass(frozen=True)
class EvidenceRecord:
    id: UUID
    run_id: UUID
    source_entity_type: str
    source_entity_id: UUID
    finance_source_type: str
    finance_source_reference: str
    currency: str
    amount: Decimal
    as_of: date
    data_through: date | None
    verification_status: str
    created_at: datetime
    verified_at: datetime | None


@dataclass(frozen=True)
class OrderDetailRecord:
    analyzed: AnalyzedOrder
    quote: QuoteDetailRecord
    purchase_orders: tuple[PurchaseOrderFact, ...]
    shipments: tuple[ShipmentFact, ...]
    cost_lines: tuple[CostLine, ...]
    fx_assumptions: tuple[FxFact, ...]
    runs: tuple[RunTimelineRecord, ...]
    evidence: tuple[EvidenceRecord, ...]
    discrepancies: tuple[ExceptionRecord, ...]


def _utc_start(value: date) -> datetime:
    return datetime.combine(value, time.min, tzinfo=UTC)


def _utc_end(value: date) -> datetime:
    return datetime.combine(value, time.max, tzinfo=UTC)


def _decimal(value: Any) -> Decimal | None:
    if value is None:
        return None
    try:
        return Decimal(str(value))
    except (ArithmeticError, TypeError, ValueError):
        return None


def _fx_fact(row: FxRateSnapshot) -> FxFact:
    return FxFact(
        snapshot_id=row.id,
        base_currency=row.base_currency,
        quote_currency=row.quote_currency,
        rate=row.rate,
        effective_at=row.effective_at,
        source=row.source,
    )


def _scenario_totals(scenario: PricingScenario) -> dict[str, Any]:
    raw = scenario.calculated_results.get("totals")
    return raw if isinstance(raw, dict) else {}


def _scenario_inputs(scenario: PricingScenario) -> dict[str, Any]:
    return scenario.pricing_inputs if isinstance(scenario.pricing_inputs, dict) else {}


def _load_scenarios(
    session: Session, *, company_id: UUID, scenario_ids: list[UUID]
) -> dict[UUID, PricingScenarioFact]:
    if not scenario_ids:
        return {}
    scenario_rows = session.execute(
        select(PricingScenario).where(
            PricingScenario.company_id == company_id,
            PricingScenario.id.in_(scenario_ids),
        )
    ).scalars()
    scenarios = {row.id: row for row in scenario_rows}
    component_rows = tuple(
        session.execute(
            select(PricingCostComponent)
            .where(
                PricingCostComponent.company_id == company_id,
                PricingCostComponent.scenario_id.in_(scenario_ids),
            )
            .order_by(PricingCostComponent.created_at, PricingCostComponent.id)
        ).scalars()
    )
    fx_ids = {row.fx_rate_snapshot_id for row in component_rows if row.fx_rate_snapshot_id}
    for scenario in scenarios.values():
        value = _scenario_inputs(scenario).get("fx_snapshot_id")
        if isinstance(value, str):
            with contextlib.suppress(ValueError):
                fx_ids.add(UUID(value))
    fx_map: dict[UUID, FxFact] = {}
    if fx_ids:
        fx_rows = session.execute(
            select(FxRateSnapshot).where(
                FxRateSnapshot.company_id == company_id,
                FxRateSnapshot.id.in_(fx_ids),
            )
        ).scalars()
        fx_map = {row.id: _fx_fact(row) for row in fx_rows}
    components_by_scenario: dict[UUID, list[PricingComponentFact]] = defaultdict(list)
    for row in component_rows:
        components_by_scenario[row.scenario_id].append(
            PricingComponentFact(
                component_id=row.id,
                cost_type=row.cost_type,
                amount=row.amount,
                currency=row.currency,
                basis=row.basis,
                verification_status=row.verification_status,
                source_reference=row.source_reference,
                product_id=row.product_id,
                fx=fx_map.get(row.fx_rate_snapshot_id)
                if row.fx_rate_snapshot_id
                else None,
            )
        )
    result: dict[UUID, PricingScenarioFact] = {}
    for scenario_id, scenario in scenarios.items():
        totals = _scenario_totals(scenario)
        inputs = _scenario_inputs(scenario)
        raw_fx_id = inputs.get("fx_snapshot_id")
        fx_id: UUID | None = None
        if isinstance(raw_fx_id, str):
            try:
                fx_id = UUID(raw_fx_id)
            except ValueError:
                fx_id = None
        result[scenario_id] = PricingScenarioFact(
            scenario_id=scenario.id,
            status=scenario.status,
            calculation_version=scenario.calculation_version,
            quote_currency=str(inputs.get("quote_currency") or scenario.target_currency),
            target_currency=scenario.target_currency,
            purchase_total=_decimal(totals.get("purchase_total")),
            additional_cost_total=_decimal(totals.get("additional_cost_total")),
            landed_total=_decimal(totals.get("landed_total")),
            sales_total=_decimal(totals.get("sales_total")),
            fx_rate=_decimal(inputs.get("fx_rate")),
            fx=fx_map.get(fx_id) if fx_id else None,
            components=tuple(components_by_scenario.get(scenario.id, ())),
        )
    return result


def _load_order_facts(
    session: Session,
    *,
    company_id: UUID,
    filters: IntelligenceFilters,
) -> tuple[OrderFacts, ...]:
    conditions = [
        SalesOrder.company_id == company_id,
        SalesOrder.confirmed_at >= _utc_start(filters.from_date),
        SalesOrder.confirmed_at <= _utc_end(filters.to_date),
    ]
    if filters.currency:
        conditions.append(SalesOrder.currency == filters.currency)
    if filters.fulfilment_model:
        conditions.append(SalesOrder.fulfilment_model == filters.fulfilment_model)
    if filters.order_status:
        conditions.append(SalesOrder.status == filters.order_status)
    if filters.customer_id:
        conditions.append(SalesOrder.customer_id == filters.customer_id)
    if filters.order_id:
        conditions.append(SalesOrder.id == filters.order_id)
    if filters.supplier_id:
        conditions.append(
            SalesOrder.id.in_(
                select(PurchaseOrder.sales_order_id).where(
                    PurchaseOrder.company_id == company_id,
                    PurchaseOrder.supplier_id == filters.supplier_id,
                )
            )
        )
    rows = session.execute(
        select(
            SalesOrder,
            Counterparty.name.label("customer_name"),
            Deal.reference.label("deal_reference"),
            SalesQuote.quote_number,
            SalesQuote.scenario_id,
            PricingScenario,
        )
        .join(
            Counterparty,
            and_(
                Counterparty.id == SalesOrder.customer_id,
                Counterparty.company_id == SalesOrder.company_id,
            ),
        )
        .outerjoin(
            Deal,
            and_(Deal.id == SalesOrder.deal_id, Deal.company_id == SalesOrder.company_id),
        )
        .join(
            SalesQuote,
            and_(
                SalesQuote.id == SalesOrder.sales_quote_id,
                SalesQuote.company_id == SalesOrder.company_id,
            ),
        )
        .join(
            PricingScenario,
            and_(
                PricingScenario.id == SalesQuote.scenario_id,
                PricingScenario.company_id == SalesQuote.company_id,
            ),
        )
        .where(*conditions)
        .order_by(SalesOrder.confirmed_at.desc(), SalesOrder.id.desc())
        .limit(MAX_ANALYSIS_ORDERS + 1)
    ).all()
    if len(rows) > MAX_ANALYSIS_ORDERS:
        raise BadRequestError(
            f"The selected analysis contains more than {MAX_ANALYSIS_ORDERS} orders. "
            "Narrow the date range or filters."
        )
    if not rows:
        return ()

    order_ids = [row[0].id for row in rows]
    scenario_ids = list({row.scenario_id for row in rows})
    scenarios = _load_scenarios(session, company_id=company_id, scenario_ids=scenario_ids)

    po_rows = session.execute(
        select(PurchaseOrder, Counterparty.name.label("supplier_name"))
        .outerjoin(
            Counterparty,
            and_(
                Counterparty.id == PurchaseOrder.supplier_id,
                Counterparty.company_id == PurchaseOrder.company_id,
            ),
        )
        .where(
            PurchaseOrder.company_id == company_id,
            PurchaseOrder.sales_order_id.in_(order_ids),
        )
        .order_by(PurchaseOrder.created_at, PurchaseOrder.id)
    ).all()
    purchase_orders: dict[UUID, list[PurchaseOrderFact]] = defaultdict(list)
    for purchase_order, supplier_name in po_rows:
        purchase_orders[purchase_order.sales_order_id].append(
            PurchaseOrderFact(
                purchase_order_id=purchase_order.id,
                po_number=purchase_order.po_number,
                status=purchase_order.status,
                currency=purchase_order.currency,
                total_cost=purchase_order.total_cost,
                supplier_id=purchase_order.supplier_id,
                supplier_name=str(supplier_name) if supplier_name else None,
            )
        )

    shipment_rows = tuple(
        session.execute(
            select(Shipment)
            .where(
                Shipment.company_id == company_id,
                Shipment.sales_order_id.in_(order_ids),
            )
            .order_by(Shipment.created_at, Shipment.id)
        ).scalars()
    )
    shipment_ids = [row.id for row in shipment_rows]
    costs_by_shipment: dict[UUID, list[ShipmentCostFact]] = defaultdict(list)
    if shipment_ids:
        cost_rows = session.execute(
            select(ShipmentCost)
            .where(
                ShipmentCost.company_id == company_id,
                ShipmentCost.shipment_id.in_(shipment_ids),
            )
            .order_by(ShipmentCost.recorded_at, ShipmentCost.id)
        ).scalars()
        for cost in cost_rows:
            costs_by_shipment[cost.shipment_id].append(
                ShipmentCostFact(
                    cost_id=cost.id,
                    cost_type=cost.cost_type,
                    stage=cost.stage,
                    currency=cost.currency,
                    amount=cost.amount,
                    reference=cost.reference,
                )
            )
    shipments_by_order: dict[UUID, list[ShipmentFact]] = defaultdict(list)
    for shipment in shipment_rows:
        shipments_by_order[shipment.sales_order_id].append(
            ShipmentFact(
                shipment_id=shipment.id,
                shipment_number=shipment.shipment_number,
                status=shipment.status,
                costs=tuple(costs_by_shipment.get(shipment.id, ())),
            )
        )

    ranked = (
        select(
            FinanceReconciliationRun.sales_order_id,
            FinanceReconciliationRun.id,
            FinanceReconciliationRun.status,
            FinanceReconciliationRun.created_at,
            FinanceReconciliationRun.data_through,
            func.row_number()
            .over(
                partition_by=FinanceReconciliationRun.sales_order_id,
                order_by=(
                    FinanceReconciliationRun.created_at.desc(),
                    FinanceReconciliationRun.id.desc(),
                ),
            )
            .label("row_number"),
        )
        .where(
            FinanceReconciliationRun.company_id == company_id,
            FinanceReconciliationRun.sales_order_id.in_(order_ids),
        )
        .subquery()
    )
    latest_runs = {
        row.sales_order_id: row
        for row in session.execute(select(ranked).where(ranked.c.row_number == 1)).all()
    }
    run_counts = {
        row[0]: int(row[1])
        for row in session.execute(
            select(
                FinanceReconciliationRun.sales_order_id,
                func.count(FinanceReconciliationRun.id),
            )
            .where(
                FinanceReconciliationRun.company_id == company_id,
                FinanceReconciliationRun.sales_order_id.in_(order_ids),
            )
            .group_by(FinanceReconciliationRun.sales_order_id)
        ).all()
    }
    open_counts = {
        row[0]: (int(row[1]), int(row[2]))
        for row in session.execute(
            select(
                FinanceReconciliationRun.sales_order_id,
                func.count(FinanceDiscrepancy.id).filter(
                    FinanceDiscrepancy.status == "OPEN"
                ),
                func.count(FinanceDiscrepancy.id).filter(
                    and_(
                        FinanceDiscrepancy.status == "OPEN",
                        FinanceDiscrepancy.severity == "BLOCKING",
                    )
                ),
            )
            .join(
                FinanceDiscrepancy,
                and_(
                    FinanceDiscrepancy.run_id == FinanceReconciliationRun.id,
                    FinanceDiscrepancy.company_id == FinanceReconciliationRun.company_id,
                ),
            )
            .where(
                FinanceReconciliationRun.company_id == company_id,
                FinanceReconciliationRun.sales_order_id.in_(order_ids),
            )
            .group_by(FinanceReconciliationRun.sales_order_id)
        ).all()
    }

    facts: list[OrderFacts] = []
    for order, customer_name, deal_reference, quote_number, scenario_id, _ in rows:
        latest = latest_runs.get(order.id)
        open_count, blocking_count = open_counts.get(order.id, (0, 0))
        facts.append(
            OrderFacts(
                sales_order_id=order.id,
                order_number=order.order_number,
                customer_id=order.customer_id,
                customer_name=str(customer_name),
                status=order.status,
                fulfilment_model=order.fulfilment_model,
                currency=order.currency,
                order_total=order.order_total,
                confirmed_at=order.confirmed_at,
                expected_delivery_date=order.expected_delivery_date,
                deal_id=order.deal_id,
                deal_reference=str(deal_reference) if deal_reference else None,
                sales_quote_id=order.sales_quote_id,
                sales_quote_number=str(quote_number),
                pricing=scenarios.get(scenario_id),
                purchase_orders=tuple(purchase_orders.get(order.id, ())),
                shipments=tuple(shipments_by_order.get(order.id, ())),
                reconciliation_status=latest.status if latest else None,
                latest_run_id=latest.id if latest else None,
                latest_run_at=latest.created_at if latest else None,
                data_through=latest.data_through if latest else None,
                open_discrepancy_count=open_count,
                blocking_discrepancy_count=blocking_count,
                run_count=run_counts.get(order.id, 0),
            )
        )
    return tuple(facts)


def _validate_filters(filters: IntelligenceFilters) -> None:
    if filters.from_date > filters.to_date:
        raise BadRequestError("'from' must not be later than 'to'.")
    if (filters.to_date - filters.from_date).days + 1 > MAX_DATE_RANGE_DAYS:
        raise BadRequestError(
            f"The analysis range cannot exceed {MAX_DATE_RANGE_DAYS} days. "
            "Narrow the date range."
        )
    if filters.reconciliation_status and filters.reconciliation_status not in {
        "NONE",
        *(status.value for status in ReconciliationStatus),
    }:
        raise BadRequestError("Unknown reconciliation status filter.")
    if filters.completeness and filters.completeness not in {
        status.value for status in CompletenessStatus
    }:
        raise BadRequestError("Unknown completeness filter.")


def _post_filter(
    items: tuple[AnalyzedOrder, ...], filters: IntelligenceFilters
) -> tuple[AnalyzedOrder, ...]:
    selected = items
    if filters.reconciliation_status == "NONE":
        selected = tuple(item for item in selected if item.facts.latest_run_id is None)
    elif filters.reconciliation_status:
        selected = tuple(
            item
            for item in selected
            if item.facts.reconciliation_status == filters.reconciliation_status
        )
    if filters.completeness:
        selected = tuple(
            item
            for item in selected
            if item.result.completeness.value == filters.completeness
        )
    return selected


def _metric(
    *,
    key: str,
    label: str,
    kind: MetricKind,
    meaning: str,
    as_of: date,
    data_through: date | None,
    classification: str,
    completeness: str,
    money_values: tuple[MoneyTotal, ...] = (),
    percentages: tuple[PercentTotal, ...] = (),
    percentage: Decimal | None = None,
    count: int | None = None,
) -> MetricRecord:
    available = (
        bool(money_values)
        or bool(percentages)
        or percentage is not None
        or count is not None
    )
    return MetricRecord(
        key=key,
        label=label,
        kind=kind,
        money=money_values,
        percentages=percentages,
        percentage=percentage,
        count=count,
        available=available,
        classification=classification,
        completeness=completeness,
        meaning=meaning,
        as_of=as_of,
        data_through=data_through,
    )


def _count_statuses(statuses: list[str]) -> tuple[CompletenessCountRecord, ...]:
    counts: dict[str, int] = defaultdict(int)
    for status in statuses:
        counts[status] += 1
    return tuple(
        CompletenessCountRecord(status=status, count=counts.get(status, 0))
        for status in CompletenessStatus
    )


def _load_filter_options(session: Session, *, company_id: UUID) -> FilterOptionsRecord:
    currencies = tuple(
        session.execute(
            select(SalesOrder.currency)
            .where(SalesOrder.company_id == company_id)
            .distinct()
            .order_by(SalesOrder.currency)
        ).scalars()
    )
    customers = tuple(
        (row.id, row.name)
        for row in session.execute(
            select(Counterparty.id, Counterparty.name)
            .where(
                Counterparty.company_id == company_id,
                Counterparty.type == "buyer",
            )
            .order_by(Counterparty.name)
            .limit(200)
        ).all()
    )
    suppliers = tuple(
        (row.id, row.name)
        for row in session.execute(
            select(Counterparty.id, Counterparty.name)
            .where(
                Counterparty.company_id == company_id,
                Counterparty.type == "supplier",
            )
            .order_by(Counterparty.name)
            .limit(200)
        ).all()
    )
    return FilterOptionsRecord(
        currencies=currencies,
        customers=customers,
        suppliers=suppliers,
        order_statuses=tuple(status.value for status in SalesOrderStatus),
        fulfilment_models=tuple(model.value for model in FulfilmentModel),
        reconciliation_statuses=(
            "NONE",
            *(status.value for status in ReconciliationStatus),
        ),
        completeness_statuses=tuple(status.value for status in CompletenessStatus),
    )


def _detail_filters(sales_order_id: UUID) -> IntelligenceFilters:
    return IntelligenceFilters(
        from_date=date(2000, 1, 1),
        to_date=date(2100, 1, 1),
        order_id=sales_order_id,
    )


def _counts_by_run(
    session: Session,
    *,
    company_id: UUID,
    run_ids: list[UUID],
    model: Any,
) -> dict[UUID, int]:
    if not run_ids:
        return {}
    return {
        row[0]: int(row[1])
        for row in session.execute(
            select(model.run_id, func.count(model.id))
            .where(model.company_id == company_id, model.run_id.in_(run_ids))
            .group_by(model.run_id)
        ).all()
    }


def _discrepancy_counts_by_run(
    session: Session, *, company_id: UUID, run_ids: list[UUID]
) -> dict[UUID, int]:
    if not run_ids:
        return {}
    return {
        row[0]: int(row[1])
        for row in session.execute(
            select(FinanceDiscrepancy.run_id, func.count(FinanceDiscrepancy.id))
            .where(
                FinanceDiscrepancy.company_id == company_id,
                FinanceDiscrepancy.run_id.in_(run_ids),
                FinanceDiscrepancy.status == "OPEN",
            )
            .group_by(FinanceDiscrepancy.run_id)
        ).all()
    }


def _fx_assumptions(facts: OrderFacts) -> tuple[FxFact, ...]:
    if facts.pricing is None:
        return ()
    snapshots: dict[UUID, FxFact] = {}
    if facts.pricing.fx is not None:
        snapshots[facts.pricing.fx.snapshot_id] = facts.pricing.fx
    for component in facts.pricing.components:
        if component.fx is not None:
            snapshots[component.fx.snapshot_id] = component.fx
    return tuple(snapshots.values())


class IntelligenceService:
    """Read-only operational financial intelligence for one active company."""

    def __init__(self, database: Database) -> None:
        self._database = database

    @staticmethod
    def _analyze(
        session: Session,
        *,
        company_id: UUID,
        filters: IntelligenceFilters,
    ) -> tuple[AnalyzedOrder, ...]:
        facts = _load_order_facts(session, company_id=company_id, filters=filters)
        items = tuple(
            AnalyzedOrder(facts=fact, result=analyse_order(fact)) for fact in facts
        )
        return _post_filter(items, filters)

    def summary(self, *, company_id: UUID, filters: IntelligenceFilters) -> SummaryRecord:
        _validate_filters(filters)
        with self._database.transaction() as session:
            apply_company_context(session, company_id)
            items = self._analyze(session, company_id=company_id, filters=filters)
            filter_options = _load_filter_options(session, company_id=company_id)
            order_ids = [item.facts.sales_order_id for item in items]
            category_rows: tuple[Any, ...] = ()
            if order_ids:
                category_rows = tuple(
                    session.execute(
                        select(
                            FinanceDiscrepancy.code,
                            func.count(FinanceDiscrepancy.id),
                        )
                        .join(
                            FinanceReconciliationRun,
                            and_(
                                FinanceReconciliationRun.id == FinanceDiscrepancy.run_id,
                                FinanceReconciliationRun.company_id
                                == FinanceDiscrepancy.company_id,
                            ),
                        )
                        .where(
                            FinanceDiscrepancy.company_id == company_id,
                            FinanceDiscrepancy.status == "OPEN",
                            FinanceReconciliationRun.sales_order_id.in_(order_ids),
                        )
                        .group_by(FinanceDiscrepancy.code)
                        .order_by(FinanceDiscrepancy.code)
                    ).all()
                )
            return self._build_summary(
                items,
                filters=filters,
                filter_options=filter_options,
                category_rows=category_rows,
            )

    @staticmethod
    def _build_summary(
        items: tuple[AnalyzedOrder, ...],
        *,
        filters: IntelligenceFilters,
        filter_options: FilterOptionsRecord,
        category_rows: tuple[Any, ...],
    ) -> SummaryRecord:
        active = tuple(item for item in items if item.active)
        cancelled = len(items) - len(active)
        as_of = filters.to_date
        data_dates = [
            item.facts.data_through
            for item in active
            if item.facts.data_through is not None
        ]
        data_through = max(data_dates) if data_dates else None
        accepted = sum_by_currency(
            [(item.facts.currency, item.result.sales_value) for item in active]
        )
        purchase = sum_by_currency(
            [
                (po.currency, po.total_cost)
                for item in active
                for po in item.facts.purchase_orders
                if po.is_committed and not po.is_cancelled
            ]
        )
        estimated_profit = sum_by_currency(
            [
                (item.result.currency, item.result.estimated_gross_profit)
                for item in active
            ]
        )
        estimated_sales: dict[str, Decimal] = defaultdict(lambda: Decimal("0"))
        estimated_profit_by_currency: dict[str, Decimal] = defaultdict(
            lambda: Decimal("0")
        )
        committed_sales: dict[str, Decimal] = defaultdict(lambda: Decimal("0"))
        committed_profit_by_currency: dict[str, Decimal] = defaultdict(
            lambda: Decimal("0")
        )
        for item in active:
            result = item.result
            if result.estimated_gross_profit is not None:
                estimated_sales[result.currency] += result.sales_value
                estimated_profit_by_currency[result.currency] += (
                    result.estimated_gross_profit
                )
            if result.committed_gross_profit is not None:
                committed_sales[result.currency] += result.sales_value
                committed_profit_by_currency[result.currency] += (
                    result.committed_gross_profit
                )
        estimated_margins = tuple(
            PercentTotal(
                currency=code,
                value=percent(
                    safe_ratio(
                        estimated_profit_by_currency[code],
                        estimated_sales[code],
                        as_percent=True,
                    )
                    or Decimal("0")
                ),
            )
            for code in sorted(estimated_sales)
            if estimated_sales[code] > 0
        )
        committed_margins = tuple(
            PercentTotal(
                currency=code,
                value=percent(
                    safe_ratio(
                        committed_profit_by_currency[code],
                        committed_sales[code],
                        as_percent=True,
                    )
                    or Decimal("0")
                ),
            )
            for code in sorted(committed_sales)
            if committed_sales[code] > 0
        )
        committed_profit = sum_by_currency(
            [
                (item.result.currency, item.result.committed_gross_profit)
                for item in active
            ]
        )
        recorded = sum_by_currency(
            [
                (item.result.currency, item.result.documented_operational_cost)
                for item in active
            ]
        )
        covered = sum(
            1
            for item in active
            if item.facts.reconciliation_status in _ACTIVE_RECONCILIATION
        )
        coverage_pct = (
            percent(Decimal(covered) * Decimal(100) / Decimal(len(active)))
            if active
            else None
        )
        open_total = sum(item.facts.open_discrepancy_count for item in items)
        blocking_total = sum(item.facts.blocking_discrepancy_count for item in items)
        estimate_complete = sum(
            1
            for item in active
            if item.result.estimate_status is CompletenessStatus.COMPLETE
        )
        required_purchase = [
            item
            for item in active
            if item.facts.fulfilment_model == "PURCHASE_RESALE"
        ]
        purchase_complete = all(
            any(po.is_committed for po in item.facts.purchase_orders)
            for item in required_purchase
        )
        documented_complete = all(
            item.result.documented_operational_cost is not None for item in active
        )
        money_kind = MetricKind.MONEY
        metrics = (
            _metric(
                key="accepted_sales_order_value",
                label="Accepted sales order value",
                kind=money_kind,
                meaning="Sum of non-cancelled accepted sales orders, grouped by order currency.",
                as_of=as_of,
                data_through=data_through,
                classification="DOCUMENTED",
                completeness="COMPLETE" if active else "MISSING",
                money_values=accepted,
            ),
            _metric(
                key="purchase_commitments",
                label="Purchase commitments",
                kind=money_kind,
                meaning="Committed supplier purchase orders grouped by their own "
                "currency; drafts and cancellations excluded.",
                as_of=as_of,
                data_through=data_through,
                classification="COMMITTED",
                completeness="COMPLETE"
                if active and purchase_complete
                else "PARTIAL"
                if active
                else "MISSING",
                money_values=purchase,
            ),
            _metric(
                key="estimated_gross_profit",
                label="Estimated gross profit",
                kind=money_kind,
                meaning="Accepted value minus same-currency Stage 3 landed cost, "
                "excluding VAT cashflow.",
                as_of=as_of,
                data_through=data_through,
                classification="ESTIMATED",
                completeness="COMPLETE"
                if active and estimate_complete == len(active)
                else "PARTIAL"
                if estimate_complete
                else "MISSING",
                money_values=estimated_profit,
            ),
            _metric(
                key="estimated_gross_margin",
                label="Estimated gross margin",
                kind=MetricKind.PERCENT,
                meaning="Estimated gross profit divided by accepted sales value "
                "per currency; not markup.",
                as_of=as_of,
                data_through=data_through,
                classification="ESTIMATED",
                completeness="COMPLETE"
                if active and estimate_complete == len(active)
                else "PARTIAL"
                if estimate_complete
                else "MISSING",
                percentages=estimated_margins,
            ),
            _metric(
                key="recorded_operational_costs",
                label="Recorded operational costs",
                kind=money_kind,
                meaning="Incurred/documented shipment costs only, grouped by order "
                "currency; quoted costs excluded.",
                as_of=as_of,
                data_through=data_through,
                classification="DOCUMENTED",
                completeness="COMPLETE"
                if active and documented_complete
                else "PARTIAL"
                if active
                else "MISSING",
                money_values=recorded,
            ),
            _metric(
                key="reconciliation_coverage",
                label="Reconciliation coverage",
                kind=MetricKind.PERCENT,
                meaning="Share of active orders whose latest run is MATCHED_EVIDENCE or VERIFIED.",
                as_of=as_of,
                data_through=data_through,
                classification="VERIFIED",
                completeness="COMPLETE" if active else "MISSING",
                count=covered,
                percentage=coverage_pct,
            ),
            _metric(
                key="open_discrepancies",
                label="Open discrepancies",
                kind=MetricKind.COUNT,
                meaning=f"Open Stage 5D findings in the filtered orders; "
                f"{blocking_total} blocking.",
                as_of=as_of,
                data_through=data_through,
                classification="DOCUMENTED",
                completeness="COMPLETE",
                count=open_total,
            ),
            _metric(
                key="committed_gross_profit",
                label="Committed gross profit",
                kind=money_kind,
                meaning="Accepted value minus committed purchases and documented "
                "shipment costs; only complete cases.",
                as_of=as_of,
                data_through=data_through,
                classification="COMMITTED",
                completeness="COMPLETE"
                if active and committed_profit
                else "PARTIAL"
                if active
                else "MISSING",
                money_values=committed_profit,
                percentages=committed_margins,
            ),
        )

        monthly_accepted: dict[tuple[str, str], Decimal] = defaultdict(
            lambda: Decimal("0")
        )
        monthly_committed: dict[tuple[str, str], Decimal] = defaultdict(
            lambda: Decimal("0")
        )
        monthly_orders: dict[tuple[str, str], int] = defaultdict(int)
        for item in active:
            month = item.facts.confirmed_at.strftime("%Y-%m")
            key = (month, item.facts.currency)
            monthly_accepted[key] += item.result.sales_value
            monthly_orders[key] += 1
            monthly_committed[key] += sum(
                (
                    po.total_cost
                    for po in item.facts.purchase_orders
                    if po.is_committed and po.currency == item.facts.currency
                ),
                Decimal("0"),
            )
        monthly = tuple(
            MonthlyCommitmentRecord(
                month=month,
                currency=currency,
                accepted_value=money(monthly_accepted[(month, currency)]),
                purchase_commitments=money(
                    monthly_committed[(month, currency)]
                ),
                order_count=monthly_orders[(month, currency)],
            )
            for month, currency in sorted(monthly_accepted)
        )

        comparison: dict[str, list[Decimal]] = defaultdict(
            lambda: [Decimal("0"), Decimal("0"), Decimal("0"), Decimal("0")]
        )
        for item in active:
            result = item.result
            if (
                result.cost_variance is not None
                and result.estimated_landed_cost is not None
                and result.documented_total_cost is not None
            ):
                row = comparison[result.currency]
                row[0] += result.estimated_landed_cost
                row[1] += result.documented_total_cost
                row[2] += result.cost_variance
                row[3] += 1
        cost_comparison = tuple(
            CostComparisonRecord(
                currency=currency,
                estimated_cost=money(values[0]),
                documented_cost=money(values[1]),
                variance=money(values[2]),
                order_count=int(values[3]),
            )
            for currency, values in sorted(comparison.items())
        )

        buckets = {
            "LOSS": 0,
            "0-9.99": 0,
            "10-19.99": 0,
            "20-29.99": 0,
            "30+": 0,
        }
        for item in active:
            value = item.result.estimated_gross_margin_pct
            if value is None:
                continue
            if value < 0:
                buckets["LOSS"] += 1
            elif value < 10:
                buckets["0-9.99"] += 1
            elif value < 20:
                buckets["10-19.99"] += 1
            elif value < 30:
                buckets["20-29.99"] += 1
            else:
                buckets["30+"] += 1
        margin_distribution = tuple(
            MarginBucketRecord(key=key, label=key, count=count)
            for key, count in buckets.items()
        )

        def review_rank(item: AnalyzedOrder) -> tuple[int, float]:
            if item.facts.blocking_discrepancy_count > 0:
                rank = 0
            elif item.result.completeness is CompletenessStatus.UNAVAILABLE:
                rank = 1
            elif item.result.completeness is CompletenessStatus.MISSING:
                rank = 2
            elif item.facts.open_discrepancy_count > 0:
                rank = 3
            else:
                rank = 4
            return rank, -item.facts.confirmed_at.timestamp()

        review_candidates = [
            item
            for item in active
            if item.facts.blocking_discrepancy_count > 0
            or item.facts.open_discrepancy_count > 0
            or item.result.completeness
            in {CompletenessStatus.PARTIAL, CompletenessStatus.MISSING}
        ]
        review_orders = tuple(sorted(review_candidates, key=review_rank)[:8])

        return SummaryRecord(
            as_of=as_of,
            data_through=data_through,
            calculation_version=CALCULATION_VERSION,
            order_count=len(items),
            active_order_count=len(active),
            cancelled_order_count=cancelled,
            metrics=metrics,
            monthly_commitments=monthly,
            cost_comparison=cost_comparison,
            margin_distribution=margin_distribution,
            discrepancy_categories=tuple(
                CategoryCountRecord(key=str(row[0]), count=int(row[1]))
                for row in category_rows
            ),
            completeness=_count_statuses(
                [item.result.completeness.value for item in items]
            ),
            review_orders=review_orders,
            filter_options=filter_options,
        )

    def orders(
        self,
        *,
        company_id: UUID,
        filters: IntelligenceFilters,
        limit: int,
        offset: int,
    ) -> OrderPage:
        _validate_filters(filters)
        with self._database.transaction() as session:
            apply_company_context(session, company_id)
            items = self._analyze(session, company_id=company_id, filters=filters)
            total = len(items)
            return OrderPage(
                items=items[offset : offset + limit],
                total=total,
                limit=limit,
                offset=offset,
            )

    def cost_variance(
        self,
        *,
        company_id: UUID,
        filters: IntelligenceFilters,
        limit: int,
        offset: int,
    ) -> CostVariancePage:
        _validate_filters(filters)
        with self._database.transaction() as session:
            apply_company_context(session, company_id)
            items = self._analyze(session, company_id=company_id, filters=filters)
            valued = tuple(
                item for item in items if item.result.cost_variance is not None
            )
            return CostVariancePage(
                items=valued[offset : offset + limit],
                total=len(valued),
                excluded_order_count=len(items) - len(valued),
                limit=limit,
                offset=offset,
            )

    def coverage(self, *, company_id: UUID, filters: IntelligenceFilters) -> CoverageRecord:
        _validate_filters(filters)
        with self._database.transaction() as session:
            apply_company_context(session, company_id)
            items = self._analyze(session, company_id=company_id, filters=filters)
            active = tuple(item for item in items if item.active)
            data_dates = [
                item.facts.data_through
                for item in active
                if item.facts.data_through is not None
            ]
            reconciliation_counts: dict[str, int] = defaultdict(int)
            for item in items:
                reconciliation_counts[item.facts.reconciliation_status or "NONE"] += 1
            missing_counts: dict[str, int] = defaultdict(int)
            for item in active:
                for key in item.result.missing_components:
                    missing_counts[key] += 1
            return CoverageRecord(
                as_of=filters.to_date,
                data_through=max(data_dates) if data_dates else None,
                order_count=len(items),
                active_order_count=len(active),
                estimate=_count_statuses(
                    [item.result.estimate_status.value for item in items]
                ),
                committed=_count_statuses(
                    [item.result.committed_status.value for item in items]
                ),
                reconciliation=tuple(
                    CategoryCountRecord(key=key, count=count)
                    for key, count in sorted(reconciliation_counts.items())
                ),
                missing_components=tuple(
                    CategoryCountRecord(key=key, count=count)
                    for key, count in sorted(
                        missing_counts.items(), key=lambda pair: (-pair[1], pair[0])
                    )
                ),
            )

    def exceptions(
        self,
        *,
        company_id: UUID,
        status: str | None = "OPEN",
        severity: str | None = None,
        code: str | None = None,
        currency: str | None = None,
        order_id: UUID | None = None,
        from_date: date | None = None,
        to_date: date | None = None,
        limit: int = 50,
        offset: int = 0,
    ) -> ExceptionPage:
        if from_date and to_date and from_date > to_date:
            raise BadRequestError("'from' must not be later than 'to'.")
        assigned = aliased(User)
        resolved = aliased(User)
        joins = (
            select(
                FinanceDiscrepancy,
                FinanceReconciliationRun,
                SalesOrder,
                Counterparty.name.label("customer_name"),
                FinanceSourceReference.source_reference,
                assigned.display_name.label("assigned_name"),
                resolved.display_name.label("resolved_name"),
            )
            .join(
                FinanceReconciliationRun,
                and_(
                    FinanceReconciliationRun.id == FinanceDiscrepancy.run_id,
                    FinanceReconciliationRun.company_id
                    == FinanceDiscrepancy.company_id,
                ),
            )
            .join(
                SalesOrder,
                and_(
                    SalesOrder.id == FinanceReconciliationRun.sales_order_id,
                    SalesOrder.company_id == FinanceReconciliationRun.company_id,
                ),
            )
            .join(
                Counterparty,
                and_(
                    Counterparty.id == SalesOrder.customer_id,
                    Counterparty.company_id == SalesOrder.company_id,
                ),
            )
            .outerjoin(
                FinanceSourceReference,
                and_(
                    FinanceSourceReference.id
                    == FinanceDiscrepancy.finance_source_reference_id,
                    FinanceSourceReference.company_id == FinanceDiscrepancy.company_id,
                ),
            )
            .outerjoin(assigned, assigned.id == FinanceDiscrepancy.assigned_to)
            .outerjoin(resolved, resolved.id == FinanceDiscrepancy.resolved_by)
        )
        conditions = [FinanceDiscrepancy.company_id == company_id]
        if status:
            conditions.append(FinanceDiscrepancy.status == status)
        if severity:
            conditions.append(FinanceDiscrepancy.severity == severity)
        if code:
            conditions.append(FinanceDiscrepancy.code == code)
        if currency:
            conditions.append(FinanceReconciliationRun.currency == currency)
        if order_id:
            conditions.append(FinanceReconciliationRun.sales_order_id == order_id)
        if from_date:
            conditions.append(FinanceDiscrepancy.created_at >= _utc_start(from_date))
        if to_date:
            conditions.append(FinanceDiscrepancy.created_at <= _utc_end(to_date))
        with self._database.transaction() as session:
            apply_company_context(session, company_id)
            total = int(
                session.execute(
                    select(func.count(FinanceDiscrepancy.id))
                    .select_from(FinanceDiscrepancy)
                    .join(
                        FinanceReconciliationRun,
                        and_(
                            FinanceReconciliationRun.id == FinanceDiscrepancy.run_id,
                            FinanceReconciliationRun.company_id
                            == FinanceDiscrepancy.company_id,
                        ),
                    )
                    .where(*conditions)
                ).scalar_one()
            )
            rows = session.execute(
                joins.where(*conditions)
                .order_by(
                    FinanceDiscrepancy.created_at.desc(),
                    FinanceDiscrepancy.id.desc(),
                )
                .limit(limit)
                .offset(offset)
            ).all()
            items = tuple(
                self._exception_record(
                    discrepancy,
                    run,
                    order,
                    str(customer_name),
                    str(source_reference) if source_reference else None,
                    str(resolved_name or assigned_name)
                    if (resolved_name or assigned_name)
                    else None,
                )
                for (
                    discrepancy,
                    run,
                    order,
                    customer_name,
                    source_reference,
                    assigned_name,
                    resolved_name,
                ) in rows
            )
            return ExceptionPage(
                items=items, total=total, limit=limit, offset=offset
            )

    @staticmethod
    def _exception_record(
        discrepancy: FinanceDiscrepancy,
        run: FinanceReconciliationRun,
        order: SalesOrder,
        customer_name: str,
        source_reference: str | None,
        reviewer_name: str | None,
    ) -> ExceptionRecord:
        return ExceptionRecord(
            id=discrepancy.id,
            run_id=discrepancy.run_id,
            sales_order_id=run.sales_order_id,
            order_number=order.order_number,
            customer_name=customer_name,
            currency=run.currency,
            order_status=order.status,
            code=discrepancy.code,
            severity=discrepancy.severity,
            status=discrepancy.status,
            title=discrepancy.title,
            detail=discrepancy.detail,
            expected=discrepancy.expected,
            observed=discrepancy.observed,
            source_entity_type=discrepancy.source_entity_type,
            source_entity_id=discrepancy.source_entity_id,
            finance_source_reference=source_reference,
            reviewer_name=reviewer_name,
            resolution_notes=discrepancy.resolution_notes,
            resolved_at=discrepancy.resolved_at,
            created_at=discrepancy.created_at,
            updated_at=discrepancy.updated_at,
            version=discrepancy.version,
        )

    def order_detail(
        self, *, company_id: UUID, sales_order_id: UUID
    ) -> OrderDetailRecord:
        with self._database.transaction() as session:
            apply_company_context(session, company_id)
            facts = _load_order_facts(
                session,
                company_id=company_id,
                filters=_detail_filters(sales_order_id),
            )
            if not facts:
                raise NotFoundError("The sales order does not exist.")
            fact = facts[0]
            analyzed = AnalyzedOrder(facts=fact, result=analyse_order(fact))
            quote = session.execute(
                select(SalesQuote).where(
                    SalesQuote.company_id == company_id,
                    SalesQuote.id == fact.sales_quote_id,
                )
            ).scalar_one()
            quote_lines = tuple(
                QuoteLineRecord(
                    product_id=row.product_id,
                    description=row.description,
                    quantity=row.quantity,
                    unit=row.unit,
                    unit_price=row.unit_price,
                    line_total=row.line_total,
                )
                for row in session.execute(
                    select(SalesQuoteItem)
                    .where(
                        SalesQuoteItem.company_id == company_id,
                        SalesQuoteItem.sales_quote_id == quote.id,
                    )
                    .order_by(SalesQuoteItem.created_at, SalesQuoteItem.id)
                ).scalars()
            )
            runs = tuple(
                session.execute(
                    select(FinanceReconciliationRun)
                    .where(
                        FinanceReconciliationRun.company_id == company_id,
                        FinanceReconciliationRun.sales_order_id == sales_order_id,
                    )
                    .order_by(
                        FinanceReconciliationRun.created_at.desc(),
                        FinanceReconciliationRun.id.desc(),
                    )
                    .limit(50)
                ).scalars()
            )
            run_ids = [run.id for run in runs]
            evidence_counts = _counts_by_run(
                session,
                company_id=company_id,
                run_ids=run_ids,
                model=FinanceReconciliationEvidence,
            )
            discrepancy_counts = _discrepancy_counts_by_run(
                session, company_id=company_id, run_ids=run_ids
            )
            review_rows = (
                tuple(
                    session.execute(
                        select(FinanceReconciliationReview)
                        .where(
                            FinanceReconciliationReview.company_id == company_id,
                            FinanceReconciliationReview.run_id.in_(run_ids),
                        )
                        .order_by(
                            FinanceReconciliationReview.created_at.desc(),
                            FinanceReconciliationReview.id.desc(),
                        )
                    ).scalars()
                )
                if run_ids
                else ()
            )
            latest_review: dict[UUID, FinanceReconciliationReview] = {}
            for review in review_rows:
                latest_review.setdefault(review.run_id, review)
            run_records = tuple(
                RunTimelineRecord(
                    run_id=run.id,
                    status=run.status,
                    as_of=run.as_of,
                    data_through=run.data_through,
                    currency=run.currency,
                    created_at=run.created_at,
                    evidence_count=evidence_counts.get(run.id, 0),
                    open_discrepancy_count=discrepancy_counts.get(run.id, 0),
                    latest_decision=latest_review[run.id].decision
                    if run.id in latest_review
                    else None,
                    latest_review_at=latest_review[run.id].created_at
                    if run.id in latest_review
                    else None,
                )
                for run in runs
            )
            evidence_rows = (
                tuple(
                    session.execute(
                        select(
                            FinanceReconciliationEvidence,
                            FinanceSourceReference.source_type,
                            FinanceSourceReference.source_reference,
                        )
                        .join(
                            FinanceSourceReference,
                            and_(
                                FinanceSourceReference.id
                                == FinanceReconciliationEvidence.finance_source_reference_id,
                                FinanceSourceReference.company_id
                                == FinanceReconciliationEvidence.company_id,
                            ),
                        )
                        .where(
                            FinanceReconciliationEvidence.company_id == company_id,
                            FinanceReconciliationEvidence.run_id.in_(run_ids),
                        )
                        .order_by(
                            FinanceReconciliationEvidence.created_at.desc(),
                            FinanceReconciliationEvidence.id.desc(),
                        )
                        .limit(100)
                    ).all()
                )
                if run_ids
                else ()
            )
            evidence = tuple(
                EvidenceRecord(
                    id=link.id,
                    run_id=link.run_id,
                    source_entity_type=link.source_entity_type,
                    source_entity_id=link.source_entity_id,
                    finance_source_type=source_type,
                    finance_source_reference=source_reference,
                    currency=link.currency,
                    amount=link.amount,
                    as_of=link.as_of,
                    data_through=link.data_through,
                    verification_status=link.verification_status,
                    created_at=link.created_at,
                    verified_at=link.verified_at,
                )
                for link, source_type, source_reference in evidence_rows
            )
            discrepancy_rows = tuple(
                session.execute(
                    select(FinanceDiscrepancy, FinanceReconciliationRun)
                    .join(
                        FinanceReconciliationRun,
                        and_(
                            FinanceReconciliationRun.id == FinanceDiscrepancy.run_id,
                            FinanceReconciliationRun.company_id
                            == FinanceDiscrepancy.company_id,
                        ),
                    )
                    .where(
                        FinanceDiscrepancy.company_id == company_id,
                        FinanceReconciliationRun.sales_order_id == sales_order_id,
                    )
                    .order_by(
                        FinanceDiscrepancy.created_at.desc(),
                        FinanceDiscrepancy.id.desc(),
                    )
                    .limit(100)
                ).all()
            )
            order = session.get(SalesOrder, sales_order_id)
            if order is None:
                raise NotFoundError("The sales order does not exist.")
            discrepancies = tuple(
                self._exception_record(
                    discrepancy,
                    run,
                    order,
                    fact.customer_name,
                    None,
                    None,
                )
                for discrepancy, run in discrepancy_rows
            )
            return OrderDetailRecord(
                analyzed=analyzed,
                quote=QuoteDetailRecord(
                    quote_id=quote.id,
                    quote_number=quote.quote_number,
                    revision=quote.revision,
                    status=quote.status,
                    currency=quote.currency,
                    incoterm=quote.incoterm,
                    named_delivery_place=quote.named_delivery_place,
                    payment_terms=quote.payment_terms,
                    valid_until=quote.valid_until,
                    approved_at=quote.approved_at,
                    lines=quote_lines,
                ),
                purchase_orders=fact.purchase_orders,
                shipments=fact.shipments,
                cost_lines=analyzed.result.cost_lines,
                fx_assumptions=_fx_assumptions(fact),
                runs=run_records,
                evidence=evidence,
                discrepancies=discrepancies,
            )

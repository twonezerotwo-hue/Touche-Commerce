"""Stage 5D reconciliation orchestration.

The service composes Commerce commercial facts, Finance observations read through
the Stage 5C read-only connector, and operator-linked evidence. It never calls a
Finance write route, never opens Finance SQLite and never attributes a
company-wide Finance balance to a sales order.
"""

from __future__ import annotations

import hashlib
import json
from dataclasses import dataclass, replace
from datetime import UTC, date, datetime
from decimal import Decimal, InvalidOperation
from typing import Any, cast
from uuid import UUID

from sqlalchemy import and_, func, select
from sqlalchemy.orm import Session

from app.core.errors import (
    BadRequestError,
    FinanceCurrencyRequiredError,
    FinanceInvalidCurrencyError,
    ForbiddenError,
    NotFoundError,
    ReconciliationCurrencyMismatchError,
    ReconciliationDuplicateEvidenceError,
    ReconciliationEvidenceInvalidError,
    ReconciliationNotVerifiableError,
    ReconciliationSourceNotMatchableError,
    ReconciliationStateError,
    VersionConflictError,
)
from app.db.models import (
    AuditAction,
    AuditOutcome,
    Counterparty,
    DiscrepancyCode,
    DiscrepancySeverity,
    DiscrepancyStatus,
    EvidenceVerificationStatus,
    FinanceCompanyMapping,
    FinanceDiscrepancy,
    FinanceReconciliationEvidence,
    FinanceReconciliationReview,
    FinanceReconciliationRun,
    FinanceSourceReference,
    FinanceSourceType,
    PricingScenario,
    PurchaseOrder,
    ReconciliationStatus,
    ReviewDecision,
    SalesOrder,
    SalesQuote,
    Shipment,
    ShipmentCost,
    SourceEntityType,
    User,
)
from app.db.tenant import apply_company_context
from app.integrations.finance.connector import (
    FinanceConnector,
    FinanceMappingSnapshot,
    FinanceResult,
)
from app.services.audit import record_audit
from app.services.reconciliation_calculations import (
    CALCULATION_VERSION,
    CommercialFacts,
    DiscrepancyDraft,
    PricingEstimateFact,
    PurchaseCommitmentFact,
    ReconciliationMetrics,
    ShipmentCostFact,
    ShipmentFact,
    analyse,
    canonical_currency,
    finance_currency_for,
    quantize_money,
)
from app.services.trade_meta import WriteMeta

_MONEY_ZERO = Decimal("0.00")
_MAX_NOTES = 2000
_TERMINAL_SOURCE_ENTITY_TYPES = frozenset(
    {
        SourceEntityType.SALES_ORDER.value,
        SourceEntityType.PURCHASE_ORDER.value,
        SourceEntityType.SHIPMENT_COST.value,
    }
)
_BLOCKING_OPEN = (
    DiscrepancyStatus.OPEN.value,
    DiscrepancySeverity.BLOCKING.value,
)


def _json_safe(value: Any) -> Any:
    if isinstance(value, Decimal):
        return str(quantize_money(value))
    if isinstance(value, (datetime, date)):
        return value.isoformat()
    if isinstance(value, UUID):
        return str(value)
    if isinstance(value, dict):
        return {str(key): _json_safe(item) for key, item in value.items()}
    if isinstance(value, (list, tuple, set, frozenset)):
        return [_json_safe(item) for item in value]
    return value


def _decimal(value: Any, *, default: Decimal | None = None) -> Decimal | None:
    if value is None:
        return default
    try:
        return Decimal(str(value))
    except (InvalidOperation, ValueError):
        return default


def _money(value: Decimal | None) -> str | None:
    return None if value is None else str(quantize_money(value))


def _hash(payload: dict[str, Any]) -> str:
    encoded = json.dumps(_json_safe(payload), sort_keys=True, separators=(",", ":")).encode("utf-8")
    return hashlib.sha256(encoded).hexdigest()


def _fingerprint(
    code: str,
    *,
    source_entity_type: str | None,
    source_entity_id: UUID | None,
    source_reference_id: UUID | None,
) -> str:
    return _hash(
        {
            "code": code,
            "source_entity_type": source_entity_type,
            "source_entity_id": str(source_entity_id) if source_entity_id else None,
            "source_reference_id": str(source_reference_id) if source_reference_id else None,
        }
    )


@dataclass(frozen=True, slots=True)
class FinanceSnapshot:
    """Secret-free Finance observations captured for one run."""

    finance_company_id: str
    finance_company_name: str | None
    finance_currency: str
    currency: str
    data_through: date | None
    available_currencies: tuple[str, ...]
    summary: dict[str, Any]
    receivable: dict[str, Any]
    payable: dict[str, Any]
    request_ids: dict[str, str | None]
    fetched_at: datetime
    duplicate_references: int = 0


@dataclass(frozen=True, slots=True)
class SourceReferenceRecord:
    id: UUID
    source_type: str
    source_reference: str
    is_transaction_level: bool
    currency: str
    observed_amount: Decimal | None
    as_of: date
    data_through: date | None
    payload: dict[str, Any]
    content_hash: str


@dataclass(frozen=True, slots=True)
class EvidenceRecord:
    id: UUID
    source_entity_type: str
    source_entity_id: UUID
    finance_source_reference_id: UUID
    source_type: str
    source_reference: str
    currency: str
    amount: Decimal
    as_of: date
    data_through: date | None
    provenance: dict[str, Any]
    verification_status: str
    notes: str | None
    created_by: UUID
    created_at: datetime
    verified_by: UUID | None
    verified_at: datetime | None


@dataclass(frozen=True, slots=True)
class DiscrepancyRecord:
    id: UUID
    run_id: UUID
    code: str
    severity: str
    status: str
    title: str
    detail: str
    expected: dict[str, Any]
    observed: dict[str, Any]
    source_entity_type: str | None
    source_entity_id: UUID | None
    finance_source_reference_id: UUID | None
    assigned_to: UUID | None
    resolution_notes: str | None
    resolved_by: UUID | None
    resolved_at: datetime | None
    created_at: datetime
    updated_at: datetime
    version: int


@dataclass(frozen=True, slots=True)
class ReviewRecord:
    id: UUID
    decision: str
    previous_status: str
    new_status: str
    notes: str
    reviewer_id: UUID
    reviewer_name: str | None
    created_at: datetime


@dataclass(frozen=True, slots=True)
class RunRecord:
    id: UUID
    company_id: UUID
    sales_order_id: UUID
    order_number: str
    customer_name: str
    finance_company_id: str
    currency: str
    finance_currency: str
    as_of: date
    data_through: date | None
    status: str
    calculation_version: str
    source_snapshot: dict[str, Any]
    created_by: UUID
    created_at: datetime
    updated_at: datetime
    version: int
    source_references: tuple[SourceReferenceRecord, ...]
    evidence: tuple[EvidenceRecord, ...]
    discrepancies: tuple[DiscrepancyRecord, ...]
    reviews: tuple[ReviewRecord, ...]


@dataclass(frozen=True, slots=True)
class RunSummaryRecord:
    id: UUID
    sales_order_id: UUID
    order_number: str
    customer_name: str
    currency: str
    as_of: date
    data_through: date | None
    status: str
    version: int
    created_at: datetime
    evidence_count: int
    open_discrepancy_count: int
    blocking_discrepancy_count: int


@dataclass(frozen=True, slots=True)
class RunPage:
    items: tuple[RunSummaryRecord, ...]
    total: int


@dataclass(frozen=True, slots=True)
class EvidencePage:
    items: tuple[EvidenceRecord, ...]
    total: int


@dataclass(frozen=True, slots=True)
class DiscrepancyPage:
    items: tuple[DiscrepancyRecord, ...]
    total: int


@dataclass(frozen=True, slots=True)
class RunFilters:
    sales_order_id: UUID | None = None
    currency: str | None = None
    status: str | None = None


@dataclass(frozen=True, slots=True)
class DiscrepancyFilters:
    run_id: UUID | None = None
    code: str | None = None
    severity: str | None = None
    status: str | None = None
    currency: str | None = None


@dataclass(frozen=True, slots=True)
class OrderFinanceRecord:
    sales_order_id: UUID
    order_number: str
    customer_name: str
    currency: str
    facts: CommercialFacts
    metrics: ReconciliationMetrics
    classifications: dict[str, str]
    limitations: tuple[str, ...]
    evidence_gaps: tuple[Any, ...]
    latest_run_id: UUID | None
    latest_run_status: str | None
    latest_run_at: datetime | None


def normalise_notes(value: str | None) -> str | None:
    if value is None:
        return None
    cleaned = " ".join(value.split())
    if not cleaned:
        return None
    if len(cleaned) > _MAX_NOTES:
        raise BadRequestError(
            "Notes must be at most 2000 characters.",
            details=[
                {
                    "field": "notes",
                    "message": "Shorten the note.",
                    "type": "value_error",
                }
            ],
        )
    return cleaned


def _parse_date(value: Any) -> date | None:
    if isinstance(value, date) and not isinstance(value, datetime):
        return value
    if isinstance(value, datetime):
        return value.date()
    if isinstance(value, str):
        try:
            return date.fromisoformat(value[:10])
        except ValueError:
            return None
    return None


def read_finance_snapshot(
    connector: FinanceConnector,
    mapping: FinanceMappingSnapshot | None,
    *,
    requested_currency: str | None,
) -> FinanceSnapshot:
    """Read only the finite Stage 5C surface and capture a secret-free snapshot.

    No Finance write method exists on the connector. A missing or unsupported
    currency is refused rather than guessed.
    """

    if not requested_currency:
        raise FinanceCurrencyRequiredError(details={"available_currencies": []})
    canonical = canonical_currency(requested_currency)
    capabilities: FinanceResult = connector.capabilities(mapping)
    available = tuple(
        str(item).upper()
        for item in capabilities.data.get("available_currencies", [])
        if isinstance(item, str)
    )
    selected = finance_currency_for(canonical, available)
    if selected is None:
        raise FinanceInvalidCurrencyError(
            details={"available_currencies": list(available), "requested": canonical}
        )

    summary = connector.summary(mapping, currency=selected)
    receivable = connector.aging(mapping, kind="receivable", currency=selected, limit=200)
    payable = connector.aging(mapping, kind="payable", currency=selected, limit=200)
    data_through = _parse_date(summary.data.get("data_through")) or _parse_date(
        capabilities.data.get("data_through")
    )
    finance_company_id = mapping.finance_company_id if mapping is not None else ""
    return FinanceSnapshot(
        finance_company_id=finance_company_id,
        finance_company_name=mapping.finance_company_name if mapping is not None else None,
        finance_currency=selected,
        currency=canonical,
        data_through=data_through,
        available_currencies=available,
        summary=dict(summary.data),
        receivable=dict(receivable.data),
        payable=dict(payable.data),
        request_ids={
            "capabilities": capabilities.request_id,
            "summary": summary.request_id,
            "receivable_aging": receivable.request_id,
            "payable_aging": payable.request_id,
        },
        fetched_at=summary.fetched_at,
    )


def _load_facts(
    session: Session, *, company_id: UUID, sales_order_id: UUID
) -> tuple[CommercialFacts, str, str]:
    row = session.execute(
        select(SalesOrder, Counterparty.name.label("customer_name"))
        .join(
            Counterparty,
            (Counterparty.id == SalesOrder.customer_id)
            & (Counterparty.company_id == SalesOrder.company_id),
        )
        .where(
            SalesOrder.id == sales_order_id,
            SalesOrder.company_id == company_id,
        )
    ).one_or_none()
    if row is None:
        raise NotFoundError("The sales order does not exist.")
    order = row[0]
    customer_name = str(row[1])

    scenario = session.execute(
        select(PricingScenario)
        .join(
            SalesQuote,
            (SalesQuote.scenario_id == PricingScenario.id)
            & (SalesQuote.company_id == PricingScenario.company_id),
        )
        .where(
            SalesQuote.id == order.sales_quote_id,
            SalesQuote.company_id == company_id,
        )
    ).scalar_one_or_none()
    estimate: PricingEstimateFact | None = None
    if scenario is not None:
        raw_results = scenario.calculated_results
        results: dict[str, Any] = raw_results if isinstance(raw_results, dict) else {}
        raw_totals = results.get("totals")
        totals: dict[str, Any] = raw_totals if isinstance(raw_totals, dict) else {}
        landed = _decimal(totals.get("landed_total"))
        sales_total = _decimal(totals.get("sales_total"))
        if scenario.status != "INCOMPLETE":
            estimate = PricingEstimateFact(
                scenario_id=scenario.id,
                status=scenario.status,
                calculation_version=scenario.calculation_version,
                target_currency=scenario.target_currency,
                landed_total=landed,
                sales_total=sales_total,
            )

    purchase_orders = tuple(
        PurchaseCommitmentFact(
            purchase_order_id=po.id,
            po_number=po.po_number,
            status=po.status,
            currency=po.currency,
            total_cost=po.total_cost,
        )
        for po in session.execute(
            select(PurchaseOrder)
            .where(
                PurchaseOrder.company_id == company_id,
                PurchaseOrder.sales_order_id == order.id,
            )
            .order_by(PurchaseOrder.created_at, PurchaseOrder.id)
        ).scalars()
    )

    shipment_rows = tuple(
        session.execute(
            select(Shipment)
            .where(
                Shipment.company_id == company_id,
                Shipment.sales_order_id == order.id,
            )
            .order_by(Shipment.created_at, Shipment.id)
        ).scalars()
    )
    costs_by_shipment: dict[UUID, list[ShipmentCostFact]] = {}
    if shipment_rows:
        cost_rows = session.execute(
            select(ShipmentCost)
            .where(
                ShipmentCost.company_id == company_id,
                ShipmentCost.shipment_id.in_([shipment.id for shipment in shipment_rows]),
            )
            .order_by(ShipmentCost.recorded_at, ShipmentCost.id)
        ).scalars()
        for cost in cost_rows:
            costs_by_shipment.setdefault(cost.shipment_id, []).append(
                ShipmentCostFact(
                    cost_id=cost.id,
                    cost_type=cost.cost_type,
                    stage=cost.stage,
                    currency=cost.currency,
                    amount=cost.amount,
                    reference=cost.reference,
                )
            )
    shipments = tuple(
        ShipmentFact(
            shipment_id=shipment.id,
            shipment_number=shipment.shipment_number,
            status=shipment.status,
            costs=tuple(costs_by_shipment.get(shipment.id, ())),
        )
        for shipment in shipment_rows
    )

    facts = CommercialFacts(
        sales_order_id=order.id,
        order_number=order.order_number,
        customer_name=customer_name,
        status=order.status,
        fulfilment_model=order.fulfilment_model,
        currency=order.currency,
        order_total=order.order_total,
        confirmed_at=order.confirmed_at.isoformat(),
        expected_delivery_date=order.expected_delivery_date,
        purchase_orders=purchase_orders,
        shipments=shipments,
        pricing_estimate=estimate,
    )
    return facts, order.order_number, customer_name


def _metrics_payload(metrics: ReconciliationMetrics) -> dict[str, Any]:
    return {
        "accepted_sales_order_value": _money(metrics.accepted_sales_order_value),
        "purchase_commitments_total": _money(metrics.purchase_commitments_total),
        "purchase_commitment_count": metrics.purchase_commitment_count,
        "estimated_landed_cost": _money(metrics.estimated_landed_cost),
        "recorded_operational_costs": _money(metrics.recorded_operational_costs),
        "estimate_vs_recorded_variance": _money(metrics.estimate_vs_recorded_variance),
        "commitment_based_margin": _money(metrics.commitment_based_margin),
        "commitment_based_margin_pct": _money(metrics.commitment_based_margin_pct),
        "document_supported_margin": None,
        "completeness_score": _money(metrics.completeness_score),
        "completeness_checks": [
            {
                "key": check.key,
                "label": check.label,
                "satisfied": check.satisfied,
                "detail": check.detail,
            }
            for check in metrics.completeness_checks
        ],
    }


def _finance_payload(snapshot: FinanceSnapshot) -> dict[str, Any]:
    def _aging(data: dict[str, Any]) -> dict[str, Any]:
        raw_items = data.get("items")
        items: list[Any] = raw_items if isinstance(raw_items, list) else []
        open_items_count = 0
        for item in items:
            if not isinstance(item, dict):
                continue
            raw_open = item.get("open_items")
            if isinstance(raw_open, list):
                open_items_count += len(raw_open)
        summary = data.get("summary")
        page = data.get("page")
        return {
            "summary": summary if isinstance(summary, dict) else {},
            "page": page if isinstance(page, dict) else {},
            "items_count": len(items),
            "open_items_count": open_items_count,
        }

    return {
        "finance_company_id": snapshot.finance_company_id,
        "finance_company_name": snapshot.finance_company_name,
        "finance_currency": snapshot.finance_currency,
        "currency": snapshot.currency,
        "data_through": snapshot.data_through.isoformat() if snapshot.data_through else None,
        "available_currencies": list(snapshot.available_currencies),
        "summary": snapshot.summary,
        "receivable": _aging(snapshot.receivable),
        "payable": _aging(snapshot.payable),
        "request_ids": snapshot.request_ids,
        "fetched_at": snapshot.fetched_at.isoformat(),
        "duplicate_references": snapshot.duplicate_references,
        "limitations": [
            "Finance exposes no order-level invoice or payment reference.",
            "Company-wide summary and account balances are not attributed to an order.",
            "Aging counterparty names are never used as matching keys.",
        ],
    }


def _run_snapshot(
    facts: CommercialFacts,
    *,
    analysis: Any,
    finance: FinanceSnapshot,
) -> dict[str, Any]:
    payload = _json_safe(
        {
            "commercial": {
                "order": {
                    "id": facts.sales_order_id,
                    "order_number": facts.order_number,
                    "customer_name": facts.customer_name,
                    "status": facts.status,
                    "fulfilment_model": facts.fulfilment_model,
                    "currency": facts.currency,
                    "order_total": facts.order_total,
                    "confirmed_at": facts.confirmed_at,
                    "expected_delivery_date": facts.expected_delivery_date,
                },
                "purchase_orders": [
                    {
                        "id": po.purchase_order_id,
                        "po_number": po.po_number,
                        "status": po.status,
                        "currency": po.currency,
                        "total_cost": po.total_cost,
                        "is_committed": po.is_committed,
                    }
                    for po in facts.purchase_orders
                ],
                "shipments": [
                    {
                        "id": shipment.shipment_id,
                        "shipment_number": shipment.shipment_number,
                        "status": shipment.status,
                        "costs": [
                            {
                                "id": cost.cost_id,
                                "cost_type": cost.cost_type,
                                "stage": cost.stage,
                                "currency": cost.currency,
                                "amount": cost.amount,
                                "reference": cost.reference,
                            }
                            for cost in shipment.costs
                        ],
                    }
                    for shipment in facts.shipments
                ],
                "pricing_estimate": (
                    None
                    if facts.pricing_estimate is None
                    else {
                        "scenario_id": facts.pricing_estimate.scenario_id,
                        "status": facts.pricing_estimate.status,
                        "calculation_version": facts.pricing_estimate.calculation_version,
                        "target_currency": facts.pricing_estimate.target_currency,
                        "landed_total": facts.pricing_estimate.landed_total,
                        "sales_total": facts.pricing_estimate.sales_total,
                    }
                ),
                "metrics": _metrics_payload(analysis.metrics),
                "classifications": analysis.classifications,
                "limitations": list(analysis.limitations),
            },
            "finance": _finance_payload(finance),
        }
    )
    return cast(dict[str, Any], payload)


def _source_reference_specs(
    snapshot: FinanceSnapshot, *, as_of: date
) -> tuple[list[dict[str, Any]], int]:
    """Extract stable Finance ids; count duplicate transaction references."""

    specs: list[dict[str, Any]] = []
    seen: set[tuple[str, str]] = set()
    duplicates = 0

    summary_key = f"summary:{snapshot.finance_currency}:{as_of.isoformat()}"
    summary_payload = {
        "kind": "company_summary",
        "finance_company_id": snapshot.finance_company_id,
        "finance_currency": snapshot.finance_currency,
        "currency": snapshot.currency,
        "balances": snapshot.summary.get("balances", {}),
        "ledger": snapshot.summary.get("ledger", {}),
        "data_through": snapshot.data_through.isoformat() if snapshot.data_through else None,
    }
    specs.append(
        {
            "source_type": FinanceSourceType.SUMMARY.value,
            "source_reference": summary_key,
            "is_transaction_level": False,
            "observed_amount": None,
            "payload": summary_payload,
        }
    )

    for source_type, data in (
        (FinanceSourceType.AGING_RECEIVABLE, snapshot.receivable),
        (FinanceSourceType.AGING_PAYABLE, snapshot.payable),
    ):
        raw_items = data.get("items")
        items: list[Any] = raw_items if isinstance(raw_items, list) else []
        for item in items:
            if not isinstance(item, dict):
                continue
            counterparty = item.get("counterparty")
            raw_open_items = item.get("open_items")
            open_items: list[Any] = []
            if isinstance(raw_open_items, list):
                open_items = raw_open_items
            for open_item in open_items:
                if not isinstance(open_item, dict):
                    continue
                reference = open_item.get("source_id")
                if not isinstance(reference, str) or not reference.strip():
                    continue
                key = (source_type.value, reference)
                if key in seen:
                    duplicates += 1
                    continue
                seen.add(key)
                remaining = open_item.get("remaining")
                amount = _decimal(
                    remaining.get("amount") if isinstance(remaining, dict) else remaining
                )
                payload = {
                    "kind": "aging_open_item",
                    "finance_company_id": snapshot.finance_company_id,
                    "finance_currency": snapshot.finance_currency,
                    "currency": snapshot.currency,
                    "source": open_item.get("source"),
                    "due_date": open_item.get("due_date"),
                    "remaining": open_item.get("remaining"),
                    "counterparty_label": counterparty,
                    "matching_key": "finance_source_id_only",
                }
                specs.append(
                    {
                        "source_type": source_type.value,
                        "source_reference": reference.strip()[:200],
                        "is_transaction_level": True,
                        "observed_amount": amount,
                        "payload": payload,
                    }
                )
    return specs, duplicates


def _discrepancy_record(row: FinanceDiscrepancy) -> DiscrepancyRecord:
    return DiscrepancyRecord(
        id=row.id,
        run_id=row.run_id,
        code=row.code,
        severity=row.severity,
        status=row.status,
        title=row.title,
        detail=row.detail,
        expected=dict(row.expected),
        observed=dict(row.observed),
        source_entity_type=row.source_entity_type,
        source_entity_id=row.source_entity_id,
        finance_source_reference_id=row.finance_source_reference_id,
        assigned_to=row.assigned_to,
        resolution_notes=row.resolution_notes,
        resolved_by=row.resolved_by,
        resolved_at=row.resolved_at,
        created_at=row.created_at,
        updated_at=row.updated_at,
        version=row.version,
    )


def _run_record(session: Session, *, company_id: UUID, run_id: UUID) -> RunRecord:
    row = session.execute(
        select(
            FinanceReconciliationRun,
            SalesOrder.order_number,
            Counterparty.name.label("customer_name"),
        )
        .join(
            SalesOrder,
            (SalesOrder.id == FinanceReconciliationRun.sales_order_id)
            & (SalesOrder.company_id == FinanceReconciliationRun.company_id),
        )
        .join(
            Counterparty,
            (Counterparty.id == SalesOrder.customer_id)
            & (Counterparty.company_id == SalesOrder.company_id),
        )
        .where(
            FinanceReconciliationRun.id == run_id,
            FinanceReconciliationRun.company_id == company_id,
        )
    ).one_or_none()
    if row is None:
        raise NotFoundError("The reconciliation run does not exist.")
    run = row[0]
    reference_rows = list(
        session.execute(
            select(FinanceSourceReference)
            .where(
                FinanceSourceReference.company_id == company_id,
                FinanceSourceReference.run_id == run.id,
            )
            .order_by(FinanceSourceReference.source_type, FinanceSourceReference.source_reference)
        ).scalars()
    )
    evidence_rows = session.execute(
        select(FinanceReconciliationEvidence, FinanceSourceReference)
        .join(
            FinanceSourceReference,
            and_(
                FinanceSourceReference.id
                == FinanceReconciliationEvidence.finance_source_reference_id,
                FinanceSourceReference.company_id == FinanceReconciliationEvidence.company_id,
                FinanceSourceReference.run_id == FinanceReconciliationEvidence.run_id,
            ),
        )
        .where(
            FinanceReconciliationEvidence.company_id == company_id,
            FinanceReconciliationEvidence.run_id == run.id,
        )
        .order_by(
            FinanceReconciliationEvidence.created_at,
            FinanceReconciliationEvidence.id,
        )
    ).all()
    discrepancy_rows = list(
        session.execute(
            select(FinanceDiscrepancy)
            .where(
                FinanceDiscrepancy.company_id == company_id,
                FinanceDiscrepancy.run_id == run.id,
            )
            .order_by(FinanceDiscrepancy.created_at, FinanceDiscrepancy.id)
        ).scalars()
    )
    review_rows = session.execute(
        select(FinanceReconciliationReview, User.display_name)
        .outerjoin(User, User.id == FinanceReconciliationReview.reviewer_id)
        .where(
            FinanceReconciliationReview.company_id == company_id,
            FinanceReconciliationReview.run_id == run.id,
        )
        .order_by(
            FinanceReconciliationReview.created_at,
            FinanceReconciliationReview.id,
        )
    ).all()

    references = tuple(
        SourceReferenceRecord(
            id=reference.id,
            source_type=reference.source_type,
            source_reference=reference.source_reference,
            is_transaction_level=reference.is_transaction_level,
            currency=reference.currency,
            observed_amount=reference.observed_amount,
            as_of=reference.as_of,
            data_through=reference.data_through,
            payload=dict(reference.payload),
            content_hash=reference.content_hash,
        )
        for reference in reference_rows
    )
    evidence = tuple(
        EvidenceRecord(
            id=item.id,
            source_entity_type=item.source_entity_type,
            source_entity_id=item.source_entity_id,
            finance_source_reference_id=item.finance_source_reference_id,
            source_type=reference.source_type,
            source_reference=reference.source_reference,
            currency=item.currency,
            amount=item.amount,
            as_of=item.as_of,
            data_through=item.data_through,
            provenance=dict(item.provenance),
            verification_status=item.verification_status,
            notes=item.notes,
            created_by=item.created_by,
            created_at=item.created_at,
            verified_by=item.verified_by,
            verified_at=item.verified_at,
        )
        for item, reference in evidence_rows
    )
    discrepancies = tuple(_discrepancy_record(item) for item in discrepancy_rows)
    reviews = tuple(
        ReviewRecord(
            id=review.id,
            decision=review.decision,
            previous_status=review.previous_status,
            new_status=review.new_status,
            notes=review.notes,
            reviewer_id=review.reviewer_id,
            reviewer_name=reviewer_name,
            created_at=review.created_at,
        )
        for review, reviewer_name in review_rows
    )
    return RunRecord(
        id=run.id,
        company_id=run.company_id,
        sales_order_id=run.sales_order_id,
        order_number=str(row[1]),
        customer_name=str(row[2]),
        finance_company_id=run.finance_company_id,
        currency=run.currency,
        finance_currency=run.finance_currency,
        as_of=run.as_of,
        data_through=run.data_through,
        status=run.status,
        calculation_version=run.calculation_version,
        source_snapshot=dict(run.source_snapshot),
        created_by=run.created_by,
        created_at=run.created_at,
        updated_at=run.updated_at,
        version=run.version,
        source_references=references,
        evidence=evidence,
        discrepancies=discrepancies,
        reviews=reviews,
    )


class ReconciliationService:
    """Transactional reads/writes over the evidence reconciliation domain."""

    def __init__(self, database: Any) -> None:
        self._database = database

    def create_run(
        self,
        session: Session,
        *,
        meta: WriteMeta,
        sales_order_id: UUID,
        requested_currency: str | None,
        as_of: date,
        mapping: FinanceCompanyMapping | None,
        finance: FinanceSnapshot,
    ) -> RunRecord:
        facts, _order_number, _customer_name = _load_facts(
            session, company_id=meta.company_id, sales_order_id=sales_order_id
        )
        if requested_currency is None:
            raise FinanceCurrencyRequiredError(
                details={"available_currencies": [canonical_currency(facts.currency)]}
            )
        canonical = canonical_currency(requested_currency)
        if canonical != canonical_currency(facts.currency):
            raise ReconciliationCurrencyMismatchError(
                details={
                    "requested": canonical,
                    "order_currency": canonical_currency(facts.currency),
                }
            )
        if canonical != finance.currency:
            raise ReconciliationCurrencyMismatchError(
                details={"requested": canonical, "finance_currency": finance.currency}
            )
        if mapping is None or mapping.status != "verified":
            raise BadRequestError("A verified Finance company mapping is required.")
        if mapping.finance_company_id != finance.finance_company_id:
            raise ReconciliationCurrencyMismatchError(
                "The Finance snapshot does not belong to the verified mapping.",
                details={
                    "mapping": mapping.finance_company_id,
                    "snapshot": finance.finance_company_id,
                },
            )

        specs, duplicates = _source_reference_specs(finance, as_of=as_of)
        snapshot_finance = replace(finance, duplicate_references=duplicates)
        analysis = analyse(
            facts,
            as_of=as_of,
            finance_data_through=snapshot_finance.data_through,
            duplicate_finance_references=duplicates,
        )
        now = datetime.now(tz=UTC)
        run = FinanceReconciliationRun(
            company_id=meta.company_id,
            sales_order_id=facts.sales_order_id,
            finance_company_id=snapshot_finance.finance_company_id,
            currency=canonical,
            finance_currency=snapshot_finance.finance_currency,
            as_of=as_of,
            data_through=snapshot_finance.data_through,
            status=analysis.status,
            calculation_version=CALCULATION_VERSION,
            source_snapshot=_run_snapshot(facts, analysis=analysis, finance=snapshot_finance),
            created_by=meta.actor_id,
            created_at=now,
            updated_at=now,
        )
        session.add(run)
        session.flush()

        for spec in specs:
            payload = cast(dict[str, Any], spec["payload"])
            session.add(
                FinanceSourceReference(
                    company_id=meta.company_id,
                    run_id=run.id,
                    source_type=cast(str, spec["source_type"]),
                    source_reference=cast(str, spec["source_reference"]),
                    is_transaction_level=cast(bool, spec["is_transaction_level"]),
                    currency=canonical,
                    observed_amount=cast(Decimal | None, spec["observed_amount"]),
                    as_of=as_of,
                    data_through=snapshot_finance.data_through,
                    payload=payload,
                    content_hash=_hash(payload),
                    created_at=now,
                )
            )
        session.flush()
        self._insert_discrepancy_drafts(session, run=run, drafts=analysis.discrepancies, now=now)

        record_audit(
            session,
            action=AuditAction.FINANCE_READ,
            outcome=AuditOutcome.SUCCESS,
            actor_id=meta.actor_id,
            company_id=meta.company_id,
            request_id=meta.request_id,
            ip_address=meta.ip_address,
            user_agent=meta.user_agent,
            resource_type="finance_reconciliation_run",
            resource_id=str(run.id),
            details={
                "endpoint": "/finance/reconciliation/runs",
                "operations": [
                    "capabilities",
                    "summary",
                    "aging:receivable",
                    "aging:payable",
                ],
                "finance_company_id": run.finance_company_id,
                "currency": run.currency,
                "finance_currency": run.finance_currency,
                "finance_request_ids": snapshot_finance.request_ids,
            },
        )
        record_audit(
            session,
            action=AuditAction.FINANCE_RECONCILIATION_RUN_CREATED,
            outcome=AuditOutcome.SUCCESS,
            actor_id=meta.actor_id,
            company_id=meta.company_id,
            request_id=meta.request_id,
            ip_address=meta.ip_address,
            user_agent=meta.user_agent,
            resource_type="finance_reconciliation_run",
            resource_id=str(run.id),
            details={
                "sales_order_id": str(run.sales_order_id),
                "status": run.status,
                "currency": run.currency,
                "finance_company_id": run.finance_company_id,
                "calculation_version": run.calculation_version,
                "discrepancy_codes": [draft.code.value for draft in analysis.discrepancies],
            },
        )
        session.flush()
        return _run_record(session, company_id=meta.company_id, run_id=run.id)

    @staticmethod
    def _insert_discrepancy_drafts(
        session: Session,
        *,
        run: FinanceReconciliationRun,
        drafts: Any,
        now: datetime,
    ) -> None:
        for draft in drafts:
            fingerprint = _fingerprint(
                draft.code.value,
                source_entity_type=draft.source_entity_type,
                source_entity_id=draft.source_entity_id,
                source_reference_id=draft.finance_source_reference_id,
            )
            session.add(
                FinanceDiscrepancy(
                    company_id=run.company_id,
                    run_id=run.id,
                    code=draft.code.value,
                    severity=draft.severity.value,
                    status=DiscrepancyStatus.OPEN.value,
                    fingerprint=fingerprint,
                    title=draft.title,
                    detail=draft.detail,
                    expected=_json_safe(draft.expected),
                    observed=_json_safe(draft.observed),
                    source_entity_type=draft.source_entity_type,
                    source_entity_id=draft.source_entity_id,
                    finance_source_reference_id=draft.finance_source_reference_id,
                    created_at=now,
                    updated_at=now,
                )
            )
        session.flush()

    # ------------------------------------------------------------------ reads
    def get_run(self, *, company_id: UUID, run_id: UUID) -> RunRecord:
        with self._database.transaction() as session:
            apply_company_context(session, company_id)
            return _run_record(session, company_id=company_id, run_id=run_id)

    def list_runs(
        self,
        *,
        company_id: UUID,
        filters: RunFilters,
        limit: int,
        offset: int,
    ) -> RunPage:
        with self._database.transaction() as session:
            apply_company_context(session, company_id)
            query = (
                select(FinanceReconciliationRun, SalesOrder.order_number, Counterparty.name)
                .join(
                    SalesOrder,
                    (SalesOrder.id == FinanceReconciliationRun.sales_order_id)
                    & (SalesOrder.company_id == FinanceReconciliationRun.company_id),
                )
                .join(
                    Counterparty,
                    (Counterparty.id == SalesOrder.customer_id)
                    & (Counterparty.company_id == SalesOrder.company_id),
                )
                .where(FinanceReconciliationRun.company_id == company_id)
            )
            if filters.sales_order_id:
                query = query.where(
                    FinanceReconciliationRun.sales_order_id == filters.sales_order_id
                )
            if filters.currency:
                query = query.where(
                    FinanceReconciliationRun.currency == canonical_currency(filters.currency)
                )
            if filters.status:
                query = query.where(FinanceReconciliationRun.status == filters.status)
            total = session.execute(
                select(func.count()).select_from(query.order_by(None).subquery())
            ).scalar_one()
            rows = session.execute(
                query.order_by(
                    FinanceReconciliationRun.created_at.desc(),
                    FinanceReconciliationRun.id.desc(),
                )
                .limit(limit)
                .offset(offset)
            ).all()
            items = []
            for run, order_number, customer_name in rows:
                evidence_count = session.execute(
                    select(func.count(FinanceReconciliationEvidence.id)).where(
                        FinanceReconciliationEvidence.company_id == company_id,
                        FinanceReconciliationEvidence.run_id == run.id,
                    )
                ).scalar_one()
                open_count = session.execute(
                    select(func.count(FinanceDiscrepancy.id)).where(
                        FinanceDiscrepancy.company_id == company_id,
                        FinanceDiscrepancy.run_id == run.id,
                        FinanceDiscrepancy.status == DiscrepancyStatus.OPEN.value,
                    )
                ).scalar_one()
                blocking_count = session.execute(
                    select(func.count(FinanceDiscrepancy.id)).where(
                        FinanceDiscrepancy.company_id == company_id,
                        FinanceDiscrepancy.run_id == run.id,
                        FinanceDiscrepancy.status == DiscrepancyStatus.OPEN.value,
                        FinanceDiscrepancy.severity == DiscrepancySeverity.BLOCKING.value,
                    )
                ).scalar_one()
                items.append(
                    RunSummaryRecord(
                        id=run.id,
                        sales_order_id=run.sales_order_id,
                        order_number=order_number,
                        customer_name=customer_name,
                        currency=run.currency,
                        as_of=run.as_of,
                        data_through=run.data_through,
                        status=run.status,
                        version=run.version,
                        created_at=run.created_at,
                        evidence_count=int(evidence_count),
                        open_discrepancy_count=int(open_count),
                        blocking_discrepancy_count=int(blocking_count),
                    )
                )
            return RunPage(items=tuple(items), total=int(total))

    def run_counts(
        self, *, company_id: UUID, currency: str | None = None
    ) -> tuple[dict[str, int], int, int]:
        with self._database.transaction() as session:
            apply_company_context(session, company_id)
            run_filter = [FinanceReconciliationRun.company_id == company_id]
            if currency:
                run_filter.append(FinanceReconciliationRun.currency == canonical_currency(currency))
            counts = {status.value: 0 for status in ReconciliationStatus}
            rows = session.execute(
                select(FinanceReconciliationRun.status, func.count(FinanceReconciliationRun.id))
                .where(*run_filter)
                .group_by(FinanceReconciliationRun.status)
            ).all()
            for status, count in rows:
                counts[str(status)] = int(count)
            run_ids = list(
                session.execute(select(FinanceReconciliationRun.id).where(*run_filter)).scalars()
            )
            if not run_ids:
                return counts, 0, 0
            open_count = session.execute(
                select(func.count(FinanceDiscrepancy.id)).where(
                    FinanceDiscrepancy.company_id == company_id,
                    FinanceDiscrepancy.run_id.in_(run_ids),
                    FinanceDiscrepancy.status == DiscrepancyStatus.OPEN.value,
                )
            ).scalar_one()
            blocking_count = session.execute(
                select(func.count(FinanceDiscrepancy.id)).where(
                    FinanceDiscrepancy.company_id == company_id,
                    FinanceDiscrepancy.run_id.in_(run_ids),
                    FinanceDiscrepancy.status == DiscrepancyStatus.OPEN.value,
                    FinanceDiscrepancy.severity == DiscrepancySeverity.BLOCKING.value,
                )
            ).scalar_one()
            return counts, int(open_count), int(blocking_count)

    def list_evidence(
        self,
        *,
        company_id: UUID,
        run_id: UUID,
        limit: int,
        offset: int,
    ) -> EvidencePage:
        with self._database.transaction() as session:
            apply_company_context(session, company_id)
            exists = session.execute(
                select(FinanceReconciliationRun.id).where(
                    FinanceReconciliationRun.company_id == company_id,
                    FinanceReconciliationRun.id == run_id,
                )
            ).scalar_one_or_none()
            if exists is None:
                raise NotFoundError("The reconciliation run does not exist.")
            total = session.execute(
                select(func.count(FinanceReconciliationEvidence.id)).where(
                    FinanceReconciliationEvidence.company_id == company_id,
                    FinanceReconciliationEvidence.run_id == run_id,
                )
            ).scalar_one()
            rows = session.execute(
                select(FinanceReconciliationEvidence, FinanceSourceReference)
                .join(
                    FinanceSourceReference,
                    (
                        FinanceSourceReference.id
                        == FinanceReconciliationEvidence.finance_source_reference_id
                    )
                    & (
                        FinanceSourceReference.company_id
                        == FinanceReconciliationEvidence.company_id
                    )
                    & (FinanceSourceReference.run_id == FinanceReconciliationEvidence.run_id),
                )
                .where(
                    FinanceReconciliationEvidence.company_id == company_id,
                    FinanceReconciliationEvidence.run_id == run_id,
                )
                .order_by(
                    FinanceReconciliationEvidence.created_at,
                    FinanceReconciliationEvidence.id,
                )
                .limit(limit)
                .offset(offset)
            ).all()
            items = tuple(
                EvidenceRecord(
                    id=item.id,
                    source_entity_type=item.source_entity_type,
                    source_entity_id=item.source_entity_id,
                    finance_source_reference_id=item.finance_source_reference_id,
                    source_type=reference.source_type,
                    source_reference=reference.source_reference,
                    currency=item.currency,
                    amount=item.amount,
                    as_of=item.as_of,
                    data_through=item.data_through,
                    provenance=dict(item.provenance),
                    verification_status=item.verification_status,
                    notes=item.notes,
                    created_by=item.created_by,
                    created_at=item.created_at,
                    verified_by=item.verified_by,
                    verified_at=item.verified_at,
                )
                for item, reference in rows
            )
            return EvidencePage(items=items, total=int(total))

    def add_evidence(
        self,
        session: Session,
        *,
        meta: WriteMeta,
        run_id: UUID,
        expected_version: int,
        source_entity_type: str,
        source_entity_id: UUID,
        finance_source_reference_id: UUID,
        notes: str | None,
    ) -> RunRecord:
        run = session.execute(
            select(FinanceReconciliationRun)
            .where(
                FinanceReconciliationRun.company_id == meta.company_id,
                FinanceReconciliationRun.id == run_id,
            )
            .with_for_update()
        ).scalar_one_or_none()
        if run is None:
            raise NotFoundError("The reconciliation run does not exist.")
        if run.version != expected_version:
            raise VersionConflictError(
                "The reconciliation run was modified by another request.",
                details={"current_version": run.version},
                headers={"ETag": f'"v{run.version}"'},
            )
        if run.status == ReconciliationStatus.VERIFIED.value:
            raise ReconciliationStateError(
                "A verified reconciliation is immutable; create a new run instead."
            )
        if source_entity_type not in _TERMINAL_SOURCE_ENTITY_TYPES:
            raise ReconciliationEvidenceInvalidError(
                "Only a sales order, purchase order or shipment cost can carry evidence.",
                details={"supported_source_entity_types": sorted(_TERMINAL_SOURCE_ENTITY_TYPES)},
            )

        reference = session.execute(
            select(FinanceSourceReference).where(
                FinanceSourceReference.company_id == meta.company_id,
                FinanceSourceReference.run_id == run.id,
                FinanceSourceReference.id == finance_source_reference_id,
            )
        ).scalar_one_or_none()
        if reference is None:
            raise NotFoundError(
                "The Finance source reference does not exist in this run.",
                details={
                    "run_id": str(run.id),
                    "finance_source_reference_id": str(finance_source_reference_id),
                },
            )
        if not reference.is_transaction_level:
            raise ReconciliationSourceNotMatchableError(
                details={"source_type": reference.source_type}
            )
        if reference.observed_amount is None:
            raise ReconciliationEvidenceInvalidError(
                "This Finance source reference has no observed amount."
            )
        if canonical_currency(reference.currency) != run.currency:
            raise ReconciliationCurrencyMismatchError(
                details={
                    "run_currency": run.currency,
                    "source_currency": canonical_currency(reference.currency),
                }
            )
        existing = session.execute(
            select(FinanceReconciliationEvidence.id).where(
                FinanceReconciliationEvidence.company_id == meta.company_id,
                FinanceReconciliationEvidence.run_id == run.id,
                FinanceReconciliationEvidence.finance_source_reference_id == reference.id,
            )
        ).scalar_one_or_none()
        if existing is not None:
            raise ReconciliationDuplicateEvidenceError(details={"evidence_id": str(existing)})

        expected_amount, entity_currency, entity_context = self._expected_amount_for_entity(
            session,
            company_id=meta.company_id,
            run=run,
            source_entity_type=source_entity_type,
            source_entity_id=source_entity_id,
        )
        if expected_amount is None:
            raise ReconciliationEvidenceInvalidError(
                "The Commerce source has no comparable monetary amount.",
                details={"source_entity_id": str(source_entity_id)},
            )
        if canonical_currency(entity_currency) != run.currency:
            raise ReconciliationCurrencyMismatchError(
                details={
                    "run_currency": run.currency,
                    "source_currency": canonical_currency(entity_currency),
                }
            )
        observed_amount = quantize_money(reference.observed_amount)
        expected = quantize_money(expected_amount)
        mismatch = observed_amount != expected
        now = datetime.now(tz=UTC)
        provenance = {
            "evidence_kind": "explicit_operator_link",
            "finance_source_id": reference.source_reference,
            "finance_source_type": reference.source_type,
            "finance_company_id": run.finance_company_id,
            "finance_currency": run.finance_currency,
            "source_entity_type": source_entity_type,
            "source_entity_id": str(source_entity_id),
            "expected_amount": str(expected),
            "observed_amount": str(observed_amount),
            "matching_keys": ["finance_source_id", "explicit_operator_decision"],
            "amount_check": "MISMATCH" if mismatch else "EXACT",
            **entity_context,
        }
        evidence = FinanceReconciliationEvidence(
            company_id=meta.company_id,
            run_id=run.id,
            finance_source_reference_id=reference.id,
            source_entity_type=source_entity_type,
            source_entity_id=source_entity_id,
            currency=run.currency,
            amount=observed_amount,
            as_of=run.as_of,
            data_through=run.data_through,
            provenance=_json_safe(provenance),
            verification_status=EvidenceVerificationStatus.UNVERIFIED.value,
            notes=normalise_notes(notes),
            created_by=meta.actor_id,
            created_at=now,
        )
        session.add(evidence)
        session.flush()

        if mismatch:
            draft = DiscrepancyDraft(
                code=DiscrepancyCode.AMOUNT_MISMATCH,
                severity=DiscrepancySeverity.BLOCKING,
                title="Linked Finance amount differs from the Commerce source",
                detail=(
                    "The explicit link is preserved for review, but the amounts do "
                    "not agree. Commerce does not alter either value."
                ),
                expected={"amount": str(expected), "currency": run.currency},
                observed={"amount": str(observed_amount), "currency": run.currency},
                source_entity_type=source_entity_type,
                source_entity_id=source_entity_id,
                finance_source_reference_id=reference.id,
            )
            self._insert_discrepancy_drafts(session, run=run, drafts=(draft,), now=now)
        self._resolve_missing_reference_discrepancy(
            session, meta=meta, run=run, evidence_id=evidence.id, now=now
        )

        open_blocking = session.execute(
            select(func.count(FinanceDiscrepancy.id)).where(
                FinanceDiscrepancy.company_id == meta.company_id,
                FinanceDiscrepancy.run_id == run.id,
                FinanceDiscrepancy.status == DiscrepancyStatus.OPEN.value,
                FinanceDiscrepancy.severity == DiscrepancySeverity.BLOCKING.value,
            )
        ).scalar_one()
        commercial_complete = _decimal(
            run.source_snapshot.get("commercial", {}).get("metrics", {}).get("completeness_score")
        ) == Decimal("100.00")
        if run.status != ReconciliationStatus.DISPUTED.value:
            if not commercial_complete:
                run.status = ReconciliationStatus.INCOMPLETE.value
            elif mismatch or int(open_blocking) > 0:
                run.status = ReconciliationStatus.POTENTIAL_MATCH.value
            else:
                run.status = ReconciliationStatus.MATCHED_EVIDENCE.value
        run.version += 1
        run.updated_at = now
        snapshot = dict(run.source_snapshot)
        finance_snapshot = dict(snapshot.get("finance", {}))
        finance_snapshot["evidence_linked"] = True
        finance_snapshot["latest_evidence_at"] = now.isoformat()
        snapshot["finance"] = finance_snapshot
        run.source_snapshot = snapshot
        record_audit(
            session,
            action=AuditAction.FINANCE_EVIDENCE_LINKED,
            outcome=AuditOutcome.SUCCESS,
            actor_id=meta.actor_id,
            company_id=meta.company_id,
            request_id=meta.request_id,
            ip_address=meta.ip_address,
            user_agent=meta.user_agent,
            resource_type="finance_reconciliation_evidence",
            resource_id=str(evidence.id),
            details={
                "run_id": str(run.id),
                "source_entity_type": source_entity_type,
                "source_entity_id": str(source_entity_id),
                "finance_source_type": reference.source_type,
                "finance_source_id": reference.source_reference,
                "amount_match": not mismatch,
                "run_status": run.status,
            },
        )
        session.flush()
        return _run_record(session, company_id=meta.company_id, run_id=run.id)

    def review(
        self,
        session: Session,
        *,
        meta: WriteMeta,
        run_id: UUID,
        expected_version: int,
        decision: str,
        notes: str,
    ) -> RunRecord:
        run = session.execute(
            select(FinanceReconciliationRun)
            .where(
                FinanceReconciliationRun.company_id == meta.company_id,
                FinanceReconciliationRun.id == run_id,
            )
            .with_for_update()
        ).scalar_one_or_none()
        if run is None:
            raise NotFoundError("The reconciliation run does not exist.")
        if run.version != expected_version:
            raise VersionConflictError(
                "The reconciliation run was modified by another request.",
                details={"current_version": run.version},
                headers={"ETag": f'"v{run.version}"'},
            )
        if meta.actor_id == run.created_by:
            raise ForbiddenError(
                "The reconciliation creator cannot act as its financial reviewer.",
                details={"reason": "SEPARATION_OF_DUTIES"},
            )
        cleaned_notes = normalise_notes(notes)
        if cleaned_notes is None or len(cleaned_notes) < 3:
            raise BadRequestError("A review note of at least 3 characters is required.")
        previous = run.status
        now = datetime.now(tz=UTC)
        try:
            resolved_decision = ReviewDecision(decision)
        except ValueError as exc:
            raise BadRequestError("Unknown review decision.") from exc

        evidence_rows = list(
            session.execute(
                select(FinanceReconciliationEvidence).where(
                    FinanceReconciliationEvidence.company_id == meta.company_id,
                    FinanceReconciliationEvidence.run_id == run.id,
                )
            ).scalars()
        )
        if resolved_decision is ReviewDecision.CONFIRM:
            if previous != ReconciliationStatus.MATCHED_EVIDENCE.value:
                raise ReconciliationNotVerifiableError(
                    "Only MATCHED_EVIDENCE can be confirmed.",
                    details={"status": previous},
                )
            if not evidence_rows:
                raise ReconciliationNotVerifiableError("No evidence is linked.")
            if not any(
                row.source_entity_type == SourceEntityType.SALES_ORDER.value
                for row in evidence_rows
            ):
                raise ReconciliationNotVerifiableError(
                    "At least one evidence link must identify the accepted sales order."
                )
            blocking = session.execute(
                select(func.count(FinanceDiscrepancy.id)).where(
                    FinanceDiscrepancy.company_id == meta.company_id,
                    FinanceDiscrepancy.run_id == run.id,
                    FinanceDiscrepancy.status == DiscrepancyStatus.OPEN.value,
                    FinanceDiscrepancy.severity == DiscrepancySeverity.BLOCKING.value,
                )
            ).scalar_one()
            if int(blocking) > 0:
                raise ReconciliationNotVerifiableError(
                    "Open blocking discrepancies must be resolved before verification.",
                    details={"open_blocking_discrepancies": int(blocking)},
                )
            for evidence in evidence_rows:
                evidence.verification_status = EvidenceVerificationStatus.VERIFIED.value
                evidence.verified_by = meta.actor_id
                evidence.verified_at = now
            new_status = ReconciliationStatus.VERIFIED.value
        elif resolved_decision is ReviewDecision.DISPUTE:
            if previous == ReconciliationStatus.DISPUTED.value:
                raise ReconciliationStateError("The run is already disputed.")
            new_status = ReconciliationStatus.DISPUTED.value
        else:
            if previous == ReconciliationStatus.VERIFIED.value:
                raise ReconciliationStateError(
                    "A verified run cannot request changes; create a new run."
                )
            new_status = previous

        run.status = new_status
        run.version += 1
        run.updated_at = now
        review = FinanceReconciliationReview(
            company_id=meta.company_id,
            run_id=run.id,
            reviewer_id=meta.actor_id,
            decision=resolved_decision.value,
            previous_status=previous,
            new_status=new_status,
            notes=cleaned_notes,
            created_at=now,
        )
        session.add(review)
        session.flush()
        record_audit(
            session,
            action=AuditAction.FINANCE_RECONCILIATION_REVIEWED,
            outcome=AuditOutcome.SUCCESS,
            actor_id=meta.actor_id,
            company_id=meta.company_id,
            request_id=meta.request_id,
            ip_address=meta.ip_address,
            user_agent=meta.user_agent,
            resource_type="finance_reconciliation_run",
            resource_id=str(run.id),
            details={
                "review_id": str(review.id),
                "decision": resolved_decision.value,
                "previous_status": previous,
                "new_status": new_status,
                "separate_reviewer": True,
            },
        )
        session.flush()
        return _run_record(session, company_id=meta.company_id, run_id=run.id)

    @staticmethod
    def _expected_amount_for_entity(
        session: Session,
        *,
        company_id: UUID,
        run: FinanceReconciliationRun,
        source_entity_type: str,
        source_entity_id: UUID,
    ) -> tuple[Decimal | None, str, dict[str, Any]]:
        if source_entity_type == SourceEntityType.SALES_ORDER.value:
            order = session.execute(
                select(SalesOrder).where(
                    SalesOrder.company_id == company_id,
                    SalesOrder.id == source_entity_id,
                )
            ).scalar_one_or_none()
            if order is None or order.id != run.sales_order_id:
                raise ReconciliationEvidenceInvalidError(
                    "The sales order does not belong to this reconciliation run."
                )
            return (
                order.order_total,
                order.currency,
                {"order_number": order.order_number},
            )
        if source_entity_type == SourceEntityType.PURCHASE_ORDER.value:
            purchase_order = session.execute(
                select(PurchaseOrder).where(
                    PurchaseOrder.company_id == company_id,
                    PurchaseOrder.id == source_entity_id,
                    PurchaseOrder.sales_order_id == run.sales_order_id,
                )
            ).scalar_one_or_none()
            if purchase_order is None:
                raise ReconciliationEvidenceInvalidError(
                    "The purchase order does not belong to this sales order."
                )
            return (
                purchase_order.total_cost,
                purchase_order.currency,
                {"po_number": purchase_order.po_number},
            )
        if source_entity_type == SourceEntityType.SHIPMENT_COST.value:
            row = session.execute(
                select(ShipmentCost, Shipment)
                .join(
                    Shipment,
                    (Shipment.id == ShipmentCost.shipment_id)
                    & (Shipment.company_id == ShipmentCost.company_id),
                )
                .where(
                    ShipmentCost.company_id == company_id,
                    ShipmentCost.id == source_entity_id,
                    Shipment.sales_order_id == run.sales_order_id,
                )
            ).one_or_none()
            if row is None:
                raise ReconciliationEvidenceInvalidError(
                    "The shipment cost does not belong to this sales order."
                )
            cost, shipment = row
            return (
                cost.amount,
                cost.currency,
                {
                    "shipment_number": shipment.shipment_number,
                    "cost_type": cost.cost_type,
                    "cost_reference": cost.reference,
                },
            )
        raise ReconciliationEvidenceInvalidError(
            "That source entity type cannot carry monetary evidence."
        )

    @staticmethod
    def _resolve_missing_reference_discrepancy(
        session: Session,
        *,
        meta: WriteMeta,
        run: FinanceReconciliationRun,
        evidence_id: UUID,
        now: datetime,
    ) -> None:
        rows = list(
            session.execute(
                select(FinanceDiscrepancy)
                .where(
                    FinanceDiscrepancy.company_id == meta.company_id,
                    FinanceDiscrepancy.run_id == run.id,
                    FinanceDiscrepancy.code == DiscrepancyCode.MISSING_FINANCE_REFERENCE.value,
                    FinanceDiscrepancy.status == DiscrepancyStatus.OPEN.value,
                )
                .with_for_update()
            ).scalars()
        )
        for row in rows:
            row.status = DiscrepancyStatus.RESOLVED.value
            row.resolution_notes = f"Resolved by explicit evidence link {evidence_id}."
            row.resolved_by = meta.actor_id
            row.resolved_at = now
            row.updated_at = now
            row.version += 1
            record_audit(
                session,
                action=AuditAction.FINANCE_DISCREPANCY_RESOLVED,
                outcome=AuditOutcome.SUCCESS,
                actor_id=meta.actor_id,
                company_id=meta.company_id,
                request_id=meta.request_id,
                ip_address=meta.ip_address,
                user_agent=meta.user_agent,
                resource_type="finance_discrepancy",
                resource_id=str(row.id),
                details={
                    "run_id": str(run.id),
                    "code": row.code,
                    "resolution": "AUTOMATIC_ON_EXPLICIT_EVIDENCE",
                    "evidence_id": str(evidence_id),
                },
            )
        session.flush()

    def list_discrepancies(
        self,
        *,
        company_id: UUID,
        filters: DiscrepancyFilters,
        limit: int,
        offset: int,
    ) -> DiscrepancyPage:
        with self._database.transaction() as session:
            apply_company_context(session, company_id)
            query = (
                select(FinanceDiscrepancy)
                .join(
                    FinanceReconciliationRun,
                    (FinanceReconciliationRun.id == FinanceDiscrepancy.run_id)
                    & (FinanceReconciliationRun.company_id == FinanceDiscrepancy.company_id),
                )
                .where(FinanceDiscrepancy.company_id == company_id)
            )
            if filters.run_id:
                query = query.where(FinanceDiscrepancy.run_id == filters.run_id)
            if filters.code:
                query = query.where(FinanceDiscrepancy.code == filters.code)
            if filters.severity:
                query = query.where(FinanceDiscrepancy.severity == filters.severity)
            if filters.status:
                query = query.where(FinanceDiscrepancy.status == filters.status)
            if filters.currency:
                query = query.where(
                    FinanceReconciliationRun.currency == canonical_currency(filters.currency)
                )
            total = session.execute(
                select(func.count()).select_from(query.order_by(None).subquery())
            ).scalar_one()
            rows = list(
                session.execute(
                    query.order_by(
                        FinanceDiscrepancy.created_at.desc(),
                        FinanceDiscrepancy.id.desc(),
                    )
                    .limit(limit)
                    .offset(offset)
                ).scalars()
            )
            return DiscrepancyPage(
                items=tuple(_discrepancy_record(row) for row in rows),
                total=int(total),
            )

    def get_discrepancy(self, *, company_id: UUID, discrepancy_id: UUID) -> DiscrepancyRecord:
        with self._database.transaction() as session:
            apply_company_context(session, company_id)
            row = session.execute(
                select(FinanceDiscrepancy).where(
                    FinanceDiscrepancy.company_id == company_id,
                    FinanceDiscrepancy.id == discrepancy_id,
                )
            ).scalar_one_or_none()
            if row is None:
                raise NotFoundError("The discrepancy does not exist.")
            return _discrepancy_record(row)

    def resolve_discrepancy(
        self,
        session: Session,
        *,
        meta: WriteMeta,
        discrepancy_id: UUID,
        expected_version: int,
        notes: str,
    ) -> DiscrepancyRecord:
        row = session.execute(
            select(FinanceDiscrepancy)
            .where(
                FinanceDiscrepancy.company_id == meta.company_id,
                FinanceDiscrepancy.id == discrepancy_id,
            )
            .with_for_update()
        ).scalar_one_or_none()
        if row is None:
            raise NotFoundError("The discrepancy does not exist.")
        if row.version != expected_version:
            raise VersionConflictError(
                "The discrepancy was modified by another request.",
                details={"current_version": row.version},
                headers={"ETag": f'"v{row.version}"'},
            )
        if row.status != DiscrepancyStatus.OPEN.value:
            raise ReconciliationStateError("Only an open discrepancy can be resolved.")
        cleaned_notes = normalise_notes(notes)
        if cleaned_notes is None or len(cleaned_notes) < 3:
            raise BadRequestError("A resolution note of at least 3 characters is required.")
        now = datetime.now(tz=UTC)
        row.status = DiscrepancyStatus.RESOLVED.value
        row.resolution_notes = cleaned_notes
        row.resolved_by = meta.actor_id
        row.resolved_at = now
        row.updated_at = now
        row.version += 1
        record_audit(
            session,
            action=AuditAction.FINANCE_DISCREPANCY_RESOLVED,
            outcome=AuditOutcome.SUCCESS,
            actor_id=meta.actor_id,
            company_id=meta.company_id,
            request_id=meta.request_id,
            ip_address=meta.ip_address,
            user_agent=meta.user_agent,
            resource_type="finance_discrepancy",
            resource_id=str(row.id),
            details={
                "run_id": str(row.run_id),
                "code": row.code,
                "severity": row.severity,
                "resolution": "REVIEWER_RESOLVED",
            },
        )
        session.flush()
        return _discrepancy_record(row)

    def order_finance_view(self, *, company_id: UUID, sales_order_id: UUID) -> OrderFinanceRecord:
        with self._database.transaction() as session:
            apply_company_context(session, company_id)
            facts, order_number, customer_name = _load_facts(
                session, company_id=company_id, sales_order_id=sales_order_id
            )
            latest = session.execute(
                select(FinanceReconciliationRun)
                .where(
                    FinanceReconciliationRun.company_id == company_id,
                    FinanceReconciliationRun.sales_order_id == sales_order_id,
                )
                .order_by(
                    FinanceReconciliationRun.created_at.desc(),
                    FinanceReconciliationRun.id.desc(),
                )
                .limit(1)
            ).scalar_one_or_none()
            as_of = latest.as_of if latest is not None else date.today()
            data_through = latest.data_through if latest is not None else None
            analysis = analyse(
                facts,
                as_of=as_of,
                finance_data_through=data_through,
            )
            return OrderFinanceRecord(
                sales_order_id=facts.sales_order_id,
                order_number=order_number,
                customer_name=customer_name,
                currency=canonical_currency(facts.currency),
                facts=facts,
                metrics=analysis.metrics,
                classifications=analysis.classifications,
                limitations=analysis.limitations,
                evidence_gaps=analysis.discrepancies,
                latest_run_id=latest.id if latest is not None else None,
                latest_run_status=latest.status if latest is not None else None,
                latest_run_at=latest.created_at if latest is not None else None,
            )

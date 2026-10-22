"""Shipments, partial allocations and delivery-derived fulfilment.

A shipment never "completes" an order by itself. Fulfilment is computed from
``shipment_item`` quantities of shipments that reached ``DELIVERED``, so five
tonnes against a twenty-tonne line leaves fifteen tonnes outstanding. Cancelling
a shipment releases its allocation, because only non-cancelled shipments count.

Evidence gates live in :mod:`app.services.order_state`; this module owns
persistence, the timeline and the derivation of the order's fulfilment state.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import UTC, datetime
from decimal import Decimal
from uuid import UUID, uuid4

from sqlalchemy import and_, func, or_, select, tuple_
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app.core.errors import (
    BadRequestError,
    ConflictError,
    NotFoundError,
    ReasonRequiredError,
    VersionConflictError,
)
from app.db.engine import Database
from app.db.models import (
    AuditAction,
    AuditOutcome,
    CostStage,
    PurchaseOrder,
    SalesOrder,
    SalesOrderItem,
    SalesOrderStatus,
    SalesOrderTransition,
    Shipment,
    ShipmentCost,
    ShipmentEvent,
    ShipmentEventType,
    ShipmentItem,
    ShipmentReference,
    ShipmentStatus,
    TransportMode,
)
from app.db.tenant import apply_company_context
from app.services.audit import record_audit
from app.services.order_state import (
    STATUS_EVENT_TYPES,
    allowed_shipment_targets,
    ensure_tracking_source,
    is_delayed,
    validate_allocation,
    validate_shipment_transition,
)
from app.services.pagination import decode_cursor, encode_cursor
from app.services.trade_meta import WriteMeta, clean_optional, escape_like

_COST_TYPES = (
    "FREIGHT",
    "INSURANCE",
    "HANDLING",
    "CUSTOMS_BROKERAGE",
    "DOMESTIC_TRANSPORT",
    "OTHER",
)
_REFERENCE_TYPES = (
    "BOOKING",
    "CONTAINER",
    "BILL_OF_LADING",
    "AIR_WAYBILL",
    "CMR",
    "TRACKING",
    "OTHER",
)
_ACTIVE_ORDER_STATUSES = (
    SalesOrderStatus.CONFIRMED.value,
    SalesOrderStatus.IN_FULFILLMENT.value,
    SalesOrderStatus.FULFILLED.value,
)


@dataclass(frozen=True, slots=True)
class ShipmentItemRecord:
    id: UUID
    sales_order_item_id: UUID
    product_id: UUID
    sku: str
    description: str
    quantity: Decimal
    unit: str
    delivered_quantity: Decimal


@dataclass(frozen=True, slots=True)
class ShipmentEventRecord:
    id: UUID
    event_type: str
    occurred_at: datetime
    location: str | None
    notes: str | None
    evidence_reference: str | None
    tracking_source: str | None
    recorded_by: UUID
    recorded_at: datetime


@dataclass(frozen=True, slots=True)
class ShipmentReferenceRecord:
    id: UUID
    reference_type: str
    reference_value: str
    provenance: str
    created_at: datetime


@dataclass(frozen=True, slots=True)
class ShipmentCostRecord:
    id: UUID
    cost_type: str
    stage: str
    amount: Decimal
    currency: str
    reference: str
    notes: str | None
    recorded_at: datetime


@dataclass(frozen=True, slots=True)
class ShipmentRecord:
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
    items: tuple[ShipmentItemRecord, ...]
    events: tuple[ShipmentEventRecord, ...]
    references: tuple[ShipmentReferenceRecord, ...]
    costs: tuple[ShipmentCostRecord, ...]
    is_delayed: bool

    @property
    def allowed_transitions(self) -> tuple[str, ...]:
        return allowed_shipment_targets(self.status)


@dataclass(frozen=True, slots=True)
class ShipmentSummaryRecord:
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


@dataclass(frozen=True, slots=True)
class FulfilmentLine:
    sales_order_item_id: UUID
    sku: str
    unit: str
    ordered: Decimal
    allocated: Decimal
    delivered: Decimal
    remaining: Decimal


@dataclass(frozen=True, slots=True)
class FulfilmentSummary:
    sales_order_id: UUID
    order_number: str
    order_status: str
    lines: tuple[FulfilmentLine, ...]
    completion_ratio: Decimal
    fully_delivered: bool
    delivered_any: bool


@dataclass(frozen=True, slots=True)
class ShipmentFilters:
    search: str | None = None
    status: str | None = None
    sales_order_id: UUID | None = None
    transport_mode: str | None = None

    def as_fingerprint(self) -> dict[str, str | None]:
        return {
            "search": self.search,
            "status": self.status,
            "sales_order_id": str(self.sales_order_id) if self.sales_order_id else None,
            "transport_mode": self.transport_mode,
        }


@dataclass(frozen=True, slots=True)
class ShipmentPage:
    items: tuple[ShipmentSummaryRecord, ...]
    next_cursor: str | None


@dataclass(frozen=True, slots=True)
class PlanItem:
    sales_order_item_id: UUID
    quantity: Decimal


@dataclass(frozen=True, slots=True)
class PlanShipmentData:
    sales_order_id: UUID
    purchase_order_id: UUID | None
    transport_mode: str
    origin: str
    destination: str
    carrier: str | None
    forwarder: str | None
    planned_dispatch_at: datetime | None
    estimated_arrival_at: datetime | None
    tracking_reference: str | None
    tracking_source: str | None
    notes: str | None
    items: tuple[PlanItem, ...]


@dataclass(frozen=True, slots=True)
class TransitionShipmentData:
    target: str
    occurred_at: datetime | None
    location: str | None
    notes: str | None
    reason: str | None
    tracking_reference: str | None
    tracking_source: str | None
    evidence_reference: str | None
    delivery_evidence_reference: str | None


@dataclass(frozen=True, slots=True)
class EventData:
    event_type: str
    occurred_at: datetime
    location: str | None
    notes: str | None
    evidence_reference: str | None
    tracking_source: str | None


@dataclass(frozen=True, slots=True)
class CostData:
    cost_type: str
    stage: str
    amount: Decimal
    currency: str
    reference: str
    notes: str | None


@dataclass(frozen=True, slots=True)
class ReferenceData:
    reference_type: str
    reference_value: str
    provenance: str


def _quantity_maps(
    session: Session, *, company_id: UUID, sales_order_id: UUID
) -> tuple[dict[UUID, Decimal], dict[UUID, Decimal]]:
    """Allocated (live shipments) and delivered quantities per order line."""
    rows = session.execute(
        select(
            ShipmentItem.sales_order_item_id,
            Shipment.status,
            func.sum(ShipmentItem.quantity),
        )
        .join(
            Shipment,
            and_(
                Shipment.id == ShipmentItem.shipment_id,
                Shipment.company_id == ShipmentItem.company_id,
            ),
        )
        .where(
            ShipmentItem.company_id == company_id,
            Shipment.sales_order_id == sales_order_id,
        )
        .group_by(ShipmentItem.sales_order_item_id, Shipment.status)
    ).all()
    allocated: dict[UUID, Decimal] = {}
    delivered: dict[UUID, Decimal] = {}
    for item_id, status, quantity in rows:
        if status == ShipmentStatus.CANCELLED.value:
            continue
        allocated[item_id] = allocated.get(item_id, Decimal("0")) + quantity
        if status == ShipmentStatus.DELIVERED.value:
            delivered[item_id] = delivered.get(item_id, Decimal("0")) + quantity
    return allocated, delivered


def _fulfilment(
    session: Session, *, company_id: UUID, sales_order_id: UUID
) -> FulfilmentSummary:
    order = session.execute(
        select(SalesOrder).where(
            SalesOrder.id == sales_order_id,
            SalesOrder.company_id == company_id,
        )
    ).scalar_one_or_none()
    if order is None:
        raise NotFoundError("The sales order does not exist.")
    item_rows = list(
        session.execute(
            select(SalesOrderItem)
            .where(
                SalesOrderItem.company_id == company_id,
                SalesOrderItem.sales_order_id == order.id,
            )
            .order_by(SalesOrderItem.sku)
        ).scalars()
    )
    allocated, delivered = _quantity_maps(
        session, company_id=company_id, sales_order_id=order.id
    )
    lines: list[FulfilmentLine] = []
    ratios: list[Decimal] = []
    fully_delivered = True
    delivered_any = False
    for item in item_rows:
        delivered_qty = delivered.get(item.id, Decimal("0"))
        allocated_qty = allocated.get(item.id, Decimal("0"))
        if delivered_qty > 0:
            delivered_any = True
        if delivered_qty < item.quantity:
            fully_delivered = False
        ratios.append(min(delivered_qty / item.quantity, Decimal("1")))
        lines.append(
            FulfilmentLine(
                sales_order_item_id=item.id,
                sku=item.sku,
                unit=item.unit,
                ordered=item.quantity,
                allocated=allocated_qty,
                delivered=delivered_qty,
                remaining=max(item.quantity - delivered_qty, Decimal("0")),
            )
        )
    completion = (
        (sum(ratios, start=Decimal("0")) / len(ratios)).quantize(Decimal("0.0001"))
        if ratios
        else Decimal("0.0000")
    )
    return FulfilmentSummary(
        sales_order_id=order.id,
        order_number=order.order_number,
        order_status=order.status,
        lines=tuple(lines),
        completion_ratio=completion,
        fully_delivered=fully_delivered and bool(lines),
        delivered_any=delivered_any,
    )


def _shipment_records(
    session: Session, *, company_id: UUID, shipment: Shipment
) -> tuple[
    tuple[ShipmentItemRecord, ...],
    tuple[ShipmentEventRecord, ...],
    tuple[ShipmentReferenceRecord, ...],
    tuple[ShipmentCostRecord, ...],
]:
    item_rows = session.execute(
        select(ShipmentItem, SalesOrderItem.sku, SalesOrderItem.description)
        .join(
            SalesOrderItem,
            and_(
                SalesOrderItem.id == ShipmentItem.sales_order_item_id,
                SalesOrderItem.company_id == ShipmentItem.company_id,
            ),
        )
        .where(
            ShipmentItem.company_id == company_id,
            ShipmentItem.shipment_id == shipment.id,
        )
        .order_by(SalesOrderItem.sku)
    ).all()
    items = tuple(
        ShipmentItemRecord(
            id=row.id,
            sales_order_item_id=row.sales_order_item_id,
            product_id=row.product_id,
            sku=sku,
            description=description,
            quantity=row.quantity,
            unit=row.unit,
            delivered_quantity=(
                row.quantity if shipment.status == ShipmentStatus.DELIVERED.value else Decimal("0")
            ),
        )
        for row, sku, description in item_rows
    )
    events = tuple(
        ShipmentEventRecord(
            id=row.id,
            event_type=row.event_type,
            occurred_at=row.occurred_at,
            location=row.location,
            notes=row.notes,
            evidence_reference=row.evidence_reference,
            tracking_source=row.tracking_source,
            recorded_by=row.recorded_by,
            recorded_at=row.recorded_at,
        )
        for row in session.execute(
            select(ShipmentEvent)
            .where(
                ShipmentEvent.company_id == company_id,
                ShipmentEvent.shipment_id == shipment.id,
            )
            .order_by(ShipmentEvent.occurred_at, ShipmentEvent.recorded_at)
        ).scalars()
    )
    references = tuple(
        ShipmentReferenceRecord(
            id=row.id,
            reference_type=row.reference_type,
            reference_value=row.reference_value,
            provenance=row.provenance,
            created_at=row.created_at,
        )
        for row in session.execute(
            select(ShipmentReference)
            .where(
                ShipmentReference.company_id == company_id,
                ShipmentReference.shipment_id == shipment.id,
            )
            .order_by(ShipmentReference.created_at)
        ).scalars()
    )
    costs = tuple(
        ShipmentCostRecord(
            id=row.id,
            cost_type=row.cost_type,
            stage=row.stage,
            amount=row.amount,
            currency=row.currency,
            reference=row.reference,
            notes=row.notes,
            recorded_at=row.recorded_at,
        )
        for row in session.execute(
            select(ShipmentCost)
            .where(
                ShipmentCost.company_id == company_id,
                ShipmentCost.shipment_id == shipment.id,
            )
            .order_by(ShipmentCost.recorded_at)
        ).scalars()
    )
    return items, events, references, costs


def _load(session: Session, *, company_id: UUID, shipment_id: UUID) -> ShipmentRecord:
    row = session.execute(
        select(Shipment, SalesOrder.order_number)
        .join(
            SalesOrder,
            and_(
                SalesOrder.id == Shipment.sales_order_id,
                SalesOrder.company_id == Shipment.company_id,
            ),
        )
        .where(Shipment.id == shipment_id, Shipment.company_id == company_id)
    ).one_or_none()
    if row is None:
        raise NotFoundError("The shipment does not exist.")
    shipment, order_number = row
    items, events, references, costs = _shipment_records(
        session, company_id=company_id, shipment=shipment
    )
    now = datetime.now(tz=UTC)
    return ShipmentRecord(
        id=shipment.id,
        company_id=shipment.company_id,
        shipment_number=shipment.shipment_number,
        sales_order_id=shipment.sales_order_id,
        order_number=order_number,
        purchase_order_id=shipment.purchase_order_id,
        transport_mode=shipment.transport_mode,
        origin=shipment.origin,
        destination=shipment.destination,
        carrier=shipment.carrier,
        forwarder=shipment.forwarder,
        planned_dispatch_at=shipment.planned_dispatch_at,
        actual_dispatch_at=shipment.actual_dispatch_at,
        estimated_arrival_at=shipment.estimated_arrival_at,
        actual_arrival_at=shipment.actual_arrival_at,
        delivered_at=shipment.delivered_at,
        status=shipment.status,
        tracking_reference=shipment.tracking_reference,
        tracking_source=shipment.tracking_source,
        delivery_evidence_reference=shipment.delivery_evidence_reference,
        delay_reason=shipment.delay_reason,
        cancellation_reason=shipment.cancellation_reason,
        notes=shipment.notes,
        version=shipment.version,
        created_at=shipment.created_at,
        updated_at=shipment.updated_at,
        items=items,
        events=events,
        references=references,
        costs=costs,
        is_delayed=is_delayed(
            status=shipment.status,
            estimated_arrival_at=shipment.estimated_arrival_at,
            delivered_at=shipment.delivered_at,
            now=now,
        ),
    )


class ShipmentService:
    """Planning, movement, evidence, costs and delivery-derived fulfilment."""

    def __init__(self, database: Database) -> None:
        self._database = database

    # ------------------------------------------------------------------ reads
    def list(
        self,
        *,
        company_id: UUID,
        filters: ShipmentFilters,
        limit: int,
        cursor: str | None,
    ) -> ShipmentPage:
        with self._database.transaction() as session:
            apply_company_context(session, company_id)
            query = (
                select(Shipment, SalesOrder.order_number)
                .join(
                    SalesOrder,
                    and_(
                        SalesOrder.id == Shipment.sales_order_id,
                        SalesOrder.company_id == Shipment.company_id,
                    ),
                )
                .where(Shipment.company_id == company_id)
            )
            if filters.status:
                query = query.where(Shipment.status == filters.status)
            if filters.sales_order_id:
                query = query.where(Shipment.sales_order_id == filters.sales_order_id)
            if filters.transport_mode:
                query = query.where(Shipment.transport_mode == filters.transport_mode)
            if filters.search:
                term = f"%{escape_like(filters.search.lower())}%"
                query = query.where(
                    or_(
                        func.lower(Shipment.shipment_number).like(term, escape="\\"),
                        func.lower(Shipment.carrier).like(term, escape="\\"),
                        func.lower(Shipment.destination).like(term, escape="\\"),
                        func.lower(SalesOrder.order_number).like(term, escape="\\"),
                    )
                )
            if cursor:
                page_cursor = decode_cursor(cursor, filters=filters.as_fingerprint())
                query = query.where(
                    tuple_(Shipment.created_at, Shipment.id)
                    < tuple_(page_cursor.created_at, page_cursor.row_id)
                )
            rows = session.execute(
                query.order_by(Shipment.created_at.desc(), Shipment.id.desc()).limit(limit + 1)
            ).all()
            has_more = len(rows) > limit
            visible = rows[:limit]
            now = datetime.now(tz=UTC)
            items = tuple(
                ShipmentSummaryRecord(
                    id=shipment.id,
                    company_id=shipment.company_id,
                    shipment_number=shipment.shipment_number,
                    sales_order_id=shipment.sales_order_id,
                    order_number=order_number,
                    transport_mode=shipment.transport_mode,
                    origin=shipment.origin,
                    destination=shipment.destination,
                    carrier=shipment.carrier,
                    forwarder=shipment.forwarder,
                    status=shipment.status,
                    estimated_arrival_at=shipment.estimated_arrival_at,
                    actual_dispatch_at=shipment.actual_dispatch_at,
                    delivered_at=shipment.delivered_at,
                    tracking_reference=shipment.tracking_reference,
                    version=shipment.version,
                    updated_at=shipment.updated_at,
                    is_delayed=is_delayed(
                        status=shipment.status,
                        estimated_arrival_at=shipment.estimated_arrival_at,
                        delivered_at=shipment.delivered_at,
                        now=now,
                    ),
                )
                for shipment, order_number in visible
            )
            next_cursor = None
            if has_more and visible:
                last = visible[-1][0]
                next_cursor = encode_cursor(
                    created_at=last.created_at,
                    row_id=last.id,
                    filters=filters.as_fingerprint(),
                )
            return ShipmentPage(items=items, next_cursor=next_cursor)

    def get(self, *, company_id: UUID, shipment_id: UUID) -> ShipmentRecord:
        with self._database.transaction() as session:
            apply_company_context(session, company_id)
            return _load(session, company_id=company_id, shipment_id=shipment_id)

    def fulfilment(self, *, company_id: UUID, sales_order_id: UUID) -> FulfilmentSummary:
        with self._database.transaction() as session:
            apply_company_context(session, company_id)
            return _fulfilment(
                session, company_id=company_id, sales_order_id=sales_order_id
            )

    # ----------------------------------------------------------------- writes
    def plan(
        self, session: Session, *, meta: WriteMeta, data: PlanShipmentData
    ) -> ShipmentRecord:
        order = session.execute(
            select(SalesOrder)
            .where(
                SalesOrder.id == data.sales_order_id,
                SalesOrder.company_id == meta.company_id,
            )
            .with_for_update()
        ).scalar_one_or_none()
        if order is None:
            raise NotFoundError("The sales order does not exist.")
        if order.status not in (
            SalesOrderStatus.CONFIRMED.value,
            SalesOrderStatus.IN_FULFILLMENT.value,
        ):
            raise ConflictError(
                "Only a confirmed or in-fulfilment order can receive a shipment.",
                details={"status": order.status, "reason": "ORDER_NOT_SHIPPABLE"},
            )
        try:
            mode = TransportMode(data.transport_mode).value
        except ValueError as exc:
            raise BadRequestError(
                "Unknown transport mode.",
                details=[
                    {
                        "field": "transport_mode",
                        "message": "Use SEA, AIR, ROAD, RAIL or MULTIMODAL.",
                        "type": "value_error",
                    }
                ],
            ) from exc

        origin = " ".join(data.origin.split())
        destination = " ".join(data.destination.split())
        if not 2 <= len(origin) <= 160 or not 2 <= len(destination) <= 160:
            raise BadRequestError("Origin and destination must be 2-160 characters.")

        if data.purchase_order_id is not None:
            purchase_order = session.execute(
                select(PurchaseOrder).where(
                    PurchaseOrder.id == data.purchase_order_id,
                    PurchaseOrder.company_id == meta.company_id,
                )
            ).scalar_one_or_none()
            if purchase_order is None or purchase_order.sales_order_id != order.id:
                raise BadRequestError(
                    "The purchase order does not belong to this sales order.",
                    details={"field": "purchase_order_id"},
                )

        if not data.items:
            raise BadRequestError("A shipment needs at least one line.")
        item_ids = [line.sales_order_item_id for line in data.items]
        if len(set(item_ids)) != len(item_ids):
            raise BadRequestError("Each order line may appear only once per shipment.")

        item_rows = {
            item.id: item
            for item in session.execute(
                select(SalesOrderItem).where(
                    SalesOrderItem.company_id == meta.company_id,
                    SalesOrderItem.sales_order_id == order.id,
                )
            ).scalars()
        }
        allocated, _delivered = _quantity_maps(
            session, company_id=meta.company_id, sales_order_id=order.id
        )
        checked: list[tuple[SalesOrderItem, Decimal]] = []
        for line in data.items:
            item = item_rows.get(line.sales_order_item_id)
            if item is None:
                raise BadRequestError(
                    "The shipment line does not belong to this sales order.",
                    details={"sales_order_item_id": str(line.sales_order_item_id)},
                )
            validate_allocation(
                ordered=item.quantity,
                already_allocated=allocated.get(item.id, Decimal("0")),
                requested=line.quantity,
                order_unit=item.unit,
                unit=item.unit,
            )
            checked.append((item, line.quantity))

        tracking_source = ensure_tracking_source(data.tracking_source)
        now = datetime.now(tz=UTC)
        shipment = Shipment(
            company_id=meta.company_id,
            shipment_number=self._generate_number(now),
            sales_order_id=order.id,
            purchase_order_id=data.purchase_order_id,
            transport_mode=mode,
            origin=origin,
            destination=destination,
            carrier=clean_optional(data.carrier),
            forwarder=clean_optional(data.forwarder),
            planned_dispatch_at=_aware(data.planned_dispatch_at),
            estimated_arrival_at=_aware(data.estimated_arrival_at),
            status=ShipmentStatus.PLANNED.value,
            tracking_reference=clean_optional(data.tracking_reference),
            tracking_source=tracking_source,
            notes=clean_optional(data.notes),
            created_by=meta.actor_id,
            created_at=now,
            updated_at=now,
        )
        session.add(shipment)
        session.flush()

        for item, quantity in checked:
            session.add(
                ShipmentItem(
                    company_id=meta.company_id,
                    shipment_id=shipment.id,
                    sales_order_item_id=item.id,
                    product_id=item.product_id,
                    quantity=quantity,
                    unit=item.unit,
                    created_at=now,
                )
            )
        session.add(
            ShipmentEvent(
                company_id=meta.company_id,
                shipment_id=shipment.id,
                event_type=ShipmentEventType.PLANNED.value,
                occurred_at=now,
                location=origin,
                notes=clean_optional(data.notes),
                tracking_source=tracking_source,
                recorded_by=meta.actor_id,
                recorded_at=now,
            )
        )
        session.flush()
        record_audit(
            session,
            action=AuditAction.SHIPMENT_CREATED,
            outcome=AuditOutcome.SUCCESS,
            actor_id=meta.actor_id,
            company_id=meta.company_id,
            request_id=meta.request_id,
            ip_address=meta.ip_address,
            user_agent=meta.user_agent,
            resource_type="shipment",
            resource_id=str(shipment.id),
            details={
                "shipment_number": shipment.shipment_number,
                "sales_order_id": str(order.id),
                "order_number": order.order_number,
                "transport_mode": mode,
                "lines": len(checked),
            },
        )
        return _load(session, company_id=meta.company_id, shipment_id=shipment.id)

    @staticmethod
    def _generate_number(now: datetime) -> str:
        return f"SH-{now:%y%m}-{uuid4().hex[:6].upper()}"

    def transition(
        self,
        session: Session,
        *,
        meta: WriteMeta,
        shipment_id: UUID,
        expected_version: int,
        data: TransitionShipmentData,
    ) -> ShipmentRecord:
        shipment = session.execute(
            select(Shipment)
            .where(Shipment.id == shipment_id, Shipment.company_id == meta.company_id)
            .with_for_update()
        ).scalar_one_or_none()
        if shipment is None:
            raise NotFoundError("The shipment does not exist.")
        if shipment.version != expected_version:
            raise VersionConflictError(
                "The shipment was modified by another request.",
                details={"current_version": shipment.version},
                headers={"ETag": f'"v{shipment.version}"'},
            )

        previous = shipment.status
        reference_count = session.execute(
            select(func.count(ShipmentReference.id)).where(
                ShipmentReference.company_id == meta.company_id,
                ShipmentReference.shipment_id == shipment.id,
            )
        ).scalar_one()
        tracking_reference = clean_optional(data.tracking_reference) or shipment.tracking_reference
        tracking_source = ensure_tracking_source(data.tracking_source) or shipment.tracking_source
        now = datetime.now(tz=UTC)
        occurred_at = _aware(data.occurred_at) or now
        delivery_evidence = (
            clean_optional(data.delivery_evidence_reference)
            or shipment.delivery_evidence_reference
        )

        dispatch_at = shipment.actual_dispatch_at
        arrival_at = shipment.actual_arrival_at
        if data.target in (ShipmentStatus.DISPATCHED.value, ShipmentStatus.ARRIVED.value):
            dispatch_at = dispatch_at or occurred_at
        if data.target == ShipmentStatus.ARRIVED.value:
            arrival_at = occurred_at

        cleaned_reason = validate_shipment_transition(
            previous,
            data.target,
            data.reason,
            actual_dispatch_at=dispatch_at,
            actual_arrival_at=arrival_at,
            delivery_evidence_reference=delivery_evidence,
            has_tracking_reference=bool(tracking_reference) or reference_count > 0,
        )

        shipment.status = data.target
        shipment.version += 1
        shipment.updated_at = now
        shipment.actual_dispatch_at = dispatch_at
        shipment.actual_arrival_at = arrival_at
        if tracking_reference:
            shipment.tracking_reference = tracking_reference
            shipment.tracking_source = tracking_source or "MANUAL"
        if data.target == ShipmentStatus.DELIVERED.value:
            shipment.delivered_at = occurred_at
            shipment.delivery_evidence_reference = delivery_evidence
        if data.target == ShipmentStatus.CANCELLED.value:
            shipment.cancellation_reason = cleaned_reason
        if clean_optional(data.notes) and not shipment.notes:
            shipment.notes = clean_optional(data.notes)

        session.add(
            ShipmentEvent(
                company_id=meta.company_id,
                shipment_id=shipment.id,
                event_type=STATUS_EVENT_TYPES[ShipmentStatus(data.target)].value,
                occurred_at=occurred_at,
                location=clean_optional(data.location) or shipment.destination,
                notes=clean_optional(data.notes),
                evidence_reference=clean_optional(data.evidence_reference),
                tracking_source=tracking_source,
                recorded_by=meta.actor_id,
                recorded_at=now,
            )
        )
        session.flush()

        record_audit(
            session,
            action=AuditAction.SHIPMENT_TRANSITIONED,
            outcome=AuditOutcome.SUCCESS,
            actor_id=meta.actor_id,
            company_id=meta.company_id,
            request_id=meta.request_id,
            ip_address=meta.ip_address,
            user_agent=meta.user_agent,
            resource_type="shipment",
            resource_id=str(shipment.id),
            details={
                "shipment_number": shipment.shipment_number,
                "from": previous,
                "to": data.target,
                "reason": cleaned_reason,
                "tracking_source": shipment.tracking_source,
                "evidence_reference": clean_optional(data.evidence_reference),
                "version": shipment.version,
            },
        )
        if data.target in (
            ShipmentStatus.DISPATCHED.value,
            ShipmentStatus.ARRIVED.value,
            ShipmentStatus.DELIVERED.value,
        ):
            self._advance_order(
                session,
                meta=meta,
                sales_order_id=shipment.sales_order_id,
                dispatched=True,
                now=now,
            )
        return _load(session, company_id=meta.company_id, shipment_id=shipment.id)

    def _advance_order(
        self,
        session: Session,
        *,
        meta: WriteMeta,
        sales_order_id: UUID,
        dispatched: bool,
        now: datetime,
    ) -> None:
        """Derive the order's fulfilment state from shipment evidence."""
        summary = _fulfilment(
            session, company_id=meta.company_id, sales_order_id=sales_order_id
        )
        order = session.execute(
            select(SalesOrder)
            .where(
                SalesOrder.id == sales_order_id,
                SalesOrder.company_id == meta.company_id,
            )
            .with_for_update()
        ).scalar_one_or_none()
        if order is None:  # pragma: no cover - FK guarantees existence
            return
        if order.status in (
            SalesOrderStatus.CLOSED.value,
            SalesOrderStatus.CANCELLED.value,
        ):
            return

        targets: list[str] = []
        if summary.fully_delivered:
            targets = [
                SalesOrderStatus.IN_FULFILLMENT.value,
                SalesOrderStatus.FULFILLED.value,
            ]
        elif summary.delivered_any or dispatched:
            targets = [SalesOrderStatus.IN_FULFILLMENT.value]

        for target in targets:
            if order.status == target:
                continue
            if order.status not in (
                SalesOrderStatus.CONFIRMED.value,
                SalesOrderStatus.IN_FULFILLMENT.value,
            ):
                continue
            previous = order.status
            order.status = target
            order.version += 1
            order.updated_at = now
            session.add(
                SalesOrderTransition(
                    company_id=meta.company_id,
                    sales_order_id=order.id,
                    from_status=previous,
                    to_status=target,
                    reason=(
                        "Derived from delivered shipment quantities"
                        if target == SalesOrderStatus.FULFILLED.value
                        else "Derived from shipment movement"
                    ),
                    actor_id=meta.actor_id,
                    request_id=meta.request_id,
                    version_after=order.version,
                    occurred_at=now,
                )
            )
            record_audit(
                session,
                action=AuditAction.SALES_ORDER_TRANSITIONED,
                outcome=AuditOutcome.SUCCESS,
                actor_id=meta.actor_id,
                company_id=meta.company_id,
                request_id=meta.request_id,
                ip_address=meta.ip_address,
                user_agent=meta.user_agent,
                resource_type="sales_order",
                resource_id=str(order.id),
                details={
                    "order_number": order.order_number,
                    "from": previous,
                    "to": target,
                    "derived": True,
                    "completion_ratio": str(summary.completion_ratio),
                },
            )
        session.flush()

    def record_event(
        self,
        session: Session,
        *,
        meta: WriteMeta,
        shipment_id: UUID,
        data: EventData,
    ) -> ShipmentRecord:
        """Record a movement or delay milestone without inventing a status."""
        shipment = session.execute(
            select(Shipment)
            .where(Shipment.id == shipment_id, Shipment.company_id == meta.company_id)
            .with_for_update()
        ).scalar_one_or_none()
        if shipment is None:
            raise NotFoundError("The shipment does not exist.")
        if shipment.status in (
            ShipmentStatus.DELIVERED.value,
            ShipmentStatus.CANCELLED.value,
        ):
            raise ConflictError("A completed shipment cannot receive new milestones.")
        try:
            event_type = ShipmentEventType(data.event_type)
        except ValueError as exc:
            raise BadRequestError("Unknown shipment event type.") from exc
        if event_type not in (
            ShipmentEventType.IN_TRANSIT,
            ShipmentEventType.DELAY_RECORDED,
        ):
            raise BadRequestError(
                "Record status changes through the transition endpoint.",
                details={"allowed": ["IN_TRANSIT", "DELAY_RECORDED"]},
            )
        notes = clean_optional(data.notes)
        if event_type is ShipmentEventType.DELAY_RECORDED and (
            notes is None or len(notes) < 3
        ):
            raise ReasonRequiredError("A delay must record a reason of at least 3 characters.")
        tracking_source = ensure_tracking_source(data.tracking_source)
        now = datetime.now(tz=UTC)
        occurred_at = _aware(data.occurred_at) or now
        if occurred_at > now:
            raise BadRequestError("A milestone cannot be recorded in the future.")
        session.add(
            ShipmentEvent(
                company_id=meta.company_id,
                shipment_id=shipment.id,
                event_type=event_type.value,
                occurred_at=occurred_at,
                location=clean_optional(data.location),
                notes=notes,
                evidence_reference=clean_optional(data.evidence_reference),
                tracking_source=tracking_source,
                recorded_by=meta.actor_id,
                recorded_at=now,
            )
        )
        if event_type is ShipmentEventType.DELAY_RECORDED:
            shipment.delay_reason = notes
            shipment.updated_at = now
        session.flush()
        record_audit(
            session,
            action=AuditAction.SHIPMENT_UPDATED,
            outcome=AuditOutcome.SUCCESS,
            actor_id=meta.actor_id,
            company_id=meta.company_id,
            request_id=meta.request_id,
            ip_address=meta.ip_address,
            user_agent=meta.user_agent,
            resource_type="shipment",
            resource_id=str(shipment.id),
            details={
                "shipment_number": shipment.shipment_number,
                "event": event_type.value,
                "occurred_at": occurred_at,
            },
        )
        return _load(session, company_id=meta.company_id, shipment_id=shipment.id)

    def add_reference(
        self,
        session: Session,
        *,
        meta: WriteMeta,
        shipment_id: UUID,
        data: ReferenceData,
    ) -> ShipmentRecord:
        shipment = session.execute(
            select(Shipment).where(
                Shipment.id == shipment_id, Shipment.company_id == meta.company_id
            )
        ).scalar_one_or_none()
        if shipment is None:
            raise NotFoundError("The shipment does not exist.")
        if shipment.status == ShipmentStatus.CANCELLED.value:
            raise ConflictError("A cancelled shipment cannot receive new references.")
        if data.reference_type not in _REFERENCE_TYPES:
            raise BadRequestError(
                "Unknown reference type.",
                details={"allowed": list(_REFERENCE_TYPES)},
            )
        value = " ".join(data.reference_value.split())
        if not 2 <= len(value) <= 120:
            raise BadRequestError("A reference value must be 2-120 characters.")
        provenance = ensure_tracking_source(data.provenance)
        if provenance is None:
            raise BadRequestError("A reference must state its provenance.")
        session.add(
            ShipmentReference(
                company_id=meta.company_id,
                shipment_id=shipment.id,
                reference_type=data.reference_type,
                reference_value=value,
                provenance=provenance,
                created_at=datetime.now(tz=UTC),
            )
        )
        try:
            session.flush()
        except IntegrityError as exc:
            raise ConflictError("That reference is already recorded for this company.") from exc
        record_audit(
            session,
            action=AuditAction.SHIPMENT_UPDATED,
            outcome=AuditOutcome.SUCCESS,
            actor_id=meta.actor_id,
            company_id=meta.company_id,
            request_id=meta.request_id,
            ip_address=meta.ip_address,
            user_agent=meta.user_agent,
            resource_type="shipment",
            resource_id=str(shipment.id),
            details={
                "reference_type": data.reference_type,
                "provenance": provenance,
                "shipment_number": shipment.shipment_number,
            },
        )
        return _load(session, company_id=meta.company_id, shipment_id=shipment.id)

    def record_cost(
        self,
        session: Session,
        *,
        meta: WriteMeta,
        shipment_id: UUID,
        data: CostData,
    ) -> ShipmentRecord:
        """Record a logistics cost without touching Stage 3 pricing assumptions."""
        shipment = session.execute(
            select(Shipment).where(
                Shipment.id == shipment_id, Shipment.company_id == meta.company_id
            )
        ).scalar_one_or_none()
        if shipment is None:
            raise NotFoundError("The shipment does not exist.")
        if data.cost_type not in _COST_TYPES:
            raise BadRequestError("Unknown cost type.", details={"allowed": list(_COST_TYPES)})
        try:
            stage = CostStage(data.stage).value
        except ValueError as exc:
            raise BadRequestError(
                "Unknown cost stage.",
                details={"allowed": [value.value for value in CostStage]},
            ) from exc
        if data.amount < 0:
            raise BadRequestError("A cost amount cannot be negative.")
        currency = data.currency.upper()
        if len(currency) != 3 or not currency.isalpha():
            raise BadRequestError("Use a three-letter ISO currency code.")
        reference = " ".join(data.reference.split())
        if not 2 <= len(reference) <= 200:
            raise BadRequestError("A cost reference must be 2-200 characters.")
        now = datetime.now(tz=UTC)
        session.add(
            ShipmentCost(
                company_id=meta.company_id,
                shipment_id=shipment.id,
                cost_type=data.cost_type,
                stage=stage,
                amount=data.amount,
                currency=currency,
                reference=reference,
                notes=clean_optional(data.notes),
                recorded_by=meta.actor_id,
                recorded_at=now,
            )
        )
        session.flush()
        record_audit(
            session,
            action=AuditAction.SHIPMENT_COST_RECORDED,
            outcome=AuditOutcome.SUCCESS,
            actor_id=meta.actor_id,
            company_id=meta.company_id,
            request_id=meta.request_id,
            ip_address=meta.ip_address,
            user_agent=meta.user_agent,
            resource_type="shipment",
            resource_id=str(shipment.id),
            details={
                "shipment_number": shipment.shipment_number,
                "cost_type": data.cost_type,
                "stage": stage,
                "amount": str(data.amount),
                "currency": currency,
            },
        )
        return _load(session, company_id=meta.company_id, shipment_id=shipment.id)


def _aware(value: datetime | None) -> datetime | None:
    """Treat a naive timestamp as UTC instead of guessing a local zone."""
    if value is None:
        return None
    return value if value.tzinfo is not None else value.replace(tzinfo=UTC)


__all__ = [
    "CostData",
    "EventData",
    "FulfilmentLine",
    "FulfilmentSummary",
    "PlanItem",
    "PlanShipmentData",
    "ReferenceData",
    "ShipmentCostRecord",
    "ShipmentEventRecord",
    "ShipmentFilters",
    "ShipmentItemRecord",
    "ShipmentPage",
    "ShipmentRecord",
    "ShipmentReferenceRecord",
    "ShipmentService",
    "ShipmentSummaryRecord",
    "TransitionShipmentData",
]

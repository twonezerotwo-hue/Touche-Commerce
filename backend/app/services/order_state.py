"""Explicit state machines for sales orders, purchase orders and shipments.

Like :mod:`app.services.deal_state`, the graphs are data and the evidence rules
are small pure functions, so the whole contract can be tested without a database
and rendered by the UI without duplicating the rules.

Three boundaries are intentional:

* a sales order becomes ``FULFILLED`` only from delivery evidence recorded by
  the shipment service, never by a direct request;
* a purchase order is never ``RECORDED_SENT`` without a channel, a timestamp and
  an external reference: the system does not send anything itself;
* a shipment is never ``DELIVERED`` without a delivery evidence reference, and an
  ETA is never treated as an arrival.
"""

from __future__ import annotations

from collections.abc import Mapping
from datetime import datetime
from decimal import Decimal

from app.core.errors import BadRequestError, InvalidTransitionError, ReasonRequiredError
from app.db.models import (
    PurchaseOrderStatus,
    SalesOrderStatus,
    ShipmentEventType,
    ShipmentStatus,
    TrackingSource,
)

SALES_ORDER_TRANSITIONS: dict[SalesOrderStatus, frozenset[SalesOrderStatus]] = {
    SalesOrderStatus.CONFIRMED: frozenset(
        {SalesOrderStatus.IN_FULFILLMENT, SalesOrderStatus.CANCELLED}
    ),
    SalesOrderStatus.IN_FULFILLMENT: frozenset(
        {SalesOrderStatus.FULFILLED, SalesOrderStatus.CANCELLED}
    ),
    SalesOrderStatus.FULFILLED: frozenset({SalesOrderStatus.CLOSED}),
    SalesOrderStatus.CLOSED: frozenset(),
    SalesOrderStatus.CANCELLED: frozenset(),
}

PURCHASE_ORDER_TRANSITIONS: dict[PurchaseOrderStatus, frozenset[PurchaseOrderStatus]] = {
    PurchaseOrderStatus.DRAFT: frozenset(
        {PurchaseOrderStatus.APPROVED, PurchaseOrderStatus.CANCELLED}
    ),
    PurchaseOrderStatus.APPROVED: frozenset(
        {PurchaseOrderStatus.RECORDED_SENT, PurchaseOrderStatus.CANCELLED}
    ),
    PurchaseOrderStatus.RECORDED_SENT: frozenset(
        {PurchaseOrderStatus.SUPPLIER_CONFIRMED, PurchaseOrderStatus.CANCELLED}
    ),
    PurchaseOrderStatus.SUPPLIER_CONFIRMED: frozenset(
        {PurchaseOrderStatus.IN_FULFILLMENT, PurchaseOrderStatus.CANCELLED}
    ),
    PurchaseOrderStatus.IN_FULFILLMENT: frozenset(
        {PurchaseOrderStatus.RECEIVED, PurchaseOrderStatus.CANCELLED}
    ),
    PurchaseOrderStatus.RECEIVED: frozenset(),
    PurchaseOrderStatus.CANCELLED: frozenset(),
}

SHIPMENT_TRANSITIONS: dict[ShipmentStatus, frozenset[ShipmentStatus]] = {
    ShipmentStatus.PLANNED: frozenset({ShipmentStatus.BOOKED, ShipmentStatus.CANCELLED}),
    ShipmentStatus.BOOKED: frozenset({ShipmentStatus.DISPATCHED, ShipmentStatus.CANCELLED}),
    ShipmentStatus.DISPATCHED: frozenset(
        {ShipmentStatus.IN_TRANSIT, ShipmentStatus.ARRIVED, ShipmentStatus.CANCELLED}
    ),
    ShipmentStatus.IN_TRANSIT: frozenset({ShipmentStatus.ARRIVED, ShipmentStatus.CANCELLED}),
    ShipmentStatus.ARRIVED: frozenset({ShipmentStatus.DELIVERED, ShipmentStatus.CANCELLED}),
    ShipmentStatus.DELIVERED: frozenset(),
    ShipmentStatus.CANCELLED: frozenset(),
}

#: Status changes that release allocated quantities and must explain themselves.
REASON_REQUIRED_TARGETS = frozenset(
    {SalesOrderStatus.CANCELLED, PurchaseOrderStatus.CANCELLED, ShipmentStatus.CANCELLED}
)

#: Every shipment transition records a timeline event of the same name.
STATUS_EVENT_TYPES: dict[ShipmentStatus, ShipmentEventType] = {
    ShipmentStatus.PLANNED: ShipmentEventType.PLANNED,
    ShipmentStatus.BOOKED: ShipmentEventType.BOOKED,
    ShipmentStatus.DISPATCHED: ShipmentEventType.DISPATCHED,
    ShipmentStatus.IN_TRANSIT: ShipmentEventType.IN_TRANSIT,
    ShipmentStatus.ARRIVED: ShipmentEventType.ARRIVED,
    ShipmentStatus.DELIVERED: ShipmentEventType.DELIVERED,
    ShipmentStatus.CANCELLED: ShipmentEventType.CANCELLED,
}

#: Tracking provenance this stage can honestly record.
AVAILABLE_TRACKING_SOURCES = frozenset(
    {TrackingSource.MANUAL, TrackingSource.DOCUMENT_EVIDENCE}
)

REASON_MIN_LENGTH = 3


def _require_reason(target: object, reason: str | None) -> str | None:
    cleaned = " ".join(reason.split()) if reason else None
    if target in REASON_REQUIRED_TARGETS:
        if cleaned is None or len(cleaned) < REASON_MIN_LENGTH:
            raise ReasonRequiredError(
                f"A reason of at least {REASON_MIN_LENGTH} characters is required to "
                f"move to {target}."
            )
        return cleaned[:500]
    if cleaned is not None and len(cleaned) > 500:
        raise ReasonRequiredError("The reason must be at most 500 characters.")
    return cleaned or None


def _ensure_edge[StatusT](
    current: StatusT,
    target: StatusT,
    graph: Mapping[StatusT, frozenset[StatusT]],
    *,
    label: str,
) -> None:
    allowed = graph.get(current, frozenset())
    if target not in allowed:
        raise InvalidTransitionError(
            f"A {label} cannot move from {current} to {target}.",
            details={
                "from": str(current),
                "to": str(target),
                "allowed_transitions": [str(value) for value in allowed],
            },
        )


def allowed_sales_order_targets(current: str) -> tuple[str, ...]:
    targets = SALES_ORDER_TRANSITIONS.get(SalesOrderStatus(current), frozenset())
    return tuple(value.value for value in SalesOrderStatus if value in targets)


def allowed_purchase_order_targets(current: str) -> tuple[str, ...]:
    targets = PURCHASE_ORDER_TRANSITIONS.get(PurchaseOrderStatus(current), frozenset())
    return tuple(value.value for value in PurchaseOrderStatus if value in targets)


def allowed_shipment_targets(current: str) -> tuple[str, ...]:
    targets = SHIPMENT_TRANSITIONS.get(ShipmentStatus(current), frozenset())
    return tuple(value.value for value in ShipmentStatus if value in targets)


def validate_sales_order_transition(
    current: str, target: str, reason: str | None
) -> str | None:
    """Validate an administrative order transition (never the delivery one)."""
    current_status = SalesOrderStatus(current)
    target_status = SalesOrderStatus(target)
    if target_status is SalesOrderStatus.FULFILLED:
        raise InvalidTransitionError(
            "FULFILLED is derived from delivered shipment quantities, not set directly.",
            details={"hint": "Record delivery against a shipment instead."},
        )
    _ensure_edge(current_status, target_status, SALES_ORDER_TRANSITIONS, label="sales order")
    return _require_reason(target_status, reason)


def validate_purchase_order_transition(
    current: str,
    target: str,
    reason: str | None,
    *,
    dispatched_at: datetime | None,
    dispatch_channel: str | None,
    dispatch_reference: str | None,
    supplier_confirmation_reference: str | None,
) -> str | None:
    """Validate a purchase-order transition and its evidence requirements."""
    current_status = PurchaseOrderStatus(current)
    target_status = PurchaseOrderStatus(target)
    _ensure_edge(
        current_status, target_status, PURCHASE_ORDER_TRANSITIONS, label="purchase order"
    )

    if target_status is PurchaseOrderStatus.RECORDED_SENT:
        missing = [
            field
            for field, value in (
                ("dispatch_channel", dispatch_channel),
                ("dispatch_reference", dispatch_reference),
            )
            if not value or not str(value).strip()
        ]
        if dispatched_at is None:
            missing.append("dispatched_at")
        if missing:
            raise BadRequestError(
                "Recording that a purchase order was sent requires the channel, the "
                "timestamp and an external reference.",
                details=[
                    {
                        "field": field,
                        "message": "Required when recording an external dispatch.",
                        "type": "evidence_required",
                    }
                    for field in missing
                ],
            )

    if target_status in (
        PurchaseOrderStatus.SUPPLIER_CONFIRMED,
        PurchaseOrderStatus.IN_FULFILLMENT,
        PurchaseOrderStatus.RECEIVED,
    ) and not (supplier_confirmation_reference and supplier_confirmation_reference.strip()):
        raise BadRequestError(
            "A supplier confirmation reference is required before this status.",
            details=[
                {
                    "field": "supplier_confirmation_reference",
                    "message": "Record the supplier's confirmation reference first.",
                    "type": "evidence_required",
                }
            ],
        )

    return _require_reason(target_status, reason)


def validate_shipment_transition(
    current: str,
    target: str,
    reason: str | None,
    *,
    actual_dispatch_at: datetime | None,
    actual_arrival_at: datetime | None,
    delivery_evidence_reference: str | None,
    has_tracking_reference: bool,
) -> str | None:
    """Validate a shipment transition and its evidence requirements."""
    current_status = ShipmentStatus(current)
    target_status = ShipmentStatus(target)
    _ensure_edge(current_status, target_status, SHIPMENT_TRANSITIONS, label="shipment")

    if target_status in (ShipmentStatus.DISPATCHED, ShipmentStatus.ARRIVED) and (
        actual_dispatch_at is None
    ):
        raise BadRequestError(
            "An actual dispatch timestamp is required before recording movement.",
            details=[
                {
                    "field": "actual_dispatch_at",
                    "message": "Record when the goods actually left.",
                    "type": "evidence_required",
                }
            ],
        )

    if target_status is ShipmentStatus.DISPATCHED and not has_tracking_reference:
        raise BadRequestError(
            "A dispatch must carry a carrier reference, booking number or document.",
            details=[
                {
                    "field": "tracking_reference",
                    "message": "Add a booking, container or tracking reference first.",
                    "type": "evidence_required",
                }
            ],
        )

    if target_status is ShipmentStatus.ARRIVED and actual_arrival_at is None:
        raise BadRequestError(
            "Arrival requires the actual arrival timestamp; an ETA is not an arrival."
        )

    if target_status is ShipmentStatus.DELIVERED and not (
        delivery_evidence_reference and delivery_evidence_reference.strip()
    ):
        raise BadRequestError(
            "Delivery requires a recorded delivery evidence reference.",
            details=[
                {
                    "field": "delivery_evidence_reference",
                    "message": "Record the signed proof of delivery or document id.",
                    "type": "evidence_required",
                }
            ],
        )

    return _require_reason(target_status, reason)


def ensure_tracking_source(source: str | None) -> str | None:
    """Refuse provenance this stage cannot verify (no carrier integration)."""
    if source is None:
        return None
    try:
        resolved = TrackingSource(source)
    except ValueError as exc:
        raise BadRequestError(
            "Unknown tracking source.",
            details=[
                {
                    "field": "tracking_source",
                    "message": "Use MANUAL or DOCUMENT_EVIDENCE.",
                    "type": "value_error",
                }
            ],
        ) from exc
    if resolved not in AVAILABLE_TRACKING_SOURCES:
        raise BadRequestError(
            "VERIFIED_EXTERNAL tracking is not available: no carrier integration exists "
            "in this stage.",
            details=[
                {
                    "field": "tracking_source",
                    "message": "Record MANUAL or DOCUMENT_EVIDENCE provenance instead.",
                    "type": "value_error",
                }
            ],
        )
    return resolved.value


def validate_allocation(
    *,
    ordered: Decimal,
    already_allocated: Decimal,
    requested: Decimal,
    order_unit: str,
    unit: str,
) -> Decimal:
    """Return the remaining quantity after a valid allocation.

    Quantities are decimals, units must match the order line exactly, and the sum
    of live allocations can never exceed what was ordered.
    """
    if unit != order_unit:
        raise BadRequestError(
            f"The shipment unit {unit!r} does not match the order line unit {order_unit!r}.",
            details=[
                {
                    "field": "unit",
                    "message": "Shipment quantities must use the order line unit.",
                    "type": "unit_mismatch",
                }
            ],
        )
    if requested <= 0:
        raise BadRequestError(
            "A shipment quantity must be greater than zero.",
            details=[
                {
                    "field": "quantity",
                    "message": "Quantity must be positive.",
                    "type": "value_error",
                }
            ],
        )
    remaining = ordered - already_allocated
    if requested > remaining:
        raise BadRequestError(
            "The shipment quantity exceeds the quantity still outstanding on the order line.",
            details={
                "ordered": str(ordered),
                "allocated": str(already_allocated),
                "remaining": str(remaining),
                "requested": str(requested),
            },
        )
    return remaining - requested


def is_delayed(
    *,
    status: str,
    estimated_arrival_at: datetime | None,
    delivered_at: datetime | None,
    now: datetime,
) -> bool:
    """A shipment is delayed only against a documented date, never a guess."""
    if status in (ShipmentStatus.DELIVERED.value, ShipmentStatus.CANCELLED.value):
        return False
    if delivered_at is not None:
        return False
    return estimated_arrival_at is not None and estimated_arrival_at < now


__all__ = [
    "AVAILABLE_TRACKING_SOURCES",
    "PURCHASE_ORDER_TRANSITIONS",
    "REASON_MIN_LENGTH",
    "REASON_REQUIRED_TARGETS",
    "SALES_ORDER_TRANSITIONS",
    "SHIPMENT_TRANSITIONS",
    "STATUS_EVENT_TYPES",
    "allowed_purchase_order_targets",
    "allowed_sales_order_targets",
    "allowed_shipment_targets",
    "ensure_tracking_source",
    "is_delayed",
    "validate_allocation",
    "validate_purchase_order_transition",
    "validate_sales_order_transition",
    "validate_shipment_transition",
]

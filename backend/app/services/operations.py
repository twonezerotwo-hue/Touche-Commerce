"""Operational aggregates for the command center.

Every number is a real ``COUNT``/``SUM`` over the active company's rows; nothing
is simulated. "Delayed" means a documented ETA that has passed on a shipment
that has not been delivered or cancelled — never a guess or an average.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import UTC, datetime
from decimal import Decimal
from uuid import UUID

from sqlalchemy import func, select

from app.db.engine import Database
from app.db.models import (
    DocumentStatus,
    PurchaseOrder,
    PurchaseOrderStatus,
    SalesOrder,
    SalesOrderStatus,
    Shipment,
    ShipmentStatus,
    TradeDocument,
    TradeDocumentType,
)
from app.db.tenant import apply_company_context

_OPEN_PO_STATUSES = (
    PurchaseOrderStatus.DRAFT.value,
    PurchaseOrderStatus.APPROVED.value,
    PurchaseOrderStatus.RECORDED_SENT.value,
    PurchaseOrderStatus.SUPPLIER_CONFIRMED.value,
    PurchaseOrderStatus.IN_FULFILLMENT.value,
)


@dataclass(frozen=True, slots=True)
class CurrencyOrderValue:
    currency: str
    order_count: int
    total_value: Decimal


@dataclass(frozen=True, slots=True)
class OperationsSummary:
    orders_total: int
    orders_confirmed: int
    orders_in_fulfillment: int
    orders_fulfilled: int
    orders_closed: int
    orders_cancelled: int
    order_value_by_currency: tuple[CurrencyOrderValue, ...]
    purchase_orders_total: int
    purchase_orders_open: int
    active_shipments: int
    delayed_shipments: int
    delivered_shipments: int
    documents_total: int
    delivered_shipments_without_evidence: int
    generated_at: datetime


class OperationsService:
    """One consistent snapshot of the operational picture."""

    def __init__(self, database: Database) -> None:
        self._database = database

    def summary(self, *, company_id: UUID) -> OperationsSummary:
        now = datetime.now(tz=UTC)
        with self._database.transaction() as session:
            apply_company_context(session, company_id)

            order_rows = session.execute(
                select(
                    SalesOrder.status,
                    func.count(SalesOrder.id),
                    func.coalesce(func.sum(SalesOrder.order_total), 0),
                )
                .where(SalesOrder.company_id == company_id)
                .group_by(SalesOrder.status)
            ).all()
            by_status = {
                status: int(count) for status, count, _total in order_rows
            }

            by_currency = session.execute(
                select(
                    SalesOrder.currency,
                    func.count(SalesOrder.id),
                    func.coalesce(func.sum(SalesOrder.order_total), 0),
                )
                .where(SalesOrder.company_id == company_id)
                .group_by(SalesOrder.currency)
                .order_by(SalesOrder.currency)
            ).all()

            purchase_orders_total = session.execute(
                select(func.count(PurchaseOrder.id)).where(
                    PurchaseOrder.company_id == company_id
                )
            ).scalar_one()
            purchase_orders_open = session.execute(
                select(func.count(PurchaseOrder.id)).where(
                    PurchaseOrder.company_id == company_id,
                    PurchaseOrder.status.in_(_OPEN_PO_STATUSES),
                )
            ).scalar_one()
            active_shipments = session.execute(
                select(func.count(Shipment.id)).where(
                    Shipment.company_id == company_id,
                    Shipment.status.notin_(
                        (
                            ShipmentStatus.DELIVERED.value,
                            ShipmentStatus.CANCELLED.value,
                        )
                    ),
                )
            ).scalar_one()
            delayed_shipments = session.execute(
                select(func.count(Shipment.id)).where(
                    Shipment.company_id == company_id,
                    Shipment.status.notin_(
                        (
                            ShipmentStatus.DELIVERED.value,
                            ShipmentStatus.CANCELLED.value,
                        )
                    ),
                    Shipment.delivered_at.is_(None),
                    Shipment.estimated_arrival_at.is_not(None),
                    Shipment.estimated_arrival_at < now,
                )
            ).scalar_one()
            delivered_shipments = session.execute(
                select(func.count(Shipment.id)).where(
                    Shipment.company_id == company_id,
                    Shipment.status == ShipmentStatus.DELIVERED.value,
                )
            ).scalar_one()
            documents_total = session.execute(
                select(func.count(TradeDocument.id)).where(
                    TradeDocument.company_id == company_id,
                    TradeDocument.status == DocumentStatus.ACTIVE.value,
                )
            ).scalar_one()
            without_evidence = session.execute(
                select(func.count(Shipment.id))
                .select_from(Shipment)
                .where(
                    Shipment.company_id == company_id,
                    Shipment.status == ShipmentStatus.DELIVERED.value,
                    ~select(TradeDocument.id)
                    .where(
                        TradeDocument.company_id == company_id,
                        TradeDocument.linked_entity_type == "SHIPMENT",
                        TradeDocument.linked_entity_id == Shipment.id,
                        TradeDocument.document_type
                        == TradeDocumentType.DELIVERY_CONFIRMATION.value,
                        TradeDocument.status == DocumentStatus.ACTIVE.value,
                    )
                    .exists(),
                )
            ).scalar_one()

            return OperationsSummary(
                orders_total=sum(by_status.values()),
                orders_confirmed=by_status.get(SalesOrderStatus.CONFIRMED.value, 0),
                orders_in_fulfillment=by_status.get(
                    SalesOrderStatus.IN_FULFILLMENT.value, 0
                ),
                orders_fulfilled=by_status.get(SalesOrderStatus.FULFILLED.value, 0),
                orders_closed=by_status.get(SalesOrderStatus.CLOSED.value, 0),
                orders_cancelled=by_status.get(SalesOrderStatus.CANCELLED.value, 0),
                order_value_by_currency=tuple(
                    CurrencyOrderValue(
                        currency=currency,
                        order_count=int(count),
                        total_value=Decimal(str(total)),
                    )
                    for currency, count, total in by_currency
                ),
                purchase_orders_total=int(purchase_orders_total),
                purchase_orders_open=int(purchase_orders_open),
                active_shipments=int(active_shipments),
                delayed_shipments=int(delayed_shipments),
                delivered_shipments=int(delivered_shipments),
                documents_total=int(documents_total),
                delivered_shipments_without_evidence=int(without_evidence),
                generated_at=now,
            )


__all__ = ["CurrencyOrderValue", "OperationsService", "OperationsSummary"]

"""Supplier purchase orders: the optional procurement leg of a sales order.

Procurement is deliberately *not* automatic. A purchase order is created by a
user for an order whose fulfilment model is ``PURCHASE_RESALE``; a brokerage
arrangement where TOUCHE is not the buyer is refused. The system never sends a
purchase order: recording that one was sent requires the channel, the timestamp
and an external reference, and supplier confirmation needs a recorded reference.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import UTC, date, datetime
from decimal import Decimal
from uuid import UUID, uuid4

from sqlalchemy import and_, func, or_, select, tuple_
from sqlalchemy.orm import Session

from app.core.errors import (
    BadRequestError,
    ConflictError,
    ForbiddenError,
    NotFoundError,
    VersionConflictError,
)
from app.db.engine import Database
from app.db.models import (
    AuditAction,
    AuditOutcome,
    Counterparty,
    FulfilmentModel,
    Product,
    PurchaseOrder,
    PurchaseOrderItem,
    PurchaseOrderStatus,
    PurchaseOrderTransition,
    SalesOrder,
    SalesOrderStatus,
    SupplierQuote,
)
from app.db.tenant import apply_company_context
from app.services.audit import record_audit
from app.services.order_state import (
    allowed_purchase_order_targets,
    validate_purchase_order_transition,
)
from app.services.pagination import decode_cursor, encode_cursor
from app.services.pricing_engine import money
from app.services.trade_meta import WriteMeta, clean_optional, escape_like

_UNITS = ("kg", "mt", "lb", "unit", "l", "m3")
_INCOTERMS = (
    "EXW",
    "FCA",
    "FAS",
    "FOB",
    "CFR",
    "CIF",
    "CPT",
    "CIP",
    "DAP",
    "DPU",
    "DDP",
)


@dataclass(frozen=True, slots=True)
class PoItemRecord:
    id: UUID
    product_id: UUID
    sku: str
    description: str
    quantity: Decimal
    unit: str
    unit_cost: Decimal
    line_total: Decimal


@dataclass(frozen=True, slots=True)
class PoTransitionRecord:
    from_status: str | None
    to_status: str
    reason: str | None
    evidence_reference: str | None
    actor_id: UUID
    occurred_at: datetime
    version_after: int


@dataclass(frozen=True, slots=True)
class PurchaseOrderRecord:
    id: UUID
    company_id: UUID
    po_number: str
    sales_order_id: UUID
    order_number: str
    supplier_id: UUID
    supplier_name: str
    supplier_quote_id: UUID | None
    currency: str
    incoterm: str
    named_delivery_place: str
    payment_terms: str
    total_cost: Decimal
    status: str
    expected_dispatch_date: date | None
    expected_delivery_date: date | None
    dispatch_channel: str | None
    dispatched_at: datetime | None
    dispatch_reference: str | None
    supplier_confirmation_reference: str | None
    supplier_confirmed_at: datetime | None
    approved_by: UUID | None
    approved_at: datetime | None
    notes: str | None
    cancelled_at: datetime | None
    cancellation_reason: str | None
    version: int
    created_at: datetime
    updated_at: datetime
    items: tuple[PoItemRecord, ...]
    transitions: tuple[PoTransitionRecord, ...]

    @property
    def allowed_transitions(self) -> tuple[str, ...]:
        return allowed_purchase_order_targets(self.status)


@dataclass(frozen=True, slots=True)
class PurchaseOrderSummaryRecord:
    id: UUID
    company_id: UUID
    po_number: str
    sales_order_id: UUID
    order_number: str
    supplier_id: UUID
    supplier_name: str
    currency: str
    total_cost: Decimal
    status: str
    expected_dispatch_date: date | None
    expected_delivery_date: date | None
    approved_at: datetime | None
    version: int
    updated_at: datetime


@dataclass(frozen=True, slots=True)
class PurchaseOrderFilters:
    search: str | None = None
    status: str | None = None
    sales_order_id: UUID | None = None
    supplier_id: UUID | None = None

    def as_fingerprint(self) -> dict[str, str | None]:
        return {
            "search": self.search,
            "status": self.status,
            "sales_order_id": str(self.sales_order_id) if self.sales_order_id else None,
            "supplier_id": str(self.supplier_id) if self.supplier_id else None,
        }


@dataclass(frozen=True, slots=True)
class PurchaseOrderPage:
    items: tuple[PurchaseOrderSummaryRecord, ...]
    next_cursor: str | None


@dataclass(frozen=True, slots=True)
class NewPoItem:
    product_id: UUID
    description: str
    quantity: Decimal
    unit: str
    unit_cost: Decimal


@dataclass(frozen=True, slots=True)
class CreatePurchaseOrderData:
    sales_order_id: UUID
    supplier_id: UUID
    supplier_quote_id: UUID | None
    incoterm: str
    named_delivery_place: str
    payment_terms: str
    expected_dispatch_date: date | None
    expected_delivery_date: date | None
    notes: str | None
    items: tuple[NewPoItem, ...]


@dataclass(frozen=True, slots=True)
class PoTransitionData:
    target: str
    reason: str | None
    dispatched_at: datetime | None
    dispatch_channel: str | None
    dispatch_reference: str | None
    supplier_confirmation_reference: str | None
    evidence_reference: str | None


def _load(
    session: Session, *, company_id: UUID, purchase_order_id: UUID
) -> PurchaseOrderRecord:
    row = session.execute(
        select(PurchaseOrder, SalesOrder.order_number, Counterparty.name)
        .join(
            SalesOrder,
            and_(
                SalesOrder.id == PurchaseOrder.sales_order_id,
                SalesOrder.company_id == PurchaseOrder.company_id,
            ),
        )
        .join(
            Counterparty,
            and_(
                Counterparty.id == PurchaseOrder.supplier_id,
                Counterparty.company_id == PurchaseOrder.company_id,
            ),
        )
        .where(
            PurchaseOrder.id == purchase_order_id,
            PurchaseOrder.company_id == company_id,
        )
    ).one_or_none()
    if row is None:
        raise NotFoundError("The purchase order does not exist.")
    order, order_number, supplier_name = row
    items = tuple(
        PoItemRecord(
            id=item.id,
            product_id=item.product_id,
            sku=product.sku,
            description=item.description,
            quantity=item.quantity,
            unit=item.unit,
            unit_cost=item.unit_cost,
            line_total=item.line_total,
        )
        for item, product in session.execute(
            select(PurchaseOrderItem, Product)
            .join(
                Product,
                and_(
                    Product.id == PurchaseOrderItem.product_id,
                    Product.company_id == PurchaseOrderItem.company_id,
                ),
            )
            .where(
                PurchaseOrderItem.company_id == company_id,
                PurchaseOrderItem.purchase_order_id == order.id,
            )
            .order_by(Product.sku)
        ).all()
    )
    transitions = tuple(
        PoTransitionRecord(
            from_status=item.from_status,
            to_status=item.to_status,
            reason=item.reason,
            evidence_reference=item.evidence_reference,
            actor_id=item.actor_id,
            occurred_at=item.occurred_at,
            version_after=item.version_after,
        )
        for item in session.execute(
            select(PurchaseOrderTransition)
            .where(
                PurchaseOrderTransition.company_id == company_id,
                PurchaseOrderTransition.purchase_order_id == order.id,
            )
            .order_by(
                PurchaseOrderTransition.occurred_at, PurchaseOrderTransition.version_after
            )
        ).scalars()
    )
    return PurchaseOrderRecord(
        id=order.id,
        company_id=order.company_id,
        po_number=order.po_number,
        sales_order_id=order.sales_order_id,
        order_number=order_number,
        supplier_id=order.supplier_id,
        supplier_name=supplier_name,
        supplier_quote_id=order.supplier_quote_id,
        currency=order.currency,
        incoterm=order.incoterm,
        named_delivery_place=order.named_delivery_place,
        payment_terms=order.payment_terms,
        total_cost=order.total_cost,
        status=order.status,
        expected_dispatch_date=order.expected_dispatch_date,
        expected_delivery_date=order.expected_delivery_date,
        dispatch_channel=order.dispatch_channel,
        dispatched_at=order.dispatched_at,
        dispatch_reference=order.dispatch_reference,
        supplier_confirmation_reference=order.supplier_confirmation_reference,
        supplier_confirmed_at=order.supplier_confirmed_at,
        approved_by=order.approved_by,
        approved_at=order.approved_at,
        notes=order.notes,
        cancelled_at=order.cancelled_at,
        cancellation_reason=order.cancellation_reason,
        version=order.version,
        created_at=order.created_at,
        updated_at=order.updated_at,
        items=items,
        transitions=transitions,
    )


class ProcurementService:
    """Purchase orders, approvals and supplier evidence."""

    def __init__(self, database: Database) -> None:
        self._database = database

    # ------------------------------------------------------------------ reads
    def list(
        self,
        *,
        company_id: UUID,
        filters: PurchaseOrderFilters,
        limit: int,
        cursor: str | None,
    ) -> PurchaseOrderPage:
        with self._database.transaction() as session:
            apply_company_context(session, company_id)
            query = (
                select(PurchaseOrder, SalesOrder.order_number, Counterparty.name)
                .join(
                    SalesOrder,
                    and_(
                        SalesOrder.id == PurchaseOrder.sales_order_id,
                        SalesOrder.company_id == PurchaseOrder.company_id,
                    ),
                )
                .join(
                    Counterparty,
                    and_(
                        Counterparty.id == PurchaseOrder.supplier_id,
                        Counterparty.company_id == PurchaseOrder.company_id,
                    ),
                )
                .where(PurchaseOrder.company_id == company_id)
            )
            if filters.status:
                query = query.where(PurchaseOrder.status == filters.status)
            if filters.sales_order_id:
                query = query.where(PurchaseOrder.sales_order_id == filters.sales_order_id)
            if filters.supplier_id:
                query = query.where(PurchaseOrder.supplier_id == filters.supplier_id)
            if filters.search:
                term = f"%{escape_like(filters.search.lower())}%"
                query = query.where(
                    or_(
                        func.lower(PurchaseOrder.po_number).like(term, escape="\\"),
                        func.lower(Counterparty.name).like(term, escape="\\"),
                        func.lower(SalesOrder.order_number).like(term, escape="\\"),
                    )
                )
            if cursor:
                page_cursor = decode_cursor(cursor, filters=filters.as_fingerprint())
                query = query.where(
                    tuple_(PurchaseOrder.created_at, PurchaseOrder.id)
                    < tuple_(page_cursor.created_at, page_cursor.row_id)
                )
            rows = session.execute(
                query.order_by(
                    PurchaseOrder.created_at.desc(), PurchaseOrder.id.desc()
                ).limit(limit + 1)
            ).all()
            has_more = len(rows) > limit
            visible = rows[:limit]
            items = tuple(
                PurchaseOrderSummaryRecord(
                    id=order.id,
                    company_id=order.company_id,
                    po_number=order.po_number,
                    sales_order_id=order.sales_order_id,
                    order_number=order_number,
                    supplier_id=order.supplier_id,
                    supplier_name=supplier_name,
                    currency=order.currency,
                    total_cost=order.total_cost,
                    status=order.status,
                    expected_dispatch_date=order.expected_dispatch_date,
                    expected_delivery_date=order.expected_delivery_date,
                    approved_at=order.approved_at,
                    version=order.version,
                    updated_at=order.updated_at,
                )
                for order, order_number, supplier_name in visible
            )
            next_cursor = None
            if has_more and visible:
                last = visible[-1][0]
                next_cursor = encode_cursor(
                    created_at=last.created_at,
                    row_id=last.id,
                    filters=filters.as_fingerprint(),
                )
            return PurchaseOrderPage(items=items, next_cursor=next_cursor)

    def get(self, *, company_id: UUID, purchase_order_id: UUID) -> PurchaseOrderRecord:
        with self._database.transaction() as session:
            apply_company_context(session, company_id)
            return _load(
                session, company_id=company_id, purchase_order_id=purchase_order_id
            )

    # ----------------------------------------------------------------- writes
    def create(
        self, session: Session, *, meta: WriteMeta, data: CreatePurchaseOrderData
    ) -> PurchaseOrderRecord:
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
        if order.status in (
            SalesOrderStatus.CANCELLED.value,
            SalesOrderStatus.CLOSED.value,
        ):
            raise ConflictError("A cancelled or closed order cannot be procured.")
        if order.fulfilment_model == FulfilmentModel.BROKERAGE.value:
            raise ConflictError(
                "This deal is a brokerage arrangement: TOUCHE is not the buyer, so no "
                "purchase order should be created.",
                details={
                    "reason": "PROCUREMENT_NOT_APPLICABLE",
                    "fulfilment_model": order.fulfilment_model,
                },
            )

        supplier = session.execute(
            select(Counterparty).where(
                Counterparty.id == data.supplier_id,
                Counterparty.company_id == meta.company_id,
            )
        ).scalar_one_or_none()
        if supplier is None:
            raise BadRequestError("The supplier does not exist in this company.")
        if supplier.type not in ("supplier", "both"):
            raise BadRequestError(
                "The selected counterparty is a customer, not a supplier.",
                details=[{"field": "supplier_id", "type": "value_error"}],
            )

        if data.supplier_quote_id is not None:
            quote_id = session.execute(
                select(SupplierQuote.id).where(
                    SupplierQuote.id == data.supplier_quote_id,
                    SupplierQuote.company_id == meta.company_id,
                )
            ).scalar_one_or_none()
            if quote_id is None:
                raise BadRequestError(
                    "The referenced supplier quote does not exist in this company."
                )

        incoterm = data.incoterm.upper()
        if incoterm not in _INCOTERMS:
            raise BadRequestError(
                "Unknown Incoterm.", details=[{"field": "incoterm", "type": "value_error"}]
            )
        place = " ".join(data.named_delivery_place.split())
        terms = " ".join(data.payment_terms.split())
        if not 2 <= len(place) <= 160 or not 2 <= len(terms) <= 200:
            raise BadRequestError(
                "The named place and payment terms must be 2-160 and 2-200 characters."
            )
        if not data.items:
            raise BadRequestError("A purchase order needs at least one line.")

        product_ids = [line.product_id for line in data.items]
        if len(set(product_ids)) != len(product_ids):
            raise BadRequestError("Each product may appear only once per purchase order.")
        products = {
            product.id: product
            for product in session.execute(
                select(Product).where(
                    Product.company_id == meta.company_id,
                    Product.id.in_(product_ids),
                )
            ).scalars()
        }
        if len(products) != len(product_ids):
            raise BadRequestError(
                "Every purchase order line must reference a catalogue product."
            )

        checked: list[tuple[NewPoItem, Product]] = []
        total = Decimal("0.00")
        for line in data.items:
            product = products[line.product_id]
            unit = line.unit if line.unit in _UNITS else product.unit
            if unit not in _UNITS:
                raise BadRequestError("Unknown unit of measure.")
            if line.quantity <= 0:
                raise BadRequestError("A purchase order quantity must be greater than zero.")
            if line.unit_cost < 0:
                raise BadRequestError("A unit cost cannot be negative.")
            total += money(line.quantity * line.unit_cost)
            checked.append(
                (
                    NewPoItem(
                        product_id=line.product_id,
                        description=" ".join(line.description.split()) or product.name,
                        quantity=line.quantity,
                        unit=unit,
                        unit_cost=line.unit_cost,
                    ),
                    product,
                )
            )
        total = money(total)

        now = datetime.now(tz=UTC)
        purchase_order = PurchaseOrder(
            company_id=meta.company_id,
            po_number=self._generate_number(now),
            sales_order_id=order.id,
            supplier_id=supplier.id,
            supplier_quote_id=data.supplier_quote_id,
            currency=order.currency,
            incoterm=incoterm,
            named_delivery_place=place,
            payment_terms=terms,
            total_cost=total,
            status=PurchaseOrderStatus.DRAFT.value,
            expected_dispatch_date=data.expected_dispatch_date,
            expected_delivery_date=data.expected_delivery_date,
            notes=clean_optional(data.notes),
            created_by=meta.actor_id,
            created_at=now,
            updated_at=now,
        )
        session.add(purchase_order)
        session.flush()
        for line, _product in checked:
            session.add(
                PurchaseOrderItem(
                    company_id=meta.company_id,
                    purchase_order_id=purchase_order.id,
                    product_id=line.product_id,
                    description=line.description,
                    quantity=line.quantity,
                    unit=line.unit,
                    unit_cost=line.unit_cost,
                    line_total=money(line.quantity * line.unit_cost),
                    created_at=now,
                )
            )
        session.add(
            PurchaseOrderTransition(
                company_id=meta.company_id,
                purchase_order_id=purchase_order.id,
                from_status=None,
                to_status=PurchaseOrderStatus.DRAFT.value,
                reason=None,
                actor_id=meta.actor_id,
                request_id=meta.request_id,
                version_after=purchase_order.version,
                occurred_at=now,
            )
        )
        session.flush()
        record_audit(
            session,
            action=AuditAction.PURCHASE_ORDER_CREATED,
            outcome=AuditOutcome.SUCCESS,
            actor_id=meta.actor_id,
            company_id=meta.company_id,
            request_id=meta.request_id,
            ip_address=meta.ip_address,
            user_agent=meta.user_agent,
            resource_type="purchase_order",
            resource_id=str(purchase_order.id),
            details={
                "po_number": purchase_order.po_number,
                "sales_order_id": str(order.id),
                "supplier_id": str(supplier.id),
                "total_cost": str(total),
                "currency": order.currency,
                "lines": len(checked),
            },
        )
        return _load(
            session, company_id=meta.company_id, purchase_order_id=purchase_order.id
        )

    @staticmethod
    def _generate_number(now: datetime) -> str:
        return f"PO-{now:%y%m}-{uuid4().hex[:6].upper()}"

    def transition(
        self,
        session: Session,
        *,
        meta: WriteMeta,
        purchase_order_id: UUID,
        expected_version: int,
        data: PoTransitionData,
        actor_can_approve: bool,
    ) -> PurchaseOrderRecord:
        """Transition a purchase order, enforcing approval and evidence gates."""
        purchase_order = session.execute(
            select(PurchaseOrder)
            .where(
                PurchaseOrder.id == purchase_order_id,
                PurchaseOrder.company_id == meta.company_id,
            )
            .with_for_update()
        ).scalar_one_or_none()
        if purchase_order is None:
            raise NotFoundError("The purchase order does not exist.")
        if purchase_order.version != expected_version:
            raise VersionConflictError(
                "The purchase order was modified by another request.",
                details={"current_version": purchase_order.version},
                headers={"ETag": f'"v{purchase_order.version}"'},
            )

        previous = purchase_order.status
        now = datetime.now(tz=UTC)
        dispatched_at = data.dispatched_at or purchase_order.dispatched_at
        if data.target == PurchaseOrderStatus.RECORDED_SENT.value and dispatched_at is None:
            dispatched_at = now
        channel = clean_optional(data.dispatch_channel) or purchase_order.dispatch_channel
        reference = (
            clean_optional(data.dispatch_reference) or purchase_order.dispatch_reference
        )
        confirmation = (
            clean_optional(data.supplier_confirmation_reference)
            or purchase_order.supplier_confirmation_reference
        )

        cleaned_reason = validate_purchase_order_transition(
            previous,
            data.target,
            data.reason,
            dispatched_at=dispatched_at,
            dispatch_channel=channel,
            dispatch_reference=reference,
            supplier_confirmation_reference=confirmation,
        )

        if data.target == PurchaseOrderStatus.APPROVED.value:
            if not actor_can_approve:
                raise ForbiddenError(
                    "Approving a purchase order requires finance.approve.",
                    details={"permission": "finance.approve"},
                )
            if purchase_order.created_by == meta.actor_id:
                raise ForbiddenError(
                    "A purchase order cannot be approved by the person who created it.",
                    details={"segregation_of_duties": True},
                )
            purchase_order.approved_by = meta.actor_id
            purchase_order.approved_at = now

        purchase_order.status = data.target
        purchase_order.version += 1
        purchase_order.updated_at = now
        purchase_order.dispatched_at = dispatched_at
        purchase_order.dispatch_channel = channel
        purchase_order.dispatch_reference = reference
        purchase_order.supplier_confirmation_reference = confirmation
        if data.target == PurchaseOrderStatus.SUPPLIER_CONFIRMED.value:
            purchase_order.supplier_confirmed_at = now
        if data.target == PurchaseOrderStatus.CANCELLED.value:
            purchase_order.cancelled_at = now
            purchase_order.cancellation_reason = cleaned_reason

        session.add(
            PurchaseOrderTransition(
                company_id=meta.company_id,
                purchase_order_id=purchase_order.id,
                from_status=previous,
                to_status=data.target,
                reason=cleaned_reason,
                evidence_reference=clean_optional(data.evidence_reference)
                or confirmation
                or reference,
                actor_id=meta.actor_id,
                request_id=meta.request_id,
                version_after=purchase_order.version,
                occurred_at=now,
            )
        )
        session.flush()
        record_audit(
            session,
            action=AuditAction.PURCHASE_ORDER_TRANSITIONED,
            outcome=AuditOutcome.SUCCESS,
            actor_id=meta.actor_id,
            company_id=meta.company_id,
            request_id=meta.request_id,
            ip_address=meta.ip_address,
            user_agent=meta.user_agent,
            resource_type="purchase_order",
            resource_id=str(purchase_order.id),
            details={
                "po_number": purchase_order.po_number,
                "from": previous,
                "to": data.target,
                "reason": cleaned_reason,
                "dispatch_channel": channel,
                "evidence_reference": clean_optional(data.evidence_reference),
                "version": purchase_order.version,
            },
        )
        return _load(
            session, company_id=meta.company_id, purchase_order_id=purchase_order.id
        )


__all__ = [
    "CreatePurchaseOrderData",
    "NewPoItem",
    "PoItemRecord",
    "PoTransitionData",
    "PoTransitionRecord",
    "ProcurementService",
    "PurchaseOrderFilters",
    "PurchaseOrderPage",
    "PurchaseOrderRecord",
    "PurchaseOrderSummaryRecord",
]

"""Sales orders: customer acceptance, conversion, history and amendments.

The conversion is the only path that makes a deal ``WON`` (ADR-032). It runs in
the caller's transaction and performs every check before writing anything:

1. the deal is locked ``FOR UPDATE`` and must still be open or in negotiation;
2. the named quote belongs to that deal and is ``APPROVED``;
3. acceptance evidence exists for the *exact* quote revision, with a channel and
   a reference, and is not older than the approval;
4. the quote customer is the deal's counterparty;
5. only then are the order, its frozen lines, the deal transition and the audit
   rows written.

The order copies the commercial facts it needs (product, description, quantity,
unit, price, totals, terms) into ``sales_order_item`` plus one ``accepted_terms``
JSONB snapshot. Nothing is reconstructed later from a mutable catalogue row or a
quote that a revision may have superseded.
"""

from __future__ import annotations

from collections.abc import Sequence
from dataclasses import dataclass
from datetime import UTC, date, datetime
from decimal import Decimal
from typing import Any
from uuid import UUID, uuid4

from sqlalchemy import and_, func, or_, select, tuple_
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app.core.errors import (
    AlreadyWonError,
    BadRequestError,
    ConflictError,
    NotFoundError,
    ReasonRequiredError,
    VersionConflictError,
)
from app.db.engine import Database
from app.db.models import (
    AcceptanceChannel,
    AuditAction,
    AuditOutcome,
    Counterparty,
    CustomerAcceptanceEvidence,
    Deal,
    DealStatus,
    DealTransition,
    FulfilmentModel,
    OrderAmendment,
    Product,
    SalesOrder,
    SalesOrderItem,
    SalesOrderStatus,
    SalesOrderTransition,
    SalesQuote,
    SalesQuoteItem,
    SalesQuoteStatus,
    Shipment,
    ShipmentItem,
    ShipmentStatus,
)
from app.db.tenant import apply_company_context
from app.services.audit import record_audit
from app.services.order_state import allowed_sales_order_targets, validate_sales_order_transition
from app.services.pagination import decode_cursor, encode_cursor
from app.services.pricing_engine import money
from app.services.trade_meta import WriteMeta, clean_optional, escape_like

_CONVERTIBLE_DEAL_STATUSES = (DealStatus.OPEN.value, DealStatus.NEGOTIATION.value)
_MAX_REASON = 500


@dataclass(frozen=True, slots=True)
class AcceptanceRecord:
    id: UUID
    company_id: UUID
    deal_id: UUID
    sales_quote_id: UUID
    sales_quote_revision: int
    channel: str
    accepted_at: datetime
    accepted_by_name: str
    evidence_reference: str
    evidence_document_id: UUID | None
    notes: str | None
    recorded_by: UUID
    recorded_at: datetime


@dataclass(frozen=True, slots=True)
class AcceptanceData:
    channel: str
    accepted_at: datetime
    accepted_by_name: str
    evidence_reference: str
    evidence_document_id: UUID | None = None
    notes: str | None = None


@dataclass(frozen=True, slots=True)
class OrderItemRecord:
    id: UUID
    product_id: UUID
    sku: str
    name: str
    description: str
    quantity: Decimal
    unit: str
    unit_price: Decimal
    line_total: Decimal


@dataclass(frozen=True, slots=True)
class OrderTransitionRecord:
    from_status: str | None
    to_status: str
    reason: str | None
    actor_id: UUID
    occurred_at: datetime
    version_after: int


@dataclass(frozen=True, slots=True)
class AmendmentRecord:
    reason: str
    changes: dict[str, Any]
    actor_id: UUID
    created_at: datetime
    version_after: int


@dataclass(frozen=True, slots=True)
class SalesOrderRecord:
    id: UUID
    company_id: UUID
    order_number: str
    deal_id: UUID
    deal_reference: str
    sales_quote_id: UUID
    quote_number: str
    sales_quote_revision: int
    acceptance_evidence_id: UUID
    customer_id: UUID
    customer_name: str
    currency: str
    incoterm: str
    named_delivery_place: str
    payment_terms_snapshot: str
    fulfilment_model: str
    order_total: Decimal
    status: str
    expected_delivery_date: date | None
    notes: str | None
    confirmed_at: datetime
    cancelled_at: datetime | None
    cancellation_reason: str | None
    version: int
    created_by: UUID
    created_at: datetime
    updated_at: datetime
    items: tuple[OrderItemRecord, ...]
    transitions: tuple[OrderTransitionRecord, ...]
    amendments: tuple[AmendmentRecord, ...]
    accepted_terms: dict[str, Any]

    @property
    def allowed_transitions(self) -> tuple[str, ...]:
        return allowed_sales_order_targets(self.status)


@dataclass(frozen=True, slots=True)
class SalesOrderSummaryRecord:
    id: UUID
    company_id: UUID
    order_number: str
    deal_id: UUID
    deal_reference: str
    sales_quote_id: UUID
    quote_number: str
    sales_quote_revision: int
    customer_id: UUID
    customer_name: str
    currency: str
    incoterm: str
    named_delivery_place: str
    fulfilment_model: str
    order_total: Decimal
    status: str
    confirmed_at: datetime
    expected_delivery_date: date | None
    version: int
    updated_at: datetime


@dataclass(frozen=True, slots=True)
class OrderFilters:
    search: str | None = None
    status: str | None = None
    customer_id: UUID | None = None
    currency: str | None = None
    deal_id: UUID | None = None

    def as_fingerprint(self) -> dict[str, str | None]:
        return {
            "search": self.search,
            "status": self.status,
            "customer_id": str(self.customer_id) if self.customer_id else None,
            "currency": self.currency,
            "deal_id": str(self.deal_id) if self.deal_id else None,
        }


@dataclass(frozen=True, slots=True)
class OrderPage:
    items: tuple[SalesOrderSummaryRecord, ...]
    next_cursor: str | None


@dataclass(frozen=True, slots=True)
class AmendmentLine:
    item_id: UUID
    quantity: Decimal


@dataclass(frozen=True, slots=True)
class AmendmentData:
    reason: str
    payment_terms: str | None = None
    named_delivery_place: str | None = None
    expected_delivery_date: date | None = None
    notes: str | None = None
    lines: tuple[AmendmentLine, ...] = ()


@dataclass(frozen=True, slots=True)
class ConversionData:
    sales_quote_id: UUID
    acceptance_evidence_id: UUID | None
    customer_acceptance: AcceptanceData | None
    fulfilment_model: str
    expected_delivery_date: date | None
    notes: str | None
    expected_total: Decimal | None
    order_number: str | None


def _acceptance_record(row: CustomerAcceptanceEvidence) -> AcceptanceRecord:
    return AcceptanceRecord(
        id=row.id,
        company_id=row.company_id,
        deal_id=row.deal_id,
        sales_quote_id=row.sales_quote_id,
        sales_quote_revision=row.sales_quote_revision,
        channel=row.channel,
        accepted_at=row.accepted_at,
        accepted_by_name=row.accepted_by_name,
        evidence_reference=row.evidence_reference,
        evidence_document_id=row.evidence_document_id,
        notes=row.notes,
        recorded_by=row.recorded_by,
        recorded_at=row.recorded_at,
    )


def _normalise_acceptance(data: AcceptanceData, *, now: datetime) -> AcceptanceData:
    try:
        channel = AcceptanceChannel(data.channel).value
    except ValueError as exc:
        raise BadRequestError(
            "Unknown acceptance channel.",
            details=[
                {
                    "field": "channel",
                    "message": "Use SIGNED_QUOTE, PURCHASE_ORDER, EMAIL, PORTAL or OTHER.",
                    "type": "value_error",
                }
            ],
        ) from exc

    name = " ".join(data.accepted_by_name.split())
    if not 2 <= len(name) <= 160:
        raise BadRequestError(
            "Record the name of the person who accepted the quote (2-160 characters).",
            details=[
                {
                    "field": "accepted_by_name",
                    "message": "A named customer contact is required.",
                    "type": "value_error",
                }
            ],
        )

    reference = " ".join(data.evidence_reference.split())
    if not 3 <= len(reference) <= 500:
        raise BadRequestError(
            "An evidence reference of 3-500 characters is required.",
            details=[
                {
                    "field": "evidence_reference",
                    "message": "Quote the signed document, PO number or email subject.",
                    "type": "evidence_required",
                }
            ],
        )

    accepted_at = data.accepted_at
    if accepted_at.tzinfo is None:
        accepted_at = accepted_at.replace(tzinfo=UTC)
    if accepted_at > now:
        raise BadRequestError(
            "The acceptance timestamp cannot be in the future.",
            details=[
                {
                    "field": "accepted_at",
                    "message": "Record when the customer actually accepted.",
                    "type": "value_error",
                }
            ],
        )

    return AcceptanceData(
        channel=channel,
        accepted_at=accepted_at,
        accepted_by_name=name,
        evidence_reference=reference,
        evidence_document_id=data.evidence_document_id,
        notes=clean_optional(data.notes),
    )


def _order_item_records(rows: list[SalesOrderItem]) -> tuple[OrderItemRecord, ...]:
    return tuple(
        OrderItemRecord(
            id=row.id,
            product_id=row.product_id,
            sku=row.sku,
            name=row.name,
            description=row.description,
            quantity=row.quantity,
            unit=row.unit,
            unit_price=row.unit_price,
            line_total=row.line_total,
        )
        for row in rows
    )


def _load(session: Session, *, company_id: UUID, sales_order_id: UUID) -> SalesOrderRecord:
    row = (
        session.execute(
            select(
                SalesOrder,
                Deal.reference.label("deal_reference"),
                SalesQuote.quote_number,
                Counterparty.name.label("customer_name"),
            )
            .join(
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
                Counterparty,
                and_(
                    Counterparty.id == SalesOrder.customer_id,
                    Counterparty.company_id == SalesOrder.company_id,
                ),
            )
            .where(
                SalesOrder.id == sales_order_id,
                SalesOrder.company_id == company_id,
            )
        )
        .mappings()
        .one_or_none()
    )
    if row is None:
        raise NotFoundError("The sales order does not exist.")
    order: SalesOrder = row["SalesOrder"]

    items = list(
        session.execute(
            select(SalesOrderItem)
            .where(
                SalesOrderItem.company_id == company_id,
                SalesOrderItem.sales_order_id == order.id,
            )
            .order_by(SalesOrderItem.sku)
        ).scalars()
    )
    transitions = list(
        session.execute(
            select(SalesOrderTransition)
            .where(
                SalesOrderTransition.company_id == company_id,
                SalesOrderTransition.sales_order_id == order.id,
            )
            .order_by(SalesOrderTransition.occurred_at, SalesOrderTransition.version_after)
        ).scalars()
    )
    amendments = list(
        session.execute(
            select(OrderAmendment)
            .where(
                OrderAmendment.company_id == company_id,
                OrderAmendment.sales_order_id == order.id,
            )
            .order_by(OrderAmendment.created_at)
        ).scalars()
    )

    return SalesOrderRecord(
        id=order.id,
        company_id=order.company_id,
        order_number=order.order_number,
        deal_id=order.deal_id,
        deal_reference=str(row["deal_reference"]),
        sales_quote_id=order.sales_quote_id,
        quote_number=str(row["quote_number"]),
        sales_quote_revision=order.sales_quote_revision,
        acceptance_evidence_id=order.acceptance_evidence_id,
        customer_id=order.customer_id,
        customer_name=str(row["customer_name"]),
        currency=order.currency,
        incoterm=order.incoterm,
        named_delivery_place=order.named_delivery_place,
        payment_terms_snapshot=order.payment_terms_snapshot,
        fulfilment_model=order.fulfilment_model,
        order_total=order.order_total,
        status=order.status,
        expected_delivery_date=order.expected_delivery_date,
        notes=order.notes,
        confirmed_at=order.confirmed_at,
        cancelled_at=order.cancelled_at,
        cancellation_reason=order.cancellation_reason,
        version=order.version,
        created_by=order.created_by,
        created_at=order.created_at,
        updated_at=order.updated_at,
        items=_order_item_records(items),
        transitions=tuple(
            OrderTransitionRecord(
                from_status=item.from_status,
                to_status=item.to_status,
                reason=item.reason,
                actor_id=item.actor_id,
                occurred_at=item.occurred_at,
                version_after=item.version_after,
            )
            for item in transitions
        ),
        amendments=tuple(
            AmendmentRecord(
                reason=item.reason,
                changes=dict(item.changes),
                actor_id=item.actor_id,
                created_at=item.created_at,
                version_after=item.version_after,
            )
            for item in amendments
        ),
        accepted_terms=dict(order.accepted_terms),
    )


def _quote_rows(
    session: Session, *, company_id: UUID, sales_quote_id: UUID
) -> list[tuple[SalesQuoteItem, Product]]:
    return list(
        session.execute(
            select(SalesQuoteItem, Product)
            .join(
                Product,
                and_(
                    Product.id == SalesQuoteItem.product_id,
                    Product.company_id == SalesQuoteItem.company_id,
                ),
            )
            .where(
                SalesQuoteItem.company_id == company_id,
                SalesQuoteItem.sales_quote_id == sales_quote_id,
            )
            .order_by(SalesQuoteItem.description)
        ).all()
    )


class SalesOrderService:
    """Reads plus the transactional conversion and lifecycle writes."""

    def __init__(self, database: Database) -> None:
        self._database = database

    # ------------------------------------------------------------------ reads
    def list(
        self,
        *,
        company_id: UUID,
        filters: OrderFilters,
        limit: int,
        cursor: str | None,
    ) -> OrderPage:
        with self._database.transaction() as session:
            apply_company_context(session, company_id)
            query = (
                select(
                    SalesOrder,
                    Deal.reference.label("deal_reference"),
                    SalesQuote.quote_number,
                    Counterparty.name.label("customer_name"),
                )
                .join(
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
                    Counterparty,
                    and_(
                        Counterparty.id == SalesOrder.customer_id,
                        Counterparty.company_id == SalesOrder.company_id,
                    ),
                )
                .where(SalesOrder.company_id == company_id)
            )
            if filters.status:
                query = query.where(SalesOrder.status == filters.status)
            if filters.customer_id:
                query = query.where(SalesOrder.customer_id == filters.customer_id)
            if filters.deal_id:
                query = query.where(SalesOrder.deal_id == filters.deal_id)
            if filters.currency:
                query = query.where(SalesOrder.currency == filters.currency.upper())
            if filters.search:
                term = f"%{escape_like(filters.search.lower())}%"
                query = query.where(
                    or_(
                        func.lower(SalesOrder.order_number).like(term, escape="\\"),
                        func.lower(Counterparty.name).like(term, escape="\\"),
                        func.lower(Deal.reference).like(term, escape="\\"),
                    )
                )
            if cursor:
                page_cursor = decode_cursor(cursor, filters=filters.as_fingerprint())
                query = query.where(
                    tuple_(SalesOrder.created_at, SalesOrder.id)
                    < tuple_(page_cursor.created_at, page_cursor.row_id)
                )
            rows = (
                session.execute(
                    query.order_by(SalesOrder.created_at.desc(), SalesOrder.id.desc()).limit(
                        limit + 1
                    )
                )
                .mappings()
                .all()
            )
            has_more = len(rows) > limit
            visible = rows[:limit]
            items = tuple(
                SalesOrderSummaryRecord(
                    id=row["SalesOrder"].id,
                    company_id=row["SalesOrder"].company_id,
                    order_number=row["SalesOrder"].order_number,
                    deal_id=row["SalesOrder"].deal_id,
                    deal_reference=str(row["deal_reference"]),
                    sales_quote_id=row["SalesOrder"].sales_quote_id,
                    quote_number=str(row["quote_number"]),
                    sales_quote_revision=row["SalesOrder"].sales_quote_revision,
                    customer_id=row["SalesOrder"].customer_id,
                    customer_name=str(row["customer_name"]),
                    currency=row["SalesOrder"].currency,
                    incoterm=row["SalesOrder"].incoterm,
                    named_delivery_place=row["SalesOrder"].named_delivery_place,
                    fulfilment_model=row["SalesOrder"].fulfilment_model,
                    order_total=row["SalesOrder"].order_total,
                    status=row["SalesOrder"].status,
                    confirmed_at=row["SalesOrder"].confirmed_at,
                    expected_delivery_date=row["SalesOrder"].expected_delivery_date,
                    version=row["SalesOrder"].version,
                    updated_at=row["SalesOrder"].updated_at,
                )
                for row in visible
            )
            next_cursor = None
            if has_more and visible:
                last = visible[-1]["SalesOrder"]
                next_cursor = encode_cursor(
                    created_at=last.created_at, row_id=last.id, filters=filters.as_fingerprint()
                )
            return OrderPage(items=items, next_cursor=next_cursor)

    def get(self, *, company_id: UUID, sales_order_id: UUID) -> SalesOrderRecord:
        with self._database.transaction() as session:
            apply_company_context(session, company_id)
            return _load(session, company_id=company_id, sales_order_id=sales_order_id)

    def list_acceptances(
        self, *, company_id: UUID, deal_id: UUID
    ) -> tuple[AcceptanceRecord, ...]:
        with self._database.transaction() as session:
            apply_company_context(session, company_id)
            rows = session.execute(
                select(CustomerAcceptanceEvidence)
                .where(
                    CustomerAcceptanceEvidence.company_id == company_id,
                    CustomerAcceptanceEvidence.deal_id == deal_id,
                )
                .order_by(CustomerAcceptanceEvidence.accepted_at.desc())
            ).scalars()
            return tuple(_acceptance_record(row) for row in rows)

    # ----------------------------------------------------------------- writes
    def record_acceptance(
        self, session: Session, *, meta: WriteMeta, deal_id: UUID, data: AcceptanceData
    ) -> AcceptanceRecord:
        """Record customer acceptance for the deal's approved quote revision."""
        deal = session.execute(
            select(Deal).where(Deal.id == deal_id, Deal.company_id == meta.company_id)
        ).scalar_one_or_none()
        if deal is None:
            raise NotFoundError("The deal does not exist.")

        quote = session.execute(
            select(SalesQuote)
            .where(
                SalesQuote.deal_id == deal.id,
                SalesQuote.company_id == meta.company_id,
                SalesQuote.status == SalesQuoteStatus.APPROVED.value,
            )
            .order_by(SalesQuote.revision.desc())
        ).scalars().first()
        if quote is None:
            raise ConflictError(
                "The deal has no approved sales quote to accept.",
                details={"reason": "QUOTE_NOT_APPROVED", "deal_id": str(deal.id)},
            )

        now = datetime.now(tz=UTC)
        normalised = _normalise_acceptance(data, now=now)
        if quote.approved_at is not None and normalised.accepted_at < quote.approved_at:
            raise BadRequestError(
                "The acceptance cannot predate the internal approval of this revision.",
                details=[
                    {
                        "field": "accepted_at",
                        "message": "Acceptance must follow the quote approval.",
                        "type": "value_error",
                    }
                ],
            )

        row = CustomerAcceptanceEvidence(
            company_id=meta.company_id,
            deal_id=deal.id,
            sales_quote_id=quote.id,
            sales_quote_revision=quote.revision,
            channel=normalised.channel,
            accepted_at=normalised.accepted_at,
            accepted_by_name=normalised.accepted_by_name,
            evidence_reference=normalised.evidence_reference,
            evidence_document_id=normalised.evidence_document_id,
            notes=normalised.notes,
            recorded_by=meta.actor_id,
            recorded_at=now,
        )
        session.add(row)
        session.flush()

        record_audit(
            session,
            action=AuditAction.CUSTOMER_ACCEPTANCE_RECORDED,
            outcome=AuditOutcome.SUCCESS,
            actor_id=meta.actor_id,
            company_id=meta.company_id,
            request_id=meta.request_id,
            ip_address=meta.ip_address,
            user_agent=meta.user_agent,
            resource_type="customer_acceptance_evidence",
            resource_id=str(row.id),
            details={
                "deal_id": str(deal.id),
                "sales_quote_id": str(quote.id),
                "revision": quote.revision,
                "channel": row.channel,
                "accepted_at": row.accepted_at,
            },
        )
        return _acceptance_record(row)

    def _resolve_acceptance(
        self,
        session: Session,
        *,
        meta: WriteMeta,
        deal: Deal,
        quote: SalesQuote,
        data: ConversionData,
        now: datetime,
    ) -> CustomerAcceptanceEvidence:
        """Return acceptance evidence that provably matches this revision."""
        if data.acceptance_evidence_id is not None:
            evidence = session.execute(
                select(CustomerAcceptanceEvidence).where(
                    CustomerAcceptanceEvidence.id == data.acceptance_evidence_id,
                    CustomerAcceptanceEvidence.company_id == meta.company_id,
                )
            ).scalar_one_or_none()
            if evidence is None:
                raise BadRequestError(
                    "The referenced customer acceptance evidence does not exist.",
                    details={"reason": "ACCEPTANCE_NOT_FOUND"},
                )
        elif data.customer_acceptance is not None:
            if quote.approved_at is None:
                raise ConflictError(
                    "The quote has no approval timestamp to accept.",
                    details={"reason": "QUOTE_NOT_APPROVED"},
                )
            normalised = _normalise_acceptance(data.customer_acceptance, now=now)
            if normalised.accepted_at < quote.approved_at:
                raise BadRequestError(
                    "Customer acceptance cannot predate the internal approval.",
                    details=[
                        {
                            "field": "customer_acceptance.accepted_at",
                            "message": "Acceptance must follow the quote approval.",
                            "type": "value_error",
                        }
                    ],
                )
            evidence = CustomerAcceptanceEvidence(
                company_id=meta.company_id,
                deal_id=deal.id,
                sales_quote_id=quote.id,
                sales_quote_revision=quote.revision,
                channel=normalised.channel,
                accepted_at=normalised.accepted_at,
                accepted_by_name=normalised.accepted_by_name,
                evidence_reference=normalised.evidence_reference,
                evidence_document_id=normalised.evidence_document_id,
                notes=normalised.notes,
                recorded_by=meta.actor_id,
                recorded_at=now,
            )
            session.add(evidence)
            session.flush()
            record_audit(
                session,
                action=AuditAction.CUSTOMER_ACCEPTANCE_RECORDED,
                outcome=AuditOutcome.SUCCESS,
                actor_id=meta.actor_id,
                company_id=meta.company_id,
                request_id=meta.request_id,
                ip_address=meta.ip_address,
                user_agent=meta.user_agent,
                resource_type="customer_acceptance_evidence",
                resource_id=str(evidence.id),
                details={
                    "deal_id": str(deal.id),
                    "sales_quote_id": str(quote.id),
                    "revision": quote.revision,
                    "channel": evidence.channel,
                    "source": "order_conversion",
                },
            )
        else:
            raise ConflictError(
                "A deal cannot become WON without recorded customer acceptance evidence.",
                details={
                    "reason": "CUSTOMER_ACCEPTANCE_REQUIRED",
                    "hint": "Record customer acceptance, then convert the deal.",
                },
            )

        if evidence.deal_id != deal.id:
            raise ConflictError(
                "The acceptance evidence belongs to a different deal.",
                details={"reason": "ACCEPTANCE_TERMS_MISMATCH"},
            )
        if evidence.sales_quote_id != quote.id or (
            evidence.sales_quote_revision != quote.revision
        ):
            raise ConflictError(
                "The acceptance evidence refers to a different quote revision.",
                details={
                    "reason": "ACCEPTANCE_REVISION_MISMATCH",
                    "accepted_revision": evidence.sales_quote_revision,
                    "current_revision": quote.revision,
                },
            )
        if quote.approved_at is not None and evidence.accepted_at < quote.approved_at:
            raise ConflictError(
                "The acceptance predates the approval of the accepted revision.",
                details={"reason": "ACCEPTANCE_BEFORE_APPROVAL"},
            )
        return evidence

    def convert(
        self, session: Session, *, meta: WriteMeta, deal_id: UUID, data: ConversionData
    ) -> SalesOrderRecord:
        """Create the order and win the deal in one transaction (ADR-032)."""
        deal = session.execute(
            select(Deal)
            .where(Deal.id == deal_id, Deal.company_id == meta.company_id)
            .with_for_update()
        ).scalar_one_or_none()
        if deal is None:
            raise NotFoundError("The deal does not exist.")
        if deal.status == DealStatus.WON.value:
            raise AlreadyWonError(
                details={
                    "deal_id": str(deal.id),
                    "hint": "A deal can only produce one initial sales order.",
                }
            )
        if deal.status not in _CONVERTIBLE_DEAL_STATUSES:
            raise ConflictError(
                "Only an open or negotiating deal can be converted into an order.",
                details={"status": deal.status, "reason": "DEAL_NOT_CONVERTIBLE"},
            )

        try:
            fulfilment_model = FulfilmentModel(data.fulfilment_model).value
        except ValueError as exc:
            raise BadRequestError(
                "Unknown fulfilment model.",
                details=[
                    {
                        "field": "fulfilment_model",
                        "message": "Use PURCHASE_RESALE or BROKERAGE.",
                        "type": "value_error",
                    }
                ],
            ) from exc

        quote = session.execute(
            select(SalesQuote)
            .where(
                SalesQuote.id == data.sales_quote_id,
                SalesQuote.company_id == meta.company_id,
                SalesQuote.deal_id == deal.id,
            )
            .with_for_update()
        ).scalar_one_or_none()
        if quote is None:
            raise NotFoundError("The sales quote does not belong to this deal.")
        if quote.status != SalesQuoteStatus.APPROVED.value or quote.approved_at is None:
            raise ConflictError(
                "Only an approved sales quote can be converted into an order.",
                details={
                    "reason": "QUOTE_NOT_APPROVED",
                    "status": quote.status,
                    "revision": quote.revision,
                },
            )
        if quote.customer_id != deal.counterparty_id:
            raise ConflictError(
                "The approved quote is addressed to a different customer than the deal.",
                details={"reason": "CUSTOMER_MISMATCH"},
            )

        rows = _quote_rows(session, company_id=meta.company_id, sales_quote_id=quote.id)
        if not rows:
            raise ConflictError(
                "The approved quote has no lines to convert.",
                details={"reason": "QUOTE_HAS_NO_LINES"},
            )
        total = money(sum((row.line_total for row, _product in rows), start=Decimal("0.00")))
        if data.expected_total is not None and money(data.expected_total) != total:
            raise ConflictError(
                "The expected total does not match the accepted quote revision.",
                details={
                    "reason": "TERMS_MISMATCH",
                    "expected_total": str(money(data.expected_total)),
                    "accepted_total": str(total),
                },
            )

        now = datetime.now(tz=UTC)
        evidence = self._resolve_acceptance(
            session, meta=meta, deal=deal, quote=quote, data=data, now=now
        )

        order = SalesOrder(
            company_id=meta.company_id,
            order_number=data.order_number or self._generate_number(now),
            deal_id=deal.id,
            sales_quote_id=quote.id,
            sales_quote_revision=quote.revision,
            acceptance_evidence_id=evidence.id,
            customer_id=quote.customer_id,
            currency=quote.currency,
            incoterm=quote.incoterm,
            named_delivery_place=quote.named_delivery_place,
            payment_terms_snapshot=quote.payment_terms,
            fulfilment_model=fulfilment_model,
            order_total=total,
            status=SalesOrderStatus.CONFIRMED.value,
            accepted_terms=self._accepted_terms(
                deal=deal, quote=quote, evidence=evidence, rows=rows, total=total, now=now
            ),
            expected_delivery_date=data.expected_delivery_date,
            notes=clean_optional(data.notes),
            confirmed_at=now,
            created_by=meta.actor_id,
            created_at=now,
            updated_at=now,
        )
        session.add(order)
        try:
            session.flush()
        except IntegrityError as exc:
            raise AlreadyWonError(
                "This deal already has a sales order.",
                details={"reason": "ORDER_ALREADY_EXISTS"},
            ) from exc

        for row, product in rows:
            session.add(
                SalesOrderItem(
                    company_id=meta.company_id,
                    sales_order_id=order.id,
                    product_id=row.product_id,
                    sku=product.sku,
                    name=product.name,
                    description=row.description,
                    quantity=row.quantity,
                    unit=row.unit,
                    unit_price=row.unit_price,
                    line_total=row.line_total,
                    created_at=now,
                )
            )
        session.flush()

        session.add(
            SalesOrderTransition(
                company_id=meta.company_id,
                sales_order_id=order.id,
                from_status=None,
                to_status=SalesOrderStatus.CONFIRMED.value,
                reason=f"Created from accepted quote {quote.quote_number} r{quote.revision}",
                actor_id=meta.actor_id,
                request_id=meta.request_id,
                version_after=order.version,
                occurred_at=now,
            )
        )
        self._win_deal(session, meta=meta, deal=deal, order=order, now=now)

        record_audit(
            session,
            action=AuditAction.SALES_ORDER_CREATED,
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
                "deal_id": str(deal.id),
                "sales_quote_id": str(quote.id),
                "revision": quote.revision,
                "acceptance_evidence_id": str(evidence.id),
                "fulfilment_model": fulfilment_model,
                "order_total": str(total),
                "currency": order.currency,
            },
        )
        session.flush()
        return _load(session, company_id=meta.company_id, sales_order_id=order.id)

    @staticmethod
    def _generate_number(now: datetime) -> str:
        return f"SO-{now:%y%m}-{uuid4().hex[:6].upper()}"

    @staticmethod
    def _accepted_terms(
        *,
        deal: Deal,
        quote: SalesQuote,
        evidence: CustomerAcceptanceEvidence,
        rows: Sequence[tuple[SalesQuoteItem, Product]],
        total: Decimal,
        now: datetime,
    ) -> dict[str, object]:
        """Immutable picture of exactly what the customer accepted."""
        return {
            "captured_at": now.isoformat(),
            "deal_id": str(deal.id),
            "deal_reference": deal.reference,
            "sales_quote_id": str(quote.id),
            "quote_number": quote.quote_number,
            "revision": quote.revision,
            "approved_by": str(quote.approved_by) if quote.approved_by else None,
            "approved_at": quote.approved_at.isoformat() if quote.approved_at else None,
            "acceptance_evidence_id": str(evidence.id),
            "acceptance_channel": evidence.channel,
            "accepted_at": evidence.accepted_at.isoformat(),
            "accepted_by_name": evidence.accepted_by_name,
            "evidence_reference": evidence.evidence_reference,
            "customer_id": str(quote.customer_id),
            "currency": quote.currency,
            "incoterm": quote.incoterm,
            "named_delivery_place": quote.named_delivery_place,
            "payment_terms": quote.payment_terms,
            "valid_until": quote.valid_until.isoformat(),
            "total_value": str(total),
            "items": [
                {
                    "product_id": str(row.product_id),
                    "sku": product.sku,
                    "name": product.name,
                    "description": row.description,
                    "quantity": str(row.quantity),
                    "unit": row.unit,
                    "unit_price": str(row.unit_price),
                    "line_total": str(row.line_total),
                }
                for row, product in rows
            ],
        }

    @staticmethod
    def _win_deal(
        session: Session, *, meta: WriteMeta, deal: Deal, order: SalesOrder, now: datetime
    ) -> None:
        """Transition the deal to WON inside the order transaction (ADR-032)."""
        previous = deal.status
        deal.status = DealStatus.WON.value
        deal.version += 1
        deal.updated_at = now
        deal.closed_at = now
        session.add(
            DealTransition(
                company_id=meta.company_id,
                deal_id=deal.id,
                from_status=previous,
                to_status=DealStatus.WON.value,
                reason=f"Sales order {order.order_number}"[:500],
                actor_id=meta.actor_id,
                request_id=meta.request_id,
                version_after=deal.version,
                occurred_at=now,
            )
        )
        session.flush()
        record_audit(
            session,
            action=AuditAction.DEAL_WON,
            outcome=AuditOutcome.SUCCESS,
            actor_id=meta.actor_id,
            company_id=meta.company_id,
            request_id=meta.request_id,
            ip_address=meta.ip_address,
            user_agent=meta.user_agent,
            resource_type="deal",
            resource_id=str(deal.id),
            details={
                "from": previous,
                "to": DealStatus.WON.value,
                "sales_order_id": str(order.id),
                "order_number": order.order_number,
                "version": deal.version,
            },
        )

    def transition(
        self,
        session: Session,
        *,
        meta: WriteMeta,
        sales_order_id: UUID,
        expected_version: int,
        target: str,
        reason: str | None,
    ) -> SalesOrderRecord:
        order = session.execute(
            select(SalesOrder)
            .where(SalesOrder.id == sales_order_id, SalesOrder.company_id == meta.company_id)
            .with_for_update()
        ).scalar_one_or_none()
        if order is None:
            raise NotFoundError("The sales order does not exist.")
        if order.version != expected_version:
            raise VersionConflictError(
                "The sales order was modified by another request.",
                details={"current_version": order.version},
                headers={"ETag": f'"v{order.version}"'},
            )

        previous = order.status
        cleaned = validate_sales_order_transition(previous, target, reason)
        now = datetime.now(tz=UTC)
        order.status = target
        order.version += 1
        order.updated_at = now
        if target == SalesOrderStatus.CANCELLED.value:
            order.cancelled_at = now
            order.cancellation_reason = cleaned
        order.notes = order.notes
        session.add(
            SalesOrderTransition(
                company_id=meta.company_id,
                sales_order_id=order.id,
                from_status=previous,
                to_status=target,
                reason=cleaned,
                actor_id=meta.actor_id,
                request_id=meta.request_id,
                version_after=order.version,
                occurred_at=now,
            )
        )
        session.flush()
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
                "reason": cleaned,
                "version": order.version,
            },
        )
        return _load(session, company_id=meta.company_id, sales_order_id=order.id)

    def amend(
        self,
        session: Session,
        *,
        meta: WriteMeta,
        sales_order_id: UUID,
        expected_version: int,
        data: AmendmentData,
    ) -> SalesOrderRecord:
        """Record a reasoned amendment without rewriting the accepted snapshot."""
        order = session.execute(
            select(SalesOrder)
            .where(SalesOrder.id == sales_order_id, SalesOrder.company_id == meta.company_id)
            .with_for_update()
        ).scalar_one_or_none()
        if order is None:
            raise NotFoundError("The sales order does not exist.")
        if order.version != expected_version:
            raise VersionConflictError(
                "The sales order was modified by another request.",
                details={"current_version": order.version},
                headers={"ETag": f'"v{order.version}"'},
            )
        if order.status in (SalesOrderStatus.CANCELLED.value, SalesOrderStatus.CLOSED.value):
            raise ConflictError(
                "A cancelled or closed order cannot be amended.",
                details={"status": order.status},
            )

        reason = clean_optional(data.reason)
        if reason is None or not 3 <= len(reason) <= _MAX_REASON:
            raise ReasonRequiredError(
                "An amendment requires a reason of 3 to 500 characters."
            )

        changes: dict[str, object] = {}
        if data.payment_terms is not None:
            terms = " ".join(data.payment_terms.split())
            if not 2 <= len(terms) <= 200:
                raise BadRequestError("Payment terms must be 2-200 characters.")
            changes["payment_terms"] = {"from": order.payment_terms_snapshot, "to": terms}
            order.payment_terms_snapshot = terms
        if data.named_delivery_place is not None:
            place = " ".join(data.named_delivery_place.split())
            if not 2 <= len(place) <= 160:
                raise BadRequestError("The named delivery place must be 2-160 characters.")
            changes["named_delivery_place"] = {
                "from": order.named_delivery_place,
                "to": place,
            }
            order.named_delivery_place = place
        if data.expected_delivery_date is not None:
            changes["expected_delivery_date"] = {
                "from": order.expected_delivery_date.isoformat()
                if order.expected_delivery_date
                else None,
                "to": data.expected_delivery_date.isoformat(),
            }
            order.expected_delivery_date = data.expected_delivery_date
        if data.notes is not None:
            changes["notes"] = {"from": order.notes, "to": clean_optional(data.notes)}
            order.notes = clean_optional(data.notes)

        if data.lines:
            item_rows = {
                item.id: item
                for item in session.execute(
                    select(SalesOrderItem).where(
                        SalesOrderItem.company_id == meta.company_id,
                        SalesOrderItem.sales_order_id == order.id,
                    )
                ).scalars()
            }
            allocated = {
                row[0]: row[1]
                for row in session.execute(
                    select(ShipmentItem.sales_order_item_id, func.sum(ShipmentItem.quantity))
                    .join(
                        Shipment,
                        and_(
                            Shipment.id == ShipmentItem.shipment_id,
                            Shipment.company_id == ShipmentItem.company_id,
                        ),
                    )
                    .where(
                        ShipmentItem.company_id == meta.company_id,
                        Shipment.sales_order_id == order.id,
                        Shipment.status != ShipmentStatus.CANCELLED.value,
                    )
                    .group_by(ShipmentItem.sales_order_item_id)
                ).all()
            }
            line_changes: list[dict[str, object]] = []
            for line in data.lines:
                item = item_rows.get(line.item_id)
                if item is None:
                    raise BadRequestError(
                        "The amended line does not belong to this order.",
                        details={"item_id": str(line.item_id)},
                    )
                if line.quantity <= 0:
                    raise BadRequestError("An amended quantity must be greater than zero.")
                already = allocated.get(item.id, Decimal("0"))
                if line.quantity < already:
                    raise ConflictError(
                        "The new quantity is below what shipments already allocate.",
                        details={
                            "item_id": str(item.id),
                            "allocated": str(already),
                            "requested": str(line.quantity),
                        },
                    )
                line_changes.append(
                    {
                        "item_id": str(item.id),
                        "sku": item.sku,
                        "from": str(item.quantity),
                        "to": str(line.quantity),
                    }
                )
                item.quantity = line.quantity
                item.line_total = money(line.quantity * item.unit_price)
            changes["lines"] = line_changes
            order.order_total = money(
                sum(
                    (item.line_total for item in item_rows.values()),
                    start=Decimal("0.00"),
                )
            )

        if not changes:
            raise BadRequestError("Provide at least one change to amend.")

        now = datetime.now(tz=UTC)
        order.version += 1
        order.updated_at = now
        session.add(
            OrderAmendment(
                company_id=meta.company_id,
                sales_order_id=order.id,
                reason=reason,
                changes=changes,
                actor_id=meta.actor_id,
                request_id=meta.request_id,
                version_after=order.version,
                created_at=now,
            )
        )
        session.flush()
        record_audit(
            session,
            action=AuditAction.SALES_ORDER_AMENDED,
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
                "reason": reason,
                "changed": sorted(changes),
                "order_total": str(order.order_total),
                "version": order.version,
            },
        )
        return _load(session, company_id=meta.company_id, sales_order_id=order.id)


__all__ = [
    "AcceptanceData",
    "AcceptanceRecord",
    "AmendmentData",
    "AmendmentLine",
    "AmendmentRecord",
    "ConversionData",
    "OrderFilters",
    "OrderItemRecord",
    "OrderPage",
    "OrderTransitionRecord",
    "SalesOrderRecord",
    "SalesOrderService",
    "SalesOrderSummaryRecord",
]

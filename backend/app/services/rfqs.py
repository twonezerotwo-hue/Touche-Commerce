"""Supplier RFQ service: creation, editing, prepared snapshots and dispatch.

An RFQ is addressed to exactly one supplier. Creating an RFQ for several
suppliers is one transaction that writes one RFQ per supplier, so comparison
across a deal happens between RFQs and every quote keeps a single supplier.

Status rules:

* ``DRAFT`` and ``PREPARED`` are distinct. Preparing writes an immutable
  :class:`~app.db.models.sourcing.SupplierRfqRevision` snapshot;
* ``SENT`` additionally requires a channel, a timestamp and recorded evidence â€”
  the database enforces the timestamp, the service requires all three;
* editing a prepared RFQ returns it to ``DRAFT`` and opens the next revision, so
  a prepared snapshot is never rewritten in place;
* a quote arriving moves the RFQ to ``RESPONDED``; closing is explicit.
"""

from __future__ import annotations

from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from datetime import UTC, date, datetime
from decimal import Decimal
from typing import Any
from uuid import UUID, uuid4

from sqlalchemy import and_, delete, func, select, tuple_
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app.core.errors import (
    BadRequestError,
    ConflictError,
    InvalidTransitionError,
    NotFoundError,
    ReasonRequiredError,
    VersionConflictError,
)
from app.db.engine import Database
from app.db.models import (
    AuditAction,
    AuditOutcome,
    Counterparty,
    Deal,
    Product,
    RfqStatus,
    SupplierQuote,
    SupplierQuoteItem,
    SupplierRfq,
    SupplierRfqItem,
    SupplierRfqRevision,
)
from app.db.tenant import apply_company_context
from app.services.audit import record_audit
from app.services.fx import normalise_currency
from app.services.pagination import decode_cursor, encode_cursor
from app.services.pricing_engine import money
from app.services.trade_meta import WriteMeta, clean_optional, escape_like

_RFQ_TRANSITIONS: dict[str, tuple[str, ...]] = {
    RfqStatus.DRAFT.value: (RfqStatus.PREPARED.value, RfqStatus.CANCELLED.value),
    RfqStatus.PREPARED.value: (RfqStatus.SENT.value, RfqStatus.CANCELLED.value),
    RfqStatus.SENT.value: (RfqStatus.CANCELLED.value,),
    RfqStatus.RESPONDED.value: (RfqStatus.CLOSED.value,),
    RfqStatus.CLOSED.value: (),
    RfqStatus.CANCELLED.value: (),
}

EDITABLE_STATUSES = (RfqStatus.DRAFT.value, RfqStatus.PREPARED.value)
"""Statuses in which header fields and lines may still change."""


@dataclass(frozen=True)
class RfqItemInput:
    product_id: UUID
    description: str
    quantity: Decimal
    unit: str
    notes: str | None = None


@dataclass(frozen=True)
class RfqItemRecord:
    id: UUID
    product_id: UUID
    sku: str
    name: str
    unit: str
    description: str
    quantity: Decimal
    notes: str | None


@dataclass(frozen=True)
class RfqQuoteSummary:
    id: UUID
    revision: int
    status: str
    currency: str
    total_value: Decimal
    valid_until: date
    received_at: datetime


@dataclass(frozen=True)
class RfqRevisionRecord:
    revision: int
    reason: str | None
    actor_id: UUID
    created_at: datetime


@dataclass(frozen=True)
class RfqRecord:
    id: UUID
    company_id: UUID
    deal_id: UUID
    deal_reference: str
    supplier_counterparty_id: UUID
    supplier_name: str
    reference_number: str
    requested_currency: str
    requested_delivery_terms: str | None
    delivery_location: str
    response_due_date: date | None
    notes: str | None
    status: str
    revision: int
    version: int
    sent_channel: str | None
    sent_at: datetime | None
    sent_evidence: str | None
    created_by: UUID
    created_at: datetime
    updated_at: datetime
    items: tuple[RfqItemRecord, ...]
    quotes: tuple[RfqQuoteSummary, ...]
    revisions: tuple[RfqRevisionRecord, ...]

    @property
    def allowed_transitions(self) -> tuple[str, ...]:
        return _RFQ_TRANSITIONS.get(self.status, ())

    @property
    def is_editable(self) -> bool:
        return self.status in EDITABLE_STATUSES


@dataclass(frozen=True)
class RfqSummaryRecord:
    id: UUID
    company_id: UUID
    deal_id: UUID
    deal_reference: str
    supplier_counterparty_id: UUID
    supplier_name: str
    reference_number: str
    requested_currency: str
    response_due_date: date | None
    status: str
    revision: int
    version: int
    item_count: int
    quote_count: int
    created_at: datetime
    updated_at: datetime


@dataclass(frozen=True)
class RfqFilters:
    search: str | None = None
    status: str | None = None
    deal_id: UUID | None = None
    supplier_counterparty_id: UUID | None = None

    def as_fingerprint(self) -> dict[str, str | None]:
        return {
            "search": self.search,
            "status": self.status,
            "deal_id": str(self.deal_id) if self.deal_id else None,
            "supplier_counterparty_id": (
                str(self.supplier_counterparty_id) if self.supplier_counterparty_id else None
            ),
        }


@dataclass(frozen=True)
class RfqPage:
    items: tuple[RfqSummaryRecord, ...]
    next_cursor: str | None


@dataclass(frozen=True)
class RfqCreateData:
    deal_id: UUID
    supplier_ids: tuple[UUID, ...]
    requested_currency: str
    requested_delivery_terms: str | None
    delivery_location: str
    response_due_date: date | None
    notes: str | None
    items: tuple[RfqItemInput, ...]


@dataclass(frozen=True)
class RfqTransitionData:
    to: RfqStatus
    channel: str | None = None
    evidence: str | None = None
    reason: str | None = None


def _item_records(session: Session, *, company_id: UUID, rfq_id: UUID) -> tuple[RfqItemRecord, ...]:
    rows = session.execute(
        select(
            SupplierRfqItem.id,
            SupplierRfqItem.product_id,
            SupplierRfqItem.description,
            SupplierRfqItem.quantity,
            SupplierRfqItem.unit,
            SupplierRfqItem.notes,
            Product.sku,
            Product.name,
        )
        .join(
            Product,
            and_(
                Product.id == SupplierRfqItem.product_id,
                Product.company_id == SupplierRfqItem.company_id,
            ),
        )
        .where(
            SupplierRfqItem.rfq_id == rfq_id,
            SupplierRfqItem.company_id == company_id,
        )
        .order_by(SupplierRfqItem.created_at, SupplierRfqItem.id)
    ).mappings()
    return tuple(
        RfqItemRecord(
            id=row["id"],
            product_id=row["product_id"],
            sku=row["sku"],
            name=row["name"],
            unit=row["unit"],
            description=row["description"],
            quantity=row["quantity"],
            notes=row["notes"],
        )
        for row in rows
    )


def _quote_summaries(
    session: Session, *, company_id: UUID, rfq_id: UUID
) -> tuple[RfqQuoteSummary, ...]:
    totals = (
        select(
            SupplierQuoteItem.quote_id.label("quote_id"),
            func.coalesce(
                func.sum(SupplierQuoteItem.quantity * SupplierQuoteItem.unit_price), 0
            ).label("total_value"),
        )
        .where(SupplierQuoteItem.company_id == company_id)
        .group_by(SupplierQuoteItem.quote_id)
        .subquery()
    )
    rows = session.execute(
        select(
            SupplierQuote.id,
            SupplierQuote.revision,
            SupplierQuote.status,
            SupplierQuote.currency,
            SupplierQuote.valid_until,
            SupplierQuote.received_at,
            totals.c.total_value,
        )
        .outerjoin(totals, totals.c.quote_id == SupplierQuote.id)
        .where(
            SupplierQuote.rfq_id == rfq_id,
            SupplierQuote.company_id == company_id,
        )
        .order_by(SupplierQuote.revision.desc(), SupplierQuote.id.desc())
    ).mappings()
    return tuple(
        RfqQuoteSummary(
            id=row["id"],
            revision=row["revision"],
            status=row["status"],
            currency=row["currency"],
            total_value=money(Decimal(str(row["total_value"] or 0))),
            valid_until=row["valid_until"],
            received_at=row["received_at"],
        )
        for row in rows
    )


def _revision_records(
    session: Session, *, company_id: UUID, rfq_id: UUID
) -> tuple[RfqRevisionRecord, ...]:
    rows = session.scalars(
        select(SupplierRfqRevision)
        .where(
            SupplierRfqRevision.rfq_id == rfq_id,
            SupplierRfqRevision.company_id == company_id,
        )
        .order_by(SupplierRfqRevision.revision.desc())
    )
    return tuple(
        RfqRevisionRecord(
            revision=row.revision,
            reason=row.reason,
            actor_id=row.actor_id,
            created_at=row.created_at,
        )
        for row in rows
    )


def _load(
    session: Session,
    *,
    company_id: UUID,
    rfq_id: UUID,
    include_children: bool = True,
) -> RfqRecord:
    row = session.execute(
        select(SupplierRfq, Deal.reference, Counterparty.name)
        .join(
            Deal,
            and_(Deal.id == SupplierRfq.deal_id, Deal.company_id == SupplierRfq.company_id),
        )
        .join(
            Counterparty,
            and_(
                Counterparty.id == SupplierRfq.supplier_counterparty_id,
                Counterparty.company_id == SupplierRfq.company_id,
            ),
        )
        .where(SupplierRfq.id == rfq_id, SupplierRfq.company_id == company_id)
    ).one_or_none()
    if row is None:
        raise NotFoundError("The RFQ does not exist.")
    rfq, deal_reference, supplier_name = row
    return RfqRecord(
        id=rfq.id,
        company_id=rfq.company_id,
        deal_id=rfq.deal_id,
        deal_reference=deal_reference,
        supplier_counterparty_id=rfq.supplier_counterparty_id,
        supplier_name=supplier_name,
        reference_number=rfq.reference_number,
        requested_currency=rfq.requested_currency,
        requested_delivery_terms=rfq.requested_delivery_terms,
        delivery_location=rfq.delivery_location,
        response_due_date=rfq.response_due_date,
        notes=rfq.notes,
        status=rfq.status,
        revision=rfq.revision,
        version=rfq.version,
        sent_channel=rfq.sent_channel,
        sent_at=rfq.sent_at,
        sent_evidence=rfq.sent_evidence,
        created_by=rfq.created_by,
        created_at=rfq.created_at,
        updated_at=rfq.updated_at,
        items=(
            _item_records(session, company_id=company_id, rfq_id=rfq.id) if include_children else ()
        ),
        quotes=(
            _quote_summaries(session, company_id=company_id, rfq_id=rfq.id)
            if include_children
            else ()
        ),
        revisions=(
            _revision_records(session, company_id=company_id, rfq_id=rfq.id)
            if include_children
            else ()
        ),
    )


def _normalise_description(value: str) -> str:
    description = " ".join(value.split())
    if not description or len(description) > 500:
        raise BadRequestError(
            "Each RFQ line needs a description of 1 to 500 characters.",
            details=[
                {
                    "field": "items.description",
                    "message": "Blank or overly long line description.",
                    "type": "value_error",
                }
            ],
        )
    return description


class RfqService:
    """RFQ persistence, preparation snapshots and dispatch."""

    def __init__(self, database: Database) -> None:
        self._database = database

    # ------------------------------------------------------------------ reads
    def list(
        self,
        *,
        company_id: UUID,
        filters: RfqFilters,
        limit: int,
        cursor: str | None,
    ) -> RfqPage:
        fingerprint = filters.as_fingerprint()
        position = decode_cursor(cursor, filters=fingerprint) if cursor else None

        item_counts = (
            select(
                SupplierRfqItem.rfq_id.label("rfq_id"),
                func.count(SupplierRfqItem.id).label("item_count"),
            )
            .where(SupplierRfqItem.company_id == company_id)
            .group_by(SupplierRfqItem.rfq_id)
            .subquery()
        )
        quote_counts = (
            select(
                SupplierQuote.rfq_id.label("rfq_id"),
                func.count(SupplierQuote.id).label("quote_count"),
            )
            .where(SupplierQuote.company_id == company_id)
            .group_by(SupplierQuote.rfq_id)
            .subquery()
        )

        with self._database.transaction() as session:
            apply_company_context(session, company_id)
            statement = (
                select(
                    SupplierRfq,
                    Deal.reference,
                    Counterparty.name,
                    func.coalesce(item_counts.c.item_count, 0).label("item_count"),
                    func.coalesce(quote_counts.c.quote_count, 0).label("quote_count"),
                )
                .join(
                    Deal,
                    and_(
                        Deal.id == SupplierRfq.deal_id,
                        Deal.company_id == SupplierRfq.company_id,
                    ),
                )
                .join(
                    Counterparty,
                    and_(
                        Counterparty.id == SupplierRfq.supplier_counterparty_id,
                        Counterparty.company_id == SupplierRfq.company_id,
                    ),
                )
                .outerjoin(item_counts, item_counts.c.rfq_id == SupplierRfq.id)
                .outerjoin(quote_counts, quote_counts.c.rfq_id == SupplierRfq.id)
                .where(SupplierRfq.company_id == company_id)
            )
            if filters.status:
                statement = statement.where(SupplierRfq.status == filters.status)
            if filters.deal_id:
                statement = statement.where(SupplierRfq.deal_id == filters.deal_id)
            if filters.supplier_counterparty_id:
                statement = statement.where(
                    SupplierRfq.supplier_counterparty_id == filters.supplier_counterparty_id
                )
            if filters.search:
                pattern = f"%{escape_like(filters.search.strip())}%"
                statement = statement.where(
                    SupplierRfq.reference_number.ilike(pattern, escape="\\")
                    | SupplierRfq.delivery_location.ilike(pattern, escape="\\")
                    | Counterparty.name.ilike(pattern, escape="\\")
                )
            if position is not None:
                statement = statement.where(
                    tuple_(SupplierRfq.created_at, SupplierRfq.id)
                    < tuple_(position.created_at, position.row_id)
                )
            statement = statement.order_by(
                SupplierRfq.created_at.desc(), SupplierRfq.id.desc()
            ).limit(limit + 1)

            rows = session.execute(statement).all()
            has_more = len(rows) > limit
            page = rows[:limit]
            next_cursor = None
            if has_more and page:
                last = page[-1][0]
                next_cursor = encode_cursor(
                    created_at=last.created_at, row_id=last.id, filters=fingerprint
                )
            items = tuple(
                RfqSummaryRecord(
                    id=rfq.id,
                    company_id=rfq.company_id,
                    deal_id=rfq.deal_id,
                    deal_reference=deal_reference,
                    supplier_counterparty_id=rfq.supplier_counterparty_id,
                    supplier_name=supplier_name,
                    reference_number=rfq.reference_number,
                    requested_currency=rfq.requested_currency,
                    response_due_date=rfq.response_due_date,
                    status=rfq.status,
                    revision=rfq.revision,
                    version=rfq.version,
                    item_count=int(item_count),
                    quote_count=int(quote_count),
                    created_at=rfq.created_at,
                    updated_at=rfq.updated_at,
                )
                for rfq, deal_reference, supplier_name, item_count, quote_count in page
            )
            return RfqPage(items=items, next_cursor=next_cursor)

    def get(self, *, company_id: UUID, rfq_id: UUID) -> RfqRecord:
        with self._database.transaction() as session:
            apply_company_context(session, company_id)
            return _load(session, company_id=company_id, rfq_id=rfq_id)

    def get_revision(
        self, *, company_id: UUID, rfq_id: UUID, revision: int
    ) -> tuple[RfqRevisionRecord, dict[str, object]]:
        with self._database.transaction() as session:
            apply_company_context(session, company_id)
            row = session.execute(
                select(SupplierRfqRevision).where(
                    SupplierRfqRevision.rfq_id == rfq_id,
                    SupplierRfqRevision.company_id == company_id,
                    SupplierRfqRevision.revision == revision,
                )
            ).scalar_one_or_none()
            if row is None:
                raise NotFoundError("The RFQ revision does not exist.")
            record = RfqRevisionRecord(
                revision=row.revision,
                reason=row.reason,
                actor_id=row.actor_id,
                created_at=row.created_at,
            )
            return record, dict(row.snapshot)

    # ----------------------------------------------------------------- writes
    def create(
        self, session: Session, *, meta: WriteMeta, data: RfqCreateData
    ) -> tuple[RfqRecord, ...]:
        deal_exists = session.execute(
            select(Deal.id).where(Deal.id == data.deal_id, Deal.company_id == meta.company_id)
        ).scalar_one_or_none()
        if deal_exists is None:
            raise BadRequestError(
                "The deal does not exist in this company.",
                details=[
                    {
                        "field": "deal_id",
                        "message": "Unknown deal for the active company.",
                        "type": "value_error",
                    }
                ],
            )

        if not data.supplier_ids:
            raise BadRequestError("At least one supplier is required.")
        if len(set(data.supplier_ids)) != len(data.supplier_ids):
            raise BadRequestError(
                "Each supplier may be selected only once.",
                details=[
                    {
                        "field": "supplier_ids",
                        "message": "Duplicate supplier in the request.",
                        "type": "value_error",
                    }
                ],
            )

        suppliers = {
            row["id"]: row["type"]
            for row in session.execute(
                select(Counterparty.id, Counterparty.type).where(
                    Counterparty.company_id == meta.company_id,
                    Counterparty.id.in_(data.supplier_ids),
                )
            ).mappings()
        }
        missing_suppliers = [
            str(supplier_id) for supplier_id in data.supplier_ids if supplier_id not in suppliers
        ]
        if missing_suppliers:
            raise BadRequestError(
                "One or more suppliers do not exist in this company.",
                details=[
                    {
                        "field": "supplier_ids",
                        "message": f"Unknown counterparties: {', '.join(missing_suppliers)}",
                        "type": "value_error",
                    }
                ],
            )
        buyers = [
            str(supplier_id)
            for supplier_id in data.supplier_ids
            if suppliers[supplier_id] == "buyer"
        ]
        if buyers:
            raise BadRequestError(
                "An RFQ can only be addressed to a supplier.",
                details=[
                    {
                        "field": "supplier_ids",
                        "message": f"Not a supplier: {', '.join(buyers)}",
                        "type": "value_error",
                    }
                ],
            )

        if not data.items:
            raise BadRequestError(
                "An RFQ needs at least one line.",
                details=[
                    {
                        "field": "items",
                        "message": "At least one product line is required.",
                        "type": "value_error",
                    }
                ],
            )
        product_ids = [item.product_id for item in data.items]
        if len(set(product_ids)) != len(product_ids):
            raise BadRequestError(
                "Each product may appear only once per RFQ.",
                details=[
                    {
                        "field": "items",
                        "message": "Duplicate product in the RFQ lines.",
                        "type": "value_error",
                    }
                ],
            )
        found = set(
            session.execute(
                select(Product.id).where(
                    Product.company_id == meta.company_id,
                    Product.id.in_(product_ids),
                )
            ).scalars()
        )
        missing_products = [
            str(product_id) for product_id in product_ids if product_id not in found
        ]
        if missing_products:
            raise BadRequestError(
                "One or more products do not exist in this company.",
                details=[
                    {
                        "field": "items.product_id",
                        "message": f"Unknown product ids: {', '.join(missing_products)}",
                        "type": "value_error",
                    }
                ],
            )

        currency = normalise_currency(data.requested_currency, "requested_currency")
        location = " ".join(data.delivery_location.split())
        if len(location) < 2:
            raise BadRequestError("The delivery location must not be empty.")
        terms = clean_optional(data.requested_delivery_terms)
        now = datetime.now(tz=UTC)

        created: list[UUID] = []
        for supplier_id in data.supplier_ids:
            rfq = SupplierRfq(
                company_id=meta.company_id,
                deal_id=data.deal_id,
                supplier_counterparty_id=supplier_id,
                reference_number=self._generate_reference(now),
                requested_currency=currency,
                requested_delivery_terms=terms,
                delivery_location=location,
                response_due_date=data.response_due_date,
                notes=clean_optional(data.notes),
                status=RfqStatus.DRAFT.value,
                revision=1,
                version=1,
                created_by=meta.actor_id,
                created_at=now,
                updated_at=now,
            )
            session.add(rfq)
            try:
                session.flush()
            except IntegrityError as exc:
                raise ConflictError("The RFQ reference already exists.") from exc
            created.append(rfq.id)

            for item in data.items:
                session.add(
                    SupplierRfqItem(
                        company_id=meta.company_id,
                        rfq_id=rfq.id,
                        product_id=item.product_id,
                        description=_normalise_description(item.description),
                        quantity=item.quantity,
                        unit=item.unit,
                        notes=clean_optional(item.notes),
                        created_at=now,
                    )
                )
            session.flush()

            record_audit(
                session,
                action=AuditAction.RFQ_CREATED,
                outcome=AuditOutcome.SUCCESS,
                actor_id=meta.actor_id,
                company_id=meta.company_id,
                request_id=meta.request_id,
                ip_address=meta.ip_address,
                user_agent=meta.user_agent,
                resource_type="supplier_rfq",
                resource_id=str(rfq.id),
                details={
                    "reference_number": rfq.reference_number,
                    "deal_id": str(rfq.deal_id),
                    "supplier_counterparty_id": str(rfq.supplier_counterparty_id),
                    "requested_currency": rfq.requested_currency,
                    "item_count": len(data.items),
                    "status": rfq.status,
                },
            )

        return tuple(
            _load(session, company_id=meta.company_id, rfq_id=rfq_id) for rfq_id in created
        )

    @staticmethod
    def _generate_reference(now: datetime) -> str:
        return f"RFQ-{now:%y%m}-{uuid4().hex[:6].upper()}"

    def update(
        self,
        session: Session,
        *,
        meta: WriteMeta,
        rfq_id: UUID,
        expected_version: int,
        changes: Mapping[str, Any],
    ) -> RfqRecord:
        rfq = session.execute(
            select(SupplierRfq)
            .where(SupplierRfq.id == rfq_id, SupplierRfq.company_id == meta.company_id)
            .with_for_update()
        ).scalar_one_or_none()
        if rfq is None:
            raise NotFoundError("The RFQ does not exist.")
        if rfq.version != expected_version:
            raise VersionConflictError(
                "The RFQ was modified by another request.",
                details={"current_version": rfq.version},
                headers={"ETag": f'"v{rfq.version}"'},
            )
        if rfq.status not in EDITABLE_STATUSES:
            raise ConflictError(
                "Only a draft or prepared RFQ can be edited.",
                details={"status": rfq.status},
            )

        applied: dict[str, Any] = {}
        if "requested_currency" in changes:
            rfq.requested_currency = normalise_currency(
                changes["requested_currency"], "requested_currency"
            )
            applied["requested_currency"] = rfq.requested_currency
        if "requested_delivery_terms" in changes:
            rfq.requested_delivery_terms = clean_optional(changes["requested_delivery_terms"])
            applied["requested_delivery_terms"] = rfq.requested_delivery_terms
        if "delivery_location" in changes:
            location = " ".join(str(changes["delivery_location"]).split())
            if len(location) < 2 or len(location) > 160:
                raise BadRequestError(
                    "The delivery location must be 2 to 160 characters.",
                    details=[
                        {
                            "field": "delivery_location",
                            "message": "Blank or overly long delivery location.",
                            "type": "value_error",
                        }
                    ],
                )
            rfq.delivery_location = location
            applied["delivery_location"] = location
        if "response_due_date" in changes:
            rfq.response_due_date = changes["response_due_date"]
            applied["response_due_date"] = (
                str(rfq.response_due_date) if rfq.response_due_date else None
            )
        if "notes" in changes:
            rfq.notes = clean_optional(changes["notes"])
            applied["notes"] = rfq.notes

        if "items" in changes and changes["items"] is not None:
            items: Sequence[RfqItemInput] = changes["items"]
            self._replace_items(session, meta=meta, rfq=rfq, items=items)
            applied["item_count"] = len(items)

        if rfq.status == RfqStatus.PREPARED.value:
            rfq.status = RfqStatus.DRAFT.value
            rfq.revision += 1
            applied["status"] = rfq.status
            applied["revision"] = rfq.revision

        rfq.version += 1
        rfq.updated_at = datetime.now(tz=UTC)
        session.flush()

        record_audit(
            session,
            action=AuditAction.RFQ_UPDATED,
            outcome=AuditOutcome.SUCCESS,
            actor_id=meta.actor_id,
            company_id=meta.company_id,
            request_id=meta.request_id,
            ip_address=meta.ip_address,
            user_agent=meta.user_agent,
            resource_type="supplier_rfq",
            resource_id=str(rfq.id),
            details={"version": rfq.version, "changed": applied},
        )
        return _load(session, company_id=meta.company_id, rfq_id=rfq.id)

    def _replace_items(
        self,
        session: Session,
        *,
        meta: WriteMeta,
        rfq: SupplierRfq,
        items: Sequence[RfqItemInput],
    ) -> None:
        product_ids = [item.product_id for item in items]
        if not product_ids:
            raise BadRequestError(
                "An RFQ needs at least one line.",
                details=[
                    {
                        "field": "items",
                        "message": "At least one product line is required.",
                        "type": "value_error",
                    }
                ],
            )
        if len(set(product_ids)) != len(product_ids):
            raise BadRequestError(
                "Each product may appear only once per RFQ.",
                details=[
                    {
                        "field": "items",
                        "message": "Duplicate product in the RFQ lines.",
                        "type": "value_error",
                    }
                ],
            )
        found = set(
            session.execute(
                select(Product.id).where(
                    Product.company_id == meta.company_id,
                    Product.id.in_(product_ids),
                )
            ).scalars()
        )
        missing = [str(product_id) for product_id in product_ids if product_id not in found]
        if missing:
            raise BadRequestError(
                "One or more products do not exist in this company.",
                details=[
                    {
                        "field": "items.product_id",
                        "message": f"Unknown product ids: {', '.join(missing)}",
                        "type": "value_error",
                    }
                ],
            )

        session.execute(
            delete(SupplierRfqItem).where(
                SupplierRfqItem.rfq_id == rfq.id,
                SupplierRfqItem.company_id == meta.company_id,
            )
        )
        now = datetime.now(tz=UTC)
        for item in items:
            session.add(
                SupplierRfqItem(
                    company_id=meta.company_id,
                    rfq_id=rfq.id,
                    product_id=item.product_id,
                    description=_normalise_description(item.description),
                    quantity=item.quantity,
                    unit=item.unit,
                    notes=clean_optional(item.notes),
                    created_at=now,
                )
            )
        session.flush()

    def transition(
        self,
        session: Session,
        *,
        meta: WriteMeta,
        rfq_id: UUID,
        target: RfqStatus,
        channel: str | None = None,
        evidence: str | None = None,
        reason: str | None = None,
        expected_version: int | None = None,
    ) -> RfqRecord:
        rfq = session.execute(
            select(SupplierRfq)
            .where(SupplierRfq.id == rfq_id, SupplierRfq.company_id == meta.company_id)
            .with_for_update()
        ).scalar_one_or_none()
        if rfq is None:
            raise NotFoundError("The RFQ does not exist.")
        if expected_version is not None and rfq.version != expected_version:
            raise VersionConflictError(
                "The RFQ was modified by another request.",
                details={"current_version": rfq.version},
                headers={"ETag": f'"v{rfq.version}"'},
            )
        allowed = _RFQ_TRANSITIONS.get(rfq.status, ())
        if target.value not in allowed:
            raise InvalidTransitionError(
                f"An RFQ cannot move from {rfq.status} to {target.value}.",
                details={
                    "status": rfq.status,
                    "requested": target.value,
                    "allowed_transitions": list(allowed),
                },
            )

        now = datetime.now(tz=UTC)
        cleaned_reason = clean_optional(reason)
        action = AuditAction.RFQ_UPDATED
        details: dict[str, Any] = {"from_status": rfq.status, "to_status": target.value}

        if target is RfqStatus.PREPARED:
            record = _load(session, company_id=meta.company_id, rfq_id=rfq.id)
            if not record.items:
                raise ConflictError(
                    "An RFQ needs at least one line before it can be prepared.",
                    details={"status": rfq.status},
                )
            session.add(
                SupplierRfqRevision(
                    company_id=meta.company_id,
                    rfq_id=rfq.id,
                    revision=rfq.revision,
                    snapshot=_snapshot(record, actor_id=meta.actor_id, now=now),
                    reason=cleaned_reason,
                    actor_id=meta.actor_id,
                    created_at=now,
                )
            )
            session.flush()
            action = AuditAction.RFQ_PREPARED
            details["revision"] = rfq.revision

        elif target is RfqStatus.SENT:
            cleaned_channel = clean_optional(channel)
            cleaned_evidence = clean_optional(evidence)
            if cleaned_channel is None or len(cleaned_channel) > 40:
                raise BadRequestError(
                    "Sending an RFQ requires the channel that was used.",
                    details=[
                        {
                            "field": "channel",
                            "message": "Provide the delivery channel, for example 'email'.",
                            "type": "value_error",
                        }
                    ],
                )
            if cleaned_evidence is None or len(cleaned_evidence) < 3:
                raise BadRequestError(
                    "Sending an RFQ requires recorded evidence.",
                    details=[
                        {
                            "field": "evidence",
                            "message": (
                                "Record the message id, thread or file that proves it was sent."
                            ),
                            "type": "value_error",
                        }
                    ],
                )
            rfq.sent_channel = cleaned_channel
            rfq.sent_evidence = cleaned_evidence
            rfq.sent_at = now
            action = AuditAction.RFQ_SENT
            details["channel"] = cleaned_channel
            details["evidence"] = cleaned_evidence
        elif target is RfqStatus.CANCELLED:
            if cleaned_reason is None or len(cleaned_reason) < 3:
                raise ReasonRequiredError(
                    "Cancelling an RFQ requires a reason of 3 to 500 characters."
                )
            action = AuditAction.RFQ_CANCELLED
            details["reason"] = cleaned_reason
        elif target is RfqStatus.CLOSED:
            action = AuditAction.RFQ_CLOSED
            if cleaned_reason:
                details["reason"] = cleaned_reason

        rfq.status = target.value
        rfq.version += 1
        rfq.updated_at = now
        session.flush()

        record_audit(
            session,
            action=action,
            outcome=AuditOutcome.SUCCESS,
            actor_id=meta.actor_id,
            company_id=meta.company_id,
            request_id=meta.request_id,
            ip_address=meta.ip_address,
            user_agent=meta.user_agent,
            resource_type="supplier_rfq",
            resource_id=str(rfq.id),
            details=details,
        )
        return _load(session, company_id=meta.company_id, rfq_id=rfq.id)


def _snapshot(record: RfqRecord, *, actor_id: UUID, now: datetime) -> dict[str, object]:
    """Render an immutable, JSON-safe picture of an RFQ at preparation time."""
    return {
        "reference_number": record.reference_number,
        "status": record.status,
        "revision": record.revision,
        "deal_id": str(record.deal_id),
        "deal_reference": record.deal_reference,
        "supplier_counterparty_id": str(record.supplier_counterparty_id),
        "supplier_name": record.supplier_name,
        "requested_currency": record.requested_currency,
        "requested_delivery_terms": record.requested_delivery_terms,
        "delivery_location": record.delivery_location,
        "response_due_date": (
            record.response_due_date.isoformat() if record.response_due_date else None
        ),
        "notes": record.notes,
        "items": [
            {
                "product_id": str(item.product_id),
                "sku": item.sku,
                "name": item.name,
                "description": item.description,
                "quantity": str(item.quantity),
                "unit": item.unit,
                "notes": item.notes,
            }
            for item in record.items
        ],
        "prepared_by": str(actor_id),
        "prepared_at": now.isoformat(),
    }


__all__ = [
    "EDITABLE_STATUSES",
    "RfqCreateData",
    "RfqFilters",
    "RfqItemInput",
    "RfqItemRecord",
    "RfqPage",
    "RfqQuoteSummary",
    "RfqRecord",
    "RfqRevisionRecord",
    "RfqService",
    "RfqSummaryRecord",
    "RfqTransitionData",
]

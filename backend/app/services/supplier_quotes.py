"""Supplier quote service: recording, revising and withdrawing quote replies.

A quote always belongs to one RFQ, and therefore to one supplier and one deal.
Prices stay ``Decimal``; a line total is ``quantity * unit_price`` rounded once,
so the quote total is the sum of the rounded line totals rather than a second,
drifting rounding.

Revision semantics: a revision is a **new row** that points at the row it
supersedes (``supersedes_quote_id``). Withdrawing or revising never mutates the
previous quote, so a price a supplier gave last month remains readable forever.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import UTC, date, datetime
from decimal import Decimal
from typing import Any
from uuid import UUID

from sqlalchemy import and_, func, select, tuple_
from sqlalchemy.orm import Session

from app.core.errors import (
    BadRequestError,
    ConflictError,
    NotFoundError,
    VersionConflictError,
)
from app.db.engine import Database
from app.db.models import (
    AuditAction,
    AuditOutcome,
    Counterparty,
    Deal,
    Incoterm,
    Product,
    RfqStatus,
    SupplierQuote,
    SupplierQuoteItem,
    SupplierQuoteRevision,
    SupplierQuoteStatus,
    SupplierRfq,
    SupplierRfqItem,
)
from app.db.tenant import apply_company_context
from app.services.audit import record_audit
from app.services.fx import normalise_currency
from app.services.pagination import decode_cursor, encode_cursor
from app.services.pricing_engine import money
from app.services.trade_meta import WriteMeta, clean_optional, escape_like

_ACTIVE_QUOTE_STATUSES = (SupplierQuoteStatus.RECEIVED.value,)
_INCOTERMS = {term.value for term in Incoterm}


@dataclass(frozen=True)
class QuoteItemInput:
    product_id: UUID
    quantity: Decimal
    unit_price: Decimal
    moq: Decimal | None = None
    notes: str | None = None


@dataclass(frozen=True)
class QuoteItemRecord:
    id: UUID
    product_id: UUID
    sku: str
    name: str
    unit: str
    description: str
    quantity: Decimal
    unit_price: Decimal
    moq: Decimal | None
    notes: str | None
    line_total: Decimal


@dataclass(frozen=True)
class QuoteRevisionRecord:
    revision: int
    reason: str | None
    actor_id: UUID
    created_at: datetime


@dataclass(frozen=True)
class QuoteRecord:
    id: UUID
    company_id: UUID
    rfq_id: UUID
    rfq_reference: str
    deal_id: UUID
    deal_reference: str
    supplier_counterparty_id: UUID
    supplier_name: str
    supplier_reference: str | None
    currency: str
    incoterm: str
    named_delivery_place: str
    payment_terms: str
    shipping_conditions: str | None
    lead_time_days: int
    valid_until: date
    status: str
    revision: int
    source_reference: str
    notes: str | None
    received_at: datetime
    supersedes_quote_id: UUID | None
    superseded_by_quote_id: UUID | None
    version: int
    created_by: UUID
    created_at: datetime
    updated_at: datetime
    items: tuple[QuoteItemRecord, ...]
    revisions: tuple[QuoteRevisionRecord, ...]
    total_value: Decimal

    @property
    def is_active(self) -> bool:
        return self.status in _ACTIVE_QUOTE_STATUSES and self.superseded_by_quote_id is None


@dataclass(frozen=True)
class QuoteSummaryRecord:
    id: UUID
    company_id: UUID
    rfq_id: UUID
    rfq_reference: str
    deal_id: UUID
    deal_reference: str
    supplier_counterparty_id: UUID
    supplier_name: str
    supplier_reference: str | None
    currency: str
    incoterm: str
    valid_until: date
    status: str
    revision: int
    received_at: datetime
    superseded_by_quote_id: UUID | None
    version: int
    item_count: int
    total_value: Decimal
    created_at: datetime
    updated_at: datetime


@dataclass(frozen=True)
class QuoteFilters:
    search: str | None = None
    status: str | None = None
    rfq_id: UUID | None = None
    deal_id: UUID | None = None
    supplier_counterparty_id: UUID | None = None
    currency: str | None = None

    def as_fingerprint(self) -> dict[str, str | None]:
        return {
            "search": self.search,
            "status": self.status,
            "rfq_id": str(self.rfq_id) if self.rfq_id else None,
            "deal_id": str(self.deal_id) if self.deal_id else None,
            "supplier_counterparty_id": (
                str(self.supplier_counterparty_id) if self.supplier_counterparty_id else None
            ),
            "currency": self.currency,
        }


@dataclass(frozen=True)
class QuotePage:
    items: tuple[QuoteSummaryRecord, ...]
    next_cursor: str | None


@dataclass(frozen=True)
class QuoteCreateData:
    supplier_reference: str | None
    currency: str
    incoterm: str
    named_delivery_place: str
    payment_terms: str
    shipping_conditions: str | None
    lead_time_days: int
    valid_until: date
    source_reference: str
    notes: str | None
    received_at: datetime | None
    items: tuple[QuoteItemInput, ...]


@dataclass(frozen=True)
class RfqLine:
    product_id: UUID
    description: str
    unit: str


def _item_records(
    session: Session, *, company_id: UUID, quote_id: UUID
) -> tuple[QuoteItemRecord, ...]:
    rows = session.execute(
        select(
            SupplierQuoteItem.id,
            SupplierQuoteItem.product_id,
            SupplierQuoteItem.description,
            SupplierQuoteItem.quantity,
            SupplierQuoteItem.unit,
            SupplierQuoteItem.unit_price,
            SupplierQuoteItem.moq,
            SupplierQuoteItem.line_notes,
            Product.sku,
            Product.name,
        )
        .join(
            Product,
            and_(
                Product.id == SupplierQuoteItem.product_id,
                Product.company_id == SupplierQuoteItem.company_id,
            ),
        )
        .where(
            SupplierQuoteItem.quote_id == quote_id,
            SupplierQuoteItem.company_id == company_id,
        )
        .order_by(SupplierQuoteItem.created_at, SupplierQuoteItem.id)
    ).mappings()
    return tuple(
        QuoteItemRecord(
            id=row["id"],
            product_id=row["product_id"],
            sku=row["sku"],
            name=row["name"],
            unit=row["unit"],
            description=row["description"],
            quantity=row["quantity"],
            unit_price=row["unit_price"],
            moq=row["moq"],
            notes=row["line_notes"],
            line_total=money(row["quantity"] * row["unit_price"]),
        )
        for row in rows
    )


def _revision_records(
    session: Session, *, company_id: UUID, quote_id: UUID
) -> tuple[QuoteRevisionRecord, ...]:
    rows = session.scalars(
        select(SupplierQuoteRevision)
        .where(
            SupplierQuoteRevision.quote_id == quote_id,
            SupplierQuoteRevision.company_id == company_id,
        )
        .order_by(SupplierQuoteRevision.revision.desc())
    )
    return tuple(
        QuoteRevisionRecord(
            revision=row.revision,
            reason=row.reason,
            actor_id=row.actor_id,
            created_at=row.created_at,
        )
        for row in rows
    )


def _superseded_by(session: Session, *, company_id: UUID, quote_id: UUID) -> UUID | None:
    return session.execute(
        select(SupplierQuote.id).where(
            SupplierQuote.supersedes_quote_id == quote_id,
            SupplierQuote.company_id == company_id,
        )
    ).scalar_one_or_none()


def _load(
    session: Session,
    *,
    company_id: UUID,
    quote_id: UUID,
    include_children: bool = True,
) -> QuoteRecord:
    row = session.execute(
        select(
            SupplierQuote,
            SupplierRfq.reference_number,
            SupplierRfq.deal_id,
            Deal.reference,
            Counterparty.name,
        )
        .join(
            SupplierRfq,
            and_(
                SupplierRfq.id == SupplierQuote.rfq_id,
                SupplierRfq.company_id == SupplierQuote.company_id,
            ),
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
                Counterparty.id == SupplierQuote.supplier_counterparty_id,
                Counterparty.company_id == SupplierQuote.company_id,
            ),
        )
        .where(SupplierQuote.id == quote_id, SupplierQuote.company_id == company_id)
    ).one_or_none()
    if row is None:
        raise NotFoundError("The supplier quote does not exist.")
    quote, rfq_reference, deal_id, deal_reference, supplier_name = row
    items = (
        _item_records(session, company_id=company_id, quote_id=quote.id) if include_children else ()
    )
    return QuoteRecord(
        id=quote.id,
        company_id=quote.company_id,
        rfq_id=quote.rfq_id,
        rfq_reference=rfq_reference,
        deal_id=deal_id,
        deal_reference=deal_reference,
        supplier_counterparty_id=quote.supplier_counterparty_id,
        supplier_name=supplier_name,
        supplier_reference=quote.supplier_reference,
        currency=quote.currency,
        incoterm=quote.incoterm,
        named_delivery_place=quote.named_delivery_place,
        payment_terms=quote.payment_terms,
        shipping_conditions=quote.shipping_conditions,
        lead_time_days=quote.lead_time_days,
        valid_until=quote.valid_until,
        status=quote.status,
        revision=quote.revision,
        source_reference=quote.source_reference,
        notes=quote.notes,
        received_at=quote.received_at,
        supersedes_quote_id=quote.supersedes_quote_id,
        superseded_by_quote_id=(
            _superseded_by(session, company_id=company_id, quote_id=quote.id)
            if include_children
            else None
        ),
        version=quote.version,
        created_by=quote.created_by,
        created_at=quote.created_at,
        updated_at=quote.updated_at,
        items=items,
        revisions=(
            _revision_records(session, company_id=company_id, quote_id=quote.id)
            if include_children
            else ()
        ),
        total_value=money(sum((item.line_total for item in items), Decimal("0.00"))),
    )


def _rfq_lines(session: Session, *, company_id: UUID, rfq_id: UUID) -> dict[UUID, RfqLine]:
    rows = session.execute(
        select(
            SupplierRfqItem.product_id,
            SupplierRfqItem.description,
            SupplierRfqItem.unit,
        ).where(
            SupplierRfqItem.rfq_id == rfq_id,
            SupplierRfqItem.company_id == company_id,
        )
    ).mappings()
    return {
        row["product_id"]: RfqLine(
            product_id=row["product_id"],
            description=row["description"],
            unit=row["unit"],
        )
        for row in rows
    }


class SupplierQuoteService:
    """Supplier quote persistence with immutable revision history."""

    def __init__(self, database: Database) -> None:
        self._database = database

    # ------------------------------------------------------------------ reads
    def list(
        self,
        *,
        company_id: UUID,
        filters: QuoteFilters,
        limit: int,
        cursor: str | None,
    ) -> QuotePage:
        fingerprint = filters.as_fingerprint()
        position = decode_cursor(cursor, filters=fingerprint) if cursor else None

        totals = (
            select(
                SupplierQuoteItem.quote_id.label("quote_id"),
                func.count(SupplierQuoteItem.id).label("item_count"),
                func.coalesce(
                    func.sum(SupplierQuoteItem.quantity * SupplierQuoteItem.unit_price), 0
                ).label("total_value"),
            )
            .where(SupplierQuoteItem.company_id == company_id)
            .group_by(SupplierQuoteItem.quote_id)
            .subquery()
        )

        with self._database.transaction() as session:
            apply_company_context(session, company_id)
            statement = (
                select(
                    SupplierQuote,
                    SupplierRfq.reference_number,
                    SupplierRfq.deal_id,
                    Deal.reference,
                    Counterparty.name,
                    func.coalesce(totals.c.item_count, 0).label("item_count"),
                    totals.c.total_value,
                )
                .join(
                    SupplierRfq,
                    and_(
                        SupplierRfq.id == SupplierQuote.rfq_id,
                        SupplierRfq.company_id == SupplierQuote.company_id,
                    ),
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
                        Counterparty.id == SupplierQuote.supplier_counterparty_id,
                        Counterparty.company_id == SupplierQuote.company_id,
                    ),
                )
                .outerjoin(totals, totals.c.quote_id == SupplierQuote.id)
                .where(SupplierQuote.company_id == company_id)
            )
            if filters.status:
                statement = statement.where(SupplierQuote.status == filters.status)
            if filters.rfq_id:
                statement = statement.where(SupplierQuote.rfq_id == filters.rfq_id)
            if filters.deal_id:
                statement = statement.where(SupplierRfq.deal_id == filters.deal_id)
            if filters.supplier_counterparty_id:
                statement = statement.where(
                    SupplierQuote.supplier_counterparty_id == filters.supplier_counterparty_id
                )
            if filters.currency:
                statement = statement.where(SupplierQuote.currency == filters.currency)
            if filters.search:
                pattern = f"%{escape_like(filters.search.strip())}%"
                statement = statement.where(
                    SupplierQuote.source_reference.ilike(pattern, escape="\\")
                    | SupplierQuote.supplier_reference.ilike(pattern, escape="\\")
                    | SupplierRfq.reference_number.ilike(pattern, escape="\\")
                    | Counterparty.name.ilike(pattern, escape="\\")
                )
            if position is not None:
                statement = statement.where(
                    tuple_(SupplierQuote.received_at, SupplierQuote.id)
                    < tuple_(position.created_at, position.row_id)
                )
            statement = statement.order_by(
                SupplierQuote.received_at.desc(), SupplierQuote.id.desc()
            ).limit(limit + 1)

            rows = session.execute(statement).all()
            has_more = len(rows) > limit
            page = rows[:limit]
            next_cursor = None
            if has_more and page:
                last = page[-1][0]
                next_cursor = encode_cursor(
                    created_at=last.received_at, row_id=last.id, filters=fingerprint
                )
            superseded = dict(
                session.execute(
                    select(SupplierQuote.supersedes_quote_id, SupplierQuote.id).where(
                        SupplierQuote.company_id == company_id,
                        SupplierQuote.supersedes_quote_id.is_not(None),
                    )
                ).all()
            )

            items = tuple(
                QuoteSummaryRecord(
                    id=quote.id,
                    company_id=quote.company_id,
                    rfq_id=quote.rfq_id,
                    rfq_reference=rfq_reference,
                    deal_id=deal_id,
                    deal_reference=deal_reference,
                    supplier_counterparty_id=quote.supplier_counterparty_id,
                    supplier_name=supplier_name,
                    supplier_reference=quote.supplier_reference,
                    currency=quote.currency,
                    incoterm=quote.incoterm,
                    valid_until=quote.valid_until,
                    status=quote.status,
                    revision=quote.revision,
                    received_at=quote.received_at,
                    superseded_by_quote_id=superseded.get(quote.id),
                    version=quote.version,
                    item_count=int(item_count),
                    total_value=money(Decimal(str(total_value or 0))),
                    created_at=quote.created_at,
                    updated_at=quote.updated_at,
                )
                for (
                    quote,
                    rfq_reference,
                    deal_id,
                    deal_reference,
                    supplier_name,
                    item_count,
                    total_value,
                ) in page
            )
            return QuotePage(items=items, next_cursor=next_cursor)

    def get(self, *, company_id: UUID, quote_id: UUID) -> QuoteRecord:
        with self._database.transaction() as session:
            apply_company_context(session, company_id)
            return _load(session, company_id=company_id, quote_id=quote_id)

    def get_revision(
        self, *, company_id: UUID, quote_id: UUID, revision: int
    ) -> tuple[QuoteRevisionRecord, dict[str, object]]:
        with self._database.transaction() as session:
            apply_company_context(session, company_id)
            row = session.execute(
                select(SupplierQuoteRevision).where(
                    SupplierQuoteRevision.quote_id == quote_id,
                    SupplierQuoteRevision.company_id == company_id,
                    SupplierQuoteRevision.revision == revision,
                )
            ).scalar_one_or_none()
            if row is None:
                raise NotFoundError("The supplier quote revision does not exist.")
            record = QuoteRevisionRecord(
                revision=row.revision,
                reason=row.reason,
                actor_id=row.actor_id,
                created_at=row.created_at,
            )
            return record, dict(row.snapshot)

    def require_active_quote(
        self, session: Session, *, company_id: UUID, quote_id: UUID
    ) -> QuoteRecord:
        """Return a received, not superseded quote or explain why it cannot be used."""
        record = _load(session, company_id=company_id, quote_id=quote_id)
        if record.status != SupplierQuoteStatus.RECEIVED.value:
            raise ConflictError(
                "Only a received supplier quote can be priced.",
                details={"status": record.status},
            )
        if record.superseded_by_quote_id is not None:
            raise ConflictError(
                "A superseded quote cannot be priced; price the latest revision.",
                details={"superseded_by_quote_id": str(record.superseded_by_quote_id)},
            )
        return record

    # ----------------------------------------------------------------- writes
    def record(
        self, session: Session, *, meta: WriteMeta, rfq_id: UUID, data: QuoteCreateData
    ) -> QuoteRecord:
        rfq = session.execute(
            select(SupplierRfq)
            .where(
                SupplierRfq.id == rfq_id,
                SupplierRfq.company_id == meta.company_id,
            )
            .with_for_update()
        ).scalar_one_or_none()
        if rfq is None:
            raise NotFoundError("The RFQ does not exist.")
        if rfq.status not in (RfqStatus.SENT.value, RfqStatus.RESPONDED.value):
            raise ConflictError(
                "A quote can only be recorded against a sent RFQ.",
                details={"status": rfq.status},
            )
        active_quote = (
            session.execute(
                select(SupplierQuote.id).where(
                    SupplierQuote.rfq_id == rfq.id,
                    SupplierQuote.company_id == meta.company_id,
                    SupplierQuote.status == SupplierQuoteStatus.RECEIVED.value,
                )
            )
            .scalars()
            .first()
        )
        if active_quote is not None:
            raise ConflictError(
                "A received quote already exists for this RFQ; record a revision instead.",
                details={"quote_id": str(active_quote)},
            )

        lines = _rfq_lines(session, company_id=meta.company_id, rfq_id=rfq.id)
        received_at = data.received_at or datetime.now(tz=UTC)
        if received_at.tzinfo is None:
            received_at = received_at.replace(tzinfo=UTC)
        values, items = _validated_quote(data, lines=lines, received_at=received_at)
        now = datetime.now(tz=UTC)

        quote = self._insert(
            session,
            meta=meta,
            rfq=rfq,
            values=values,
            items=items,
            received_at=received_at,
            now=now,
            revision=1,
            supersedes_quote_id=None,
        )

        if rfq.status == RfqStatus.SENT.value:
            rfq.status = RfqStatus.RESPONDED.value
            rfq.version += 1
            rfq.updated_at = now
            session.flush()

        record_audit(
            session,
            action=AuditAction.SUPPLIER_QUOTE_RECORDED,
            outcome=AuditOutcome.SUCCESS,
            actor_id=meta.actor_id,
            company_id=meta.company_id,
            request_id=meta.request_id,
            ip_address=meta.ip_address,
            user_agent=meta.user_agent,
            resource_type="supplier_quote",
            resource_id=str(quote.id),
            details={
                "rfq_id": str(rfq.id),
                "rfq_reference": rfq.reference_number,
                "supplier_counterparty_id": str(quote.supplier_counterparty_id),
                "currency": quote.currency,
                "item_count": len(items),
                "revision": quote.revision,
                "rfq_status": rfq.status,
            },
        )
        return _load(session, company_id=meta.company_id, quote_id=quote.id)

    def revise(
        self,
        session: Session,
        *,
        meta: WriteMeta,
        quote_id: UUID,
        expected_version: int,
        data: QuoteCreateData,
        reason: str | None = None,
    ) -> QuoteRecord:
        previous = session.execute(
            select(SupplierQuote)
            .where(
                SupplierQuote.id == quote_id,
                SupplierQuote.company_id == meta.company_id,
            )
            .with_for_update()
        ).scalar_one_or_none()
        if previous is None:
            raise NotFoundError("The supplier quote does not exist.")
        if previous.version != expected_version:
            raise VersionConflictError(
                "The supplier quote was modified by another request.",
                details={"current_version": previous.version},
                headers={"ETag": f'"v{previous.version}"'},
            )
        if previous.status != SupplierQuoteStatus.RECEIVED.value:
            raise ConflictError(
                "Only a received quote can be revised.",
                details={"status": previous.status},
            )
        child = _superseded_by(session, company_id=meta.company_id, quote_id=quote_id)
        if child is not None:
            raise ConflictError(
                "A newer revision of this quote already exists.",
                details={"superseded_by_quote_id": str(child)},
            )

        rfq = session.execute(
            select(SupplierRfq)
            .where(
                SupplierRfq.id == previous.rfq_id,
                SupplierRfq.company_id == meta.company_id,
            )
            .with_for_update()
        ).scalar_one_or_none()
        if rfq is None:  # pragma: no cover - the composite FK guarantees the parent
            raise NotFoundError("The RFQ does not exist.")

        lines = _rfq_lines(session, company_id=meta.company_id, rfq_id=rfq.id)
        received_at = data.received_at or datetime.now(tz=UTC)
        if received_at.tzinfo is None:
            received_at = received_at.replace(tzinfo=UTC)
        values, items = _validated_quote(data, lines=lines, received_at=received_at)
        now = datetime.now(tz=UTC)

        quote = self._insert(
            session,
            meta=meta,
            rfq=rfq,
            values=values,
            items=items,
            received_at=received_at,
            now=now,
            revision=previous.revision + 1,
            supersedes_quote_id=previous.id,
        )
        record_audit(
            session,
            action=AuditAction.SUPPLIER_QUOTE_REVISED,
            outcome=AuditOutcome.SUCCESS,
            actor_id=meta.actor_id,
            company_id=meta.company_id,
            request_id=meta.request_id,
            ip_address=meta.ip_address,
            user_agent=meta.user_agent,
            resource_type="supplier_quote",
            resource_id=str(quote.id),
            details={
                "rfq_id": str(rfq.id),
                "supersedes_quote_id": str(previous.id),
                "revision": quote.revision,
                "currency": quote.currency,
                "item_count": len(items),
                "reason": clean_optional(reason),
            },
        )
        return _load(session, company_id=meta.company_id, quote_id=quote.id)

    def withdraw(
        self,
        session: Session,
        *,
        meta: WriteMeta,
        quote_id: UUID,
        expected_version: int,
        reason: str,
    ) -> QuoteRecord:
        quote = session.execute(
            select(SupplierQuote)
            .where(
                SupplierQuote.id == quote_id,
                SupplierQuote.company_id == meta.company_id,
            )
            .with_for_update()
        ).scalar_one_or_none()
        if quote is None:
            raise NotFoundError("The supplier quote does not exist.")
        if quote.version != expected_version:
            raise VersionConflictError(
                "The supplier quote was modified by another request.",
                details={"current_version": quote.version},
                headers={"ETag": f'"v{quote.version}"'},
            )
        if quote.status != SupplierQuoteStatus.RECEIVED.value:
            raise ConflictError(
                "Only a received quote can be withdrawn.",
                details={"status": quote.status},
            )
        if _superseded_by(session, company_id=meta.company_id, quote_id=quote_id) is not None:
            raise ConflictError("A superseded quote cannot be withdrawn.")

        cleaned = clean_optional(reason)
        if cleaned is None or len(cleaned) < 3:
            raise BadRequestError(
                "Withdrawing a quote requires a reason of 3 to 500 characters.",
                details=[
                    {
                        "field": "reason",
                        "message": "Explain why the quote was withdrawn.",
                        "type": "value_error",
                    }
                ],
            )

        quote.status = SupplierQuoteStatus.WITHDRAWN.value
        quote.version += 1
        quote.updated_at = datetime.now(tz=UTC)
        session.flush()

        record_audit(
            session,
            action=AuditAction.SUPPLIER_QUOTE_WITHDRAWN,
            outcome=AuditOutcome.SUCCESS,
            actor_id=meta.actor_id,
            company_id=meta.company_id,
            request_id=meta.request_id,
            ip_address=meta.ip_address,
            user_agent=meta.user_agent,
            resource_type="supplier_quote",
            resource_id=str(quote.id),
            details={"reason": cleaned, "version": quote.version},
        )
        return _load(session, company_id=meta.company_id, quote_id=quote.id)

    def _insert(
        self,
        session: Session,
        *,
        meta: WriteMeta,
        rfq: SupplierRfq,
        values: dict[str, Any],
        items: tuple[dict[str, Any], ...],
        received_at: datetime,
        now: datetime,
        revision: int,
        supersedes_quote_id: UUID | None,
    ) -> SupplierQuote:
        quote = SupplierQuote(
            company_id=meta.company_id,
            rfq_id=rfq.id,
            supplier_counterparty_id=rfq.supplier_counterparty_id,
            status=SupplierQuoteStatus.RECEIVED.value,
            revision=revision,
            received_at=received_at,
            supersedes_quote_id=supersedes_quote_id,
            version=1,
            created_by=meta.actor_id,
            created_at=now,
            updated_at=now,
            **values,
        )
        session.add(quote)
        session.flush()

        for item in items:
            session.add(
                SupplierQuoteItem(
                    company_id=meta.company_id,
                    quote_id=quote.id,
                    created_at=now,
                    **item,
                )
            )
        session.flush()

        record = _load(session, company_id=meta.company_id, quote_id=quote.id)
        session.add(
            SupplierQuoteRevision(
                company_id=meta.company_id,
                quote_id=quote.id,
                revision=revision,
                snapshot=_snapshot(record, now=now),
                reason=None,
                actor_id=meta.actor_id,
                created_at=now,
            )
        )
        session.flush()
        return quote


def _validated_quote(
    data: QuoteCreateData, *, lines: dict[UUID, RfqLine], received_at: datetime
) -> tuple[dict[str, Any], tuple[dict[str, Any], ...]]:
    """Normalise a quote payload and bind every line to the RFQ it answers."""
    currency = normalise_currency(data.currency, "currency")
    incoterm = str(data.incoterm).strip().upper()
    if incoterm not in _INCOTERMS:
        raise BadRequestError(
            "Unknown Incoterm; use one of the Incoterms 2020 codes.",
            details=[
                {
                    "field": "incoterm",
                    "message": f"{incoterm} is not an Incoterms 2020 code.",
                    "type": "value_error",
                }
            ],
        )
    place = " ".join(data.named_delivery_place.split())
    if not 2 <= len(place) <= 160:
        raise BadRequestError("The named delivery place must be 2 to 160 characters.")
    payment_terms = " ".join(data.payment_terms.split())
    if not 2 <= len(payment_terms) <= 200:
        raise BadRequestError("The payment terms must be 2 to 200 characters.")
    source_reference = " ".join(data.source_reference.split())
    if not 3 <= len(source_reference) <= 200:
        raise BadRequestError(
            "The source reference must be 3 to 200 characters.",
            details=[
                {
                    "field": "source_reference",
                    "message": ("Reference the email, file or portal message the quote came from."),
                    "type": "value_error",
                }
            ],
        )
    if data.lead_time_days < 0:
        raise BadRequestError(
            "The lead time cannot be negative.",
            details=[
                {
                    "field": "lead_time_days",
                    "message": "Use zero or a positive number of days.",
                    "type": "value_error",
                }
            ],
        )
    if data.valid_until < received_at.date():
        raise BadRequestError(
            "A quote cannot expire before it was received.",
            details=[
                {
                    "field": "valid_until",
                    "message": "The validity date is before the receipt date.",
                    "type": "value_error",
                }
            ],
        )

    if not data.items:
        raise BadRequestError(
            "A supplier quote needs at least one line.",
            details=[
                {
                    "field": "items",
                    "message": "At least one priced line is required.",
                    "type": "value_error",
                }
            ],
        )
    product_ids = [item.product_id for item in data.items]
    if len(set(product_ids)) != len(product_ids):
        raise BadRequestError(
            "Each product may appear only once per quote.",
            details=[
                {
                    "field": "items",
                    "message": "Duplicate product in the quote lines.",
                    "type": "value_error",
                }
            ],
        )
    unknown = [str(product_id) for product_id in product_ids if product_id not in lines]
    if unknown:
        raise BadRequestError(
            "Every quoted product must appear on the RFQ.",
            details=[
                {
                    "field": "items.product_id",
                    "message": f"Products not requested: {', '.join(unknown)}",
                    "type": "value_error",
                }
            ],
        )

    prepared: list[dict[str, Any]] = []
    for item in data.items:
        line = lines[item.product_id]
        if item.quantity <= 0:
            raise BadRequestError(
                "A quoted quantity must be greater than zero.",
                details=[
                    {
                        "field": "items.quantity",
                        "message": f"Invalid quantity for {line.description}.",
                        "type": "value_error",
                    }
                ],
            )
        if item.unit_price < 0:
            raise BadRequestError(
                "A quoted unit price cannot be negative.",
                details=[
                    {
                        "field": "items.unit_price",
                        "message": f"Invalid unit price for {line.description}.",
                        "type": "value_error",
                    }
                ],
            )
        if item.moq is not None and item.moq <= 0:
            raise BadRequestError(
                "A minimum order quantity must be greater than zero.",
                details=[
                    {
                        "field": "items.moq",
                        "message": f"Invalid MOQ for {line.description}.",
                        "type": "value_error",
                    }
                ],
            )
        prepared.append(
            {
                "product_id": item.product_id,
                "description": line.description,
                "quantity": item.quantity,
                "unit": line.unit,
                "unit_price": item.unit_price,
                "moq": item.moq,
                "line_notes": clean_optional(item.notes),
            }
        )

    values: dict[str, Any] = {
        "supplier_reference": clean_optional(data.supplier_reference),
        "currency": currency,
        "incoterm": incoterm,
        "named_delivery_place": place,
        "payment_terms": payment_terms,
        "shipping_conditions": clean_optional(data.shipping_conditions),
        "lead_time_days": data.lead_time_days,
        "valid_until": data.valid_until,
        "source_reference": source_reference,
        "notes": clean_optional(data.notes),
    }
    return values, tuple(prepared)


def _snapshot(record: QuoteRecord, *, now: datetime) -> dict[str, object]:
    """Render an immutable, JSON-safe picture of a quote revision."""
    return {
        "rfq_id": str(record.rfq_id),
        "rfq_reference": record.rfq_reference,
        "deal_id": str(record.deal_id),
        "deal_reference": record.deal_reference,
        "supplier_counterparty_id": str(record.supplier_counterparty_id),
        "supplier_name": record.supplier_name,
        "supplier_reference": record.supplier_reference,
        "currency": record.currency,
        "incoterm": record.incoterm,
        "named_delivery_place": record.named_delivery_place,
        "payment_terms": record.payment_terms,
        "shipping_conditions": record.shipping_conditions,
        "lead_time_days": record.lead_time_days,
        "valid_until": record.valid_until.isoformat(),
        "source_reference": record.source_reference,
        "notes": record.notes,
        "received_at": record.received_at.isoformat(),
        "revision": record.revision,
        "total_value": str(record.total_value),
        "items": [
            {
                "product_id": str(item.product_id),
                "sku": item.sku,
                "name": item.name,
                "unit": item.unit,
                "description": item.description,
                "quantity": str(item.quantity),
                "unit_price": str(item.unit_price),
                "moq": str(item.moq) if item.moq is not None else None,
                "line_total": str(item.line_total),
                "notes": item.notes,
            }
            for item in record.items
        ],
        "recorded_at": now.isoformat(),
    }


__all__ = [
    "QuoteCreateData",
    "QuoteFilters",
    "QuoteItemInput",
    "QuoteItemRecord",
    "QuotePage",
    "QuoteRecord",
    "QuoteRevisionRecord",
    "QuoteSummaryRecord",
    "RfqLine",
    "SupplierQuoteService",
]

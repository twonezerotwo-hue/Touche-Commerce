"""Sales quote service: customer-facing quotations with an approval workflow.

A sales quote is generated from one pricing scenario, so its prices come from a
stored, deterministic landed-cost calculation rather than from whatever the
database says today. The workflow is deliberately boring and auditable:

``DRAFT -> PENDING_APPROVAL -> APPROVED | REJECTED``, with ``WITHDRAWN``
available before approval.

Two rules are enforced in the service, not just in the UI:

* a quote can only be submitted when its scenario's inputs are ``VERIFIED_INPUTS``
  â€” an estimate may be drafted and discussed, never sent for approval;
* the approver must hold ``finance.approve`` (checked by the route) **and** must
  not be the person who submitted the quote (checked here).
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import UTC, date, datetime
from decimal import Decimal
from typing import Any
from uuid import UUID, uuid4

from sqlalchemy import and_, func, select, tuple_
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app.core.errors import (
    BadRequestError,
    ConflictError,
    ForbiddenError,
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
    Incoterm,
    PricingScenario,
    Product,
    SalesQuote,
    SalesQuoteItem,
    SalesQuoteRevision,
    SalesQuoteStatus,
    ScenarioStatus,
)
from app.db.tenant import apply_company_context
from app.services.audit import record_audit
from app.services.fx import normalise_currency
from app.services.pagination import decode_cursor, encode_cursor
from app.services.pricing_engine import money
from app.services.trade_meta import WriteMeta, clean_optional, escape_like

_SALES_TRANSITIONS: dict[str, tuple[str, ...]] = {
    SalesQuoteStatus.DRAFT.value: (
        SalesQuoteStatus.PENDING_APPROVAL.value,
        SalesQuoteStatus.WITHDRAWN.value,
    ),
    SalesQuoteStatus.PENDING_APPROVAL.value: (
        SalesQuoteStatus.APPROVED.value,
        SalesQuoteStatus.REJECTED.value,
        SalesQuoteStatus.WITHDRAWN.value,
    ),
    SalesQuoteStatus.APPROVED.value: (),
    SalesQuoteStatus.REJECTED.value: (),
    SalesQuoteStatus.WITHDRAWN.value: (),
}

_INCOTERMS = {term.value for term in Incoterm}
_APPROVABLE_SCENARIO_STATUSES = (ScenarioStatus.VERIFIED_INPUTS.value,)


@dataclass(frozen=True)
class SalesQuoteItemRecord:
    id: UUID
    product_id: UUID
    sku: str
    name: str
    unit: str
    description: str
    quantity: Decimal
    unit_price: Decimal
    line_total: Decimal


@dataclass(frozen=True)
class SalesQuoteRevisionRecord:
    revision: int
    reason: str | None
    actor_id: UUID
    created_at: datetime


@dataclass(frozen=True)
class SalesQuoteRecord:
    id: UUID
    company_id: UUID
    deal_id: UUID
    deal_reference: str
    quote_number: str
    revision: int
    scenario_id: UUID
    scenario_status: str
    customer_id: UUID
    customer_name: str
    currency: str
    valid_until: date
    incoterm: str
    named_delivery_place: str
    payment_terms: str
    status: str
    notes: str | None
    approved_by: UUID | None
    approved_at: datetime | None
    rejection_reason: str | None
    submitted_by: UUID | None
    submitted_at: datetime | None
    supersedes_sales_quote_id: UUID | None
    superseded_by_sales_quote_id: UUID | None
    version: int
    created_by: UUID
    created_at: datetime
    updated_at: datetime
    items: tuple[SalesQuoteItemRecord, ...]
    revisions: tuple[SalesQuoteRevisionRecord, ...]
    total_value: Decimal

    @property
    def allowed_transitions(self) -> tuple[str, ...]:
        return _SALES_TRANSITIONS.get(self.status, ())

    @property
    def can_submit(self) -> bool:
        return (
            self.status == SalesQuoteStatus.DRAFT.value
            and self.scenario_status in _APPROVABLE_SCENARIO_STATUSES
        )


@dataclass(frozen=True)
class SalesQuoteSummaryRecord:
    id: UUID
    company_id: UUID
    deal_id: UUID
    deal_reference: str
    quote_number: str
    revision: int
    scenario_id: UUID
    scenario_status: str
    customer_id: UUID
    customer_name: str
    currency: str
    valid_until: date
    status: str
    total_value: Decimal
    version: int
    created_at: datetime
    updated_at: datetime


@dataclass(frozen=True)
class SalesQuoteFilters:
    search: str | None = None
    status: str | None = None
    deal_id: UUID | None = None
    customer_id: UUID | None = None
    currency: str | None = None

    def as_fingerprint(self) -> dict[str, str | None]:
        return {
            "search": self.search,
            "status": self.status,
            "deal_id": str(self.deal_id) if self.deal_id else None,
            "customer_id": str(self.customer_id) if self.customer_id else None,
            "currency": self.currency,
        }


@dataclass(frozen=True)
class SalesQuotePage:
    items: tuple[SalesQuoteSummaryRecord, ...]
    next_cursor: str | None


@dataclass(frozen=True)
class SalesQuoteCreateData:
    scenario_id: UUID
    customer_id: UUID
    valid_until: date
    incoterm: str
    named_delivery_place: str
    payment_terms: str
    notes: str | None


@dataclass(frozen=True)
class SalesQuoteReviseData:
    valid_until: date
    notes: str | None
    reason: str | None


@dataclass(frozen=True)
class ScenarioLines:
    scenario_id: UUID
    deal_id: UUID
    currency: str
    status: str
    lines: tuple[dict[str, Any], ...]


def _scenario_lines(session: Session, *, company_id: UUID, scenario_id: UUID) -> ScenarioLines:
    scenario = session.execute(
        select(PricingScenario).where(
            PricingScenario.id == scenario_id,
            PricingScenario.company_id == company_id,
        )
    ).scalar_one_or_none()
    if scenario is None:
        raise NotFoundError("The pricing scenario does not exist.")
    raw_lines = scenario.calculated_results.get("lines")
    lines: list[dict[str, Any]] = []
    if isinstance(raw_lines, list):
        for raw in raw_lines:
            if not isinstance(raw, dict):
                continue
            product_id = raw.get("product_id")
            if not isinstance(product_id, str):
                continue
            lines.append(
                {
                    "product_id": UUID(product_id),
                    "description": str(raw.get("description", "")),
                    "unit": str(raw.get("unit", "")),
                    "quantity": Decimal(str(raw.get("quantity", "0"))),
                    "unit_price": Decimal(str(raw.get("unit_sale_price", "0"))),
                }
            )
    if not lines:
        raise ConflictError("The pricing scenario has no priced lines to quote.")
    return ScenarioLines(
        scenario_id=scenario.id,
        deal_id=scenario.deal_id,
        currency=scenario.target_currency,
        status=scenario.status,
        lines=tuple(lines),
    )


def _item_records(
    session: Session, *, company_id: UUID, sales_quote_id: UUID
) -> tuple[SalesQuoteItemRecord, ...]:
    rows = session.execute(
        select(
            SalesQuoteItem.id,
            SalesQuoteItem.product_id,
            SalesQuoteItem.description,
            SalesQuoteItem.quantity,
            SalesQuoteItem.unit,
            SalesQuoteItem.unit_price,
            SalesQuoteItem.line_total,
            Product.sku,
            Product.name,
        )
        .join(
            Product,
            and_(
                Product.id == SalesQuoteItem.product_id,
                Product.company_id == SalesQuoteItem.company_id,
            ),
        )
        .where(
            SalesQuoteItem.sales_quote_id == sales_quote_id,
            SalesQuoteItem.company_id == company_id,
        )
        .order_by(SalesQuoteItem.created_at, SalesQuoteItem.id)
    ).mappings()
    return tuple(
        SalesQuoteItemRecord(
            id=row["id"],
            product_id=row["product_id"],
            sku=row["sku"],
            name=row["name"],
            unit=row["unit"],
            description=row["description"],
            quantity=row["quantity"],
            unit_price=row["unit_price"],
            line_total=row["line_total"],
        )
        for row in rows
    )


def _revision_records(
    session: Session, *, company_id: UUID, sales_quote_id: UUID
) -> tuple[SalesQuoteRevisionRecord, ...]:
    rows = session.scalars(
        select(SalesQuoteRevision)
        .where(
            SalesQuoteRevision.sales_quote_id == sales_quote_id,
            SalesQuoteRevision.company_id == company_id,
        )
        .order_by(SalesQuoteRevision.revision.desc())
    )
    return tuple(
        SalesQuoteRevisionRecord(
            revision=row.revision,
            reason=row.reason,
            actor_id=row.actor_id,
            created_at=row.created_at,
        )
        for row in rows
    )


def _superseded_by(session: Session, *, company_id: UUID, sales_quote_id: UUID) -> UUID | None:
    return session.execute(
        select(SalesQuote.id).where(
            SalesQuote.supersedes_sales_quote_id == sales_quote_id,
            SalesQuote.company_id == company_id,
        )
    ).scalar_one_or_none()


def _load(
    session: Session,
    *,
    company_id: UUID,
    sales_quote_id: UUID,
    include_children: bool = True,
) -> SalesQuoteRecord:
    row = session.execute(
        select(
            SalesQuote,
            Deal.reference,
            Counterparty.name,
            PricingScenario.status,
        )
        .join(
            Deal,
            and_(
                Deal.id == SalesQuote.deal_id,
                Deal.company_id == SalesQuote.company_id,
            ),
        )
        .join(
            Counterparty,
            and_(
                Counterparty.id == SalesQuote.customer_id,
                Counterparty.company_id == SalesQuote.company_id,
            ),
        )
        .join(
            PricingScenario,
            and_(
                PricingScenario.id == SalesQuote.scenario_id,
                PricingScenario.company_id == SalesQuote.company_id,
            ),
        )
        .where(
            SalesQuote.id == sales_quote_id,
            SalesQuote.company_id == company_id,
        )
    ).one_or_none()
    if row is None:
        raise NotFoundError("The sales quote does not exist.")
    quote, deal_reference, customer_name, scenario_status = row
    items = (
        _item_records(session, company_id=company_id, sales_quote_id=quote.id)
        if include_children
        else ()
    )
    return SalesQuoteRecord(
        id=quote.id,
        company_id=quote.company_id,
        deal_id=quote.deal_id,
        deal_reference=deal_reference,
        quote_number=quote.quote_number,
        revision=quote.revision,
        scenario_id=quote.scenario_id,
        scenario_status=scenario_status,
        customer_id=quote.customer_id,
        customer_name=customer_name,
        currency=quote.currency,
        valid_until=quote.valid_until,
        incoterm=quote.incoterm,
        named_delivery_place=quote.named_delivery_place,
        payment_terms=quote.payment_terms,
        status=quote.status,
        notes=quote.notes,
        approved_by=quote.approved_by,
        approved_at=quote.approved_at,
        rejection_reason=quote.rejection_reason,
        submitted_by=quote.submitted_by,
        submitted_at=quote.submitted_at,
        supersedes_sales_quote_id=quote.supersedes_sales_quote_id,
        superseded_by_sales_quote_id=(
            _superseded_by(session, company_id=company_id, sales_quote_id=quote.id)
            if include_children
            else None
        ),
        version=quote.version,
        created_by=quote.created_by,
        created_at=quote.created_at,
        updated_at=quote.updated_at,
        items=items,
        revisions=(
            _revision_records(session, company_id=company_id, sales_quote_id=quote.id)
            if include_children
            else ()
        ),
        total_value=money(sum((item.line_total for item in items), Decimal("0.00"))),
    )


def _validate_header(
    *, incoterm: str, named_delivery_place: str, payment_terms: str
) -> tuple[str, str, str]:
    resolved = str(incoterm).strip().upper()
    if resolved not in _INCOTERMS:
        raise BadRequestError(
            "Unknown Incoterm; use an Incoterms 2020 code.",
            details=[
                {
                    "field": "incoterm",
                    "message": f"{resolved} is not an Incoterms 2020 code.",
                    "type": "value_error",
                }
            ],
        )
    place = " ".join(named_delivery_place.split())
    if not 2 <= len(place) <= 160:
        raise BadRequestError("The named delivery place must be 2 to 160 characters.")
    terms = " ".join(payment_terms.split())
    if not 2 <= len(terms) <= 200:
        raise BadRequestError("The payment terms must be 2 to 200 characters.")
    return resolved, place, terms


class SalesQuoteService:
    """Sales quote persistence and the approval workflow."""

    def __init__(self, database: Database) -> None:
        self._database = database

    # ------------------------------------------------------------------ reads
    def list(
        self,
        *,
        company_id: UUID,
        filters: SalesQuoteFilters,
        limit: int,
        cursor: str | None,
    ) -> SalesQuotePage:
        fingerprint = filters.as_fingerprint()
        position = decode_cursor(cursor, filters=fingerprint) if cursor else None

        totals = (
            select(
                SalesQuoteItem.sales_quote_id.label("sales_quote_id"),
                func.coalesce(func.sum(SalesQuoteItem.line_total), 0).label("total_value"),
            )
            .where(SalesQuoteItem.company_id == company_id)
            .group_by(SalesQuoteItem.sales_quote_id)
            .subquery()
        )

        with self._database.transaction() as session:
            apply_company_context(session, company_id)
            statement = (
                select(
                    SalesQuote,
                    Deal.reference,
                    Counterparty.name,
                    PricingScenario.status,
                    totals.c.total_value,
                )
                .join(
                    Deal,
                    and_(
                        Deal.id == SalesQuote.deal_id,
                        Deal.company_id == SalesQuote.company_id,
                    ),
                )
                .join(
                    Counterparty,
                    and_(
                        Counterparty.id == SalesQuote.customer_id,
                        Counterparty.company_id == SalesQuote.company_id,
                    ),
                )
                .join(
                    PricingScenario,
                    and_(
                        PricingScenario.id == SalesQuote.scenario_id,
                        PricingScenario.company_id == SalesQuote.company_id,
                    ),
                )
                .outerjoin(totals, totals.c.sales_quote_id == SalesQuote.id)
                .where(SalesQuote.company_id == company_id)
            )
            if filters.status:
                statement = statement.where(SalesQuote.status == filters.status)
            if filters.deal_id:
                statement = statement.where(SalesQuote.deal_id == filters.deal_id)
            if filters.customer_id:
                statement = statement.where(SalesQuote.customer_id == filters.customer_id)
            if filters.currency:
                statement = statement.where(SalesQuote.currency == filters.currency)
            if filters.search:
                pattern = f"%{escape_like(filters.search.strip())}%"
                statement = statement.where(
                    SalesQuote.quote_number.ilike(pattern, escape="\\")
                    | Counterparty.name.ilike(pattern, escape="\\")
                    | Deal.reference.ilike(pattern, escape="\\")
                )
            if position is not None:
                statement = statement.where(
                    tuple_(SalesQuote.created_at, SalesQuote.id)
                    < tuple_(position.created_at, position.row_id)
                )
            statement = statement.order_by(
                SalesQuote.created_at.desc(), SalesQuote.id.desc()
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
                SalesQuoteSummaryRecord(
                    id=quote.id,
                    company_id=quote.company_id,
                    deal_id=quote.deal_id,
                    deal_reference=deal_reference,
                    quote_number=quote.quote_number,
                    revision=quote.revision,
                    scenario_id=quote.scenario_id,
                    scenario_status=scenario_status,
                    customer_id=quote.customer_id,
                    customer_name=customer_name,
                    currency=quote.currency,
                    valid_until=quote.valid_until,
                    status=quote.status,
                    total_value=money(Decimal(str(total_value or 0))),
                    version=quote.version,
                    created_at=quote.created_at,
                    updated_at=quote.updated_at,
                )
                for (
                    quote,
                    deal_reference,
                    customer_name,
                    scenario_status,
                    total_value,
                ) in page
            )
            return SalesQuotePage(items=items, next_cursor=next_cursor)

    def get(self, *, company_id: UUID, sales_quote_id: UUID) -> SalesQuoteRecord:
        with self._database.transaction() as session:
            apply_company_context(session, company_id)
            return _load(session, company_id=company_id, sales_quote_id=sales_quote_id)

    def get_revision(
        self, *, company_id: UUID, sales_quote_id: UUID, revision: int
    ) -> tuple[SalesQuoteRevisionRecord, dict[str, object]]:
        with self._database.transaction() as session:
            apply_company_context(session, company_id)
            row = session.execute(
                select(SalesQuoteRevision).where(
                    SalesQuoteRevision.sales_quote_id == sales_quote_id,
                    SalesQuoteRevision.company_id == company_id,
                    SalesQuoteRevision.revision == revision,
                )
            ).scalar_one_or_none()
            if row is None:
                raise NotFoundError("The sales quote revision does not exist.")
            record = SalesQuoteRevisionRecord(
                revision=row.revision,
                reason=row.reason,
                actor_id=row.actor_id,
                created_at=row.created_at,
            )
            return record, dict(row.snapshot)

    # ----------------------------------------------------------------- writes
    def create(
        self, session: Session, *, meta: WriteMeta, data: SalesQuoteCreateData
    ) -> SalesQuoteRecord:
        scenario = _scenario_lines(
            session, company_id=meta.company_id, scenario_id=data.scenario_id
        )
        customer_type = session.execute(
            select(Counterparty.type).where(
                Counterparty.id == data.customer_id,
                Counterparty.company_id == meta.company_id,
            )
        ).scalar_one_or_none()
        if customer_type is None:
            raise BadRequestError(
                "The customer does not exist in this company.",
                details=[
                    {
                        "field": "customer_id",
                        "message": "Unknown counterparty for the active company.",
                        "type": "value_error",
                    }
                ],
            )
        if customer_type == "supplier":
            raise BadRequestError(
                "A sales quote is addressed to a buyer, not a supplier.",
                details=[
                    {
                        "field": "customer_id",
                        "message": "This counterparty is a supplier.",
                        "type": "value_error",
                    }
                ],
            )

        incoterm, place, terms = _validate_header(
            incoterm=data.incoterm,
            named_delivery_place=data.named_delivery_place,
            payment_terms=data.payment_terms,
        )
        now = datetime.now(tz=UTC)
        if data.valid_until < now.date():
            raise BadRequestError(
                "The validity date cannot be in the past.",
                details=[
                    {
                        "field": "valid_until",
                        "message": "Choose a date on or after today.",
                        "type": "value_error",
                    }
                ],
            )

        quote = self._insert(
            session,
            meta=meta,
            scenario=scenario,
            customer_id=data.customer_id,
            valid_until=data.valid_until,
            incoterm=incoterm,
            named_delivery_place=place,
            payment_terms=terms,
            notes=clean_optional(data.notes),
            now=now,
        )
        record_audit(
            session,
            action=AuditAction.SALES_QUOTE_CREATED,
            outcome=AuditOutcome.SUCCESS,
            actor_id=meta.actor_id,
            company_id=meta.company_id,
            request_id=meta.request_id,
            ip_address=meta.ip_address,
            user_agent=meta.user_agent,
            resource_type="sales_quote",
            resource_id=str(quote.id),
            details={
                "quote_number": quote.quote_number,
                "scenario_id": str(scenario.scenario_id),
                "deal_id": str(scenario.deal_id),
                "customer_id": str(data.customer_id),
                "currency": quote.currency,
                "item_count": len(scenario.lines),
                "revision": quote.revision,
            },
        )
        return _load(session, company_id=meta.company_id, sales_quote_id=quote.id)

    def _insert(
        self,
        session: Session,
        *,
        meta: WriteMeta,
        scenario: ScenarioLines,
        customer_id: UUID,
        valid_until: date,
        incoterm: str,
        named_delivery_place: str,
        payment_terms: str,
        notes: str | None,
        now: datetime,
        revision: int = 1,
        quote_number: str | None = None,
        supersedes_sales_quote_id: UUID | None = None,
    ) -> SalesQuote:
        quote = SalesQuote(
            company_id=meta.company_id,
            deal_id=scenario.deal_id,
            quote_number=quote_number or self._generate_number(now),
            revision=revision,
            scenario_id=scenario.scenario_id,
            customer_id=customer_id,
            currency=normalise_currency(scenario.currency, "currency"),
            valid_until=valid_until,
            incoterm=incoterm,
            named_delivery_place=named_delivery_place,
            payment_terms=payment_terms,
            status=SalesQuoteStatus.DRAFT.value,
            notes=notes,
            supersedes_sales_quote_id=supersedes_sales_quote_id,
            version=1,
            created_by=meta.actor_id,
            created_at=now,
            updated_at=now,
        )
        session.add(quote)
        try:
            session.flush()
        except IntegrityError as exc:  # pragma: no cover - generated numbers are unique
            raise ConflictError("The sales quote number already exists.") from exc

        for line in scenario.lines:
            session.add(
                SalesQuoteItem(
                    company_id=meta.company_id,
                    sales_quote_id=quote.id,
                    product_id=line["product_id"],
                    description=line["description"],
                    quantity=line["quantity"],
                    unit=line["unit"],
                    unit_price=line["unit_price"],
                    line_total=money(line["quantity"] * line["unit_price"]),
                    created_at=now,
                )
            )
        session.flush()

        record = _load(session, company_id=meta.company_id, sales_quote_id=quote.id)
        session.add(
            SalesQuoteRevision(
                company_id=meta.company_id,
                sales_quote_id=quote.id,
                revision=revision,
                snapshot=_snapshot(record, now=now),
                reason=None,
                actor_id=meta.actor_id,
                created_at=now,
            )
        )
        session.flush()
        return quote

    @staticmethod
    def _generate_number(now: datetime) -> str:
        return f"SQ-{now:%y%m}-{uuid4().hex[:6].upper()}"

    def _lock(
        self,
        session: Session,
        *,
        meta: WriteMeta,
        sales_quote_id: UUID,
        expected_version: int,
    ) -> SalesQuote:
        quote = session.execute(
            select(SalesQuote)
            .where(
                SalesQuote.id == sales_quote_id,
                SalesQuote.company_id == meta.company_id,
            )
            .with_for_update()
        ).scalar_one_or_none()
        if quote is None:
            raise NotFoundError("The sales quote does not exist.")
        if quote.version != expected_version:
            raise VersionConflictError(
                "The sales quote was modified by another request.",
                details={"current_version": quote.version},
                headers={"ETag": f'"v{quote.version}"'},
            )
        return quote

    @staticmethod
    def _ensure_target(quote: SalesQuote, target: SalesQuoteStatus) -> None:
        allowed = _SALES_TRANSITIONS.get(quote.status, ())
        if target.value not in allowed:
            raise InvalidTransitionError(
                f"A sales quote cannot move from {quote.status} to {target.value}.",
                details={
                    "status": quote.status,
                    "requested": target.value,
                    "allowed_transitions": list(allowed),
                },
            )

    def _audit(
        self,
        session: Session,
        *,
        meta: WriteMeta,
        action: AuditAction,
        quote: SalesQuote,
        details: dict[str, Any],
    ) -> None:
        record_audit(
            session,
            action=action,
            outcome=AuditOutcome.SUCCESS,
            actor_id=meta.actor_id,
            company_id=meta.company_id,
            request_id=meta.request_id,
            ip_address=meta.ip_address,
            user_agent=meta.user_agent,
            resource_type="sales_quote",
            resource_id=str(quote.id),
            details={"quote_number": quote.quote_number, **details},
        )

    def submit(
        self,
        session: Session,
        *,
        meta: WriteMeta,
        sales_quote_id: UUID,
        expected_version: int,
    ) -> SalesQuoteRecord:
        quote = self._lock(
            session, meta=meta, sales_quote_id=sales_quote_id, expected_version=expected_version
        )
        self._ensure_target(quote, SalesQuoteStatus.PENDING_APPROVAL)

        scenario_status = session.execute(
            select(PricingScenario.status)
            .where(
                PricingScenario.id == quote.scenario_id,
                PricingScenario.company_id == meta.company_id,
            )
            .with_for_update()
        ).scalar_one_or_none()
        if scenario_status is None:  # pragma: no cover - the FK guarantees the parent
            raise NotFoundError("The pricing scenario does not exist.")
        if scenario_status not in _APPROVABLE_SCENARIO_STATUSES:
            raise ConflictError(
                "The pricing scenario must have verified inputs before approval is requested.",
                details={"scenario_status": scenario_status},
            )

        now = datetime.now(tz=UTC)
        quote.status = SalesQuoteStatus.PENDING_APPROVAL.value
        quote.submitted_by = meta.actor_id
        quote.submitted_at = now
        quote.version += 1
        quote.updated_at = now
        session.flush()
        self._audit(
            session,
            meta=meta,
            action=AuditAction.SALES_QUOTE_SUBMITTED,
            quote=quote,
            details={
                "scenario_id": str(quote.scenario_id),
                "scenario_status": scenario_status,
                "version": quote.version,
            },
        )
        return _load(session, company_id=meta.company_id, sales_quote_id=quote.id)

    def approve(
        self,
        session: Session,
        *,
        meta: WriteMeta,
        sales_quote_id: UUID,
        expected_version: int,
        reason: str | None = None,
    ) -> SalesQuoteRecord:
        quote = self._lock(
            session, meta=meta, sales_quote_id=sales_quote_id, expected_version=expected_version
        )
        self._ensure_target(quote, SalesQuoteStatus.APPROVED)
        if quote.submitted_by is not None and quote.submitted_by == meta.actor_id:
            raise ForbiddenError(
                "A quote cannot be approved by the person who submitted it.",
                details={"submitted_by": str(quote.submitted_by)},
            )

        now = datetime.now(tz=UTC)
        quote.status = SalesQuoteStatus.APPROVED.value
        quote.approved_by = meta.actor_id
        quote.approved_at = now
        quote.rejection_reason = None
        quote.version += 1
        quote.updated_at = now
        session.flush()
        self._audit(
            session,
            meta=meta,
            action=AuditAction.SALES_QUOTE_APPROVED,
            quote=quote,
            details={
                "version": quote.version,
                "submitted_by": str(quote.submitted_by) if quote.submitted_by else None,
                "reason": clean_optional(reason),
            },
        )
        return _load(session, company_id=meta.company_id, sales_quote_id=quote.id)

    def reject(
        self,
        session: Session,
        *,
        meta: WriteMeta,
        sales_quote_id: UUID,
        expected_version: int,
        reason: str,
    ) -> SalesQuoteRecord:
        quote = self._lock(
            session, meta=meta, sales_quote_id=sales_quote_id, expected_version=expected_version
        )
        self._ensure_target(quote, SalesQuoteStatus.REJECTED)
        cleaned = clean_optional(reason)
        if cleaned is None or len(cleaned) < 3:
            raise ReasonRequiredError("Rejecting a quote requires a reason of 3 to 500 characters.")

        now = datetime.now(tz=UTC)
        quote.status = SalesQuoteStatus.REJECTED.value
        quote.rejection_reason = cleaned
        quote.approved_by = None
        quote.approved_at = None
        quote.version += 1
        quote.updated_at = now
        session.flush()
        self._audit(
            session,
            meta=meta,
            action=AuditAction.SALES_QUOTE_REJECTED,
            quote=quote,
            details={"version": quote.version, "reason": cleaned},
        )
        return _load(session, company_id=meta.company_id, sales_quote_id=quote.id)

    def withdraw(
        self,
        session: Session,
        *,
        meta: WriteMeta,
        sales_quote_id: UUID,
        expected_version: int,
        reason: str | None = None,
    ) -> SalesQuoteRecord:
        quote = self._lock(
            session, meta=meta, sales_quote_id=sales_quote_id, expected_version=expected_version
        )
        self._ensure_target(quote, SalesQuoteStatus.WITHDRAWN)
        cleaned = clean_optional(reason)

        now = datetime.now(tz=UTC)
        quote.status = SalesQuoteStatus.WITHDRAWN.value
        quote.version += 1
        quote.updated_at = now
        session.flush()
        self._audit(
            session,
            meta=meta,
            action=AuditAction.SALES_QUOTE_WITHDRAWN,
            quote=quote,
            details={"version": quote.version, "reason": cleaned},
        )
        return _load(session, company_id=meta.company_id, sales_quote_id=quote.id)

    def revise(
        self,
        session: Session,
        *,
        meta: WriteMeta,
        sales_quote_id: UUID,
        expected_version: int,
        data: SalesQuoteReviseData,
    ) -> SalesQuoteRecord:
        previous = self._lock(
            session, meta=meta, sales_quote_id=sales_quote_id, expected_version=expected_version
        )
        if previous.status not in (
            SalesQuoteStatus.APPROVED.value,
            SalesQuoteStatus.REJECTED.value,
            SalesQuoteStatus.WITHDRAWN.value,
        ):
            raise ConflictError(
                "Only an approved, rejected or withdrawn quote can be revised.",
                details={"status": previous.status},
            )
        child = _superseded_by(session, company_id=meta.company_id, sales_quote_id=previous.id)
        if child is not None:
            raise ConflictError(
                "A newer revision of this sales quote already exists.",
                details={"superseded_by_sales_quote_id": str(child)},
            )

        scenario = _scenario_lines(
            session, company_id=meta.company_id, scenario_id=previous.scenario_id
        )
        now = datetime.now(tz=UTC)
        if data.valid_until < now.date():
            raise BadRequestError(
                "The validity date cannot be in the past.",
                details=[
                    {
                        "field": "valid_until",
                        "message": "Choose a date on or after today.",
                        "type": "value_error",
                    }
                ],
            )

        quote = self._insert(
            session,
            meta=meta,
            scenario=scenario,
            customer_id=previous.customer_id,
            valid_until=data.valid_until,
            incoterm=previous.incoterm,
            named_delivery_place=previous.named_delivery_place,
            payment_terms=previous.payment_terms,
            notes=clean_optional(data.notes) or previous.notes,
            now=now,
            revision=previous.revision + 1,
            quote_number=previous.quote_number,
            supersedes_sales_quote_id=previous.id,
        )
        self._audit(
            session,
            meta=meta,
            action=AuditAction.SALES_QUOTE_CREATED,
            quote=quote,
            details={
                "revision": quote.revision,
                "supersedes_sales_quote_id": str(previous.id),
                "reason": clean_optional(data.reason),
                "scenario_id": str(quote.scenario_id),
            },
        )
        return _load(session, company_id=meta.company_id, sales_quote_id=quote.id)


def _snapshot(record: SalesQuoteRecord, *, now: datetime) -> dict[str, object]:
    """Render an immutable, JSON-safe picture of a sales quote revision."""
    return {
        "quote_number": record.quote_number,
        "revision": record.revision,
        "deal_id": str(record.deal_id),
        "deal_reference": record.deal_reference,
        "scenario_id": str(record.scenario_id),
        "scenario_status": record.scenario_status,
        "customer_id": str(record.customer_id),
        "customer_name": record.customer_name,
        "currency": record.currency,
        "valid_until": record.valid_until.isoformat(),
        "incoterm": record.incoterm,
        "named_delivery_place": record.named_delivery_place,
        "payment_terms": record.payment_terms,
        "notes": record.notes,
        "status": record.status,
        "total_value": str(record.total_value),
        "items": [
            {
                "product_id": str(item.product_id),
                "sku": item.sku,
                "name": item.name,
                "description": item.description,
                "quantity": str(item.quantity),
                "unit": item.unit,
                "unit_price": str(item.unit_price),
                "line_total": str(item.line_total),
            }
            for item in record.items
        ],
        "created_at": now.isoformat(),
    }


__all__ = [
    "SalesQuoteCreateData",
    "SalesQuoteFilters",
    "SalesQuoteItemRecord",
    "SalesQuotePage",
    "SalesQuoteRecord",
    "SalesQuoteReviseData",
    "SalesQuoteRevisionRecord",
    "SalesQuoteService",
    "SalesQuoteSummaryRecord",
    "ScenarioLines",
]

"""Trade deal service: creation, editing, state transitions and reporting.

The state machine lives in :mod:`app.services.deal_state`; this module adds
persistence, concurrency control and the audit trail. Two invariants are worth
stating explicitly because they are enforced transactionally, not by convention:

* a transition locks the deal row (``SELECT ... FOR UPDATE``), re-reads its status
  and writes the new status, the ``deal_transition`` history row and the audit
  row in one transaction — there is no window in which a deal has moved without
  its history;
* ``PATCH`` never accepts ``status``; the request schema forbids unknown fields,
  and the service refuses to edit a closed deal.
"""

from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass
from datetime import UTC, date, datetime
from decimal import ROUND_HALF_UP, Decimal
from typing import Any
from uuid import UUID, uuid4

from sqlalchemy import and_, func, select, tuple_
from sqlalchemy.exc import IntegrityError
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
    AuditRecord,
    Counterparty,
    Deal,
    DealItem,
    DealStatus,
    DealTransition,
    Product,
)
from app.db.tenant import apply_company_context
from app.services.audit import record_audit
from app.services.deal_state import (
    TERMINAL_STATUSES,
    allowed_targets,
    is_terminal,
    validate_transition,
)
from app.services.pagination import decode_cursor, encode_cursor
from app.services.trade_meta import WriteMeta, clean_optional, escape_like

MONEY_QUANTUM = Decimal("0.01")


@dataclass(frozen=True)
class DealItemInput:
    product_id: UUID
    quantity: Decimal
    unit_price: Decimal


@dataclass(frozen=True)
class DealItemRecord:
    id: UUID
    product_id: UUID
    sku: str
    name: str
    unit: str
    quantity: Decimal
    unit_price: Decimal
    line_total: Decimal


@dataclass(frozen=True)
class DealTransitionRecord:
    id: UUID
    from_status: str | None
    to_status: str
    reason: str | None
    actor_id: UUID
    request_id: str | None
    version_after: int
    occurred_at: datetime


@dataclass(frozen=True)
class DealRecord:
    id: UUID
    company_id: UUID
    reference: str
    title: str
    status: DealStatus
    counterparty_id: UUID
    counterparty_name: str
    currency: str
    expected_close_date: date | None
    notes: str | None
    version: int
    created_by: UUID
    closed_at: datetime | None
    created_at: datetime
    updated_at: datetime
    items: tuple[DealItemRecord, ...]
    transitions: tuple[DealTransitionRecord, ...]
    total_value: Decimal

    @property
    def allowed_transitions(self) -> tuple[DealStatus, ...]:
        return allowed_targets(self.status)


@dataclass(frozen=True)
class DealFilters:
    search: str | None = None
    status: str | None = None
    counterparty_id: UUID | None = None

    def as_fingerprint(self) -> dict[str, str | None]:
        return {
            "search": self.search,
            "status": self.status,
            "counterparty_id": str(self.counterparty_id) if self.counterparty_id else None,
        }


@dataclass(frozen=True)
class DealPage:
    items: tuple[DealRecord, ...]
    next_cursor: str | None


@dataclass(frozen=True)
class DealCreateData:
    title: str
    counterparty_id: UUID
    currency: str
    expected_close_date: date | None
    notes: str | None
    reference: str | None
    items: tuple[DealItemInput, ...]


def _money(value: Decimal) -> Decimal:
    return Decimal(value).quantize(MONEY_QUANTUM, rounding=ROUND_HALF_UP)



def _item_records(
    session: Session, *, company_id: UUID, deal_id: UUID
) -> tuple[DealItemRecord, ...]:
    rows = session.execute(
        select(
            DealItem.id,
            DealItem.product_id,
            DealItem.quantity,
            DealItem.unit_price,
            Product.sku,
            Product.name,
            Product.unit,
        )
        .join(
            Product,
            and_(
                Product.id == DealItem.product_id,
                Product.company_id == DealItem.company_id,
            ),
        )
        .where(DealItem.deal_id == deal_id, DealItem.company_id == company_id)
        .order_by(DealItem.created_at, DealItem.id)
    ).mappings()
    return tuple(
        DealItemRecord(
            id=row["id"],
            product_id=row["product_id"],
            sku=row["sku"],
            name=row["name"],
            unit=row["unit"],
            quantity=row["quantity"],
            unit_price=row["unit_price"],
            line_total=_money(row["quantity"] * row["unit_price"]),
        )
        for row in rows
    )


def _transition_records(
    session: Session, *, company_id: UUID, deal_id: UUID
) -> tuple[DealTransitionRecord, ...]:
    rows = session.scalars(
        select(DealTransition)
        .where(
            DealTransition.deal_id == deal_id,
            DealTransition.company_id == company_id,
        )
        .order_by(DealTransition.occurred_at, DealTransition.id)
    )
    return tuple(
        DealTransitionRecord(
            id=row.id,
            from_status=row.from_status,
            to_status=row.to_status,
            reason=row.reason,
            actor_id=row.actor_id,
            request_id=row.request_id,
            version_after=row.version_after,
            occurred_at=row.occurred_at,
        )
        for row in rows
    )


def _load(
    session: Session,
    *,
    company_id: UUID,
    deal_id: UUID,
    include_history: bool = True,
) -> DealRecord:
    row = session.execute(
        select(Deal, Counterparty.name)
        .join(
            Counterparty,
            and_(
                Counterparty.id == Deal.counterparty_id,
                Counterparty.company_id == Deal.company_id,
            ),
        )
        .where(Deal.id == deal_id, Deal.company_id == company_id)
    ).one_or_none()
    if row is None:
        raise NotFoundError("The deal does not exist.")
    deal, counterparty_name = row
    items = _item_records(session, company_id=company_id, deal_id=deal.id)
    total = sum((item.line_total for item in items), Decimal("0.00"))
    return DealRecord(
        id=deal.id,
        company_id=deal.company_id,
        reference=deal.reference,
        title=deal.title,
        status=DealStatus(deal.status),
        counterparty_id=deal.counterparty_id,
        counterparty_name=counterparty_name,
        currency=deal.currency,
        expected_close_date=deal.expected_close_date,
        notes=deal.notes,
        version=deal.version,
        created_by=deal.created_by,
        closed_at=deal.closed_at,
        created_at=deal.created_at,
        updated_at=deal.updated_at,
        items=items,
        transitions=(
            _transition_records(session, company_id=company_id, deal_id=deal.id)
            if include_history
            else ()
        ),
        total_value=_money(total),
    )


@dataclass(frozen=True)
class StatusAggregate:
    status: str
    deal_count: int
    total_value: Decimal


@dataclass(frozen=True)
class CurrencyAggregate:
    currency: str
    deal_count: int
    total_value: Decimal


@dataclass(frozen=True)
class ActivityEntry:
    action: str
    outcome: str
    occurred_at: datetime
    resource_type: str | None
    resource_id: str | None


@dataclass(frozen=True)
class DashboardSummary:
    deals_total: int
    status_counts: tuple[StatusAggregate, ...]
    pipeline: tuple[CurrencyAggregate, ...]
    counterparties_total: int
    counterparties_active: int
    products_total: int
    products_active: int
    recent_deals: tuple[DealRecord, ...]
    recent_activity: tuple[ActivityEntry, ...]


class DealService:
    """Deal persistence, state transitions and dashboard aggregates."""

    def __init__(self, database: Database) -> None:
        self._database = database

    # ------------------------------------------------------------------ reads
    def list(
        self,
        *,
        company_id: UUID,
        filters: DealFilters,
        limit: int,
        cursor: str | None,
    ) -> DealPage:
        fingerprint = filters.as_fingerprint()
        position = decode_cursor(cursor, filters=fingerprint) if cursor else None

        with self._database.transaction() as session:
            apply_company_context(session, company_id)
            statement = select(Deal).where(Deal.company_id == company_id)
            if filters.status:
                statement = statement.where(Deal.status == filters.status)
            if filters.counterparty_id:
                statement = statement.where(Deal.counterparty_id == filters.counterparty_id)
            if filters.search:
                pattern = f"%{escape_like(filters.search.strip())}%"
                statement = statement.where(
                    Deal.reference.ilike(pattern, escape="\\")
                    | Deal.title.ilike(pattern, escape="\\")
                )
            if position is not None:
                statement = statement.where(
                    tuple_(Deal.created_at, Deal.id)
                    < tuple_(position.created_at, position.row_id)
                )
            statement = statement.order_by(Deal.created_at.desc(), Deal.id.desc()).limit(
                limit + 1
            )

            rows = list(session.scalars(statement))
            has_more = len(rows) > limit
            page = rows[:limit]
            records = tuple(
                _load(session, company_id=company_id, deal_id=row.id, include_history=False)
                for row in page
            )
            next_cursor = None
            if has_more and page:
                last = page[-1]
                next_cursor = encode_cursor(
                    created_at=last.created_at, row_id=last.id, filters=fingerprint
                )
            return DealPage(items=records, next_cursor=next_cursor)

    def get(self, *, company_id: UUID, deal_id: UUID) -> DealRecord:
        with self._database.transaction() as session:
            apply_company_context(session, company_id)
            return _load(session, company_id=company_id, deal_id=deal_id)



    # ----------------------------------------------------------------- writes
    def create(
        self,
        session: Session,
        *,
        meta: WriteMeta,
        data: DealCreateData,
    ) -> DealRecord:
        counterparty = session.execute(
            select(Counterparty.id).where(
                Counterparty.id == data.counterparty_id,
                Counterparty.company_id == meta.company_id,
            )
        ).scalar_one_or_none()
        if counterparty is None:
            raise BadRequestError(
                "The counterparty does not exist in this company.",
                details=[
                    {
                        "field": "counterparty_id",
                        "message": "Unknown counterparty for the active company.",
                        "type": "value_error",
                    }
                ],
            )

        product_ids = [item.product_id for item in data.items]
        if len(set(product_ids)) != len(product_ids):
            raise BadRequestError(
                "Each product may appear only once per deal.",
                details=[
                    {
                        "field": "items",
                        "message": "Duplicate product in the deal lines.",
                        "type": "value_error",
                    }
                ],
            )
        found = set(
            session.execute(
                select(Product.id).where(
                    Product.company_id == meta.company_id, Product.id.in_(product_ids)
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

        now = datetime.now(tz=UTC)
        deal = Deal(
            company_id=meta.company_id,
            reference=data.reference or self._generate_reference(now),
            title=data.title,
            status=DealStatus.DRAFT.value,
            counterparty_id=data.counterparty_id,
            currency=data.currency,
            expected_close_date=data.expected_close_date,
            notes=data.notes,
            version=1,
            created_by=meta.actor_id,
            created_at=now,
            updated_at=now,
        )
        session.add(deal)
        session.flush()

        for item in data.items:
            session.add(
                DealItem(
                    company_id=meta.company_id,
                    deal_id=deal.id,
                    product_id=item.product_id,
                    quantity=item.quantity,
                    unit_price=item.unit_price,
                    created_at=now,
                )
            )
        session.flush()

        session.add(
            DealTransition(
                company_id=meta.company_id,
                deal_id=deal.id,
                from_status=None,
                to_status=DealStatus.DRAFT.value,
                reason=None,
                actor_id=meta.actor_id,
                request_id=meta.request_id,
                version_after=1,
                occurred_at=now,
            )
        )
        session.flush()

        record = _load(session, company_id=meta.company_id, deal_id=deal.id)
        record_audit(
            session,
            action=AuditAction.DEAL_CREATED,
            outcome=AuditOutcome.SUCCESS,
            actor_id=meta.actor_id,
            company_id=meta.company_id,
            request_id=meta.request_id,
            ip_address=meta.ip_address,
            user_agent=meta.user_agent,
            resource_type="deal",
            resource_id=str(deal.id),
            details={
                "reference": deal.reference,
                "counterparty_id": str(deal.counterparty_id),
                "currency": deal.currency,
                "item_count": len(data.items),
                "total_value": str(record.total_value),
                "status": deal.status,
            },
        )
        return record

    @staticmethod
    def _generate_reference(now: datetime) -> str:
        return f"T-{now:%y%m}-{uuid4().hex[:6].upper()}"

    def update(
        self,
        session: Session,
        *,
        meta: WriteMeta,
        deal_id: UUID,
        expected_version: int,
        changes: Mapping[str, Any],
    ) -> DealRecord:
        deal = session.execute(
            select(Deal)
            .where(Deal.id == deal_id, Deal.company_id == meta.company_id)
            .with_for_update()
        ).scalar_one_or_none()
        if deal is None:
            raise NotFoundError("The deal does not exist.")
        if deal.version != expected_version:
            raise VersionConflictError(
                "The deal was modified by another request.",
                details={"current_version": deal.version},
                headers={"ETag": f'"v{deal.version}"'},
            )
        if is_terminal(DealStatus(deal.status)):
            raise ConflictError("A closed deal cannot be edited.")

        applied: dict[str, Any] = {}
        if "counterparty_id" in changes:
            exists = session.execute(
                select(Counterparty.id).where(
                    Counterparty.id == changes["counterparty_id"],
                    Counterparty.company_id == meta.company_id,
                )
            ).scalar_one_or_none()
            if exists is None:
                raise BadRequestError(
                    "The counterparty does not exist in this company.",
                    details=[
                        {
                            "field": "counterparty_id",
                            "message": "Unknown counterparty for the active company.",
                            "type": "value_error",
                        }
                    ],
                )
            deal.counterparty_id = changes["counterparty_id"]
            applied["counterparty_id"] = str(changes["counterparty_id"])

        if "title" in changes:
            title = " ".join(str(changes["title"]).split())
            if not title:
                raise BadRequestError("The deal title must not be empty.")
            deal.title = title
            applied["title"] = title
        if "currency" in changes:
            deal.currency = str(changes["currency"]).strip().upper()
            applied["currency"] = deal.currency
        if "expected_close_date" in changes:
            deal.expected_close_date = changes["expected_close_date"]
            applied["expected_close_date"] = (
                str(deal.expected_close_date) if deal.expected_close_date else None
            )
        if "notes" in changes:
            deal.notes = clean_optional(changes["notes"])
            applied["notes"] = deal.notes

        deal.version += 1
        deal.updated_at = datetime.now(tz=UTC)
        try:
            session.flush()
        except IntegrityError as exc:  # pragma: no cover - defensive
            raise ConflictError("The deal could not be updated.") from exc

        record_audit(
            session,
            action=AuditAction.DEAL_UPDATED,
            outcome=AuditOutcome.SUCCESS,
            actor_id=meta.actor_id,
            company_id=meta.company_id,
            request_id=meta.request_id,
            ip_address=meta.ip_address,
            user_agent=meta.user_agent,
            resource_type="deal",
            resource_id=str(deal.id),
            details={"version": deal.version, "changed": applied},
        )
        return _load(session, company_id=meta.company_id, deal_id=deal.id)

    def transition(
        self,
        session: Session,
        *,
        meta: WriteMeta,
        deal_id: UUID,
        target: DealStatus,
        reason: str | None,
        expected_version: int | None = None,
    ) -> DealRecord:
        deal = session.execute(
            select(Deal)
            .where(Deal.id == deal_id, Deal.company_id == meta.company_id)
            .with_for_update()
        ).scalar_one_or_none()
        if deal is None:
            raise NotFoundError("The deal does not exist.")
        if expected_version is not None and deal.version != expected_version:
            raise VersionConflictError(
                "The deal was modified by another request.",
                details={"current_version": deal.version},
                headers={"ETag": f'"v{deal.version}"'},
            )

        current = DealStatus(deal.status)
        cleaned_reason = validate_transition(current, target, reason)

        now = datetime.now(tz=UTC)
        deal.status = target.value
        deal.version += 1
        deal.updated_at = now
        if is_terminal(target):
            deal.closed_at = now
        session.add(
            DealTransition(
                company_id=meta.company_id,
                deal_id=deal.id,
                from_status=current.value,
                to_status=target.value,
                reason=cleaned_reason,
                actor_id=meta.actor_id,
                request_id=meta.request_id,
                version_after=deal.version,
                occurred_at=now,
            )
        )
        session.flush()

        record_audit(
            session,
            action=AuditAction.DEAL_TRANSITIONED,
            outcome=AuditOutcome.SUCCESS,
            actor_id=meta.actor_id,
            company_id=meta.company_id,
            request_id=meta.request_id,
            ip_address=meta.ip_address,
            user_agent=meta.user_agent,
            resource_type="deal",
            resource_id=str(deal.id),
            details={
                "from": current.value,
                "to": target.value,
                "reason": cleaned_reason,
                "version": deal.version,
            },
        )
        return _load(session, company_id=meta.company_id, deal_id=deal.id)


    # --------------------------------------------------------------- dashboard
    def dashboard(self, *, company_id: UUID) -> DashboardSummary:
        """One consistent snapshot for the command center (no cross-query drift)."""
        with self._database.transaction() as session:
            apply_company_context(session, company_id)

            totals = (
                select(
                    DealItem.deal_id.label("deal_id"),
                    func.sum(DealItem.quantity * DealItem.unit_price).label("total"),
                )
                .where(DealItem.company_id == company_id)
                .group_by(DealItem.deal_id)
                .subquery()
            )

            status_rows = (
                session.execute(
                    select(
                        Deal.status,
                        func.count(Deal.id).label("deal_count"),
                        func.coalesce(func.sum(totals.c.total), 0).label("total_value"),
                    )
                    .select_from(Deal)
                    .outerjoin(totals, totals.c.deal_id == Deal.id)
                    .where(Deal.company_id == company_id)
                    .group_by(Deal.status)
                )
                .mappings()
                .all()
            )
            by_status = {str(row["status"]): row for row in status_rows}
            status_counts = tuple(
                StatusAggregate(
                    status=status.value,
                    deal_count=int(by_status[status.value]["deal_count"])
                    if status.value in by_status
                    else 0,
                    total_value=_money(
                        Decimal(str(by_status[status.value]["total_value"]))
                        if status.value in by_status
                        else Decimal("0")
                    ),
                )
                for status in DealStatus
            )

            terminal = [status.value for status in TERMINAL_STATUSES]
            pipeline_rows = (
                session.execute(
                    select(
                        Deal.currency,
                        func.count(Deal.id).label("deal_count"),
                        func.coalesce(func.sum(totals.c.total), 0).label("total_value"),
                    )
                    .select_from(Deal)
                    .outerjoin(totals, totals.c.deal_id == Deal.id)
                    .where(
                        Deal.company_id == company_id,
                        Deal.status.notin_(terminal),
                    )
                    .group_by(Deal.currency)
                    .order_by(Deal.currency)
                )
                .mappings()
                .all()
            )
            pipeline = tuple(
                CurrencyAggregate(
                    currency=str(row["currency"]),
                    deal_count=int(row["deal_count"]),
                    total_value=_money(Decimal(str(row["total_value"]))),
                )
                for row in pipeline_rows
            )

            recent_ids = list(
                session.scalars(
                    select(Deal.id)
                    .where(Deal.company_id == company_id)
                    .order_by(Deal.created_at.desc(), Deal.id.desc())
                    .limit(5)
                )
            )
            recent_deals = tuple(
                _load(session, company_id=company_id, deal_id=deal_id, include_history=False)
                for deal_id in recent_ids
            )

            activity_rows = (
                session.execute(
                    select(
                        AuditRecord.action,
                        AuditRecord.outcome,
                        AuditRecord.occurred_at,
                        AuditRecord.resource_type,
                        AuditRecord.resource_id,
                    )
                    .where(AuditRecord.company_id == company_id)
                    .order_by(AuditRecord.occurred_at.desc(), AuditRecord.id.desc())
                    .limit(8)
                )
                .mappings()
                .all()
            )
            recent_activity = tuple(
                ActivityEntry(
                    action=str(row["action"]),
                    outcome=str(row["outcome"]),
                    occurred_at=row["occurred_at"],
                    resource_type=row["resource_type"],
                    resource_id=row["resource_id"],
                )
                for row in activity_rows
            )

            counterparties_total, counterparties_active = session.execute(
                select(
                    func.count(Counterparty.id),
                    func.count(Counterparty.id).filter(Counterparty.status == "active"),
                ).where(Counterparty.company_id == company_id)
            ).one()
            products_total, products_active = session.execute(
                select(
                    func.count(Product.id),
                    func.count(Product.id).filter(Product.status == "active"),
                ).where(Product.company_id == company_id)
            ).one()

            return DashboardSummary(
                deals_total=sum(item.deal_count for item in status_counts),
                status_counts=status_counts,
                pipeline=pipeline,
                counterparties_total=int(counterparties_total),
                counterparties_active=int(counterparties_active),
                products_total=int(products_total),
                products_active=int(products_active),
                recent_deals=recent_deals,
                recent_activity=recent_activity,
            )


__all__ = [
    "ActivityEntry",
    "CurrencyAggregate",
    "DashboardSummary",
    "DealCreateData",
    "DealFilters",
    "DealItemInput",
    "DealItemRecord",
    "DealPage",
    "DealRecord",
    "DealService",
    "DealTransitionRecord",
    "StatusAggregate",
]



"""Explicit FX rate snapshots.

A rate is a recorded observation, never a guess: the base/quote pair, the rate,
the moment it was effective and the source it came from are all stored. Pricing
can only convert between two currencies by pointing at one of these rows, which
is what makes a landed-cost calculation reproducible months later.

Snapshots are immutable in practice: the table has no ``version`` column and no
update endpoint. A correction is a new row with a later ``effective_at``; the
unique constraint on ``(company_id, base_currency, quote_currency,
effective_at)`` keeps the history unambiguous.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import UTC, datetime
from decimal import Decimal
from typing import Any
from uuid import UUID

from sqlalchemy import select, tuple_
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app.core.errors import BadRequestError, ConflictError, NotFoundError
from app.db.engine import Database
from app.db.models import AuditAction, AuditOutcome, FxRateSnapshot
from app.db.tenant import apply_company_context
from app.services.audit import record_audit
from app.services.pagination import decode_cursor, encode_cursor
from app.services.trade_meta import WriteMeta


@dataclass(frozen=True)
class FxRateRecord:
    id: UUID
    company_id: UUID
    base_currency: str
    quote_currency: str
    rate: Decimal
    effective_at: datetime
    source: str
    recorded_by: UUID
    recorded_at: datetime


@dataclass(frozen=True)
class FxRateFilters:
    base_currency: str | None = None
    quote_currency: str | None = None

    def as_fingerprint(self) -> dict[str, str | None]:
        return {
            "base_currency": self.base_currency,
            "quote_currency": self.quote_currency,
        }


@dataclass(frozen=True)
class FxRatePage:
    items: tuple[FxRateRecord, ...]
    next_cursor: str | None


def _to_record(row: FxRateSnapshot) -> FxRateRecord:
    return FxRateRecord(
        id=row.id,
        company_id=row.company_id,
        base_currency=row.base_currency,
        quote_currency=row.quote_currency,
        rate=row.rate,
        effective_at=row.effective_at,
        source=row.source,
        recorded_by=row.recorded_by,
        recorded_at=row.recorded_at,
    )


def normalise_currency(value: str, field: str) -> str:
    """Upper-case and validate an ISO-4217-looking code."""
    cleaned = str(value).strip().upper()
    if len(cleaned) != 3 or not cleaned.isalpha():
        raise BadRequestError(
            f"{field} must be a three-letter ISO-4217 code.",
            details=[
                {
                    "field": field,
                    "message": "Use a three-letter ISO-4217 currency code.",
                    "type": "value_error",
                }
            ],
        )
    return cleaned


def normalise_fx_values(data: dict[str, Any]) -> dict[str, Any]:
    """Validate and normalise a snapshot before it reaches the database."""
    base_currency = normalise_currency(data["base_currency"], "base_currency")
    quote_currency = normalise_currency(data["quote_currency"], "quote_currency")
    if base_currency == quote_currency:
        raise BadRequestError(
            "The base and quote currency must differ.",
            details=[
                {
                    "field": "quote_currency",
                    "message": "A conversion needs two different currencies.",
                    "type": "value_error",
                }
            ],
        )
    rate = Decimal(str(data["rate"]))
    if rate <= 0:
        raise BadRequestError(
            "The rate must be greater than zero.",
            details=[
                {
                    "field": "rate",
                    "message": "A rate of zero or below cannot price anything.",
                    "type": "value_error",
                }
            ],
        )
    source = " ".join(str(data["source"]).split())
    if len(source) < 3:
        raise BadRequestError(
            "The source must name where the rate came from.",
            details=[
                {
                    "field": "source",
                    "message": "At least three characters, for example 'ECB 2026-10-22'.",
                    "type": "value_error",
                }
            ],
        )
    effective_at = data["effective_at"]
    if effective_at.tzinfo is None:
        effective_at = effective_at.replace(tzinfo=UTC)
    return {
        "base_currency": base_currency,
        "quote_currency": quote_currency,
        "rate": rate,
        "effective_at": effective_at,
        "source": source,
    }


class FxRateService:
    """Tenant-scoped FX snapshot reads and writes."""

    def __init__(self, database: Database) -> None:
        self._database = database

    # ------------------------------------------------------------------ reads
    def list(
        self,
        *,
        company_id: UUID,
        filters: FxRateFilters,
        limit: int,
        cursor: str | None,
    ) -> FxRatePage:
        fingerprint = filters.as_fingerprint()
        position = decode_cursor(cursor, filters=fingerprint) if cursor else None

        with self._database.transaction() as session:
            apply_company_context(session, company_id)
            statement = select(FxRateSnapshot).where(FxRateSnapshot.company_id == company_id)
            if filters.base_currency:
                statement = statement.where(FxRateSnapshot.base_currency == filters.base_currency)
            if filters.quote_currency:
                statement = statement.where(FxRateSnapshot.quote_currency == filters.quote_currency)
            if position is not None:
                statement = statement.where(
                    tuple_(FxRateSnapshot.recorded_at, FxRateSnapshot.id)
                    < tuple_(position.created_at, position.row_id)
                )
            statement = statement.order_by(
                FxRateSnapshot.recorded_at.desc(), FxRateSnapshot.id.desc()
            ).limit(limit + 1)

            rows = list(session.scalars(statement))
            has_more = len(rows) > limit
            page = rows[:limit]
            next_cursor = None
            if has_more and page:
                last = page[-1]
                next_cursor = encode_cursor(
                    created_at=last.recorded_at, row_id=last.id, filters=fingerprint
                )
            return FxRatePage(items=tuple(_to_record(row) for row in page), next_cursor=next_cursor)

    def get(self, *, company_id: UUID, snapshot_id: UUID) -> FxRateRecord:
        with self._database.transaction() as session:
            apply_company_context(session, company_id)
            row = session.execute(
                select(FxRateSnapshot).where(
                    FxRateSnapshot.id == snapshot_id,
                    FxRateSnapshot.company_id == company_id,
                )
            ).scalar_one_or_none()
            if row is None:
                raise NotFoundError("The FX rate snapshot does not exist.")
            return _to_record(row)

    # ----------------------------------------------------------------- writes
    def create(self, session: Session, *, meta: WriteMeta, data: dict[str, Any]) -> FxRateRecord:
        values = normalise_fx_values(data)
        row = FxRateSnapshot(
            company_id=meta.company_id,
            recorded_by=meta.actor_id,
            **values,
        )
        session.add(row)
        try:
            session.flush()
        except IntegrityError as exc:
            raise ConflictError(
                "An FX rate for this pair and effective time already exists."
            ) from exc
        session.refresh(row)

        record_audit(
            session,
            action=AuditAction.FX_RATE_RECORDED,
            outcome=AuditOutcome.SUCCESS,
            actor_id=meta.actor_id,
            company_id=meta.company_id,
            request_id=meta.request_id,
            ip_address=meta.ip_address,
            user_agent=meta.user_agent,
            resource_type="fx_rate_snapshot",
            resource_id=str(row.id),
            details={
                "base_currency": row.base_currency,
                "quote_currency": row.quote_currency,
                "rate": str(row.rate),
                "effective_at": row.effective_at.isoformat(),
                "source": row.source,
            },
        )
        return _to_record(row)


__all__ = [
    "FxRateFilters",
    "FxRatePage",
    "FxRateRecord",
    "FxRateService",
    "normalise_currency",
    "normalise_fx_values",
]

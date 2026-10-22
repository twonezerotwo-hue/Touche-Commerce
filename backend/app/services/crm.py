"""Counterparty (CRM) service.

Read methods own a short transaction and return immutable snapshots; write
methods join the caller's transaction so the business change, the audit row and
the idempotency record commit together (ADR-009, ADR-012).
"""

from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass
from datetime import datetime
from typing import Any
from uuid import UUID

from sqlalchemy import func, select, tuple_
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app.core.errors import ConflictError, NotFoundError, VersionConflictError
from app.db.engine import Database
from app.db.models import AuditAction, AuditOutcome, Counterparty
from app.db.tenant import apply_company_context
from app.services.audit import record_audit
from app.services.pagination import decode_cursor, encode_cursor
from app.services.trade_meta import WriteMeta, clean_optional, escape_like


@dataclass(frozen=True)
class CounterpartyRecord:
    id: UUID
    company_id: UUID
    name: str
    type: str
    country: str | None
    contact_name: str | None
    email: str | None
    phone: str | None
    notes: str | None
    status: str
    version: int
    created_at: datetime
    updated_at: datetime


@dataclass(frozen=True)
class CounterpartyFilters:
    search: str | None = None
    status: str | None = None
    kind: str | None = None

    def as_fingerprint(self) -> dict[str, str | None]:
        return {"search": self.search, "status": self.status, "type": self.kind}


@dataclass(frozen=True)
class CounterpartyPage:
    items: tuple[CounterpartyRecord, ...]
    next_cursor: str | None


def _to_record(row: Counterparty) -> CounterpartyRecord:
    return CounterpartyRecord(
        id=row.id,
        company_id=row.company_id,
        name=row.name,
        type=row.type,
        country=row.country,
        contact_name=row.contact_name,
        email=row.email,
        phone=row.phone,
        notes=row.notes,
        status=row.status,
        version=row.version,
        created_at=row.created_at,
        updated_at=row.updated_at,
    )


def _normalise_create(data: Mapping[str, Any]) -> dict[str, Any]:
    name = " ".join(str(data["name"]).split())
    if not name:
        raise ConflictError("The counterparty name must not be empty.")
    email = clean_optional(data.get("email"))
    country = clean_optional(data.get("country"))
    return {
        "name": name,
        "type": str(data.get("type") or "buyer"),
        "country": country.upper() if country else None,
        "contact_name": clean_optional(data.get("contact_name")),
        "email": email.lower() if email else None,
        "phone": clean_optional(data.get("phone")),
        "notes": clean_optional(data.get("notes")),
    }


class CounterpartyService:
    """CRUD for tenant-scoped counterparties."""

    def __init__(self, database: Database) -> None:
        self._database = database

    # ------------------------------------------------------------------ reads
    def list(
        self,
        *,
        company_id: UUID,
        filters: CounterpartyFilters,
        limit: int,
        cursor: str | None,
    ) -> CounterpartyPage:
        fingerprint = filters.as_fingerprint()
        position = decode_cursor(cursor, filters=fingerprint) if cursor else None

        with self._database.transaction() as session:
            apply_company_context(session, company_id)
            statement = select(Counterparty).where(Counterparty.company_id == company_id)
            if filters.status:
                statement = statement.where(Counterparty.status == filters.status)
            if filters.kind:
                statement = statement.where(Counterparty.type == filters.kind)
            if filters.search:
                pattern = f"%{escape_like(filters.search.strip())}%"
                statement = statement.where(Counterparty.name.ilike(pattern, escape="\\"))
            if position is not None:
                statement = statement.where(
                    tuple_(Counterparty.created_at, Counterparty.id)
                    < tuple_(position.created_at, position.row_id)
                )
            statement = statement.order_by(
                Counterparty.created_at.desc(), Counterparty.id.desc()
            ).limit(limit + 1)

            rows = list(session.scalars(statement))
            has_more = len(rows) > limit
            page = rows[:limit]
            next_cursor = None
            if has_more and page:
                last = page[-1]
                next_cursor = encode_cursor(
                    created_at=last.created_at, row_id=last.id, filters=fingerprint
                )
            return CounterpartyPage(
                items=tuple(_to_record(row) for row in page), next_cursor=next_cursor
            )

    def get(self, *, company_id: UUID, counterparty_id: UUID) -> CounterpartyRecord:
        with self._database.transaction() as session:
            apply_company_context(session, company_id)
            row = session.execute(
                select(Counterparty).where(
                    Counterparty.id == counterparty_id,
                    Counterparty.company_id == company_id,
                )
            ).scalar_one_or_none()
            if row is None:
                raise NotFoundError("The counterparty does not exist.")
            return _to_record(row)

    def counts(self, *, company_id: UUID) -> tuple[int, int]:
        """Return ``(total, active)`` for the dashboard."""
        with self._database.transaction() as session:
            apply_company_context(session, company_id)
            total = session.execute(
                select(func.count())
                .select_from(Counterparty)
                .where(Counterparty.company_id == company_id)
            ).scalar_one()
            active = session.execute(
                select(func.count())
                .select_from(Counterparty)
                .where(
                    Counterparty.company_id == company_id,
                    Counterparty.status == "active",
                )
            ).scalar_one()
            return int(total), int(active)

    # ----------------------------------------------------------------- writes
    def create(
        self,
        session: Session,
        *,
        meta: WriteMeta,
        data: Mapping[str, Any],
    ) -> CounterpartyRecord:
        values = _normalise_create(data)
        row = Counterparty(company_id=meta.company_id, **values)
        session.add(row)
        try:
            session.flush()
        except IntegrityError as exc:
            raise ConflictError(
                "A counterparty with this name already exists in this company."
            ) from exc
        session.refresh(row)

        record_audit(
            session,
            action=AuditAction.COUNTERPARTY_CREATED,
            outcome=AuditOutcome.SUCCESS,
            actor_id=meta.actor_id,
            company_id=meta.company_id,
            request_id=meta.request_id,
            ip_address=meta.ip_address,
            user_agent=meta.user_agent,
            resource_type="counterparty",
            resource_id=str(row.id),
            details={
                "name": row.name,
                "type": row.type,
                "country": row.country,
                "status": row.status,
            },
        )
        return _to_record(row)

    def update(
        self,
        session: Session,
        *,
        meta: WriteMeta,
        counterparty_id: UUID,
        expected_version: int,
        changes: Mapping[str, Any],
    ) -> CounterpartyRecord:
        row = session.execute(
            select(Counterparty)
            .where(
                Counterparty.id == counterparty_id,
                Counterparty.company_id == meta.company_id,
            )
            .with_for_update()
        ).scalar_one_or_none()
        if row is None:
            raise NotFoundError("The counterparty does not exist.")
        if row.version != expected_version:
            raise VersionConflictError(
                "The counterparty was modified by another request.",
                details={"current_version": row.version},
                headers={"ETag": f'"v{row.version}"'},
            )

        applied: dict[str, Any] = {}
        for field in ("name", "type", "country", "contact_name", "email", "phone", "notes"):
            if field not in changes:
                continue
            value = changes[field]
            if field == "name":
                value = " ".join(str(value).split())
                if not value:
                    raise ConflictError("The counterparty name must not be empty.")
            elif field == "country":
                value = clean_optional(value)
                value = value.upper() if value else None
            elif field == "email":
                value = clean_optional(value)
                value = value.lower() if value else None
            elif field == "type":
                value = str(value)
            else:
                value = clean_optional(value)
            setattr(row, field, value)
            applied[field] = value

        if "status" in changes:
            row.status = str(changes["status"])
            applied["status"] = row.status

        row.version += 1
        try:
            session.flush()
        except IntegrityError as exc:
            raise ConflictError(
                "A counterparty with this name already exists in this company."
            ) from exc
        session.refresh(row)

        record_audit(
            session,
            action=AuditAction.COUNTERPARTY_UPDATED,
            outcome=AuditOutcome.SUCCESS,
            actor_id=meta.actor_id,
            company_id=meta.company_id,
            request_id=meta.request_id,
            ip_address=meta.ip_address,
            user_agent=meta.user_agent,
            resource_type="counterparty",
            resource_id=str(row.id),
            details={"version": row.version, "changed": applied},
        )
        return _to_record(row)


__all__ = [
    "CounterpartyFilters",
    "CounterpartyPage",
    "CounterpartyRecord",
    "CounterpartyService",
]


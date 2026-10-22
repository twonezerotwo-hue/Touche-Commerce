"""Product catalogue service (tenant-scoped, versioned)."""

from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass
from datetime import datetime
from decimal import Decimal
from typing import Any
from uuid import UUID

from sqlalchemy import func, select, tuple_
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app.core.errors import ConflictError, NotFoundError, VersionConflictError
from app.db.engine import Database
from app.db.models import AuditAction, AuditOutcome, Product
from app.db.tenant import apply_company_context
from app.services.audit import record_audit
from app.services.pagination import decode_cursor, encode_cursor
from app.services.trade_meta import WriteMeta, escape_like


@dataclass(frozen=True)
class ProductRecord:
    id: UUID
    company_id: UUID
    sku: str
    name: str
    unit: str
    currency: str
    unit_price: Decimal
    status: str
    version: int
    created_at: datetime
    updated_at: datetime


@dataclass(frozen=True)
class ProductFilters:
    search: str | None = None
    status: str | None = None

    def as_fingerprint(self) -> dict[str, str | None]:
        return {"search": self.search, "status": self.status}


@dataclass(frozen=True)
class ProductPage:
    items: tuple[ProductRecord, ...]
    next_cursor: str | None


def _to_record(row: Product) -> ProductRecord:
    return ProductRecord(
        id=row.id,
        company_id=row.company_id,
        sku=row.sku,
        name=row.name,
        unit=row.unit,
        currency=row.currency,
        unit_price=row.unit_price,
        status=row.status,
        version=row.version,
        created_at=row.created_at,
        updated_at=row.updated_at,
    )


def _normalise_create(data: Mapping[str, Any]) -> dict[str, Any]:
    sku = str(data["sku"]).strip().upper()
    name = " ".join(str(data["name"]).split())
    if not sku:
        raise ConflictError("The SKU must not be empty.")
    if not name:
        raise ConflictError("The product name must not be empty.")
    return {
        "sku": sku,
        "name": name,
        "unit": str(data["unit"]),
        "currency": str(data["currency"]).strip().upper(),
        "unit_price": Decimal(str(data["unit_price"])),
    }


class ProductService:
    """CRUD for the tenant product catalogue."""

    def __init__(self, database: Database) -> None:
        self._database = database

    # ------------------------------------------------------------------ reads
    def list(
        self,
        *,
        company_id: UUID,
        filters: ProductFilters,
        limit: int,
        cursor: str | None,
    ) -> ProductPage:
        fingerprint = filters.as_fingerprint()
        position = decode_cursor(cursor, filters=fingerprint) if cursor else None

        with self._database.transaction() as session:
            apply_company_context(session, company_id)
            statement = select(Product).where(Product.company_id == company_id)
            if filters.status:
                statement = statement.where(Product.status == filters.status)
            if filters.search:
                pattern = f"%{escape_like(filters.search.strip())}%"
                statement = statement.where(
                    Product.sku.ilike(pattern, escape="\\")
                    | Product.name.ilike(pattern, escape="\\")
                )
            if position is not None:
                statement = statement.where(
                    tuple_(Product.created_at, Product.id)
                    < tuple_(position.created_at, position.row_id)
                )
            statement = statement.order_by(
                Product.created_at.desc(), Product.id.desc()
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
            return ProductPage(
                items=tuple(_to_record(row) for row in page), next_cursor=next_cursor
            )

    def get(self, *, company_id: UUID, product_id: UUID) -> ProductRecord:
        with self._database.transaction() as session:
            apply_company_context(session, company_id)
            row = session.execute(
                select(Product).where(
                    Product.id == product_id, Product.company_id == company_id
                )
            ).scalar_one_or_none()
            if row is None:
                raise NotFoundError("The product does not exist.")
            return _to_record(row)

    def counts(self, *, company_id: UUID) -> tuple[int, int]:
        """Return ``(total, active)`` for the dashboard."""
        with self._database.transaction() as session:
            apply_company_context(session, company_id)
            total = session.execute(
                select(func.count()).select_from(Product).where(Product.company_id == company_id)
            ).scalar_one()
            active = session.execute(
                select(func.count())
                .select_from(Product)
                .where(Product.company_id == company_id, Product.status == "active")
            ).scalar_one()
            return int(total), int(active)

    # ----------------------------------------------------------------- writes
    def create(
        self, session: Session, *, meta: WriteMeta, data: Mapping[str, Any]
    ) -> ProductRecord:
        values = _normalise_create(data)
        row = Product(company_id=meta.company_id, **values)
        session.add(row)
        try:
            session.flush()
        except IntegrityError as exc:
            raise ConflictError("A product with this SKU already exists in this company.") from exc
        session.refresh(row)

        record_audit(
            session,
            action=AuditAction.PRODUCT_CREATED,
            outcome=AuditOutcome.SUCCESS,
            actor_id=meta.actor_id,
            company_id=meta.company_id,
            request_id=meta.request_id,
            ip_address=meta.ip_address,
            user_agent=meta.user_agent,
            resource_type="product",
            resource_id=str(row.id),
            details={
                "sku": row.sku,
                "name": row.name,
                "unit": row.unit,
                "currency": row.currency,
                "unit_price": str(row.unit_price),
            },
        )
        return _to_record(row)

    def update(
        self,
        session: Session,
        *,
        meta: WriteMeta,
        product_id: UUID,
        expected_version: int,
        changes: Mapping[str, Any],
    ) -> ProductRecord:
        row = session.execute(
            select(Product)
            .where(Product.id == product_id, Product.company_id == meta.company_id)
            .with_for_update()
        ).scalar_one_or_none()
        if row is None:
            raise NotFoundError("The product does not exist.")
        if row.version != expected_version:
            raise VersionConflictError(
                "The product was modified by another request.",
                details={"current_version": row.version},
                headers={"ETag": f'"v{row.version}"'},
            )

        applied: dict[str, Any] = {}
        for field in ("sku", "name", "unit", "currency", "unit_price", "status"):
            if field not in changes:
                continue
            value = changes[field]
            if field == "sku":
                value = str(value).strip().upper()
                if not value:
                    raise ConflictError("The SKU must not be empty.")
            elif field == "name":
                value = " ".join(str(value).split())
                if not value:
                    raise ConflictError("The product name must not be empty.")
            elif field == "currency":
                value = str(value).strip().upper()
            elif field == "unit_price":
                value = Decimal(str(value))
            elif field == "unit":
                value = str(value)
            else:
                value = str(value)
            setattr(row, field, value)
            applied[field] = str(value) if isinstance(value, Decimal) else value

        row.version += 1
        try:
            session.flush()
        except IntegrityError as exc:
            raise ConflictError("A product with this SKU already exists in this company.") from exc
        session.refresh(row)

        record_audit(
            session,
            action=AuditAction.PRODUCT_UPDATED,
            outcome=AuditOutcome.SUCCESS,
            actor_id=meta.actor_id,
            company_id=meta.company_id,
            request_id=meta.request_id,
            ip_address=meta.ip_address,
            user_agent=meta.user_agent,
            resource_type="product",
            resource_id=str(row.id),
            details={"version": row.version, "changed": applied},
        )
        return _to_record(row)


__all__ = ["ProductFilters", "ProductPage", "ProductRecord", "ProductService"]


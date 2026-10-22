"""Trade-module storage: counterparties, products, deals, deal lines and history.

Design notes that are enforced by the database, not only by application code:

* every table carries ``company_id`` and is protected by row level security
  (ADR-004), so a missing ``WHERE company_id = ...`` cannot leak a tenant;
* every child row references its parent through a **composite** foreign key that
  includes ``company_id`` (the rule established by ``company_setting_entry``), so
  a line item can never be attached to another company's deal even if a bug
  supplied the wrong pair of ids;
* mutable rows carry ``version`` for optimistic concurrency (ADR-013);
* ``deal_transition`` is the immutable state history: one row per accepted
  transition, written in the same transaction as the deal update (ADR-025).
"""

from __future__ import annotations

from datetime import date, datetime
from decimal import Decimal
from enum import StrEnum
from uuid import UUID

from sqlalchemy import (
    CheckConstraint,
    Date,
    DateTime,
    ForeignKey,
    ForeignKeyConstraint,
    Index,
    Integer,
    Numeric,
    String,
    Text,
    UniqueConstraint,
    func,
    text,
)
from sqlalchemy.dialects.postgresql import UUID as PG_UUID
from sqlalchemy.orm import Mapped, mapped_column

from app.db.models.base import Base


class RecordStatus(StrEnum):
    """Lifecycle of a catalogue/CRM record. Archiving keeps history intact."""

    ACTIVE = "active"
    ARCHIVED = "archived"


class CounterpartyType(StrEnum):
    """Commercial role of a counterparty inside one company."""

    BUYER = "buyer"
    SUPPLIER = "supplier"
    BOTH = "both"


class ProductUnit(StrEnum):
    """Units of measure accepted by the catalogue."""

    KG = "kg"
    MT = "mt"
    LB = "lb"
    UNIT = "unit"
    LITRE = "l"
    CUBIC_METRE = "m3"


class DealStatus(StrEnum):
    """Deal lifecycle. ``WON`` exists in the contract but is not reachable yet."""

    DRAFT = "DRAFT"
    OPEN = "OPEN"
    NEGOTIATION = "NEGOTIATION"
    WON = "WON"
    LOST = "LOST"
    CANCELLED = "CANCELLED"


def _in_list(column: str, values: tuple[str, ...]) -> str:
    rendered = ", ".join(f"'{value}'" for value in values)
    return f"{column} IN ({rendered})"


_RECORD_STATUSES = tuple(status.value for status in RecordStatus)
_COUNTERPARTY_TYPES = tuple(kind.value for kind in CounterpartyType)
_PRODUCT_UNITS = tuple(unit.value for unit in ProductUnit)
_DEAL_STATUSES = tuple(status.value for status in DealStatus)


class Counterparty(Base):
    """A customer or supplier belonging to exactly one company."""

    __tablename__ = "counterparty"
    __table_args__ = (
        UniqueConstraint("company_id", "name", name="uq_counterparty_company_id_name"),
        # Target of the composite FKs used by deal rows.
        UniqueConstraint("id", "company_id", name="uq_counterparty_id_company_id"),
        CheckConstraint("name = btrim(name)", name="ck_counterparty_name_trimmed"),
        CheckConstraint("char_length(name) BETWEEN 1 AND 160", name="ck_counterparty_name_length"),
        CheckConstraint(_in_list("type", _COUNTERPARTY_TYPES), name="ck_counterparty_type"),
        CheckConstraint(_in_list("status", _RECORD_STATUSES), name="ck_counterparty_status"),
        CheckConstraint(
            "country IS NULL OR country ~ '^[A-Z]{2}$'", name="ck_counterparty_country_iso"
        ),
        CheckConstraint(
            "contact_name IS NULL OR char_length(contact_name) BETWEEN 1 AND 120",
            name="ck_counterparty_contact_name",
        ),
        CheckConstraint(
            "email IS NULL OR (email = lower(email) AND char_length(email) BETWEEN 3 AND 320)",
            name="ck_counterparty_email",
        ),
        CheckConstraint(
            "notes IS NULL OR char_length(notes) <= 2000", name="ck_counterparty_notes"
        ),
        CheckConstraint("version >= 1", name="ck_counterparty_version"),
        Index("ix_counterparty_company_status", "company_id", "status"),
        Index("ix_counterparty_company_created_at", "company_id", "created_at"),
        {"schema": "touche", "comment": "Tenant-scoped customers and suppliers (RLS protected)."},
    )

    id: Mapped[UUID] = mapped_column(
        PG_UUID(as_uuid=True), primary_key=True, server_default=func.gen_random_uuid()
    )
    company_id: Mapped[UUID] = mapped_column(
        PG_UUID(as_uuid=True),
        ForeignKey(
            "touche.company.id", name="fk_counterparty_company_id_company", ondelete="CASCADE"
        ),
        nullable=False,
    )
    name: Mapped[str] = mapped_column(Text, nullable=False)
    type: Mapped[str] = mapped_column(String(16), nullable=False, server_default=text("'buyer'"))
    country: Mapped[str | None] = mapped_column(String(2), nullable=True)
    contact_name: Mapped[str | None] = mapped_column(Text, nullable=True)
    email: Mapped[str | None] = mapped_column(Text, nullable=True)
    phone: Mapped[str | None] = mapped_column(String(40), nullable=True)
    notes: Mapped[str | None] = mapped_column(Text, nullable=True)
    status: Mapped[str] = mapped_column(String(16), nullable=False, server_default=text("'active'"))
    version: Mapped[int] = mapped_column(Integer, nullable=False, server_default=text("1"))
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now()
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now(), onupdate=func.now()
    )

    def __repr__(self) -> str:  # pragma: no cover - debugging helper
        return f"<Counterparty {self.name}>"


class Product(Base):
    """A tradable product in the company catalogue."""

    __tablename__ = "product"
    __table_args__ = (
        UniqueConstraint("company_id", "sku", name="uq_product_company_id_sku"),
        UniqueConstraint("id", "company_id", name="uq_product_id_company_id"),
        CheckConstraint("sku = upper(sku)", name="ck_product_sku_upper"),
        CheckConstraint("char_length(sku) BETWEEN 1 AND 40", name="ck_product_sku_length"),
        CheckConstraint("char_length(name) BETWEEN 1 AND 160", name="ck_product_name_length"),
        CheckConstraint(_in_list("unit", _PRODUCT_UNITS), name="ck_product_unit"),
        CheckConstraint("currency ~ '^[A-Z]{3}$'", name="ck_product_currency_iso"),
        CheckConstraint("unit_price >= 0", name="ck_product_unit_price"),
        CheckConstraint(_in_list("status", _RECORD_STATUSES), name="ck_product_status"),
        CheckConstraint("version >= 1", name="ck_product_version"),
        Index("ix_product_company_status", "company_id", "status"),
        Index("ix_product_company_created_at", "company_id", "created_at"),
        {"schema": "touche", "comment": "Tenant-scoped product catalogue (RLS protected)."},
    )

    id: Mapped[UUID] = mapped_column(
        PG_UUID(as_uuid=True), primary_key=True, server_default=func.gen_random_uuid()
    )
    company_id: Mapped[UUID] = mapped_column(
        PG_UUID(as_uuid=True),
        ForeignKey("touche.company.id", name="fk_product_company_id_company", ondelete="CASCADE"),
        nullable=False,
    )
    sku: Mapped[str] = mapped_column(String(40), nullable=False)
    name: Mapped[str] = mapped_column(Text, nullable=False)
    unit: Mapped[str] = mapped_column(String(16), nullable=False)
    currency: Mapped[str] = mapped_column(String(3), nullable=False)
    unit_price: Mapped[Decimal] = mapped_column(Numeric(18, 4), nullable=False)
    status: Mapped[str] = mapped_column(String(16), nullable=False, server_default=text("'active'"))
    version: Mapped[int] = mapped_column(Integer, nullable=False, server_default=text("1"))
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now()
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now(), onupdate=func.now()
    )



class Deal(Base):
    """A trade deal header. Lines live in :class:`DealItem`."""

    __tablename__ = "deal"
    __table_args__ = (
        UniqueConstraint("company_id", "reference", name="uq_deal_company_id_reference"),
        # Target of the composite FKs used by deal_item and deal_transition.
        UniqueConstraint("id", "company_id", name="uq_deal_id_company_id"),
        ForeignKeyConstraint(
            ["counterparty_id", "company_id"],
            ["touche.counterparty.id", "touche.counterparty.company_id"],
            name="fk_deal_counterparty_company",
            ondelete="RESTRICT",
        ),
        CheckConstraint("reference = upper(reference)", name="ck_deal_reference_upper"),
        CheckConstraint("char_length(reference) BETWEEN 3 AND 32", name="ck_deal_reference_length"),
        CheckConstraint("char_length(title) BETWEEN 1 AND 160", name="ck_deal_title_length"),
        CheckConstraint(_in_list("status", _DEAL_STATUSES), name="ck_deal_status"),
        CheckConstraint("currency ~ '^[A-Z]{3}$'", name="ck_deal_currency_iso"),
        CheckConstraint(
            "notes IS NULL OR char_length(notes) <= 2000", name="ck_deal_notes_length"
        ),
        CheckConstraint("version >= 1", name="ck_deal_version"),
        CheckConstraint(
            "(status IN ('WON', 'LOST', 'CANCELLED')) = (closed_at IS NOT NULL)",
            name="ck_deal_closed_at",
        ),
        Index("ix_deal_company_status", "company_id", "status"),
        Index("ix_deal_company_created_at", "company_id", "created_at"),
        Index("ix_deal_company_counterparty", "company_id", "counterparty_id"),
        {"schema": "touche", "comment": "Tenant-scoped trade deals (RLS protected)."},
    )

    id: Mapped[UUID] = mapped_column(
        PG_UUID(as_uuid=True), primary_key=True, server_default=func.gen_random_uuid()
    )
    company_id: Mapped[UUID] = mapped_column(
        PG_UUID(as_uuid=True),
        ForeignKey("touche.company.id", name="fk_deal_company_id_company", ondelete="CASCADE"),
        nullable=False,
    )
    reference: Mapped[str] = mapped_column(String(32), nullable=False)
    title: Mapped[str] = mapped_column(Text, nullable=False)
    status: Mapped[str] = mapped_column(String(16), nullable=False, server_default=text("'DRAFT'"))
    counterparty_id: Mapped[UUID] = mapped_column(PG_UUID(as_uuid=True), nullable=False)
    currency: Mapped[str] = mapped_column(String(3), nullable=False)
    expected_close_date: Mapped[date | None] = mapped_column(Date, nullable=True)
    notes: Mapped[str | None] = mapped_column(Text, nullable=True)
    version: Mapped[int] = mapped_column(Integer, nullable=False, server_default=text("1"))
    created_by: Mapped[UUID] = mapped_column(
        PG_UUID(as_uuid=True),
        ForeignKey("touche.app_user.id", name="fk_deal_created_by_app_user", ondelete="RESTRICT"),
        nullable=False,
    )
    closed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now()
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now(), onupdate=func.now()
    )

    def __repr__(self) -> str:  # pragma: no cover - debugging helper
        return f"<Deal {self.reference} {self.status}>"


class DealItem(Base):
    """One product line of a deal."""

    __tablename__ = "deal_item"
    __table_args__ = (
        ForeignKeyConstraint(
            ["deal_id", "company_id"],
            ["touche.deal.id", "touche.deal.company_id"],
            name="fk_deal_item_deal_company",
            ondelete="CASCADE",
        ),
        ForeignKeyConstraint(
            ["product_id", "company_id"],
            ["touche.product.id", "touche.product.company_id"],
            name="fk_deal_item_product_company",
            ondelete="RESTRICT",
        ),
        UniqueConstraint("deal_id", "product_id", name="uq_deal_item_deal_id_product_id"),
        CheckConstraint("quantity > 0", name="ck_deal_item_quantity"),
        CheckConstraint("unit_price >= 0", name="ck_deal_item_unit_price"),
        Index("ix_deal_item_company_deal", "company_id", "deal_id"),
        {"schema": "touche", "comment": "Tenant-scoped deal lines (RLS protected)."},
    )

    id: Mapped[UUID] = mapped_column(
        PG_UUID(as_uuid=True), primary_key=True, server_default=func.gen_random_uuid()
    )
    company_id: Mapped[UUID] = mapped_column(PG_UUID(as_uuid=True), nullable=False)
    deal_id: Mapped[UUID] = mapped_column(PG_UUID(as_uuid=True), nullable=False)
    product_id: Mapped[UUID] = mapped_column(PG_UUID(as_uuid=True), nullable=False)
    quantity: Mapped[Decimal] = mapped_column(Numeric(18, 3), nullable=False)
    unit_price: Mapped[Decimal] = mapped_column(Numeric(18, 4), nullable=False)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now()
    )

    def __repr__(self) -> str:  # pragma: no cover - debugging helper
        return f"<DealItem deal={self.deal_id} product={self.product_id}>"


class DealTransition(Base):
    """Immutable record of one accepted deal status change."""

    __tablename__ = "deal_transition"
    __table_args__ = (
        ForeignKeyConstraint(
            ["deal_id", "company_id"],
            ["touche.deal.id", "touche.deal.company_id"],
            name="fk_deal_transition_deal_company",
            ondelete="CASCADE",
        ),
        CheckConstraint(_in_list("to_status", _DEAL_STATUSES), name="ck_deal_transition_to_status"),
        CheckConstraint(
            "from_status IS NULL OR " + _in_list("from_status", _DEAL_STATUSES),
            name="ck_deal_transition_from_status",
        ),
        CheckConstraint(
            "reason IS NULL OR char_length(btrim(reason)) BETWEEN 3 AND 500",
            name="ck_deal_transition_reason",
        ),
        # A terminal state always explains itself; the graph itself is enforced
        # in the service layer, this is the last line of defence.
        CheckConstraint(
            "to_status NOT IN ('LOST', 'CANCELLED') OR reason IS NOT NULL",
            name="ck_deal_transition_terminal_reason",
        ),
        CheckConstraint("version_after >= 1", name="ck_deal_transition_version"),
        Index("ix_deal_transition_company_deal", "company_id", "deal_id", "occurred_at"),
        {"schema": "touche", "comment": "Immutable deal status history (RLS protected)."},
    )

    id: Mapped[UUID] = mapped_column(
        PG_UUID(as_uuid=True), primary_key=True, server_default=func.gen_random_uuid()
    )
    company_id: Mapped[UUID] = mapped_column(PG_UUID(as_uuid=True), nullable=False)
    deal_id: Mapped[UUID] = mapped_column(PG_UUID(as_uuid=True), nullable=False)
    from_status: Mapped[str | None] = mapped_column(String(16), nullable=True)
    to_status: Mapped[str] = mapped_column(String(16), nullable=False)
    reason: Mapped[str | None] = mapped_column(Text, nullable=True)
    actor_id: Mapped[UUID] = mapped_column(
        PG_UUID(as_uuid=True),
        ForeignKey("touche.app_user.id", name="fk_deal_transition_actor_app_user"),
        nullable=False,
    )
    request_id: Mapped[str | None] = mapped_column(String(128), nullable=True)
    version_after: Mapped[int] = mapped_column(Integer, nullable=False)
    occurred_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now()
    )

    def __repr__(self) -> str:  # pragma: no cover - debugging helper
        return f"<DealTransition {self.from_status} -> {self.to_status}>"


__all__ = [
    "Counterparty",
    "CounterpartyType",
    "Deal",
    "DealItem",
    "DealStatus",
    "DealTransition",
    "Product",
    "ProductUnit",
    "RecordStatus",
]


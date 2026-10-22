"""Stage 4 execution storage: sales orders, procurement, logistics and documents.

The rules are the same ones the previous stages established, and they are again
enforced by the database rather than only by services:

* every table carries ``company_id`` and is protected by row level security;
* every child row references its parent through a **composite** foreign key on
  ``(id, company_id)``, so a line can never be attached to another tenant's
  header even if a bug supplied the wrong pair of ids;
* money and quantities are ``Numeric`` and travel as ``Decimal`` end to end;
* mutable headers carry ``version`` for optimistic concurrency;
* history tables (``sales_order_transition``, ``order_amendment``,
  ``shipment_event``, ``customer_acceptance_evidence``) are append-only: the
  runtime role receives no UPDATE/DELETE, so a recorded commercial fact can
  never be silently rewritten.

Two honest boundaries are deliberately encoded here:

* ``CLOSED`` is an *order administration* state. Payment settlement is not
  modelled in Stage 4 at all, so no payment column exists to be mistaken for
  one.
* a document is linked through an allow-listed ``linked_entity_type`` and the
  service verifies that the entity exists in the same company. A single
  composite FK cannot express that polymorphism, and a fake one would be worse
  than the explicit check.
"""

from __future__ import annotations

from datetime import date, datetime
from decimal import Decimal
from enum import StrEnum
from uuid import UUID

from sqlalchemy import (
    BigInteger,
    Boolean,
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
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.dialects.postgresql import UUID as PG_UUID
from sqlalchemy.orm import Mapped, mapped_column

from app.db.models.base import Base


class FulfilmentModel(StrEnum):
    """Who actually supplies the goods.

    ``PURCHASE_RESALE`` means TOUCHE buys from a supplier and resells, so a
    supplier purchase order is legitimate. ``BROKERAGE`` means TOUCHE arranges
    the trade without being the buyer; procurement must stay optional and a
    purchase order is refused by the service.
    """

    PURCHASE_RESALE = "PURCHASE_RESALE"
    BROKERAGE = "BROKERAGE"


class AcceptanceChannel(StrEnum):
    """How the customer accepted the quote. Never inferred from a draft."""

    SIGNED_QUOTE = "SIGNED_QUOTE"
    PURCHASE_ORDER = "PURCHASE_ORDER"
    EMAIL = "EMAIL"
    PORTAL = "PORTAL"
    OTHER = "OTHER"


class SalesOrderStatus(StrEnum):
    CONFIRMED = "CONFIRMED"
    IN_FULFILLMENT = "IN_FULFILLMENT"
    FULFILLED = "FULFILLED"
    CLOSED = "CLOSED"
    CANCELLED = "CANCELLED"


class PurchaseOrderStatus(StrEnum):
    DRAFT = "DRAFT"
    APPROVED = "APPROVED"
    RECORDED_SENT = "RECORDED_SENT"
    SUPPLIER_CONFIRMED = "SUPPLIER_CONFIRMED"
    IN_FULFILLMENT = "IN_FULFILLMENT"
    RECEIVED = "RECEIVED"
    CANCELLED = "CANCELLED"


class TransportMode(StrEnum):
    SEA = "SEA"
    AIR = "AIR"
    ROAD = "ROAD"
    RAIL = "RAIL"
    MULTIMODAL = "MULTIMODAL"


class ShipmentStatus(StrEnum):
    PLANNED = "PLANNED"
    BOOKED = "BOOKED"
    DISPATCHED = "DISPATCHED"
    IN_TRANSIT = "IN_TRANSIT"
    ARRIVED = "ARRIVED"
    DELIVERED = "DELIVERED"
    CANCELLED = "CANCELLED"


class TrackingSource(StrEnum):
    """Provenance of a tracking reference.

    ``VERIFIED_EXTERNAL`` is not reachable in Stage 4: there is no carrier
    integration, so the service refuses to record it rather than pretending.
    """

    MANUAL = "MANUAL"
    DOCUMENT_EVIDENCE = "DOCUMENT_EVIDENCE"
    VERIFIED_EXTERNAL = "VERIFIED_EXTERNAL"


class ShipmentEventType(StrEnum):
    PLANNED = "PLANNED"
    BOOKED = "BOOKED"
    DISPATCHED = "DISPATCHED"
    IN_TRANSIT = "IN_TRANSIT"
    ARRIVED = "ARRIVED"
    DELIVERED = "DELIVERED"
    DELAY_RECORDED = "DELAY_RECORDED"
    CANCELLED = "CANCELLED"


class CostStage(StrEnum):
    """Logistics cost certainty. Estimates never masquerade as incurred costs."""

    ESTIMATED = "ESTIMATED"
    QUOTED = "QUOTED"
    INCURRED = "INCURRED"
    DOCUMENTED = "DOCUMENTED"


class TradeDocumentType(StrEnum):
    COMMERCIAL_INVOICE = "COMMERCIAL_INVOICE"
    PROFORMA_INVOICE = "PROFORMA_INVOICE"
    PACKING_LIST = "PACKING_LIST"
    BILL_OF_LADING = "BILL_OF_LADING"
    AIR_WAYBILL = "AIR_WAYBILL"
    CMR_CONSIGNMENT_NOTE = "CMR_CONSIGNMENT_NOTE"
    CERTIFICATE_OF_ORIGIN = "CERTIFICATE_OF_ORIGIN"
    INSURANCE_CERTIFICATE = "INSURANCE_CERTIFICATE"
    QUALITY_INSPECTION_CERTIFICATE = "QUALITY_INSPECTION_CERTIFICATE"
    CUSTOMS_DECLARATION = "CUSTOMS_DECLARATION"
    PURCHASE_ORDER = "PURCHASE_ORDER"
    SALES_ORDER = "SALES_ORDER"
    DELIVERY_CONFIRMATION = "DELIVERY_CONFIRMATION"
    OTHER = "OTHER"


class LinkedEntityType(StrEnum):
    DEAL = "DEAL"
    SALES_ORDER = "SALES_ORDER"
    PURCHASE_ORDER = "PURCHASE_ORDER"
    SHIPMENT = "SHIPMENT"
    CUSTOMER_ACCEPTANCE = "CUSTOMER_ACCEPTANCE"


class DocumentStatus(StrEnum):
    ACTIVE = "ACTIVE"
    ARCHIVED = "ARCHIVED"


class DocumentVerificationStatus(StrEnum):
    UNVERIFIED = "UNVERIFIED"
    VERIFIED = "VERIFIED"
    REJECTED = "REJECTED"


def _in_list(column: str, values: tuple[str, ...]) -> str:
    rendered = ", ".join(f"'{value}'" for value in values)
    return f"{column} IN ({rendered})"


_UNITS = ("kg", "mt", "lb", "unit", "l", "m3")
_CURRENCY_CHECK = "~ '^[A-Z]{3}$'"
_INCOTERMS = "('EXW','FCA','FAS','FOB','CFR','CIF','CPT','CIP','DAP','DPU','DDP')"

_FULFILMENT_MODELS = tuple(value.value for value in FulfilmentModel)
_ACCEPTANCE_CHANNELS = tuple(value.value for value in AcceptanceChannel)
_SALES_ORDER_STATUSES = tuple(value.value for value in SalesOrderStatus)
_PURCHASE_ORDER_STATUSES = tuple(value.value for value in PurchaseOrderStatus)
_TRANSPORT_MODES = tuple(value.value for value in TransportMode)
_SHIPMENT_STATUSES = tuple(value.value for value in ShipmentStatus)
_TRACKING_SOURCES = tuple(value.value for value in TrackingSource)
_SHIPMENT_EVENT_TYPES = tuple(value.value for value in ShipmentEventType)
_COST_STAGES = tuple(value.value for value in CostStage)
_DOCUMENT_TYPES = tuple(value.value for value in TradeDocumentType)
_LINKED_ENTITY_TYPES = tuple(value.value for value in LinkedEntityType)
_DOCUMENT_STATUSES = tuple(value.value for value in DocumentStatus)
_VERIFICATION_STATUSES = tuple(value.value for value in DocumentVerificationStatus)


class CustomerAcceptanceEvidence(Base):
    """Append-only proof that the *customer* accepted one quote revision.

    The row is written by a user who reviewed real evidence. Nothing in this
    system infers acceptance from a draft, an RFQ, a supplier response or an
    AI-generated message.
    """

    __tablename__ = "customer_acceptance_evidence"
    __table_args__ = (
        UniqueConstraint(
            "id", "company_id", name="uq_customer_acceptance_evidence_id_company_id"
        ),
        ForeignKeyConstraint(
            ["deal_id", "company_id"],
            ["touche.deal.id", "touche.deal.company_id"],
            name="fk_customer_acceptance_deal_company",
            ondelete="CASCADE",
        ),
        ForeignKeyConstraint(
            ["sales_quote_id", "company_id"],
            ["touche.sales_quote.id", "touche.sales_quote.company_id"],
            name="fk_customer_acceptance_quote_company",
            ondelete="RESTRICT",
        ),
        CheckConstraint(
            _in_list("channel", _ACCEPTANCE_CHANNELS), name="ck_customer_acceptance_channel"
        ),
        CheckConstraint("sales_quote_revision >= 1", name="ck_customer_acceptance_revision"),
        CheckConstraint(
            "char_length(btrim(accepted_by_name)) BETWEEN 2 AND 160",
            name="ck_customer_acceptance_name",
        ),
        CheckConstraint(
            "char_length(btrim(evidence_reference)) BETWEEN 3 AND 500",
            name="ck_customer_acceptance_evidence",
        ),
        CheckConstraint(
            "notes IS NULL OR char_length(notes) <= 2000", name="ck_customer_acceptance_notes"
        ),
        Index(
            "ix_customer_acceptance_company_quote",
            "company_id",
            "sales_quote_id",
            "sales_quote_revision",
        ),
        Index("ix_customer_acceptance_company_deal", "company_id", "deal_id"),
        {
            "schema": "touche",
            "comment": "Append-only customer acceptance evidence (RLS protected).",
        },
    )

    id: Mapped[UUID] = mapped_column(
        PG_UUID(as_uuid=True), primary_key=True, server_default=func.gen_random_uuid()
    )
    company_id: Mapped[UUID] = mapped_column(PG_UUID(as_uuid=True), nullable=False)
    deal_id: Mapped[UUID] = mapped_column(PG_UUID(as_uuid=True), nullable=False)
    sales_quote_id: Mapped[UUID] = mapped_column(PG_UUID(as_uuid=True), nullable=False)
    sales_quote_revision: Mapped[int] = mapped_column(Integer, nullable=False)
    channel: Mapped[str] = mapped_column(String(24), nullable=False)
    accepted_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    accepted_by_name: Mapped[str] = mapped_column(Text, nullable=False)
    evidence_reference: Mapped[str] = mapped_column(Text, nullable=False)
    evidence_document_id: Mapped[UUID | None] = mapped_column(PG_UUID(as_uuid=True), nullable=True)
    notes: Mapped[str | None] = mapped_column(Text, nullable=True)
    recorded_by: Mapped[UUID] = mapped_column(
        PG_UUID(as_uuid=True),
        ForeignKey("touche.app_user.id", name="fk_customer_acceptance_recorded_by_app_user"),
        nullable=False,
    )
    recorded_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now()
    )

    def __repr__(self) -> str:  # pragma: no cover - debugging helper
        return (
            f"<CustomerAcceptanceEvidence quote={self.sales_quote_id} "
            f"r{self.sales_quote_revision}>"
        )


class SalesOrder(Base):
    """A confirmed customer order created from an accepted quote revision."""

    __tablename__ = "sales_order"
    __table_args__ = (
        UniqueConstraint("id", "company_id", name="uq_sales_order_id_company_id"),
        UniqueConstraint("company_id", "order_number", name="uq_sales_order_company_number"),
        # One initial order per deal, enforced by the database as well as by the
        # conversion service: a second order cannot exist behind a WON deal.
        UniqueConstraint("company_id", "deal_id", name="uq_sales_order_company_deal"),
        ForeignKeyConstraint(
            ["deal_id", "company_id"],
            ["touche.deal.id", "touche.deal.company_id"],
            name="fk_sales_order_deal_company",
            ondelete="RESTRICT",
        ),
        ForeignKeyConstraint(
            ["sales_quote_id", "company_id"],
            ["touche.sales_quote.id", "touche.sales_quote.company_id"],
            name="fk_sales_order_quote_company",
            ondelete="RESTRICT",
        ),
        ForeignKeyConstraint(
            ["customer_id", "company_id"],
            ["touche.counterparty.id", "touche.counterparty.company_id"],
            name="fk_sales_order_customer_company",
            ondelete="RESTRICT",
        ),
        ForeignKeyConstraint(
            ["acceptance_evidence_id", "company_id"],
            [
                "touche.customer_acceptance_evidence.id",
                "touche.customer_acceptance_evidence.company_id",
            ],
            name="fk_sales_order_acceptance_company",
            ondelete="RESTRICT",
        ),
        CheckConstraint(f"currency {_CURRENCY_CHECK}", name="ck_sales_order_currency_iso"),
        CheckConstraint(f"incoterm IN {_INCOTERMS}", name="ck_sales_order_incoterm"),
        CheckConstraint(_in_list("status", _SALES_ORDER_STATUSES), name="ck_sales_order_status"),
        CheckConstraint(
            _in_list("fulfilment_model", _FULFILMENT_MODELS),
            name="ck_sales_order_fulfilment_model",
        ),
        CheckConstraint(
            "char_length(btrim(order_number)) BETWEEN 3 AND 40", name="ck_sales_order_number"
        ),
        CheckConstraint(
            "char_length(btrim(named_delivery_place)) BETWEEN 2 AND 160",
            name="ck_sales_order_place",
        ),
        CheckConstraint(
            "char_length(btrim(payment_terms_snapshot)) BETWEEN 2 AND 200",
            name="ck_sales_order_payment_terms",
        ),
        CheckConstraint("order_total >= 0", name="ck_sales_order_total"),
        CheckConstraint("sales_quote_revision >= 1", name="ck_sales_order_quote_revision"),
        CheckConstraint("version >= 1", name="ck_sales_order_version"),
        CheckConstraint(
            "jsonb_typeof(accepted_terms) = 'object'", name="ck_sales_order_accepted_terms"
        ),
        CheckConstraint(
            "(status = 'CANCELLED') = (cancelled_at IS NOT NULL)",
            name="ck_sales_order_cancelled_at",
        ),
        CheckConstraint(
            "status <> 'CANCELLED' OR cancellation_reason IS NOT NULL",
            name="ck_sales_order_cancellation_reason",
        ),
        Index("ix_sales_order_company_status", "company_id", "status"),
        Index("ix_sales_order_company_created_at", "company_id", "created_at"),
        Index("ix_sales_order_company_customer", "company_id", "customer_id"),
        {"schema": "touche", "comment": "Tenant-scoped sales orders (RLS protected)."},
    )

    id: Mapped[UUID] = mapped_column(
        PG_UUID(as_uuid=True), primary_key=True, server_default=func.gen_random_uuid()
    )
    company_id: Mapped[UUID] = mapped_column(PG_UUID(as_uuid=True), nullable=False)
    order_number: Mapped[str] = mapped_column(String(40), nullable=False)
    deal_id: Mapped[UUID] = mapped_column(PG_UUID(as_uuid=True), nullable=False)
    sales_quote_id: Mapped[UUID] = mapped_column(PG_UUID(as_uuid=True), nullable=False)
    sales_quote_revision: Mapped[int] = mapped_column(Integer, nullable=False)
    acceptance_evidence_id: Mapped[UUID] = mapped_column(PG_UUID(as_uuid=True), nullable=False)
    customer_id: Mapped[UUID] = mapped_column(PG_UUID(as_uuid=True), nullable=False)
    currency: Mapped[str] = mapped_column(String(3), nullable=False)
    incoterm: Mapped[str] = mapped_column(String(3), nullable=False)
    named_delivery_place: Mapped[str] = mapped_column(Text, nullable=False)
    payment_terms_snapshot: Mapped[str] = mapped_column(Text, nullable=False)
    fulfilment_model: Mapped[str] = mapped_column(String(24), nullable=False)
    order_total: Mapped[Decimal] = mapped_column(Numeric(18, 2), nullable=False)
    status: Mapped[str] = mapped_column(
        String(16), nullable=False, server_default=text("'CONFIRMED'")
    )
    accepted_terms: Mapped[dict[str, object]] = mapped_column(JSONB, nullable=False)
    expected_delivery_date: Mapped[date | None] = mapped_column(Date, nullable=True)
    notes: Mapped[str | None] = mapped_column(Text, nullable=True)
    confirmed_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    cancelled_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    cancellation_reason: Mapped[str | None] = mapped_column(Text, nullable=True)
    created_by: Mapped[UUID] = mapped_column(
        PG_UUID(as_uuid=True),
        ForeignKey("touche.app_user.id", name="fk_sales_order_created_by_app_user"),
        nullable=False,
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now()
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now(), onupdate=func.now()
    )
    version: Mapped[int] = mapped_column(Integer, nullable=False, server_default=text("1"))

    def __repr__(self) -> str:  # pragma: no cover - debugging helper
        return f"<SalesOrder {self.order_number} {self.status}>"


class SalesOrderItem(Base):
    """An immutable commercial line captured from the accepted quote revision."""

    __tablename__ = "sales_order_item"
    __table_args__ = (
        ForeignKeyConstraint(
            ["sales_order_id", "company_id"],
            ["touche.sales_order.id", "touche.sales_order.company_id"],
            name="fk_sales_order_item_order_company",
            ondelete="CASCADE",
        ),
        ForeignKeyConstraint(
            ["product_id", "company_id"],
            ["touche.product.id", "touche.product.company_id"],
            name="fk_sales_order_item_product_company",
            ondelete="RESTRICT",
        ),
        UniqueConstraint(
            "sales_order_id", "product_id", name="uq_sales_order_item_order_id_product_id"
        ),
        UniqueConstraint("id", "company_id", name="uq_sales_order_item_id_company_id"),
        CheckConstraint("quantity > 0", name="ck_sales_order_item_quantity"),
        CheckConstraint("unit_price >= 0", name="ck_sales_order_item_unit_price"),
        CheckConstraint("line_total >= 0", name="ck_sales_order_item_line_total"),
        CheckConstraint(_in_list("unit", _UNITS), name="ck_sales_order_item_unit"),
        Index("ix_sales_order_item_company_order", "company_id", "sales_order_id"),
        {"schema": "touche", "comment": "Tenant-scoped sales order lines (RLS protected)."},
    )

    id: Mapped[UUID] = mapped_column(
        PG_UUID(as_uuid=True), primary_key=True, server_default=func.gen_random_uuid()
    )
    company_id: Mapped[UUID] = mapped_column(PG_UUID(as_uuid=True), nullable=False)
    sales_order_id: Mapped[UUID] = mapped_column(PG_UUID(as_uuid=True), nullable=False)
    product_id: Mapped[UUID] = mapped_column(PG_UUID(as_uuid=True), nullable=False)
    sku: Mapped[str] = mapped_column(String(40), nullable=False)
    name: Mapped[str] = mapped_column(Text, nullable=False)
    description: Mapped[str] = mapped_column(Text, nullable=False)
    quantity: Mapped[Decimal] = mapped_column(Numeric(18, 3), nullable=False)
    unit: Mapped[str] = mapped_column(String(16), nullable=False)
    unit_price: Mapped[Decimal] = mapped_column(Numeric(18, 4), nullable=False)
    line_total: Mapped[Decimal] = mapped_column(Numeric(18, 2), nullable=False)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now()
    )

    def __repr__(self) -> str:  # pragma: no cover - debugging helper
        return f"<SalesOrderItem order={self.sales_order_id} sku={self.sku}>"


class SalesOrderTransition(Base):
    """Append-only record of one accepted sales-order status change."""

    __tablename__ = "sales_order_transition"
    __table_args__ = (
        ForeignKeyConstraint(
            ["sales_order_id", "company_id"],
            ["touche.sales_order.id", "touche.sales_order.company_id"],
            name="fk_sales_order_transition_order_company",
            ondelete="CASCADE",
        ),
        CheckConstraint(
            _in_list("to_status", _SALES_ORDER_STATUSES),
            name="ck_sales_order_transition_to_status",
        ),
        CheckConstraint(
            "from_status IS NULL OR " + _in_list("from_status", _SALES_ORDER_STATUSES),
            name="ck_sales_order_transition_from_status",
        ),
        CheckConstraint(
            "reason IS NULL OR char_length(btrim(reason)) BETWEEN 3 AND 500",
            name="ck_sales_order_transition_reason",
        ),
        CheckConstraint(
            "to_status NOT IN ('CANCELLED') OR reason IS NOT NULL",
            name="ck_sales_order_transition_cancel_reason",
        ),
        CheckConstraint("version_after >= 1", name="ck_sales_order_transition_version"),
        Index(
            "ix_sales_order_transition_company_order",
            "company_id",
            "sales_order_id",
            "occurred_at",
        ),
        {"schema": "touche", "comment": "Immutable sales order history (RLS protected)."},
    )

    id: Mapped[UUID] = mapped_column(
        PG_UUID(as_uuid=True), primary_key=True, server_default=func.gen_random_uuid()
    )
    company_id: Mapped[UUID] = mapped_column(PG_UUID(as_uuid=True), nullable=False)
    sales_order_id: Mapped[UUID] = mapped_column(PG_UUID(as_uuid=True), nullable=False)
    from_status: Mapped[str | None] = mapped_column(String(16), nullable=True)
    to_status: Mapped[str] = mapped_column(String(16), nullable=False)
    reason: Mapped[str | None] = mapped_column(Text, nullable=True)
    actor_id: Mapped[UUID] = mapped_column(
        PG_UUID(as_uuid=True),
        ForeignKey("touche.app_user.id", name="fk_sales_order_transition_actor_app_user"),
        nullable=False,
    )
    request_id: Mapped[str | None] = mapped_column(String(128), nullable=True)
    version_after: Mapped[int] = mapped_column(Integer, nullable=False)
    occurred_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now()
    )

    def __repr__(self) -> str:  # pragma: no cover - debugging helper
        return f"<SalesOrderTransition {self.from_status} -> {self.to_status}>"


class OrderAmendment(Base):
    """Append-only, reasoned change to an order after it was accepted.

    The accepted commercial snapshot on :class:`SalesOrder` is never rewritten;
    an amendment records exactly what changed and by whom.
    """

    __tablename__ = "order_amendment"
    __table_args__ = (
        ForeignKeyConstraint(
            ["sales_order_id", "company_id"],
            ["touche.sales_order.id", "touche.sales_order.company_id"],
            name="fk_order_amendment_order_company",
            ondelete="CASCADE",
        ),
        CheckConstraint(
            "char_length(btrim(reason)) BETWEEN 3 AND 500", name="ck_order_amendment_reason"
        ),
        CheckConstraint(
            "jsonb_typeof(changes) = 'object'", name="ck_order_amendment_changes"
        ),
        CheckConstraint("version_after >= 1", name="ck_order_amendment_version"),
        Index("ix_order_amendment_company_order", "company_id", "sales_order_id", "created_at"),
        {"schema": "touche", "comment": "Immutable order amendments (RLS protected)."},
    )

    id: Mapped[UUID] = mapped_column(
        PG_UUID(as_uuid=True), primary_key=True, server_default=func.gen_random_uuid()
    )
    company_id: Mapped[UUID] = mapped_column(PG_UUID(as_uuid=True), nullable=False)
    sales_order_id: Mapped[UUID] = mapped_column(PG_UUID(as_uuid=True), nullable=False)
    reason: Mapped[str] = mapped_column(Text, nullable=False)
    changes: Mapped[dict[str, object]] = mapped_column(JSONB, nullable=False)
    actor_id: Mapped[UUID] = mapped_column(
        PG_UUID(as_uuid=True),
        ForeignKey("touche.app_user.id", name="fk_order_amendment_actor_app_user"),
        nullable=False,
    )
    request_id: Mapped[str | None] = mapped_column(String(128), nullable=True)
    version_after: Mapped[int] = mapped_column(Integer, nullable=False)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now()
    )

    def __repr__(self) -> str:  # pragma: no cover - debugging helper
        return f"<OrderAmendment order={self.sales_order_id}>"


class PurchaseOrder(Base):
    """A supplier purchase order. Never treated as sent until that is recorded."""

    __tablename__ = "purchase_order"
    __table_args__ = (
        UniqueConstraint("id", "company_id", name="uq_purchase_order_id_company_id"),
        UniqueConstraint("company_id", "po_number", name="uq_purchase_order_company_number"),
        ForeignKeyConstraint(
            ["sales_order_id", "company_id"],
            ["touche.sales_order.id", "touche.sales_order.company_id"],
            name="fk_purchase_order_sales_order_company",
            ondelete="RESTRICT",
        ),
        ForeignKeyConstraint(
            ["supplier_id", "company_id"],
            ["touche.counterparty.id", "touche.counterparty.company_id"],
            name="fk_purchase_order_supplier_company",
            ondelete="RESTRICT",
        ),
        CheckConstraint(f"currency {_CURRENCY_CHECK}", name="ck_purchase_order_currency_iso"),
        CheckConstraint(f"incoterm IN {_INCOTERMS}", name="ck_purchase_order_incoterm"),
        CheckConstraint(
            _in_list("status", _PURCHASE_ORDER_STATUSES), name="ck_purchase_order_status"
        ),
        CheckConstraint(
            "char_length(btrim(po_number)) BETWEEN 3 AND 40", name="ck_purchase_order_number"
        ),
        CheckConstraint(
            "char_length(btrim(named_delivery_place)) BETWEEN 2 AND 160",
            name="ck_purchase_order_place",
        ),
        CheckConstraint(
            "char_length(btrim(payment_terms)) BETWEEN 2 AND 200",
            name="ck_purchase_order_payment_terms",
        ),
        CheckConstraint("total_cost >= 0", name="ck_purchase_order_total"),
        CheckConstraint("version >= 1", name="ck_purchase_order_version"),
        CheckConstraint(
            "status NOT IN ('DRAFT','APPROVED') OR dispatched_at IS NULL",
            name="ck_purchase_order_dispatched_at",
        ),
        CheckConstraint(
            "status <> 'RECORDED_SENT' OR dispatch_channel IS NOT NULL",
            name="ck_purchase_order_dispatch_channel",
        ),
        CheckConstraint(
            "status NOT IN ('SUPPLIER_CONFIRMED', 'IN_FULFILLMENT', 'RECEIVED') "
            "OR supplier_confirmation_reference IS NOT NULL",
            name="ck_purchase_order_supplier_confirmation",
        ),
        CheckConstraint(
            "(status = 'CANCELLED') = (cancelled_at IS NOT NULL)",
            name="ck_purchase_order_cancelled_at",
        ),
        Index("ix_purchase_order_company_status", "company_id", "status"),
        Index("ix_purchase_order_company_sales_order", "company_id", "sales_order_id"),
        Index("ix_purchase_order_company_supplier", "company_id", "supplier_id"),
        {"schema": "touche", "comment": "Tenant-scoped purchase orders (RLS protected)."},
    )

    id: Mapped[UUID] = mapped_column(
        PG_UUID(as_uuid=True), primary_key=True, server_default=func.gen_random_uuid()
    )
    company_id: Mapped[UUID] = mapped_column(PG_UUID(as_uuid=True), nullable=False)
    po_number: Mapped[str] = mapped_column(String(40), nullable=False)
    sales_order_id: Mapped[UUID] = mapped_column(PG_UUID(as_uuid=True), nullable=False)
    supplier_id: Mapped[UUID] = mapped_column(PG_UUID(as_uuid=True), nullable=False)
    supplier_quote_id: Mapped[UUID | None] = mapped_column(PG_UUID(as_uuid=True), nullable=True)
    currency: Mapped[str] = mapped_column(String(3), nullable=False)
    incoterm: Mapped[str] = mapped_column(String(3), nullable=False)
    named_delivery_place: Mapped[str] = mapped_column(Text, nullable=False)
    payment_terms: Mapped[str] = mapped_column(Text, nullable=False)
    total_cost: Mapped[Decimal] = mapped_column(Numeric(18, 2), nullable=False)
    status: Mapped[str] = mapped_column(
        String(24), nullable=False, server_default=text("'DRAFT'")
    )
    expected_dispatch_date: Mapped[date | None] = mapped_column(Date, nullable=True)
    expected_delivery_date: Mapped[date | None] = mapped_column(Date, nullable=True)
    dispatch_channel: Mapped[str | None] = mapped_column(String(32), nullable=True)
    dispatched_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    dispatch_reference: Mapped[str | None] = mapped_column(Text, nullable=True)
    supplier_confirmation_reference: Mapped[str | None] = mapped_column(Text, nullable=True)
    supplier_confirmed_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )
    approved_by: Mapped[UUID | None] = mapped_column(
        PG_UUID(as_uuid=True),
        ForeignKey("touche.app_user.id", name="fk_purchase_order_approved_by_app_user"),
        nullable=True,
    )
    approved_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    notes: Mapped[str | None] = mapped_column(Text, nullable=True)
    cancelled_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    cancellation_reason: Mapped[str | None] = mapped_column(Text, nullable=True)
    created_by: Mapped[UUID] = mapped_column(
        PG_UUID(as_uuid=True),
        ForeignKey("touche.app_user.id", name="fk_purchase_order_created_by_app_user"),
        nullable=False,
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now()
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now(), onupdate=func.now()
    )
    version: Mapped[int] = mapped_column(Integer, nullable=False, server_default=text("1"))

    def __repr__(self) -> str:  # pragma: no cover - debugging helper
        return f"<PurchaseOrder {self.po_number} {self.status}>"


class PurchaseOrderItem(Base):
    __tablename__ = "purchase_order_item"
    __table_args__ = (
        ForeignKeyConstraint(
            ["purchase_order_id", "company_id"],
            ["touche.purchase_order.id", "touche.purchase_order.company_id"],
            name="fk_purchase_order_item_order_company",
            ondelete="CASCADE",
        ),
        ForeignKeyConstraint(
            ["product_id", "company_id"],
            ["touche.product.id", "touche.product.company_id"],
            name="fk_purchase_order_item_product_company",
            ondelete="RESTRICT",
        ),
        UniqueConstraint(
            "purchase_order_id", "product_id", name="uq_purchase_order_item_order_id_product_id"
        ),
        CheckConstraint("quantity > 0", name="ck_purchase_order_item_quantity"),
        CheckConstraint("unit_cost >= 0", name="ck_purchase_order_item_unit_cost"),
        CheckConstraint("line_total >= 0", name="ck_purchase_order_item_line_total"),
        CheckConstraint(_in_list("unit", _UNITS), name="ck_purchase_order_item_unit"),
        Index("ix_purchase_order_item_company_order", "company_id", "purchase_order_id"),
        {"schema": "touche", "comment": "Tenant-scoped purchase order lines (RLS protected)."},
    )

    id: Mapped[UUID] = mapped_column(
        PG_UUID(as_uuid=True), primary_key=True, server_default=func.gen_random_uuid()
    )
    company_id: Mapped[UUID] = mapped_column(PG_UUID(as_uuid=True), nullable=False)
    purchase_order_id: Mapped[UUID] = mapped_column(PG_UUID(as_uuid=True), nullable=False)
    product_id: Mapped[UUID] = mapped_column(PG_UUID(as_uuid=True), nullable=False)
    description: Mapped[str] = mapped_column(Text, nullable=False)
    quantity: Mapped[Decimal] = mapped_column(Numeric(18, 3), nullable=False)
    unit: Mapped[str] = mapped_column(String(16), nullable=False)
    unit_cost: Mapped[Decimal] = mapped_column(Numeric(18, 4), nullable=False)
    line_total: Mapped[Decimal] = mapped_column(Numeric(18, 2), nullable=False)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now()
    )

    def __repr__(self) -> str:  # pragma: no cover - debugging helper
        return f"<PurchaseOrderItem order={self.purchase_order_id} product={self.product_id}>"


class PurchaseOrderTransition(Base):
    __tablename__ = "purchase_order_transition"
    __table_args__ = (
        ForeignKeyConstraint(
            ["purchase_order_id", "company_id"],
            ["touche.purchase_order.id", "touche.purchase_order.company_id"],
            name="fk_purchase_order_transition_order_company",
            ondelete="CASCADE",
        ),
        CheckConstraint(
            _in_list("to_status", _PURCHASE_ORDER_STATUSES),
            name="ck_purchase_order_transition_to_status",
        ),
        CheckConstraint(
            "from_status IS NULL OR " + _in_list("from_status", _PURCHASE_ORDER_STATUSES),
            name="ck_purchase_order_transition_from_status",
        ),
        CheckConstraint(
            "reason IS NULL OR char_length(btrim(reason)) BETWEEN 3 AND 500",
            name="ck_purchase_order_transition_reason",
        ),
        CheckConstraint("version_after >= 1", name="ck_purchase_order_transition_version"),
        Index(
            "ix_purchase_order_transition_company_order",
            "company_id",
            "purchase_order_id",
            "occurred_at",
        ),
        {"schema": "touche", "comment": "Immutable purchase order history (RLS protected)."},
    )

    id: Mapped[UUID] = mapped_column(
        PG_UUID(as_uuid=True), primary_key=True, server_default=func.gen_random_uuid()
    )
    company_id: Mapped[UUID] = mapped_column(PG_UUID(as_uuid=True), nullable=False)
    purchase_order_id: Mapped[UUID] = mapped_column(PG_UUID(as_uuid=True), nullable=False)
    from_status: Mapped[str | None] = mapped_column(String(24), nullable=True)
    to_status: Mapped[str] = mapped_column(String(24), nullable=False)
    reason: Mapped[str | None] = mapped_column(Text, nullable=True)
    evidence_reference: Mapped[str | None] = mapped_column(Text, nullable=True)
    actor_id: Mapped[UUID] = mapped_column(
        PG_UUID(as_uuid=True),
        ForeignKey("touche.app_user.id", name="fk_purchase_order_transition_actor_app_user"),
        nullable=False,
    )
    request_id: Mapped[str | None] = mapped_column(String(128), nullable=True)
    version_after: Mapped[int] = mapped_column(Integer, nullable=False)
    occurred_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now()
    )

    def __repr__(self) -> str:  # pragma: no cover - debugging helper
        return f"<PurchaseOrderTransition {self.from_status} -> {self.to_status}>"


class Shipment(Base):
    """A planned or executed movement of goods for one sales order."""

    __tablename__ = "shipment"
    __table_args__ = (
        UniqueConstraint("id", "company_id", name="uq_shipment_id_company_id"),
        UniqueConstraint("company_id", "shipment_number", name="uq_shipment_company_number"),
        ForeignKeyConstraint(
            ["sales_order_id", "company_id"],
            ["touche.sales_order.id", "touche.sales_order.company_id"],
            name="fk_shipment_sales_order_company",
            ondelete="RESTRICT",
        ),
        ForeignKeyConstraint(
            ["purchase_order_id", "company_id"],
            ["touche.purchase_order.id", "touche.purchase_order.company_id"],
            name="fk_shipment_purchase_order_company",
            ondelete="RESTRICT",
        ),
        CheckConstraint(_in_list("status", _SHIPMENT_STATUSES), name="ck_shipment_status"),
        CheckConstraint(
            _in_list("transport_mode", _TRANSPORT_MODES), name="ck_shipment_transport_mode"
        ),
        CheckConstraint(
            "tracking_source IS NULL OR " + _in_list("tracking_source", _TRACKING_SOURCES),
            name="ck_shipment_tracking_source",
        ),
        CheckConstraint(
            "char_length(btrim(shipment_number)) BETWEEN 3 AND 40",
            name="ck_shipment_number",
        ),
        CheckConstraint("char_length(btrim(origin)) BETWEEN 2 AND 160", name="ck_shipment_origin"),
        CheckConstraint(
            "char_length(btrim(destination)) BETWEEN 2 AND 160", name="ck_shipment_destination"
        ),
        CheckConstraint("version >= 1", name="ck_shipment_version"),
        CheckConstraint(
            "actual_arrival_at IS NULL OR actual_dispatch_at IS NULL "
            "OR actual_arrival_at >= actual_dispatch_at",
            name="ck_shipment_arrival_order",
        ),
        CheckConstraint(
            "delivered_at IS NULL OR actual_arrival_at IS NULL "
            "OR delivered_at >= actual_arrival_at",
            name="ck_shipment_delivery_order",
        ),
        CheckConstraint(
            "status <> 'CANCELLED' OR cancellation_reason IS NOT NULL",
            name="ck_shipment_cancellation_reason",
        ),
        CheckConstraint(
            "status <> 'DELIVERED' OR delivery_evidence_reference IS NOT NULL",
            name="ck_shipment_delivery_evidence",
        ),
        Index("ix_shipment_company_status", "company_id", "status"),
        Index("ix_shipment_company_sales_order", "company_id", "sales_order_id"),
        Index("ix_shipment_company_eta", "company_id", "estimated_arrival_at"),
        {"schema": "touche", "comment": "Tenant-scoped shipments (RLS protected)."},
    )

    id: Mapped[UUID] = mapped_column(
        PG_UUID(as_uuid=True), primary_key=True, server_default=func.gen_random_uuid()
    )
    company_id: Mapped[UUID] = mapped_column(PG_UUID(as_uuid=True), nullable=False)
    shipment_number: Mapped[str] = mapped_column(String(40), nullable=False)
    sales_order_id: Mapped[UUID] = mapped_column(PG_UUID(as_uuid=True), nullable=False)
    purchase_order_id: Mapped[UUID | None] = mapped_column(PG_UUID(as_uuid=True), nullable=True)
    transport_mode: Mapped[str] = mapped_column(String(16), nullable=False)
    origin: Mapped[str] = mapped_column(Text, nullable=False)
    destination: Mapped[str] = mapped_column(Text, nullable=False)
    carrier: Mapped[str | None] = mapped_column(Text, nullable=True)
    forwarder: Mapped[str | None] = mapped_column(Text, nullable=True)
    planned_dispatch_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )
    actual_dispatch_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )
    estimated_arrival_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )
    actual_arrival_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )
    delivered_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    status: Mapped[str] = mapped_column(
        String(16), nullable=False, server_default=text("'PLANNED'")
    )
    tracking_reference: Mapped[str | None] = mapped_column(Text, nullable=True)
    tracking_source: Mapped[str | None] = mapped_column(String(24), nullable=True)
    delivery_evidence_reference: Mapped[str | None] = mapped_column(Text, nullable=True)
    delay_reason: Mapped[str | None] = mapped_column(Text, nullable=True)
    cancellation_reason: Mapped[str | None] = mapped_column(Text, nullable=True)
    notes: Mapped[str | None] = mapped_column(Text, nullable=True)
    created_by: Mapped[UUID] = mapped_column(
        PG_UUID(as_uuid=True),
        ForeignKey("touche.app_user.id", name="fk_shipment_created_by_app_user"),
        nullable=False,
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now()
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now(), onupdate=func.now()
    )
    version: Mapped[int] = mapped_column(Integer, nullable=False, server_default=text("1"))

    def __repr__(self) -> str:  # pragma: no cover - debugging helper
        return f"<Shipment {self.shipment_number} {self.status}>"


class ShipmentItem(Base):
    """Allocated quantity of one order line on one shipment."""

    __tablename__ = "shipment_item"
    __table_args__ = (
        ForeignKeyConstraint(
            ["shipment_id", "company_id"],
            ["touche.shipment.id", "touche.shipment.company_id"],
            name="fk_shipment_item_shipment_company",
            ondelete="CASCADE",
        ),
        ForeignKeyConstraint(
            ["sales_order_item_id", "company_id"],
            ["touche.sales_order_item.id", "touche.sales_order_item.company_id"],
            name="fk_shipment_item_order_item_company",
            ondelete="RESTRICT",
        ),
        UniqueConstraint(
            "shipment_id", "sales_order_item_id", name="uq_shipment_item_shipment_id_order_item"
        ),
        CheckConstraint("quantity > 0", name="ck_shipment_item_quantity"),
        CheckConstraint(_in_list("unit", _UNITS), name="ck_shipment_item_unit"),
        Index("ix_shipment_item_company_shipment", "company_id", "shipment_id"),
        Index("ix_shipment_item_company_order_item", "company_id", "sales_order_item_id"),
        {"schema": "touche", "comment": "Tenant-scoped shipment lines (RLS protected)."},
    )

    id: Mapped[UUID] = mapped_column(
        PG_UUID(as_uuid=True), primary_key=True, server_default=func.gen_random_uuid()
    )
    company_id: Mapped[UUID] = mapped_column(PG_UUID(as_uuid=True), nullable=False)
    shipment_id: Mapped[UUID] = mapped_column(PG_UUID(as_uuid=True), nullable=False)
    sales_order_item_id: Mapped[UUID] = mapped_column(PG_UUID(as_uuid=True), nullable=False)
    product_id: Mapped[UUID] = mapped_column(PG_UUID(as_uuid=True), nullable=False)
    quantity: Mapped[Decimal] = mapped_column(Numeric(18, 3), nullable=False)
    unit: Mapped[str] = mapped_column(String(16), nullable=False)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now()
    )

    def __repr__(self) -> str:  # pragma: no cover - debugging helper
        return f"<ShipmentItem shipment={self.shipment_id} item={self.sales_order_item_id}>"


class ShipmentEvent(Base):
    """Append-only milestone on a shipment timeline."""

    __tablename__ = "shipment_event"
    __table_args__ = (
        ForeignKeyConstraint(
            ["shipment_id", "company_id"],
            ["touche.shipment.id", "touche.shipment.company_id"],
            name="fk_shipment_event_shipment_company",
            ondelete="CASCADE",
        ),
        CheckConstraint(
            _in_list("event_type", _SHIPMENT_EVENT_TYPES), name="ck_shipment_event_type"
        ),
        CheckConstraint(
            "tracking_source IS NULL OR " + _in_list("tracking_source", _TRACKING_SOURCES),
            name="ck_shipment_event_tracking_source",
        ),
        CheckConstraint(
            "notes IS NULL OR char_length(notes) <= 2000", name="ck_shipment_event_notes"
        ),
        Index("ix_shipment_event_company_shipment", "company_id", "shipment_id", "occurred_at"),
        {"schema": "touche", "comment": "Immutable shipment milestones (RLS protected)."},
    )

    id: Mapped[UUID] = mapped_column(
        PG_UUID(as_uuid=True), primary_key=True, server_default=func.gen_random_uuid()
    )
    company_id: Mapped[UUID] = mapped_column(PG_UUID(as_uuid=True), nullable=False)
    shipment_id: Mapped[UUID] = mapped_column(PG_UUID(as_uuid=True), nullable=False)
    event_type: Mapped[str] = mapped_column(String(24), nullable=False)
    occurred_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    location: Mapped[str | None] = mapped_column(Text, nullable=True)
    notes: Mapped[str | None] = mapped_column(Text, nullable=True)
    evidence_reference: Mapped[str | None] = mapped_column(Text, nullable=True)
    tracking_source: Mapped[str | None] = mapped_column(String(24), nullable=True)
    recorded_by: Mapped[UUID] = mapped_column(
        PG_UUID(as_uuid=True),
        ForeignKey("touche.app_user.id", name="fk_shipment_event_recorded_by_app_user"),
        nullable=False,
    )
    recorded_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now()
    )

    def __repr__(self) -> str:  # pragma: no cover - debugging helper
        return f"<ShipmentEvent {self.event_type} shipment={self.shipment_id}>"


class ShipmentReference(Base):
    """Booking, container or bill-of-lading reference supplied by the carrier."""

    __tablename__ = "shipment_reference"
    __table_args__ = (
        ForeignKeyConstraint(
            ["shipment_id", "company_id"],
            ["touche.shipment.id", "touche.shipment.company_id"],
            name="fk_shipment_reference_shipment_company",
            ondelete="CASCADE",
        ),
        UniqueConstraint(
            "company_id",
            "reference_type",
            "reference_value",
            name="uq_shipment_reference_company_type_value",
        ),
        CheckConstraint(
            "reference_type IN ('BOOKING','CONTAINER','BILL_OF_LADING','AIR_WAYBILL',"
            "'CMR','TRACKING','OTHER')",
            name="ck_shipment_reference_type",
        ),
        CheckConstraint(
            "char_length(btrim(reference_value)) BETWEEN 2 AND 120",
            name="ck_shipment_reference_value",
        ),
        CheckConstraint(
            _in_list("provenance", _TRACKING_SOURCES), name="ck_shipment_reference_provenance"
        ),
        Index("ix_shipment_reference_company_shipment", "company_id", "shipment_id"),
        {"schema": "touche", "comment": "Tenant-scoped shipment references (RLS protected)."},
    )

    id: Mapped[UUID] = mapped_column(
        PG_UUID(as_uuid=True), primary_key=True, server_default=func.gen_random_uuid()
    )
    company_id: Mapped[UUID] = mapped_column(PG_UUID(as_uuid=True), nullable=False)
    shipment_id: Mapped[UUID] = mapped_column(PG_UUID(as_uuid=True), nullable=False)
    reference_type: Mapped[str] = mapped_column(String(24), nullable=False)
    reference_value: Mapped[str] = mapped_column(Text, nullable=False)
    provenance: Mapped[str] = mapped_column(String(24), nullable=False)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now()
    )

    def __repr__(self) -> str:  # pragma: no cover - debugging helper
        return f"<ShipmentReference {self.reference_type} {self.reference_value}>"


class ShipmentCost(Base):
    """Recorded logistics cost, with its certainty stage kept explicit."""

    __tablename__ = "shipment_cost"
    __table_args__ = (
        ForeignKeyConstraint(
            ["shipment_id", "company_id"],
            ["touche.shipment.id", "touche.shipment.company_id"],
            name="fk_shipment_cost_shipment_company",
            ondelete="CASCADE",
        ),
        CheckConstraint(
            "cost_type IN ('FREIGHT','INSURANCE','HANDLING','CUSTOMS_BROKERAGE',"
            "'DOMESTIC_TRANSPORT','OTHER')",
            name="ck_shipment_cost_type",
        ),
        CheckConstraint(_in_list("stage", _COST_STAGES), name="ck_shipment_cost_stage"),
        CheckConstraint("amount >= 0", name="ck_shipment_cost_amount"),
        CheckConstraint(
            "char_length(btrim(reference)) BETWEEN 2 AND 200", name="ck_shipment_cost_reference"
        ),
        Index("ix_shipment_cost_company_shipment", "company_id", "shipment_id"),
        {"schema": "touche", "comment": "Tenant-scoped shipment costs (RLS protected)."},
    )

    id: Mapped[UUID] = mapped_column(
        PG_UUID(as_uuid=True), primary_key=True, server_default=func.gen_random_uuid()
    )
    company_id: Mapped[UUID] = mapped_column(PG_UUID(as_uuid=True), nullable=False)
    shipment_id: Mapped[UUID] = mapped_column(PG_UUID(as_uuid=True), nullable=False)
    cost_type: Mapped[str] = mapped_column(String(24), nullable=False)
    stage: Mapped[str] = mapped_column(String(16), nullable=False)
    amount: Mapped[Decimal] = mapped_column(Numeric(18, 2), nullable=False)
    currency: Mapped[str] = mapped_column(String(3), nullable=False)
    reference: Mapped[str] = mapped_column(Text, nullable=False)
    notes: Mapped[str | None] = mapped_column(Text, nullable=True)
    recorded_by: Mapped[UUID] = mapped_column(
        PG_UUID(as_uuid=True),
        ForeignKey("touche.app_user.id", name="fk_shipment_cost_recorded_by_app_user"),
        nullable=False,
    )
    recorded_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now()
    )

    def __repr__(self) -> str:  # pragma: no cover - debugging helper
        return f"<ShipmentCost {self.stage} {self.amount} {self.currency}>"


class TradeDocument(Base):
    """Metadata for a file stored by the private local document adapter.

    ``storage_key`` is generated by the server; a client-supplied path is never
    trusted and never stored. ``sha256`` is recomputed on upload and verified on
    download, so a missing or corrupted file is detected rather than served.
    """

    __tablename__ = "trade_document"
    __table_args__ = (
        UniqueConstraint("id", "company_id", name="uq_trade_document_id_company_id"),
        UniqueConstraint("storage_key", name="uq_trade_document_storage_key"),
        ForeignKeyConstraint(
            ["supersedes_document_id", "company_id"],
            ["touche.trade_document.id", "touche.trade_document.company_id"],
            name="fk_trade_document_supersedes_company",
            ondelete="RESTRICT",
        ),
        CheckConstraint(
            _in_list("document_type", _DOCUMENT_TYPES), name="ck_trade_document_type"
        ),
        CheckConstraint(
            _in_list("linked_entity_type", _LINKED_ENTITY_TYPES),
            name="ck_trade_document_entity_type",
        ),
        CheckConstraint(_in_list("status", _DOCUMENT_STATUSES), name="ck_trade_document_status"),
        CheckConstraint(
            _in_list("verification_status", _VERIFICATION_STATUSES),
            name="ck_trade_document_verification",
        ),
        CheckConstraint("version >= 1", name="ck_trade_document_version"),
        CheckConstraint("size_bytes > 0", name="ck_trade_document_size"),
        CheckConstraint("sha256 ~ '^[0-9a-f]{64}$'", name="ck_trade_document_sha256"),
        CheckConstraint(
            "char_length(btrim(original_filename)) BETWEEN 1 AND 255",
            name="ck_trade_document_filename",
        ),
        Index(
            "ix_trade_document_company_entity",
            "company_id",
            "linked_entity_type",
            "linked_entity_id",
        ),
        Index("ix_trade_document_company_type", "company_id", "document_type"),
        Index("ix_trade_document_company_status", "company_id", "status"),
        {"schema": "touche", "comment": "Tenant-scoped document metadata (RLS protected)."},
    )

    id: Mapped[UUID] = mapped_column(
        PG_UUID(as_uuid=True), primary_key=True, server_default=func.gen_random_uuid()
    )
    company_id: Mapped[UUID] = mapped_column(PG_UUID(as_uuid=True), nullable=False)
    document_type: Mapped[str] = mapped_column(String(48), nullable=False)
    linked_entity_type: Mapped[str] = mapped_column(String(32), nullable=False)
    linked_entity_id: Mapped[UUID] = mapped_column(PG_UUID(as_uuid=True), nullable=False)
    title: Mapped[str] = mapped_column(Text, nullable=False)
    original_filename: Mapped[str] = mapped_column(Text, nullable=False)
    storage_key: Mapped[str] = mapped_column(Text, nullable=False)
    mime_type: Mapped[str] = mapped_column(String(160), nullable=False)
    size_bytes: Mapped[int] = mapped_column(BigInteger, nullable=False)
    sha256: Mapped[str] = mapped_column(String(64), nullable=False)
    version: Mapped[int] = mapped_column(Integer, nullable=False, server_default=text("1"))
    supersedes_document_id: Mapped[UUID | None] = mapped_column(
        PG_UUID(as_uuid=True), nullable=True
    )
    status: Mapped[str] = mapped_column(
        String(16), nullable=False, server_default=text("'ACTIVE'")
    )
    verification_status: Mapped[str] = mapped_column(
        String(16), nullable=False, server_default=text("'UNVERIFIED'")
    )
    is_draft: Mapped[bool] = mapped_column(
        Boolean, nullable=False, server_default=text("false")
    )
    archived_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    archived_by: Mapped[UUID | None] = mapped_column(
        PG_UUID(as_uuid=True),
        ForeignKey("touche.app_user.id", name="fk_trade_document_archived_by_app_user"),
        nullable=True,
    )
    uploaded_by: Mapped[UUID] = mapped_column(
        PG_UUID(as_uuid=True),
        ForeignKey("touche.app_user.id", name="fk_trade_document_uploaded_by_app_user"),
        nullable=False,
    )
    uploaded_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now()
    )

    def __repr__(self) -> str:  # pragma: no cover - debugging helper
        return f"<TradeDocument {self.document_type} {self.original_filename}>"


__all__ = [
    "AcceptanceChannel",
    "CostStage",
    "CustomerAcceptanceEvidence",
    "DocumentStatus",
    "DocumentVerificationStatus",
    "FulfilmentModel",
    "LinkedEntityType",
    "OrderAmendment",
    "PurchaseOrder",
    "PurchaseOrderItem",
    "PurchaseOrderStatus",
    "PurchaseOrderTransition",
    "SalesOrder",
    "SalesOrderItem",
    "SalesOrderStatus",
    "SalesOrderTransition",
    "Shipment",
    "ShipmentCost",
    "ShipmentEvent",
    "ShipmentEventType",
    "ShipmentItem",
    "ShipmentReference",
    "ShipmentStatus",
    "TrackingSource",
    "TradeDocument",
    "TradeDocumentType",
    "TransportMode",
]

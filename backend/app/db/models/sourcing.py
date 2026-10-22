"""Stage 3 sourcing storage: RFQs, supplier quotes, FX, pricing and sales quotes.

Design rules carried over from Stage 1B, and enforced by the database:

* every table carries ``company_id`` and is protected by row level security;
* every child row references its parent through a **composite** foreign key that
  includes ``company_id``, so a child can never be attached to another tenant's
  parent even if a bug supplied the wrong pair of ids;
* monetary values are ``Numeric`` and travel as ``Decimal`` end to end;
* mutable headers carry ``version`` for optimistic concurrency;
* every revision table is append-only (the runtime role gets no UPDATE/DELETE),
  which is what makes a superseded RFQ, quote or sales quote readable forever.

A supplier RFQ is issued to exactly one supplier. Selecting several suppliers in
the UI creates one RFQ per supplier in one transaction, so comparison happens
across the RFQs of a deal and every quote keeps a single, unambiguous supplier.
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
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.dialects.postgresql import UUID as PG_UUID
from sqlalchemy.orm import Mapped, mapped_column

from app.db.models.base import Base


class RfqStatus(StrEnum):
    """RFQ lifecycle. ``PREPARED`` is explicitly not ``SENT``."""

    DRAFT = "DRAFT"
    PREPARED = "PREPARED"
    SENT = "SENT"
    RESPONDED = "RESPONDED"
    CLOSED = "CLOSED"
    CANCELLED = "CANCELLED"


class SupplierQuoteStatus(StrEnum):
    RECEIVED = "RECEIVED"
    WITHDRAWN = "WITHDRAWN"


class Incoterm(StrEnum):
    """Incoterms 2020. Stored as data; never interpreted as a tax authority."""

    EXW = "EXW"
    FCA = "FCA"
    FAS = "FAS"
    FOB = "FOB"
    CFR = "CFR"
    CIF = "CIF"
    CPT = "CPT"
    CIP = "CIP"
    DAP = "DAP"
    DPU = "DPU"
    DDP = "DDP"


class CostType(StrEnum):
    PURCHASE = "PURCHASE"
    FREIGHT = "FREIGHT"
    DOMESTIC_TRANSPORT = "DOMESTIC_TRANSPORT"
    INSURANCE = "INSURANCE"
    CUSTOMS_DUTY = "CUSTOMS_DUTY"
    CUSTOMS_BROKERAGE = "CUSTOMS_BROKERAGE"
    QUALITY_INSPECTION = "QUALITY_INSPECTION"
    BANKING_FINANCE = "BANKING_FINANCE"
    OTHER = "OTHER"
    CONTINGENCY = "CONTINGENCY"
    VAT_CASHFLOW = "VAT_CASHFLOW"


class CostBasis(StrEnum):
    """How a cost component is allocated to product lines."""

    ORDER = "ORDER"
    LINE = "LINE"


class VerificationStatus(StrEnum):
    ESTIMATED = "ESTIMATED"
    VERIFIED = "VERIFIED"


class ScenarioStatus(StrEnum):
    INCOMPLETE = "INCOMPLETE"
    ESTIMATED = "ESTIMATED"
    VERIFIED_INPUTS = "VERIFIED_INPUTS"


class SalesQuoteStatus(StrEnum):
    DRAFT = "DRAFT"
    PENDING_APPROVAL = "PENDING_APPROVAL"
    APPROVED = "APPROVED"
    REJECTED = "REJECTED"
    WITHDRAWN = "WITHDRAWN"


def _in_list(column: str, values: tuple[str, ...]) -> str:
    rendered = ", ".join(f"'{value}'" for value in values)
    return f"{column} IN ({rendered})"


_RFQ_STATUSES = tuple(status.value for status in RfqStatus)
_QUOTE_STATUSES = tuple(status.value for status in SupplierQuoteStatus)
_INCOTERMS = tuple(term.value for term in Incoterm)
_COST_TYPES = tuple(kind.value for kind in CostType)
_COST_BASES = tuple(basis.value for basis in CostBasis)
_VERIFICATION_STATUSES = tuple(status.value for status in VerificationStatus)
_SCENARIO_STATUSES = tuple(status.value for status in ScenarioStatus)
_SALES_QUOTE_STATUSES = tuple(status.value for status in SalesQuoteStatus)
_UNITS = ("kg", "mt", "lb", "unit", "l", "m3")
_CURRENCY_CHECK = "~ '^[A-Z]{3}$'"


class FxRateSnapshot(Base):
    """An explicit, sourced FX observation. The engine never invents a rate."""

    __tablename__ = "fx_rate_snapshot"
    __table_args__ = (
        UniqueConstraint(
            "company_id",
            "base_currency",
            "quote_currency",
            "effective_at",
            name="uq_fx_rate_snapshot_company_pair_effective",
        ),
        UniqueConstraint("id", "company_id", name="uq_fx_rate_snapshot_id_company_id"),
        CheckConstraint(f"base_currency {_CURRENCY_CHECK}", name="ck_fx_rate_base_currency"),
        CheckConstraint(f"quote_currency {_CURRENCY_CHECK}", name="ck_fx_rate_quote_currency"),
        CheckConstraint("base_currency <> quote_currency", name="ck_fx_rate_distinct_currency"),
        CheckConstraint("rate > 0", name="ck_fx_rate_positive"),
        CheckConstraint(
            "char_length(btrim(source)) BETWEEN 3 AND 160", name="ck_fx_rate_source_length"
        ),
        Index("ix_fx_rate_snapshot_company_pair", "company_id", "base_currency", "quote_currency"),
        {"schema": "touche", "comment": "Sourced FX observations (RLS protected)."},
    )

    id: Mapped[UUID] = mapped_column(
        PG_UUID(as_uuid=True), primary_key=True, server_default=func.gen_random_uuid()
    )
    company_id: Mapped[UUID] = mapped_column(
        PG_UUID(as_uuid=True),
        ForeignKey(
            "touche.company.id", name="fk_fx_rate_snapshot_company_id_company", ondelete="CASCADE"
        ),
        nullable=False,
    )
    base_currency: Mapped[str] = mapped_column(String(3), nullable=False)
    quote_currency: Mapped[str] = mapped_column(String(3), nullable=False)
    rate: Mapped[Decimal] = mapped_column(Numeric(20, 10), nullable=False)
    effective_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    source: Mapped[str] = mapped_column(Text, nullable=False)
    recorded_by: Mapped[UUID] = mapped_column(
        PG_UUID(as_uuid=True),
        ForeignKey("touche.app_user.id", name="fk_fx_rate_snapshot_recorded_by_app_user"),
        nullable=False,
    )
    recorded_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now()
    )

    def __repr__(self) -> str:  # pragma: no cover - debugging helper
        return f"<FxRateSnapshot {self.base_currency}/{self.quote_currency} {self.rate}>"


class SupplierRfq(Base):
    """A request for quotation issued to one supplier for one deal."""

    __tablename__ = "supplier_rfq"
    __table_args__ = (
        UniqueConstraint(
            "company_id", "reference_number", name="uq_supplier_rfq_company_reference"
        ),
        UniqueConstraint("id", "company_id", name="uq_supplier_rfq_id_company_id"),
        ForeignKeyConstraint(
            ["deal_id", "company_id"],
            ["touche.deal.id", "touche.deal.company_id"],
            name="fk_supplier_rfq_deal_company",
            ondelete="CASCADE",
        ),
        ForeignKeyConstraint(
            ["supplier_counterparty_id", "company_id"],
            ["touche.counterparty.id", "touche.counterparty.company_id"],
            name="fk_supplier_rfq_supplier_company",
            ondelete="RESTRICT",
        ),
        CheckConstraint(
            "reference_number = upper(reference_number)", name="ck_supplier_rfq_ref_upper"
        ),
        CheckConstraint(
            "char_length(reference_number) BETWEEN 3 AND 40", name="ck_supplier_rfq_ref_length"
        ),
        CheckConstraint(
            f"requested_currency {_CURRENCY_CHECK}", name="ck_supplier_rfq_currency_iso"
        ),
        CheckConstraint(_in_list("status", _RFQ_STATUSES), name="ck_supplier_rfq_status"),
        CheckConstraint(
            "char_length(btrim(delivery_location)) BETWEEN 2 AND 160",
            name="ck_supplier_rfq_delivery_location",
        ),
        CheckConstraint(
            "requested_delivery_terms IS NULL OR "
            "char_length(requested_delivery_terms) BETWEEN 3 AND 40",
            name="ck_supplier_rfq_delivery_terms",
        ),
        CheckConstraint("revision >= 1", name="ck_supplier_rfq_revision"),
        CheckConstraint("version >= 1", name="ck_supplier_rfq_version"),
        CheckConstraint(
            "status NOT IN ('SENT', 'RESPONDED') OR sent_at IS NOT NULL",
            name="ck_supplier_rfq_sent_evidence",
        ),
        Index("ix_supplier_rfq_company_deal", "company_id", "deal_id", "created_at"),
        Index("ix_supplier_rfq_company_status", "company_id", "status"),
        Index("ix_supplier_rfq_company_supplier", "company_id", "supplier_counterparty_id"),
        {"schema": "touche", "comment": "Tenant-scoped supplier RFQs (RLS protected)."},
    )

    id: Mapped[UUID] = mapped_column(
        PG_UUID(as_uuid=True), primary_key=True, server_default=func.gen_random_uuid()
    )
    company_id: Mapped[UUID] = mapped_column(PG_UUID(as_uuid=True), nullable=False)
    deal_id: Mapped[UUID] = mapped_column(PG_UUID(as_uuid=True), nullable=False)
    supplier_counterparty_id: Mapped[UUID] = mapped_column(PG_UUID(as_uuid=True), nullable=False)
    reference_number: Mapped[str] = mapped_column(String(40), nullable=False)
    requested_currency: Mapped[str] = mapped_column(String(3), nullable=False)
    requested_delivery_terms: Mapped[str | None] = mapped_column(String(40), nullable=True)
    delivery_location: Mapped[str] = mapped_column(Text, nullable=False)
    response_due_date: Mapped[date | None] = mapped_column(Date, nullable=True)
    notes: Mapped[str | None] = mapped_column(Text, nullable=True)
    status: Mapped[str] = mapped_column(String(16), nullable=False, server_default=text("'DRAFT'"))
    revision: Mapped[int] = mapped_column(Integer, nullable=False, server_default=text("1"))
    version: Mapped[int] = mapped_column(Integer, nullable=False, server_default=text("1"))
    sent_channel: Mapped[str | None] = mapped_column(String(40), nullable=True)
    sent_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    sent_evidence: Mapped[str | None] = mapped_column(Text, nullable=True)
    created_by: Mapped[UUID] = mapped_column(
        PG_UUID(as_uuid=True),
        ForeignKey("touche.app_user.id", name="fk_supplier_rfq_created_by_app_user"),
        nullable=False,
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now()
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now(), onupdate=func.now()
    )

    def __repr__(self) -> str:  # pragma: no cover - debugging helper
        return f"<SupplierRfq {self.reference_number} {self.status}>"


class SupplierRfqItem(Base):
    """One requested product line, with its specifications snapshot."""

    __tablename__ = "supplier_rfq_item"
    __table_args__ = (
        ForeignKeyConstraint(
            ["rfq_id", "company_id"],
            ["touche.supplier_rfq.id", "touche.supplier_rfq.company_id"],
            name="fk_supplier_rfq_item_rfq_company",
            ondelete="CASCADE",
        ),
        ForeignKeyConstraint(
            ["product_id", "company_id"],
            ["touche.product.id", "touche.product.company_id"],
            name="fk_supplier_rfq_item_product_company",
            ondelete="RESTRICT",
        ),
        UniqueConstraint("rfq_id", "product_id", name="uq_supplier_rfq_item_rfq_id_product_id"),
        CheckConstraint("quantity > 0", name="ck_supplier_rfq_item_quantity"),
        CheckConstraint(_in_list("unit", _UNITS), name="ck_supplier_rfq_item_unit"),
        CheckConstraint(
            "char_length(btrim(description)) BETWEEN 1 AND 500",
            name="ck_supplier_rfq_item_description",
        ),
        Index("ix_supplier_rfq_item_company_rfq", "company_id", "rfq_id"),
        {"schema": "touche", "comment": "Tenant-scoped RFQ lines (RLS protected)."},
    )

    id: Mapped[UUID] = mapped_column(
        PG_UUID(as_uuid=True), primary_key=True, server_default=func.gen_random_uuid()
    )
    company_id: Mapped[UUID] = mapped_column(PG_UUID(as_uuid=True), nullable=False)
    rfq_id: Mapped[UUID] = mapped_column(PG_UUID(as_uuid=True), nullable=False)
    product_id: Mapped[UUID] = mapped_column(PG_UUID(as_uuid=True), nullable=False)
    description: Mapped[str] = mapped_column(Text, nullable=False)
    quantity: Mapped[Decimal] = mapped_column(Numeric(18, 3), nullable=False)
    unit: Mapped[str] = mapped_column(String(16), nullable=False)
    notes: Mapped[str | None] = mapped_column(Text, nullable=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now()
    )

    def __repr__(self) -> str:  # pragma: no cover - debugging helper
        return f"<SupplierRfqItem rfq={self.rfq_id} product={self.product_id}>"


class SupplierRfqRevision(Base):
    """Immutable snapshot of an RFQ at a prepared/revised point."""

    __tablename__ = "supplier_rfq_revision"
    __table_args__ = (
        ForeignKeyConstraint(
            ["rfq_id", "company_id"],
            ["touche.supplier_rfq.id", "touche.supplier_rfq.company_id"],
            name="fk_supplier_rfq_revision_rfq_company",
            ondelete="CASCADE",
        ),
        UniqueConstraint("rfq_id", "revision", name="uq_supplier_rfq_revision_rfq_revision"),
        CheckConstraint("revision >= 1", name="ck_supplier_rfq_revision_no"),
        CheckConstraint(
            "jsonb_typeof(snapshot) = 'object'", name="ck_supplier_rfq_revision_snapshot"
        ),
        Index("ix_supplier_rfq_revision_company_rfq", "company_id", "rfq_id"),
        {"schema": "touche", "comment": "Append-only RFQ revision history (RLS protected)."},
    )

    id: Mapped[UUID] = mapped_column(
        PG_UUID(as_uuid=True), primary_key=True, server_default=func.gen_random_uuid()
    )
    company_id: Mapped[UUID] = mapped_column(PG_UUID(as_uuid=True), nullable=False)
    rfq_id: Mapped[UUID] = mapped_column(PG_UUID(as_uuid=True), nullable=False)
    revision: Mapped[int] = mapped_column(Integer, nullable=False)
    snapshot: Mapped[dict[str, object]] = mapped_column(JSONB, nullable=False)
    reason: Mapped[str | None] = mapped_column(Text, nullable=True)
    actor_id: Mapped[UUID] = mapped_column(
        PG_UUID(as_uuid=True),
        ForeignKey("touche.app_user.id", name="fk_supplier_rfq_revision_actor_app_user"),
        nullable=False,
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now()
    )

    def __repr__(self) -> str:  # pragma: no cover - debugging helper
        return f"<SupplierRfqRevision rfq={self.rfq_id} r{self.revision}>"


class SupplierQuote(Base):
    """A supplier's response to one RFQ, with immutable revisions."""

    __tablename__ = "supplier_quote"
    __table_args__ = (
        UniqueConstraint("id", "company_id", name="uq_supplier_quote_id_company_id"),
        UniqueConstraint("supersedes_quote_id", name="uq_supplier_quote_supersedes"),
        ForeignKeyConstraint(
            ["rfq_id", "company_id"],
            ["touche.supplier_rfq.id", "touche.supplier_rfq.company_id"],
            name="fk_supplier_quote_rfq_company",
            ondelete="CASCADE",
        ),
        ForeignKeyConstraint(
            ["supplier_counterparty_id", "company_id"],
            ["touche.counterparty.id", "touche.counterparty.company_id"],
            name="fk_supplier_quote_supplier_company",
            ondelete="RESTRICT",
        ),
        ForeignKeyConstraint(
            ["supersedes_quote_id", "company_id"],
            ["touche.supplier_quote.id", "touche.supplier_quote.company_id"],
            name="fk_supplier_quote_supersedes_company",
            ondelete="RESTRICT",
        ),
        CheckConstraint(f"currency {_CURRENCY_CHECK}", name="ck_supplier_quote_currency_iso"),
        CheckConstraint(_in_list("incoterm", _INCOTERMS), name="ck_supplier_quote_incoterm"),
        CheckConstraint(_in_list("status", _QUOTE_STATUSES), name="ck_supplier_quote_status"),
        CheckConstraint(
            "char_length(btrim(named_delivery_place)) BETWEEN 2 AND 160",
            name="ck_supplier_quote_place",
        ),
        CheckConstraint(
            "char_length(btrim(payment_terms)) BETWEEN 2 AND 200",
            name="ck_supplier_quote_payment_terms",
        ),
        CheckConstraint(
            "char_length(btrim(source_reference)) BETWEEN 3 AND 200",
            name="ck_supplier_quote_source_reference",
        ),
        CheckConstraint("lead_time_days >= 0", name="ck_supplier_quote_lead_time"),
        CheckConstraint("revision >= 1", name="ck_supplier_quote_revision"),
        CheckConstraint("version >= 1", name="ck_supplier_quote_version"),
        Index("ix_supplier_quote_company_rfq", "company_id", "rfq_id", "revision"),
        Index("ix_supplier_quote_company_supplier", "company_id", "supplier_counterparty_id"),
        Index("ix_supplier_quote_company_valid_until", "company_id", "valid_until"),
        {"schema": "touche", "comment": "Tenant-scoped supplier quotes (RLS protected)."},
    )

    id: Mapped[UUID] = mapped_column(
        PG_UUID(as_uuid=True), primary_key=True, server_default=func.gen_random_uuid()
    )
    company_id: Mapped[UUID] = mapped_column(PG_UUID(as_uuid=True), nullable=False)
    rfq_id: Mapped[UUID] = mapped_column(PG_UUID(as_uuid=True), nullable=False)
    supplier_counterparty_id: Mapped[UUID] = mapped_column(PG_UUID(as_uuid=True), nullable=False)
    supplier_reference: Mapped[str | None] = mapped_column(String(80), nullable=True)
    currency: Mapped[str] = mapped_column(String(3), nullable=False)
    incoterm: Mapped[str] = mapped_column(String(3), nullable=False)
    named_delivery_place: Mapped[str] = mapped_column(Text, nullable=False)
    payment_terms: Mapped[str] = mapped_column(Text, nullable=False)
    shipping_conditions: Mapped[str | None] = mapped_column(Text, nullable=True)
    lead_time_days: Mapped[int] = mapped_column(Integer, nullable=False)
    valid_until: Mapped[date] = mapped_column(Date, nullable=False)
    status: Mapped[str] = mapped_column(
        String(16), nullable=False, server_default=text("'RECEIVED'")
    )
    revision: Mapped[int] = mapped_column(Integer, nullable=False, server_default=text("1"))
    source_reference: Mapped[str] = mapped_column(Text, nullable=False)
    notes: Mapped[str | None] = mapped_column(Text, nullable=True)
    received_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    supersedes_quote_id: Mapped[UUID | None] = mapped_column(PG_UUID(as_uuid=True), nullable=True)
    version: Mapped[int] = mapped_column(Integer, nullable=False, server_default=text("1"))
    created_by: Mapped[UUID] = mapped_column(
        PG_UUID(as_uuid=True),
        ForeignKey("touche.app_user.id", name="fk_supplier_quote_created_by_app_user"),
        nullable=False,
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now()
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now(), onupdate=func.now()
    )

    def __repr__(self) -> str:  # pragma: no cover - debugging helper
        return f"<SupplierQuote {self.id} r{self.revision} {self.status}>"


class SupplierQuoteItem(Base):
    """One priced line of a supplier quote."""

    __tablename__ = "supplier_quote_item"
    __table_args__ = (
        ForeignKeyConstraint(
            ["quote_id", "company_id"],
            ["touche.supplier_quote.id", "touche.supplier_quote.company_id"],
            name="fk_supplier_quote_item_quote_company",
            ondelete="CASCADE",
        ),
        ForeignKeyConstraint(
            ["product_id", "company_id"],
            ["touche.product.id", "touche.product.company_id"],
            name="fk_supplier_quote_item_product_company",
            ondelete="RESTRICT",
        ),
        UniqueConstraint("quote_id", "product_id", name="uq_supplier_quote_item_quote_product"),
        CheckConstraint("quantity > 0", name="ck_supplier_quote_item_quantity"),
        CheckConstraint("unit_price >= 0", name="ck_supplier_quote_item_unit_price"),
        CheckConstraint("moq IS NULL OR moq > 0", name="ck_supplier_quote_item_moq"),
        CheckConstraint(_in_list("unit", _UNITS), name="ck_supplier_quote_item_unit"),
        Index("ix_supplier_quote_item_company_quote", "company_id", "quote_id"),
        {"schema": "touche", "comment": "Tenant-scoped supplier quote lines (RLS protected)."},
    )

    id: Mapped[UUID] = mapped_column(
        PG_UUID(as_uuid=True), primary_key=True, server_default=func.gen_random_uuid()
    )
    company_id: Mapped[UUID] = mapped_column(PG_UUID(as_uuid=True), nullable=False)
    quote_id: Mapped[UUID] = mapped_column(PG_UUID(as_uuid=True), nullable=False)
    product_id: Mapped[UUID] = mapped_column(PG_UUID(as_uuid=True), nullable=False)
    description: Mapped[str] = mapped_column(Text, nullable=False)
    quantity: Mapped[Decimal] = mapped_column(Numeric(18, 3), nullable=False)
    unit: Mapped[str] = mapped_column(String(16), nullable=False)
    unit_price: Mapped[Decimal] = mapped_column(Numeric(18, 4), nullable=False)
    moq: Mapped[Decimal | None] = mapped_column(Numeric(18, 3), nullable=True)
    line_notes: Mapped[str | None] = mapped_column(Text, nullable=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now()
    )

    def __repr__(self) -> str:  # pragma: no cover - debugging helper
        return f"<SupplierQuoteItem quote={self.quote_id} product={self.product_id}>"


class SupplierQuoteRevision(Base):
    """Immutable snapshot of a supplier quote revision."""

    __tablename__ = "supplier_quote_revision"
    __table_args__ = (
        ForeignKeyConstraint(
            ["quote_id", "company_id"],
            ["touche.supplier_quote.id", "touche.supplier_quote.company_id"],
            name="fk_supplier_quote_revision_quote_company",
            ondelete="CASCADE",
        ),
        UniqueConstraint("quote_id", "revision", name="uq_supplier_quote_revision_quote_revision"),
        CheckConstraint("revision >= 1", name="ck_supplier_quote_revision_no"),
        CheckConstraint(
            "jsonb_typeof(snapshot) = 'object'", name="ck_supplier_quote_revision_snapshot"
        ),
        Index("ix_supplier_quote_revision_company_quote", "company_id", "quote_id"),
        {"schema": "touche", "comment": "Append-only supplier quote revisions (RLS protected)."},
    )

    id: Mapped[UUID] = mapped_column(
        PG_UUID(as_uuid=True), primary_key=True, server_default=func.gen_random_uuid()
    )
    company_id: Mapped[UUID] = mapped_column(PG_UUID(as_uuid=True), nullable=False)
    quote_id: Mapped[UUID] = mapped_column(PG_UUID(as_uuid=True), nullable=False)
    revision: Mapped[int] = mapped_column(Integer, nullable=False)
    snapshot: Mapped[dict[str, object]] = mapped_column(JSONB, nullable=False)
    reason: Mapped[str | None] = mapped_column(Text, nullable=True)
    actor_id: Mapped[UUID] = mapped_column(
        PG_UUID(as_uuid=True),
        ForeignKey("touche.app_user.id", name="fk_supplier_quote_revision_actor_app_user"),
        nullable=False,
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now()
    )

    def __repr__(self) -> str:  # pragma: no cover - debugging helper
        return f"<SupplierQuoteRevision quote={self.quote_id} r{self.revision}>"


class PricingScenario(Base):
    """A deterministic landed-cost calculation for one supplier quote."""

    __tablename__ = "pricing_scenario"
    __table_args__ = (
        UniqueConstraint("id", "company_id", name="uq_pricing_scenario_id_company_id"),
        ForeignKeyConstraint(
            ["deal_id", "company_id"],
            ["touche.deal.id", "touche.deal.company_id"],
            name="fk_pricing_scenario_deal_company",
            ondelete="CASCADE",
        ),
        ForeignKeyConstraint(
            ["supplier_quote_id", "company_id"],
            ["touche.supplier_quote.id", "touche.supplier_quote.company_id"],
            name="fk_pricing_scenario_quote_company",
            ondelete="RESTRICT",
        ),
        CheckConstraint(
            f"target_currency {_CURRENCY_CHECK}", name="ck_pricing_scenario_currency_iso"
        ),
        CheckConstraint(_in_list("status", _SCENARIO_STATUSES), name="ck_pricing_scenario_status"),
        CheckConstraint(
            "char_length(btrim(calculation_version)) BETWEEN 3 AND 40",
            name="ck_pricing_scenario_calculation_version",
        ),
        CheckConstraint("version >= 1", name="ck_pricing_scenario_version"),
        CheckConstraint(
            "jsonb_typeof(pricing_inputs) = 'object'", name="ck_pricing_scenario_inputs_object"
        ),
        CheckConstraint(
            "jsonb_typeof(calculated_results) = 'object'",
            name="ck_pricing_scenario_results_object",
        ),
        Index("ix_pricing_scenario_company_deal", "company_id", "deal_id", "created_at"),
        Index("ix_pricing_scenario_company_quote", "company_id", "supplier_quote_id"),
        Index("ix_pricing_scenario_company_status", "company_id", "status"),
        {"schema": "touche", "comment": "Tenant-scoped landed-cost scenarios (RLS protected)."},
    )

    id: Mapped[UUID] = mapped_column(
        PG_UUID(as_uuid=True), primary_key=True, server_default=func.gen_random_uuid()
    )
    company_id: Mapped[UUID] = mapped_column(PG_UUID(as_uuid=True), nullable=False)
    deal_id: Mapped[UUID] = mapped_column(PG_UUID(as_uuid=True), nullable=False)
    supplier_quote_id: Mapped[UUID] = mapped_column(PG_UUID(as_uuid=True), nullable=False)
    target_currency: Mapped[str] = mapped_column(String(3), nullable=False)
    sales_incoterm: Mapped[str | None] = mapped_column(String(3), nullable=True)
    sales_named_place: Mapped[str | None] = mapped_column(Text, nullable=True)
    pricing_inputs: Mapped[dict[str, object]] = mapped_column(JSONB, nullable=False)
    calculated_results: Mapped[dict[str, object]] = mapped_column(JSONB, nullable=False)
    calculation_version: Mapped[str] = mapped_column(String(40), nullable=False)
    status: Mapped[str] = mapped_column(
        String(24), nullable=False, server_default=text("'INCOMPLETE'")
    )
    completeness: Mapped[dict[str, object]] = mapped_column(
        JSONB, nullable=False, server_default=text("'{}'::jsonb")
    )
    created_by: Mapped[UUID] = mapped_column(
        PG_UUID(as_uuid=True),
        ForeignKey("touche.app_user.id", name="fk_pricing_scenario_created_by_app_user"),
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
        return f"<PricingScenario {self.id} {self.status}>"


class PricingCostComponent(Base):
    """One sourced cost line of a pricing scenario."""

    __tablename__ = "pricing_cost_component"
    __table_args__ = (
        ForeignKeyConstraint(
            ["scenario_id", "company_id"],
            ["touche.pricing_scenario.id", "touche.pricing_scenario.company_id"],
            name="fk_pricing_cost_component_scenario_company",
            ondelete="CASCADE",
        ),
        ForeignKeyConstraint(
            ["fx_rate_snapshot_id", "company_id"],
            ["touche.fx_rate_snapshot.id", "touche.fx_rate_snapshot.company_id"],
            name="fk_pricing_cost_component_fx_company",
            ondelete="RESTRICT",
        ),
        ForeignKeyConstraint(
            ["product_id", "company_id"],
            ["touche.product.id", "touche.product.company_id"],
            name="fk_pricing_cost_component_product_company",
            ondelete="RESTRICT",
        ),
        CheckConstraint(_in_list("cost_type", _COST_TYPES), name="ck_pricing_cost_component_type"),
        CheckConstraint(_in_list("basis", _COST_BASES), name="ck_pricing_cost_component_basis"),
        CheckConstraint(
            _in_list("verification_status", _VERIFICATION_STATUSES),
            name="ck_pricing_cost_component_verification",
        ),
        CheckConstraint("amount >= 0", name="ck_pricing_cost_component_amount"),
        CheckConstraint(
            "(basis = 'LINE') = (product_id IS NOT NULL)",
            name="ck_pricing_cost_component_line_product",
        ),
        CheckConstraint(
            f"currency {_CURRENCY_CHECK}", name="ck_pricing_cost_component_currency_iso"
        ),
        CheckConstraint(
            "char_length(btrim(source_reference)) BETWEEN 3 AND 200",
            name="ck_pricing_cost_component_source",
        ),
        Index("ix_pricing_cost_component_company_scenario", "company_id", "scenario_id"),
        {"schema": "touche", "comment": "Tenant-scoped cost components (RLS protected)."},
    )

    id: Mapped[UUID] = mapped_column(
        PG_UUID(as_uuid=True), primary_key=True, server_default=func.gen_random_uuid()
    )
    company_id: Mapped[UUID] = mapped_column(PG_UUID(as_uuid=True), nullable=False)
    scenario_id: Mapped[UUID] = mapped_column(PG_UUID(as_uuid=True), nullable=False)
    cost_type: Mapped[str] = mapped_column(String(32), nullable=False)
    amount: Mapped[Decimal] = mapped_column(Numeric(18, 2), nullable=False)
    currency: Mapped[str] = mapped_column(String(3), nullable=False)
    basis: Mapped[str] = mapped_column(String(8), nullable=False, server_default=text("'ORDER'"))
    source_reference: Mapped[str] = mapped_column(Text, nullable=False)
    verification_status: Mapped[str] = mapped_column(String(16), nullable=False)
    fx_rate_snapshot_id: Mapped[UUID | None] = mapped_column(PG_UUID(as_uuid=True), nullable=True)
    product_id: Mapped[UUID | None] = mapped_column(PG_UUID(as_uuid=True), nullable=True)
    notes: Mapped[str | None] = mapped_column(Text, nullable=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now()
    )

    def __repr__(self) -> str:  # pragma: no cover - debugging helper
        return f"<PricingCostComponent {self.cost_type} {self.amount} {self.currency}>"


class SalesQuote(Base):
    """A customer-facing sales quotation derived from one pricing scenario."""

    __tablename__ = "sales_quote"
    __table_args__ = (
        UniqueConstraint("id", "company_id", name="uq_sales_quote_id_company_id"),
        UniqueConstraint(
            "company_id", "quote_number", "revision", name="uq_sales_quote_company_number_revision"
        ),
        UniqueConstraint("supersedes_sales_quote_id", name="uq_sales_quote_supersedes"),
        ForeignKeyConstraint(
            ["deal_id", "company_id"],
            ["touche.deal.id", "touche.deal.company_id"],
            name="fk_sales_quote_deal_company",
            ondelete="CASCADE",
        ),
        ForeignKeyConstraint(
            ["scenario_id", "company_id"],
            ["touche.pricing_scenario.id", "touche.pricing_scenario.company_id"],
            name="fk_sales_quote_scenario_company",
            ondelete="RESTRICT",
        ),
        ForeignKeyConstraint(
            ["customer_id", "company_id"],
            ["touche.counterparty.id", "touche.counterparty.company_id"],
            name="fk_sales_quote_customer_company",
            ondelete="RESTRICT",
        ),
        ForeignKeyConstraint(
            ["supersedes_sales_quote_id", "company_id"],
            ["touche.sales_quote.id", "touche.sales_quote.company_id"],
            name="fk_sales_quote_supersedes_company",
            ondelete="RESTRICT",
        ),
        CheckConstraint(f"currency {_CURRENCY_CHECK}", name="ck_sales_quote_currency_iso"),
        CheckConstraint(_in_list("status", _SALES_QUOTE_STATUSES), name="ck_sales_quote_status"),
        CheckConstraint(
            "char_length(btrim(quote_number)) BETWEEN 3 AND 40", name="ck_sales_quote_number"
        ),
        CheckConstraint(
            "char_length(btrim(named_delivery_place)) BETWEEN 2 AND 160",
            name="ck_sales_quote_place",
        ),
        CheckConstraint(
            "char_length(btrim(payment_terms)) BETWEEN 2 AND 200",
            name="ck_sales_quote_payment_terms",
        ),
        CheckConstraint("revision >= 1", name="ck_sales_quote_revision"),
        CheckConstraint("version >= 1", name="ck_sales_quote_version"),
        CheckConstraint(
            "(status = 'APPROVED') = (approved_by IS NOT NULL AND approved_at IS NOT NULL)",
            name="ck_sales_quote_approval_pair",
        ),
        CheckConstraint(
            "status <> 'REJECTED' OR rejection_reason IS NOT NULL",
            name="ck_sales_quote_rejection_reason",
        ),
        Index("ix_sales_quote_company_deal", "company_id", "deal_id", "created_at"),
        Index("ix_sales_quote_company_status", "company_id", "status"),
        Index("ix_sales_quote_company_number", "company_id", "quote_number"),
        {"schema": "touche", "comment": "Tenant-scoped sales quotes (RLS protected)."},
    )

    id: Mapped[UUID] = mapped_column(
        PG_UUID(as_uuid=True), primary_key=True, server_default=func.gen_random_uuid()
    )
    company_id: Mapped[UUID] = mapped_column(PG_UUID(as_uuid=True), nullable=False)
    deal_id: Mapped[UUID] = mapped_column(PG_UUID(as_uuid=True), nullable=False)
    quote_number: Mapped[str] = mapped_column(String(40), nullable=False)
    revision: Mapped[int] = mapped_column(Integer, nullable=False, server_default=text("1"))
    scenario_id: Mapped[UUID] = mapped_column(PG_UUID(as_uuid=True), nullable=False)
    customer_id: Mapped[UUID] = mapped_column(PG_UUID(as_uuid=True), nullable=False)
    currency: Mapped[str] = mapped_column(String(3), nullable=False)
    valid_until: Mapped[date] = mapped_column(Date, nullable=False)
    incoterm: Mapped[str] = mapped_column(String(3), nullable=False)
    named_delivery_place: Mapped[str] = mapped_column(Text, nullable=False)
    payment_terms: Mapped[str] = mapped_column(Text, nullable=False)
    status: Mapped[str] = mapped_column(String(24), nullable=False, server_default=text("'DRAFT'"))
    notes: Mapped[str | None] = mapped_column(Text, nullable=True)
    approved_by: Mapped[UUID | None] = mapped_column(
        PG_UUID(as_uuid=True),
        ForeignKey("touche.app_user.id", name="fk_sales_quote_approved_by_app_user"),
        nullable=True,
    )
    approved_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    rejection_reason: Mapped[str | None] = mapped_column(Text, nullable=True)
    submitted_by: Mapped[UUID | None] = mapped_column(
        PG_UUID(as_uuid=True),
        ForeignKey("touche.app_user.id", name="fk_sales_quote_submitted_by_app_user"),
        nullable=True,
    )
    submitted_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    supersedes_sales_quote_id: Mapped[UUID | None] = mapped_column(
        PG_UUID(as_uuid=True), nullable=True
    )
    created_by: Mapped[UUID] = mapped_column(
        PG_UUID(as_uuid=True),
        ForeignKey("touche.app_user.id", name="fk_sales_quote_created_by_app_user"),
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
        return f"<SalesQuote {self.quote_number} r{self.revision} {self.status}>"


class SalesQuoteItem(Base):
    """One immutable customer-facing quotation line."""

    __tablename__ = "sales_quote_item"
    __table_args__ = (
        ForeignKeyConstraint(
            ["sales_quote_id", "company_id"],
            ["touche.sales_quote.id", "touche.sales_quote.company_id"],
            name="fk_sales_quote_item_quote_company",
            ondelete="CASCADE",
        ),
        ForeignKeyConstraint(
            ["product_id", "company_id"],
            ["touche.product.id", "touche.product.company_id"],
            name="fk_sales_quote_item_product_company",
            ondelete="RESTRICT",
        ),
        UniqueConstraint(
            "sales_quote_id", "product_id", name="uq_sales_quote_item_quote_id_product_id"
        ),
        CheckConstraint("quantity > 0", name="ck_sales_quote_item_quantity"),
        CheckConstraint("unit_price >= 0", name="ck_sales_quote_item_unit_price"),
        CheckConstraint("line_total >= 0", name="ck_sales_quote_item_line_total"),
        CheckConstraint(_in_list("unit", _UNITS), name="ck_sales_quote_item_unit"),
        Index("ix_sales_quote_item_company_quote", "company_id", "sales_quote_id"),
        {"schema": "touche", "comment": "Tenant-scoped sales quote lines (RLS protected)."},
    )

    id: Mapped[UUID] = mapped_column(
        PG_UUID(as_uuid=True), primary_key=True, server_default=func.gen_random_uuid()
    )
    company_id: Mapped[UUID] = mapped_column(PG_UUID(as_uuid=True), nullable=False)
    sales_quote_id: Mapped[UUID] = mapped_column(PG_UUID(as_uuid=True), nullable=False)
    product_id: Mapped[UUID] = mapped_column(PG_UUID(as_uuid=True), nullable=False)
    description: Mapped[str] = mapped_column(Text, nullable=False)
    quantity: Mapped[Decimal] = mapped_column(Numeric(18, 3), nullable=False)
    unit: Mapped[str] = mapped_column(String(16), nullable=False)
    unit_price: Mapped[Decimal] = mapped_column(Numeric(18, 4), nullable=False)
    line_total: Mapped[Decimal] = mapped_column(Numeric(18, 2), nullable=False)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now()
    )

    def __repr__(self) -> str:  # pragma: no cover - debugging helper
        return f"<SalesQuoteItem quote={self.sales_quote_id} product={self.product_id}>"


class SalesQuoteRevision(Base):
    """Immutable snapshot of a sales quote revision (never a confirmed sale)."""

    __tablename__ = "sales_quote_revision"
    __table_args__ = (
        ForeignKeyConstraint(
            ["sales_quote_id", "company_id"],
            ["touche.sales_quote.id", "touche.sales_quote.company_id"],
            name="fk_sales_quote_revision_quote_company",
            ondelete="CASCADE",
        ),
        UniqueConstraint(
            "sales_quote_id", "revision", name="uq_sales_quote_revision_quote_revision"
        ),
        CheckConstraint("revision >= 1", name="ck_sales_quote_revision_no"),
        CheckConstraint(
            "jsonb_typeof(snapshot) = 'object'", name="ck_sales_quote_revision_snapshot"
        ),
        Index("ix_sales_quote_revision_company_quote", "company_id", "sales_quote_id"),
        {"schema": "touche", "comment": "Append-only sales quote revisions (RLS protected)."},
    )

    id: Mapped[UUID] = mapped_column(
        PG_UUID(as_uuid=True), primary_key=True, server_default=func.gen_random_uuid()
    )
    company_id: Mapped[UUID] = mapped_column(PG_UUID(as_uuid=True), nullable=False)
    sales_quote_id: Mapped[UUID] = mapped_column(PG_UUID(as_uuid=True), nullable=False)
    revision: Mapped[int] = mapped_column(Integer, nullable=False)
    snapshot: Mapped[dict[str, object]] = mapped_column(JSONB, nullable=False)
    reason: Mapped[str | None] = mapped_column(Text, nullable=True)
    actor_id: Mapped[UUID] = mapped_column(
        PG_UUID(as_uuid=True),
        ForeignKey("touche.app_user.id", name="fk_sales_quote_revision_actor_app_user"),
        nullable=False,
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now()
    )

    def __repr__(self) -> str:  # pragma: no cover - debugging helper
        return f"<SalesQuoteRevision quote={self.sales_quote_id} r{self.revision}>"


__all__ = [
    "CostBasis",
    "CostType",
    "FxRateSnapshot",
    "Incoterm",
    "PricingCostComponent",
    "PricingScenario",
    "RfqStatus",
    "SalesQuote",
    "SalesQuoteItem",
    "SalesQuoteRevision",
    "SalesQuoteStatus",
    "ScenarioStatus",
    "SupplierQuote",
    "SupplierQuoteItem",
    "SupplierQuoteRevision",
    "SupplierQuoteStatus",
    "SupplierRfq",
    "SupplierRfqItem",
    "SupplierRfqRevision",
    "VerificationStatus",
]

"""Stage 5D evidence-based financial reconciliation.

These tables never post an accounting entry. They record a reproducible snapshot
of commercial facts and Finance observations, stable Finance source references,
explicit evidence links, deterministic discrepancies and human review decisions.

Every child row uses a composite ``(id, company_id)`` foreign key, so a
cross-tenant link is rejected by PostgreSQL even if a service check were wrong.
"""

from __future__ import annotations

from datetime import date, datetime
from decimal import Decimal
from enum import StrEnum
from typing import Any
from uuid import UUID

from sqlalchemy import (
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


class ReconciliationStatus(StrEnum):
    """Exact lifecycle states for a reconciliation run."""

    INCOMPLETE = "INCOMPLETE"
    UNMATCHED = "UNMATCHED"
    POTENTIAL_MATCH = "POTENTIAL_MATCH"
    MATCHED_EVIDENCE = "MATCHED_EVIDENCE"
    VERIFIED = "VERIFIED"
    DISPUTED = "DISPUTED"


class SourceEntityType(StrEnum):
    """Commerce entities that may carry reconciliation evidence."""

    SALES_ORDER = "SALES_ORDER"
    PURCHASE_ORDER = "PURCHASE_ORDER"
    SHIPMENT = "SHIPMENT"
    SHIPMENT_COST = "SHIPMENT_COST"


class FinanceSourceType(StrEnum):
    """Finance observations that can be snapshotted.

    Only aging open items are transaction-level and eligible for an evidence
    link. ``SUMMARY`` and ``ACCOUNT`` observations are company-wide and must
    never be used to infer an order-level relationship.
    """

    AGING_RECEIVABLE = "AGING_RECEIVABLE"
    AGING_PAYABLE = "AGING_PAYABLE"
    ACCOUNT = "ACCOUNT"
    SUMMARY = "SUMMARY"


class EvidenceVerificationStatus(StrEnum):
    UNVERIFIED = "UNVERIFIED"
    VERIFIED = "VERIFIED"
    REJECTED = "REJECTED"


class DiscrepancyCode(StrEnum):
    MISSING_EVIDENCE = "MISSING_EVIDENCE"
    MISSING_FINANCE_REFERENCE = "MISSING_FINANCE_REFERENCE"
    AMOUNT_MISMATCH = "AMOUNT_MISMATCH"
    CURRENCY_MISMATCH = "CURRENCY_MISMATCH"
    DUPLICATE_REFERENCE = "DUPLICATE_REFERENCE"
    INCOMPLETE_COSTS = "INCOMPLETE_COSTS"
    UNMATCHED_FINANCE_ITEM = "UNMATCHED_FINANCE_ITEM"
    SOURCE_STALE = "SOURCE_STALE"
    COMPANY_MAPPING_INVALID = "COMPANY_MAPPING_INVALID"
    MANUAL_REVIEW_REQUIRED = "MANUAL_REVIEW_REQUIRED"


class DiscrepancySeverity(StrEnum):
    INFO = "INFO"
    WARNING = "WARNING"
    ERROR = "ERROR"
    BLOCKING = "BLOCKING"


class DiscrepancyStatus(StrEnum):
    OPEN = "OPEN"
    RESOLVED = "RESOLVED"
    DISMISSED = "DISMISSED"


class ReviewDecision(StrEnum):
    CONFIRM = "CONFIRM"
    DISPUTE = "DISPUTE"
    REQUEST_CHANGES = "REQUEST_CHANGES"


_RECONCILIATION_STATUSES = tuple(status.value for status in ReconciliationStatus)
_SOURCE_ENTITY_TYPES = tuple(value.value for value in SourceEntityType)
_FINANCE_SOURCE_TYPES = tuple(value.value for value in FinanceSourceType)
_EVIDENCE_STATUSES = tuple(value.value for value in EvidenceVerificationStatus)
_DISCREPANCY_CODES = tuple(value.value for value in DiscrepancyCode)
_DISCREPANCY_SEVERITIES = tuple(value.value for value in DiscrepancySeverity)
_DISCREPANCY_STATUSES = tuple(value.value for value in DiscrepancyStatus)
_REVIEW_DECISIONS = tuple(value.value for value in ReviewDecision)


def _in_list(column: str, values: tuple[str, ...]) -> str:
    rendered = ", ".join(f"'{value}'" for value in values)
    return f"{column} IN ({rendered})"


class FinanceReconciliationRun(Base):
    """One reproducible reconciliation snapshot for one sales order."""

    __tablename__ = "finance_reconciliation_run"
    __table_args__ = (
        UniqueConstraint("id", "company_id", name="uq_finance_reconciliation_run_id_company_id"),
        ForeignKeyConstraint(
            ["sales_order_id", "company_id"],
            ["touche.sales_order.id", "touche.sales_order.company_id"],
            name="fk_finance_reconciliation_run_sales_order_company",
            ondelete="RESTRICT",
        ),
        CheckConstraint(
            _in_list("status", _RECONCILIATION_STATUSES),
            name="ck_finance_reconciliation_run_status",
        ),
        CheckConstraint("currency ~ '^[A-Z]{2,3}$'", name="ck_finance_reconciliation_run_currency"),
        CheckConstraint(
            "finance_currency ~ '^[A-Z]{2,3}$'",
            name="ck_finance_reconciliation_run_finance_currency",
        ),
        CheckConstraint(
            "finance_company_id ~ '^[a-z][a-z0-9_]{1,63}$'",
            name="ck_finance_reconciliation_run_finance_company",
        ),
        CheckConstraint(
            "char_length(btrim(calculation_version)) BETWEEN 3 AND 40",
            name="ck_finance_reconciliation_run_calculation_version",
        ),
        CheckConstraint("version >= 1", name="ck_finance_reconciliation_run_version"),
        CheckConstraint(
            "jsonb_typeof(source_snapshot) = 'object'",
            name="ck_finance_reconciliation_run_snapshot_object",
        ),
        Index(
            "ix_finance_reconciliation_run_company_order",
            "company_id",
            "sales_order_id",
            "created_at",
        ),
        Index(
            "ix_finance_reconciliation_run_company_currency_status",
            "company_id",
            "currency",
            "status",
        ),
        {
            "schema": "touche",
            "comment": "Tenant-scoped reconciliation snapshots (RLS protected).",
        },
    )

    id: Mapped[UUID] = mapped_column(
        PG_UUID(as_uuid=True), primary_key=True, server_default=func.gen_random_uuid()
    )
    company_id: Mapped[UUID] = mapped_column(PG_UUID(as_uuid=True), nullable=False)
    sales_order_id: Mapped[UUID] = mapped_column(PG_UUID(as_uuid=True), nullable=False)
    finance_company_id: Mapped[str] = mapped_column(String(64), nullable=False)
    currency: Mapped[str] = mapped_column(String(3), nullable=False)
    finance_currency: Mapped[str] = mapped_column(String(3), nullable=False)
    as_of: Mapped[date] = mapped_column(Date, nullable=False)
    data_through: Mapped[date | None] = mapped_column(Date, nullable=True)
    status: Mapped[str] = mapped_column(String(24), nullable=False)
    calculation_version: Mapped[str] = mapped_column(String(40), nullable=False)
    source_snapshot: Mapped[dict[str, Any]] = mapped_column(JSONB, nullable=False)
    created_by: Mapped[UUID] = mapped_column(
        PG_UUID(as_uuid=True),
        ForeignKey("touche.app_user.id", name="fk_finance_reconciliation_run_created_by_app_user"),
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
        return f"<FinanceReconciliationRun {self.id} {self.status}>"


class FinanceSourceReference(Base):
    """A stable Finance source observation captured inside one run.

    ``source_reference`` is the identifier Finance itself exposes (for example an
    aging ``fis_id``). No counterparty name, free-text ``cari`` value or balance
    total is ever used as a matching key.
    """

    __tablename__ = "finance_source_reference"
    __table_args__ = (
        UniqueConstraint(
            "id", "company_id", "run_id", name="uq_finance_source_reference_id_company_run"
        ),
        UniqueConstraint(
            "run_id",
            "company_id",
            "source_type",
            "source_reference",
            name="uq_finance_source_reference_run_type_reference",
        ),
        ForeignKeyConstraint(
            ["run_id", "company_id"],
            [
                "touche.finance_reconciliation_run.id",
                "touche.finance_reconciliation_run.company_id",
            ],
            name="fk_finance_source_reference_run_company",
            ondelete="CASCADE",
        ),
        CheckConstraint(
            _in_list("source_type", _FINANCE_SOURCE_TYPES),
            name="ck_finance_source_reference_type",
        ),
        CheckConstraint(
            "char_length(btrim(source_reference)) BETWEEN 1 AND 200",
            name="ck_finance_source_reference_reference",
        ),
        CheckConstraint("currency ~ '^[A-Z]{2,3}$'", name="ck_finance_source_reference_currency"),
        CheckConstraint("content_hash ~ '^[0-9a-f]{64}$'", name="ck_finance_source_reference_hash"),
        CheckConstraint(
            "jsonb_typeof(payload) = 'object'", name="ck_finance_source_reference_payload_object"
        ),
        CheckConstraint(
            "(source_type IN ('AGING_RECEIVABLE', 'AGING_PAYABLE')) = is_transaction_level",
            name="ck_finance_source_reference_transaction_level",
        ),
        Index(
            "ix_finance_source_reference_company_run",
            "company_id",
            "run_id",
            "source_type",
        ),
        {
            "schema": "touche",
            "comment": "Finance source snapshot; names are never matching keys (RLS protected).",
        },
    )

    id: Mapped[UUID] = mapped_column(
        PG_UUID(as_uuid=True), primary_key=True, server_default=func.gen_random_uuid()
    )
    company_id: Mapped[UUID] = mapped_column(PG_UUID(as_uuid=True), nullable=False)
    run_id: Mapped[UUID] = mapped_column(PG_UUID(as_uuid=True), nullable=False)
    source_type: Mapped[str] = mapped_column(String(24), nullable=False)
    source_reference: Mapped[str] = mapped_column(String(200), nullable=False)
    is_transaction_level: Mapped[bool] = mapped_column(Boolean, nullable=False)
    currency: Mapped[str] = mapped_column(String(3), nullable=False)
    observed_amount: Mapped[Decimal | None] = mapped_column(Numeric(18, 2), nullable=True)
    as_of: Mapped[date] = mapped_column(Date, nullable=False)
    data_through: Mapped[date | None] = mapped_column(Date, nullable=True)
    payload: Mapped[dict[str, Any]] = mapped_column(JSONB, nullable=False)
    content_hash: Mapped[str] = mapped_column(String(64), nullable=False)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now()
    )

    def __repr__(self) -> str:  # pragma: no cover - debugging helper
        return (
            f"<FinanceSourceReference {self.source_type} {self.source_reference} "
            f"{self.observed_amount}>"
        )


class FinanceReconciliationEvidence(Base):
    """An explicit operator link between a Commerce source and Finance source."""

    __tablename__ = "finance_reconciliation_evidence"
    __table_args__ = (
        UniqueConstraint(
            "run_id",
            "company_id",
            "finance_source_reference_id",
            name="uq_finance_reconciliation_evidence_run_source",
        ),
        ForeignKeyConstraint(
            ["run_id", "company_id"],
            [
                "touche.finance_reconciliation_run.id",
                "touche.finance_reconciliation_run.company_id",
            ],
            name="fk_finance_reconciliation_evidence_run_company",
            ondelete="CASCADE",
        ),
        ForeignKeyConstraint(
            ["finance_source_reference_id", "company_id", "run_id"],
            [
                "touche.finance_source_reference.id",
                "touche.finance_source_reference.company_id",
                "touche.finance_source_reference.run_id",
            ],
            name="fk_finance_reconciliation_evidence_source_run",
            ondelete="RESTRICT",
        ),
        CheckConstraint(
            _in_list("source_entity_type", _SOURCE_ENTITY_TYPES),
            name="ck_finance_reconciliation_evidence_entity_type",
        ),
        CheckConstraint(
            _in_list("verification_status", _EVIDENCE_STATUSES),
            name="ck_finance_reconciliation_evidence_verification",
        ),
        CheckConstraint(
            "currency ~ '^[A-Z]{2,3}$'",
            name="ck_finance_reconciliation_evidence_currency",
        ),
        CheckConstraint("amount >= 0", name="ck_finance_reconciliation_evidence_amount"),
        CheckConstraint(
            "jsonb_typeof(provenance) = 'object'",
            name="ck_finance_reconciliation_evidence_provenance_object",
        ),
        CheckConstraint(
            "notes IS NULL OR char_length(notes) <= 2000",
            name="ck_finance_reconciliation_evidence_notes",
        ),
        CheckConstraint(
            "(verification_status = 'VERIFIED') = "
            "(verified_by IS NOT NULL AND verified_at IS NOT NULL)",
            name="ck_finance_reconciliation_evidence_verified_pair",
        ),
        Index(
            "ix_finance_reconciliation_evidence_company_run",
            "company_id",
            "run_id",
            "source_entity_type",
        ),
        Index(
            "ix_finance_reconciliation_evidence_company_entity",
            "company_id",
            "source_entity_type",
            "source_entity_id",
        ),
        {
            "schema": "touche",
            "comment": "Explicit evidence links; append-only for runtime (RLS protected).",
        },
    )

    id: Mapped[UUID] = mapped_column(
        PG_UUID(as_uuid=True), primary_key=True, server_default=func.gen_random_uuid()
    )
    company_id: Mapped[UUID] = mapped_column(PG_UUID(as_uuid=True), nullable=False)
    run_id: Mapped[UUID] = mapped_column(PG_UUID(as_uuid=True), nullable=False)
    finance_source_reference_id: Mapped[UUID] = mapped_column(PG_UUID(as_uuid=True), nullable=False)
    source_entity_type: Mapped[str] = mapped_column(String(24), nullable=False)
    source_entity_id: Mapped[UUID] = mapped_column(PG_UUID(as_uuid=True), nullable=False)
    currency: Mapped[str] = mapped_column(String(3), nullable=False)
    amount: Mapped[Decimal] = mapped_column(Numeric(18, 2), nullable=False)
    as_of: Mapped[date] = mapped_column(Date, nullable=False)
    data_through: Mapped[date | None] = mapped_column(Date, nullable=True)
    provenance: Mapped[dict[str, Any]] = mapped_column(JSONB, nullable=False)
    verification_status: Mapped[str] = mapped_column(
        String(16), nullable=False, server_default=text("'UNVERIFIED'")
    )
    notes: Mapped[str | None] = mapped_column(Text, nullable=True)
    created_by: Mapped[UUID] = mapped_column(
        PG_UUID(as_uuid=True),
        ForeignKey(
            "touche.app_user.id", name="fk_finance_reconciliation_evidence_created_by_app_user"
        ),
        nullable=False,
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now()
    )
    verified_by: Mapped[UUID | None] = mapped_column(
        PG_UUID(as_uuid=True),
        ForeignKey(
            "touche.app_user.id", name="fk_finance_reconciliation_evidence_verified_by_app_user"
        ),
        nullable=True,
    )
    verified_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)

    def __repr__(self) -> str:  # pragma: no cover - debugging helper
        return (
            f"<FinanceReconciliationEvidence {self.source_entity_type} "
            f"{self.source_entity_id} -> {self.finance_source_reference_id}>"
        )


class FinanceDiscrepancy(Base):
    """A deterministic, reviewable discrepancy. Never a silent Finance change."""

    __tablename__ = "finance_discrepancy"
    __table_args__ = (
        UniqueConstraint("run_id", "fingerprint", name="uq_finance_discrepancy_run_fingerprint"),
        UniqueConstraint("id", "company_id", name="uq_finance_discrepancy_id_company_id"),
        ForeignKeyConstraint(
            ["run_id", "company_id"],
            [
                "touche.finance_reconciliation_run.id",
                "touche.finance_reconciliation_run.company_id",
            ],
            name="fk_finance_discrepancy_run_company",
            ondelete="CASCADE",
        ),
        ForeignKeyConstraint(
            ["finance_source_reference_id", "company_id", "run_id"],
            [
                "touche.finance_source_reference.id",
                "touche.finance_source_reference.company_id",
                "touche.finance_source_reference.run_id",
            ],
            name="fk_finance_discrepancy_source_run",
            ondelete="RESTRICT",
        ),
        CheckConstraint(_in_list("code", _DISCREPANCY_CODES), name="ck_finance_discrepancy_code"),
        CheckConstraint(
            _in_list("severity", _DISCREPANCY_SEVERITIES),
            name="ck_finance_discrepancy_severity",
        ),
        CheckConstraint(
            _in_list("status", _DISCREPANCY_STATUSES), name="ck_finance_discrepancy_status"
        ),
        CheckConstraint(
            "source_entity_type IS NULL OR " + _in_list("source_entity_type", _SOURCE_ENTITY_TYPES),
            name="ck_finance_discrepancy_entity_type",
        ),
        CheckConstraint(
            "char_length(btrim(fingerprint)) = 64", name="ck_finance_discrepancy_fingerprint"
        ),
        CheckConstraint(
            "char_length(btrim(title)) BETWEEN 3 AND 160", name="ck_finance_discrepancy_title"
        ),
        CheckConstraint(
            "resolution_notes IS NULL OR char_length(resolution_notes) <= 2000",
            name="ck_finance_discrepancy_resolution_notes",
        ),
        CheckConstraint("version >= 1", name="ck_finance_discrepancy_version"),
        CheckConstraint(
            "(status = 'OPEN') = (resolved_by IS NULL AND resolved_at IS NULL)",
            name="ck_finance_discrepancy_resolution_pair",
        ),
        Index(
            "ix_finance_discrepancy_company_run_status",
            "company_id",
            "run_id",
            "status",
            "severity",
        ),
        {
            "schema": "touche",
            "comment": "Deterministic reconciliation discrepancies (RLS protected).",
        },
    )

    id: Mapped[UUID] = mapped_column(
        PG_UUID(as_uuid=True), primary_key=True, server_default=func.gen_random_uuid()
    )
    company_id: Mapped[UUID] = mapped_column(PG_UUID(as_uuid=True), nullable=False)
    run_id: Mapped[UUID] = mapped_column(PG_UUID(as_uuid=True), nullable=False)
    finance_source_reference_id: Mapped[UUID | None] = mapped_column(
        PG_UUID(as_uuid=True), nullable=True
    )
    source_entity_type: Mapped[str | None] = mapped_column(String(24), nullable=True)
    source_entity_id: Mapped[UUID | None] = mapped_column(PG_UUID(as_uuid=True), nullable=True)
    code: Mapped[str] = mapped_column(String(32), nullable=False)
    severity: Mapped[str] = mapped_column(String(16), nullable=False)
    status: Mapped[str] = mapped_column(String(16), nullable=False, server_default=text("'OPEN'"))
    fingerprint: Mapped[str] = mapped_column(String(64), nullable=False)
    title: Mapped[str] = mapped_column(String(160), nullable=False)
    detail: Mapped[str] = mapped_column(Text, nullable=False)
    expected: Mapped[dict[str, Any]] = mapped_column(
        JSONB, nullable=False, server_default=text("'{}'::jsonb")
    )
    observed: Mapped[dict[str, Any]] = mapped_column(
        JSONB, nullable=False, server_default=text("'{}'::jsonb")
    )
    assigned_to: Mapped[UUID | None] = mapped_column(
        PG_UUID(as_uuid=True),
        ForeignKey("touche.app_user.id", name="fk_finance_discrepancy_assigned_to_app_user"),
        nullable=True,
    )
    resolution_notes: Mapped[str | None] = mapped_column(Text, nullable=True)
    resolved_by: Mapped[UUID | None] = mapped_column(
        PG_UUID(as_uuid=True),
        ForeignKey("touche.app_user.id", name="fk_finance_discrepancy_resolved_by_app_user"),
        nullable=True,
    )
    resolved_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now()
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now(), onupdate=func.now()
    )
    version: Mapped[int] = mapped_column(Integer, nullable=False, server_default=text("1"))

    def __repr__(self) -> str:  # pragma: no cover - debugging helper
        return f"<FinanceDiscrepancy {self.code} {self.severity} {self.status}>"


class FinanceReconciliationReview(Base):
    """Append-only human decision. Reviewer identity is never inferred."""

    __tablename__ = "finance_reconciliation_review"
    __table_args__ = (
        UniqueConstraint("id", "company_id", name="uq_finance_reconciliation_review_id_company_id"),
        ForeignKeyConstraint(
            ["run_id", "company_id"],
            [
                "touche.finance_reconciliation_run.id",
                "touche.finance_reconciliation_run.company_id",
            ],
            name="fk_finance_reconciliation_review_run_company",
            ondelete="CASCADE",
        ),
        CheckConstraint(
            _in_list("decision", _REVIEW_DECISIONS),
            name="ck_finance_reconciliation_review_decision",
        ),
        CheckConstraint(
            _in_list("previous_status", _RECONCILIATION_STATUSES),
            name="ck_finance_reconciliation_review_previous_status",
        ),
        CheckConstraint(
            _in_list("new_status", _RECONCILIATION_STATUSES),
            name="ck_finance_reconciliation_review_new_status",
        ),
        CheckConstraint(
            "char_length(btrim(notes)) BETWEEN 3 AND 2000",
            name="ck_finance_reconciliation_review_notes",
        ),
        Index(
            "ix_finance_reconciliation_review_company_run",
            "company_id",
            "run_id",
            "created_at",
        ),
        {
            "schema": "touche",
            "comment": "Append-only financial review decisions (RLS protected).",
        },
    )

    id: Mapped[UUID] = mapped_column(
        PG_UUID(as_uuid=True), primary_key=True, server_default=func.gen_random_uuid()
    )
    company_id: Mapped[UUID] = mapped_column(PG_UUID(as_uuid=True), nullable=False)
    run_id: Mapped[UUID] = mapped_column(PG_UUID(as_uuid=True), nullable=False)
    reviewer_id: Mapped[UUID] = mapped_column(
        PG_UUID(as_uuid=True),
        ForeignKey("touche.app_user.id", name="fk_finance_reconciliation_review_reviewer_app_user"),
        nullable=False,
    )
    decision: Mapped[str] = mapped_column(String(24), nullable=False)
    previous_status: Mapped[str] = mapped_column(String(24), nullable=False)
    new_status: Mapped[str] = mapped_column(String(24), nullable=False)
    notes: Mapped[str] = mapped_column(Text, nullable=False)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now()
    )

    def __repr__(self) -> str:  # pragma: no cover - debugging helper
        return (
            f"<FinanceReconciliationReview {self.decision} "
            f"{self.previous_status}->{self.new_status}>"
        )


__all__ = [
    "DiscrepancyCode",
    "DiscrepancySeverity",
    "DiscrepancyStatus",
    "EvidenceVerificationStatus",
    "FinanceDiscrepancy",
    "FinanceReconciliationEvidence",
    "FinanceReconciliationReview",
    "FinanceReconciliationRun",
    "FinanceSourceReference",
    "FinanceSourceType",
    "ReconciliationStatus",
    "ReviewDecision",
    "SourceEntityType",
]

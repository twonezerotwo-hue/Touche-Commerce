"""Tenant-scoped mapping from a Commerce company to a Finance ``faaliyet_key``.

The mapping is deliberately explicit and singular: one Commerce company can point
at one Finance company, and the pair is configured by an authorised operator with
the privileged CLI. Nothing is inferred from company names, free-text
counterparties or the Finance key's wildcard-free company list.

This table is read-only for the runtime role. The CLI uses the migration role to
configure it; every configuration change is written to the audit trail.
"""

from __future__ import annotations

from datetime import datetime
from enum import StrEnum
from typing import Any
from uuid import UUID

from sqlalchemy import (
    CheckConstraint,
    DateTime,
    ForeignKey,
    Index,
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


class FinanceMappingStatus(StrEnum):
    """Lifecycle of an explicit Commerce → Finance company mapping."""

    PENDING = "pending"
    VERIFIED = "verified"
    DISABLED = "disabled"
    INVALID = "invalid"


_MAPPING_STATUSES = tuple(status.value for status in FinanceMappingStatus)


class FinanceCompanyMapping(Base):
    """One explicit, audited Commerce company → Finance company mapping."""

    __tablename__ = "finance_company_mapping"
    __table_args__ = (
        UniqueConstraint("company_id", name="uq_finance_company_mapping_company_id"),
        CheckConstraint(
            "finance_company_id ~ '^[a-z][a-z0-9_]{1,63}$'",
            name="ck_finance_company_mapping_finance_id",
        ),
        CheckConstraint(
            "status IN ('pending', 'verified', 'disabled', 'invalid')",
            name="ck_finance_company_mapping_status",
        ),
        CheckConstraint(
            "source IN ('manual_cli')",
            name="ck_finance_company_mapping_source",
        ),
        CheckConstraint(
            "last_verification_error IS NULL OR char_length(last_verification_error) <= 512",
            name="ck_finance_company_mapping_verification_error_length",
        ),
        CheckConstraint(
            "jsonb_typeof(verification_details) = 'object'",
            name="ck_finance_company_mapping_details_object",
        ),
        Index("ix_finance_company_mapping_status", "status"),
        {
            "schema": "touche",
            "comment": "Explicit tenant-scoped Commerce → Finance company mapping (RLS protected).",
        },
    )

    id: Mapped[UUID] = mapped_column(
        PG_UUID(as_uuid=True), primary_key=True, server_default=func.gen_random_uuid()
    )
    company_id: Mapped[UUID] = mapped_column(
        PG_UUID(as_uuid=True),
        ForeignKey(
            "touche.company.id",
            name="fk_finance_company_mapping_company_id_company",
            ondelete="CASCADE",
        ),
        nullable=False,
    )
    finance_company_id: Mapped[str] = mapped_column(String(64), nullable=False)
    finance_company_name: Mapped[str | None] = mapped_column(Text, nullable=True)
    status: Mapped[str] = mapped_column(
        String(16), nullable=False, server_default=text("'pending'")
    )
    source: Mapped[str] = mapped_column(
        String(32), nullable=False, server_default=text("'manual_cli'")
    )
    configured_by: Mapped[UUID | None] = mapped_column(
        PG_UUID(as_uuid=True),
        ForeignKey(
            "touche.app_user.id",
            name="fk_finance_company_mapping_configured_by_app_user",
            ondelete="SET NULL",
        ),
        nullable=True,
    )
    configured_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now()
    )
    last_verified_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )
    last_verification_error: Mapped[str | None] = mapped_column(Text, nullable=True)
    verification_details: Mapped[dict[str, Any]] = mapped_column(
        JSONB, nullable=False, server_default=text("'{}'::jsonb")
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now()
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now(), onupdate=func.now()
    )

    def __repr__(self) -> str:  # pragma: no cover - debugging helper
        return (
            f"<FinanceCompanyMapping company={self.company_id} "
            f"finance={self.finance_company_id}>"
        )


__all__ = ["FinanceCompanyMapping", "FinanceMappingStatus"]

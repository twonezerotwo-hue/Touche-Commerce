"""Stage 7C2 immutable contact suppression ledger.

Only company, CRM counterparty, channel and a coarse reason are stored.
There are no recipient addresses, messages, tokens or opt-in assertions.
Rows are append-only and can only block sending.
"""

from __future__ import annotations

from datetime import datetime
from enum import StrEnum
from uuid import UUID

from sqlalchemy import (
    CheckConstraint,
    DateTime,
    ForeignKey,
    ForeignKeyConstraint,
    Index,
    String,
    UniqueConstraint,
    func,
)
from sqlalchemy.dialects.postgresql import UUID as PG_UUID
from sqlalchemy.orm import Mapped, mapped_column

from app.db.models.base import Base


class SuppressionChannel(StrEnum):
    EMAIL = "EMAIL"
    WHATSAPP_BUSINESS = "WHATSAPP_BUSINESS"


class SuppressionReason(StrEnum):
    CONTACT_REQUEST = "CONTACT_REQUEST"
    COMPLIANCE_REVIEW = "COMPLIANCE_REVIEW"
    IMPORTED_BLOCK = "IMPORTED_BLOCK"


class CommunicationSuppression(Base):
    """One permanent per-company contact/channel block, never inferred consent."""

    __tablename__ = "communication_suppression"
    __table_args__ = (
        UniqueConstraint(
            "company_id", "counterparty_id", "channel",
            name="uq_communication_suppression_company_contact_channel",
        ),
        ForeignKeyConstraint(
            ["counterparty_id", "company_id"],
            ["touche.counterparty.id", "touche.counterparty.company_id"],
            name="fk_communication_suppression_counterparty_company",
            ondelete="RESTRICT",
        ),
        CheckConstraint(
            "channel IN ('EMAIL', 'WHATSAPP_BUSINESS')",
            name="ck_communication_suppression_channel",
        ),
        CheckConstraint(
            "reason IN ('CONTACT_REQUEST', 'COMPLIANCE_REVIEW', 'IMPORTED_BLOCK')",
            name="ck_communication_suppression_reason",
        ),
        Index(
            "ix_communication_suppression_company_created",
            "company_id", "created_at",
        ),
        {"schema": "touche", "comment": "Immutable tenant-scoped outbound contact blocks."},
    )

    id: Mapped[UUID] = mapped_column(
        PG_UUID(as_uuid=True), primary_key=True, server_default=func.gen_random_uuid()
    )
    company_id: Mapped[UUID] = mapped_column(
        PG_UUID(as_uuid=True),
        ForeignKey("touche.company.id", name="fk_communication_suppression_company_id_company"),
        nullable=False,
    )
    counterparty_id: Mapped[UUID] = mapped_column(PG_UUID(as_uuid=True), nullable=False)
    channel: Mapped[str] = mapped_column(String(24), nullable=False)
    reason: Mapped[str] = mapped_column(String(24), nullable=False)
    recorded_by: Mapped[UUID] = mapped_column(
        PG_UUID(as_uuid=True),
        ForeignKey("touche.app_user.id", name="fk_communication_suppression_recorded_by_user"),
        nullable=False,
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now()
    )

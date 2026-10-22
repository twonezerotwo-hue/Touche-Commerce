"""Tenant-owned storage: company settings, setting entries and idempotency records.

Every table here carries ``company_id`` and is protected by row level security
(ADR-004). ``company_setting_entry`` is the reference example of the composite
foreign-key rule: a child row references its parent by ``(settings_id,
company_id)``, so it is impossible to attach an entry to another tenant's
settings row, even if a bug supplied the wrong pair of ids.
"""

from __future__ import annotations

from datetime import datetime
from typing import Any
from uuid import UUID

from sqlalchemy import (
    CheckConstraint,
    DateTime,
    ForeignKey,
    ForeignKeyConstraint,
    Index,
    Integer,
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


class CompanySettings(Base):
    """Per-company configuration container (one row per company)."""

    __tablename__ = "company_settings"
    __table_args__ = (
        UniqueConstraint("company_id", name="uq_company_settings_company_id"),
        # Target of the composite FK used by company_setting_entry.
        UniqueConstraint("id", "company_id", name="uq_company_settings_id_company_id"),
        CheckConstraint("version >= 1", name="ck_company_settings_version"),
        CheckConstraint("char_length(timezone) BETWEEN 1 AND 64", name="ck_company_settings_tz"),
        CheckConstraint("char_length(locale) BETWEEN 2 AND 16", name="ck_company_settings_locale"),
        {"schema": "touche", "comment": "Tenant-scoped company settings (RLS protected)."},
    )

    id: Mapped[UUID] = mapped_column(
        PG_UUID(as_uuid=True), primary_key=True, server_default=func.gen_random_uuid()
    )
    company_id: Mapped[UUID] = mapped_column(
        PG_UUID(as_uuid=True),
        ForeignKey(
            "touche.company.id",
            name="fk_company_settings_company_id_company",
            ondelete="CASCADE",
        ),
        nullable=False,
    )
    timezone: Mapped[str] = mapped_column(Text, nullable=False, server_default=text("'UTC'"))
    locale: Mapped[str] = mapped_column(String(16), nullable=False, server_default=text("'en'"))
    version: Mapped[int] = mapped_column(Integer, nullable=False, server_default=text("1"))
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now()
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now(), onupdate=func.now()
    )

    def __repr__(self) -> str:  # pragma: no cover - debugging helper
        return f"<CompanySettings company={self.company_id}>"


class CompanySettingEntry(Base):
    """Individual key/value setting, tenant-scoped through a composite FK."""

    __tablename__ = "company_setting_entry"
    __table_args__ = (
        UniqueConstraint("settings_id", "key", name="uq_company_setting_entry_settings_id_key"),
        ForeignKeyConstraint(
            ["settings_id", "company_id"],
            ["touche.company_settings.id", "touche.company_settings.company_id"],
            name="fk_company_setting_entry_settings",
            ondelete="CASCADE",
        ),
        Index("ix_company_setting_entry_company_id", "company_id"),
        CheckConstraint("char_length(key) BETWEEN 1 AND 80", name="ck_company_setting_entry_key"),
        CheckConstraint(
            "jsonb_typeof(value) IN ('object', 'array', 'string', 'number', 'boolean')",
            name="ck_company_setting_entry_value",
        ),
        {"schema": "touche", "comment": "Tenant-scoped settings entries (RLS protected)."},
    )

    id: Mapped[UUID] = mapped_column(
        PG_UUID(as_uuid=True), primary_key=True, server_default=func.gen_random_uuid()
    )
    company_id: Mapped[UUID] = mapped_column(PG_UUID(as_uuid=True), nullable=False)
    settings_id: Mapped[UUID] = mapped_column(PG_UUID(as_uuid=True), nullable=False)
    key: Mapped[str] = mapped_column(String(80), nullable=False)
    value: Mapped[Any] = mapped_column(JSONB, nullable=False)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now()
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now(), onupdate=func.now()
    )

    def __repr__(self) -> str:  # pragma: no cover - debugging helper
        return f"<CompanySettingEntry {self.key}>"


class IdempotencyRecord(Base):
    """Durable home for the idempotent-replay contract (ADR-012).

    The record is written inside the *same* transaction as the business change
    (Stage 1B), so a replay can only exist for an operation that actually
    committed. ``endpoint`` is part of the identity, which is why the same key
    used against a different endpoint is a different operation rather than a
    conflict.
    """

    __tablename__ = "idempotency_record"
    __table_args__ = (
        UniqueConstraint(
            "actor_id",
            "company_id",
            "endpoint",
            "key",
            name="uq_idempotency_record_actor_company_endpoint_key",
        ),
        CheckConstraint(
            "status IN ('in_flight', 'completed', 'failed')", name="ck_idempotency_status"
        ),
        CheckConstraint("char_length(key) BETWEEN 1 AND 200", name="ck_idempotency_key_length"),
        CheckConstraint(
            "char_length(endpoint) BETWEEN 1 AND 160", name="ck_idempotency_endpoint_length"
        ),
        CheckConstraint(
            "char_length(request_fingerprint) = 64", name="ck_idempotency_fingerprint"
        ),
        Index("ix_idempotency_record_expires_at", "expires_at"),
        {"schema": "touche", "comment": "Idempotency records (RLS protected per company)."},
    )

    id: Mapped[UUID] = mapped_column(
        PG_UUID(as_uuid=True), primary_key=True, server_default=func.gen_random_uuid()
    )
    actor_id: Mapped[UUID | None] = mapped_column(PG_UUID(as_uuid=True), nullable=True)
    company_id: Mapped[UUID | None] = mapped_column(
        PG_UUID(as_uuid=True),
        ForeignKey(
            "touche.company.id",
            name="fk_idempotency_record_company_id_company",
            ondelete="CASCADE",
        ),
        nullable=True,
    )
    endpoint: Mapped[str] = mapped_column(String(160), nullable=False)
    key: Mapped[str] = mapped_column(String(200), nullable=False)
    request_fingerprint: Mapped[str] = mapped_column(String(64), nullable=False)
    status: Mapped[str] = mapped_column(
        String(16), nullable=False, server_default=text("'in_flight'")
    )
    response_status: Mapped[int | None] = mapped_column(Integer, nullable=True)
    response_body: Mapped[dict[str, Any] | None] = mapped_column(JSONB, nullable=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now()
    )
    expires_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)

    def __repr__(self) -> str:  # pragma: no cover - debugging helper
        return f"<IdempotencyRecord {self.key} {self.status}>"


__all__ = ["CompanySettingEntry", "CompanySettings", "IdempotencyRecord"]

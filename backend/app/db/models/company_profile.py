"""Stage 13 company profile: the facts printed on customer-facing trade documents.

Legal name, tax number, address and bank details are entered by the company's administrator;
the platform never invents them. Every column is optional, and a document built from an
incomplete profile says exactly which fields are missing.
"""

from __future__ import annotations

from datetime import datetime
from uuid import UUID

from sqlalchemy import CheckConstraint, DateTime, ForeignKey, Integer, String, Text, func
from sqlalchemy.dialects.postgresql import UUID as PG_UUID
from sqlalchemy.orm import Mapped, mapped_column

from app.db.models.base import Base

_TEXT_FIELDS = (
    ("legal_name", 200),
    ("tax_office", 120),
    ("tax_number", 40),
    ("city", 120),
    ("postal_code", 20),
    ("phone", 40),
    ("email", 254),
    ("website", 200),
    ("bank_name", 120),
    ("iban", 40),
    ("swift_bic", 11),
)


class CompanyProfile(Base):
    __tablename__ = "company_profile"
    __table_args__ = (
        *(
            CheckConstraint(
                f"{name} IS NULL OR char_length(btrim({name})) BETWEEN 1 AND {limit}",
                name=f"ck_company_profile_{name}",
            )
            for name, limit in _TEXT_FIELDS
        ),
        CheckConstraint(
            "address IS NULL OR char_length(btrim(address)) BETWEEN 1 AND 400",
            name="ck_company_profile_address",
        ),
        CheckConstraint("version >= 1", name="ck_company_profile_version"),
        {"schema": "touche", "comment": "Optional legal details printed on trade documents."},
    )

    company_id: Mapped[UUID] = mapped_column(
        PG_UUID(as_uuid=True), ForeignKey("touche.company.id"), primary_key=True
    )
    legal_name: Mapped[str | None] = mapped_column(String(200))
    tax_office: Mapped[str | None] = mapped_column(String(120))
    tax_number: Mapped[str | None] = mapped_column(String(40))
    address: Mapped[str | None] = mapped_column(Text)
    city: Mapped[str | None] = mapped_column(String(120))
    postal_code: Mapped[str | None] = mapped_column(String(20))
    phone: Mapped[str | None] = mapped_column(String(40))
    email: Mapped[str | None] = mapped_column(String(254))
    website: Mapped[str | None] = mapped_column(String(200))
    bank_name: Mapped[str | None] = mapped_column(String(120))
    iban: Mapped[str | None] = mapped_column(String(40))
    swift_bic: Mapped[str | None] = mapped_column(String(11))
    version: Mapped[int] = mapped_column(Integer, nullable=False, default=1, server_default="1")
    updated_by: Mapped[UUID] = mapped_column(
        PG_UUID(as_uuid=True), ForeignKey("touche.app_user.id"), nullable=False
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now(), onupdate=func.now()
    )

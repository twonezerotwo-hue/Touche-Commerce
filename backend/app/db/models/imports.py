"""Stage 13C durable ledger of web CSV/XLSX imports.

One row records one committed import of one exact file (its SHA-256) into one company.
The unique ``(company_id, kind, source_sha256)`` key is the durable idempotency guard:
submitting the same file again never writes a second time. The row holds counts and the
sanitised file name only — never a cell value, a price or a contact detail.
"""

from __future__ import annotations

from datetime import datetime
from uuid import UUID

from sqlalchemy import (
    CheckConstraint,
    DateTime,
    ForeignKey,
    Index,
    Integer,
    String,
    UniqueConstraint,
    func,
)
from sqlalchemy.dialects.postgresql import UUID as PG_UUID
from sqlalchemy.orm import Mapped, mapped_column

from app.db.models.base import Base


class ImportBatch(Base):
    __tablename__ = "import_batch"
    __table_args__ = (
        UniqueConstraint(
            "company_id", "kind", "source_sha256", name="uq_import_batch_company_kind_hash"
        ),
        CheckConstraint("kind IN ('products', 'counterparties')", name="ck_import_batch_kind"),
        CheckConstraint("source_sha256 ~ '^[0-9a-f]{64}$'", name="ck_import_batch_hash"),
        CheckConstraint(
            "total_rows >= 1 AND created_rows >= 0 AND skipped_rows >= 0 "
            "AND created_rows + skipped_rows = total_rows",
            name="ck_import_batch_counts",
        ),
        CheckConstraint(
            "char_length(btrim(filename)) BETWEEN 1 AND 120", name="ck_import_batch_filename"
        ),
        Index("ix_import_batch_company_created", "company_id", "created_at"),
        {"schema": "touche", "comment": "Committed CSV/XLSX imports, append-only (RLS protected)."},
    )

    id: Mapped[UUID] = mapped_column(
        PG_UUID(as_uuid=True), primary_key=True, server_default=func.gen_random_uuid()
    )
    company_id: Mapped[UUID] = mapped_column(
        PG_UUID(as_uuid=True),
        ForeignKey("touche.company.id", name="fk_import_batch_company_id_company"),
        nullable=False,
    )
    kind: Mapped[str] = mapped_column(String(16), nullable=False)
    source_sha256: Mapped[str] = mapped_column(String(64), nullable=False)
    filename: Mapped[str] = mapped_column(String(120), nullable=False)
    total_rows: Mapped[int] = mapped_column(Integer, nullable=False)
    created_rows: Mapped[int] = mapped_column(Integer, nullable=False)
    skipped_rows: Mapped[int] = mapped_column(Integer, nullable=False)
    created_by: Mapped[UUID] = mapped_column(
        PG_UUID(as_uuid=True),
        ForeignKey("touche.app_user.id", name="fk_import_batch_created_by_app_user"),
        nullable=False,
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now()
    )


__all__ = ["ImportBatch"]

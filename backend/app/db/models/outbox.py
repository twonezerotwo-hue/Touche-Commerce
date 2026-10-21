"""Transactional outbox — the integration foundation for later stages.

Only the minimum foundation is implemented in Stage 0: the durable table and
its ORM mapping.  Producers (trade deals, quotes, finance documents) and the
relay/worker that pushes events to E-YAY, Touche Finance, Gmail or WhatsApp
Business are Stage 2+ work (docs/DECISIONS.md #17).

Events are written in the *same* transaction as the business change so an
integration can never observe a state that was rolled back, and a lost message
can never hide a committed business change.
"""

from __future__ import annotations

from datetime import datetime
from typing import Any
from uuid import UUID

from sqlalchemy import DateTime, Index, Integer, String, Text, func, text
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.dialects.postgresql import UUID as PG_UUID
from sqlalchemy.orm import Mapped, mapped_column

from app.db.models.base import Base


class OutboxEvent(Base):
    """A durable integration event awaiting delivery to an external system."""

    __tablename__ = "outbox_event"
    __table_args__ = (
        Index(
            "ix_outbox_event_pending",
            "available_at",
            postgresql_where=text("processed_at IS NULL"),
        ),
        Index("ix_outbox_event_company_occurred_at", "company_id", "occurred_at"),
        {
            "schema": "touche",
            "comment": "Transactional outbox for future E-YAY / Touche Finance integrations.",
        },
    )

    id: Mapped[UUID] = mapped_column(
        PG_UUID(as_uuid=True), primary_key=True, server_default=func.gen_random_uuid()
    )
    # No FK yet: the company table arrives with Stage 1A multi-company model.
    company_id: Mapped[UUID | None] = mapped_column(PG_UUID(as_uuid=True), nullable=True)
    event_type: Mapped[str] = mapped_column(String(120), nullable=False)
    aggregate_type: Mapped[str] = mapped_column(String(64), nullable=False)
    aggregate_id: Mapped[str] = mapped_column(String(64), nullable=False)
    payload: Mapped[dict[str, Any]] = mapped_column(JSONB, nullable=False)
    occurred_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now()
    )
    available_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now()
    )
    attempts: Mapped[int] = mapped_column(Integer, nullable=False, server_default=text("0"))
    last_error: Mapped[str | None] = mapped_column(Text, nullable=True)
    processed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now()
    )

    def __repr__(self) -> str:  # pragma: no cover - debugging helper
        return f"<OutboxEvent {self.event_type} {self.aggregate_type}:{self.aggregate_id}>"

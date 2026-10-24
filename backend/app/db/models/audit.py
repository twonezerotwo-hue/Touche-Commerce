"""Append-only audit trail.

Design (ADR-009): one table, one writer, no second audit system. Rows are written
in the same transaction as the change they describe, they are never updated or
deleted by the application role, and a database trigger rejects both operations
even for a privileged role. ``details`` is a redacted JSON object — never a
password, token, hash or document body.
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
    func,
    text,
)
from sqlalchemy.dialects.postgresql import INET, JSONB
from sqlalchemy.dialects.postgresql import UUID as PG_UUID
from sqlalchemy.orm import Mapped, mapped_column

from app.db.models.base import Base


class AuditActorType(StrEnum):
    USER = "user"
    SYSTEM = "system"
    AGENT = "agent"


class AuditOutcome(StrEnum):
    SUCCESS = "success"
    FAILURE = "failure"
    DENIED = "denied"


class AuditAction(StrEnum):
    """Stable, dotted action names. Never renamed once released."""

    LOGIN_SUCCESS = "auth.login.success"
    LOGIN_FAILURE = "auth.login.failure"
    LOGOUT = "auth.logout"
    COMPANY_SWITCH = "session.company.switch"
    SESSION_REVOKED = "session.revoked"
    MEMBERSHIP_CHANGED = "membership.changed"
    ACCESS_DENIED = "access.denied"
    IDENTITY_BOOTSTRAPPED = "identity.bootstrap"
    # Stage 1B trade module.
    COUNTERPARTY_CREATED = "counterparty.created"
    COUNTERPARTY_UPDATED = "counterparty.updated"
    PRODUCT_CREATED = "product.created"
    PRODUCT_UPDATED = "product.updated"
    DEAL_CREATED = "deal.created"
    DEAL_UPDATED = "deal.updated"
    DEAL_TRANSITIONED = "deal.transitioned"
    # Stage 3 sourcing, pricing and sales-quote module.
    RFQ_CREATED = "rfq.created"
    RFQ_UPDATED = "rfq.updated"
    RFQ_PREPARED = "rfq.prepared"
    RFQ_SENT = "rfq.sent"
    RFQ_CANCELLED = "rfq.cancelled"
    RFQ_CLOSED = "rfq.closed"
    SUPPLIER_QUOTE_RECORDED = "supplier_quote.recorded"
    SUPPLIER_QUOTE_REVISED = "supplier_quote.revised"
    SUPPLIER_QUOTE_WITHDRAWN = "supplier_quote.withdrawn"
    FX_RATE_RECORDED = "fx_rate.recorded"
    PRICING_SCENARIO_CREATED = "pricing_scenario.created"
    PRICING_SCENARIO_UPDATED = "pricing_scenario.updated"
    SALES_QUOTE_CREATED = "sales_quote.created"
    SALES_QUOTE_SUBMITTED = "sales_quote.submitted"
    SALES_QUOTE_APPROVED = "sales_quote.approved"
    SALES_QUOTE_REJECTED = "sales_quote.rejected"
    SALES_QUOTE_WITHDRAWN = "sales_quote.withdrawn"
    # Stage 4 orders, procurement, logistics and documents.
    DEAL_WON = "deal.won"
    CUSTOMER_ACCEPTANCE_RECORDED = "customer_acceptance.recorded"
    SALES_ORDER_CREATED = "sales_order.created"
    SALES_ORDER_TRANSITIONED = "sales_order.transitioned"
    SALES_ORDER_AMENDED = "sales_order.amended"
    PURCHASE_ORDER_CREATED = "purchase_order.created"
    PURCHASE_ORDER_TRANSITIONED = "purchase_order.transitioned"
    SHIPMENT_CREATED = "shipment.created"
    SHIPMENT_UPDATED = "shipment.updated"
    SHIPMENT_TRANSITIONED = "shipment.transitioned"
    SHIPMENT_COST_RECORDED = "shipment.cost_recorded"
    DOCUMENT_UPLOADED = "document.uploaded"
    DOCUMENT_DOWNLOADED = "document.downloaded"
    DOCUMENT_ARCHIVED = "document.archived"
    DOCUMENT_VERIFIED = "document.verified"
    # Stage 5C read-only Finance integration.
    FINANCE_MAPPING_CONFIGURED = "finance.mapping.configured"
    FINANCE_MAPPING_DISABLED = "finance.mapping.disabled"
    FINANCE_READ = "finance.read"
    # Stage 5D read-only evidence reconciliation.
    FINANCE_RECONCILIATION_RUN_CREATED = "finance.reconciliation_run.created"
    FINANCE_EVIDENCE_LINKED = "finance.evidence.linked"
    FINANCE_DISCREPANCY_RESOLVED = "finance.discrepancy.resolved"
    FINANCE_RECONCILIATION_REVIEWED = "finance.reconciliation.reviewed"
    # Stage 6 AI Trade Director. Tool and run events are written with the agent actor
    # type; ``actor_id`` is the person on whose authority the agent acted.
    AI_CONVERSATION_CREATED = "ai.conversation.created"
    AI_RUN_COMPLETED = "ai.run.completed"
    AI_RUN_FAILED = "ai.run.failed"
    AI_RUN_CANCELLED = "ai.run.cancelled"
    AI_TOOL_EXECUTED = "ai.tool.executed"
    AI_TOOL_DENIED = "ai.tool.denied"
    AI_ACTION_BLOCKED = "ai.action.blocked"
    AI_PROPOSAL_CREATED = "ai.proposal.created"
    AI_PROPOSAL_EDITED = "ai.proposal.edited"
    AI_PROPOSAL_APPROVED = "ai.proposal.approved"
    AI_PROPOSAL_REJECTED = "ai.proposal.rejected"
    # Stage 7C2: irrevocable outbound contact suppression; no contact data in audit.
    COMMUNICATION_SUPPRESSION_RECORDED = "communications.suppression.recorded"
    # Stage 13C: a web CSV/XLSX import was committed (counts only, never cell values).
    IMPORT_COMMITTED = "import.committed"
    # Stage 13: the company's document details changed (field names only, never values).
    COMPANY_PROFILE_UPDATED = "company_profile.updated"
    # Stage 13: a customer-facing document was rendered (kind, format, locale; no content).
    DOCUMENT_GENERATED = "document.generated"


_AUDIT_ACTIONS = tuple(action.value for action in AuditAction)
_ACTOR_TYPES = tuple(actor.value for actor in AuditActorType)
_OUTCOMES = tuple(outcome.value for outcome in AuditOutcome)


def _in_list(column: str, values: tuple[str, ...]) -> str:
    rendered = ", ".join(f"'{value}'" for value in values)
    return f"{column} IN ({rendered})"


class AuditRecord(Base):
    """A single security-relevant event."""

    __tablename__ = "audit_record"
    __table_args__ = (
        CheckConstraint(_in_list("actor_type", _ACTOR_TYPES), name="ck_audit_actor_type"),
        CheckConstraint(_in_list("outcome", _OUTCOMES), name="ck_audit_outcome"),
        CheckConstraint(_in_list("action", _AUDIT_ACTIONS), name="ck_audit_action"),
        CheckConstraint("char_length(action) BETWEEN 3 AND 80", name="ck_audit_action_length"),
        CheckConstraint("jsonb_typeof(details) = 'object'", name="ck_audit_details_object"),
        Index("ix_audit_record_occurred_at", "occurred_at"),
        Index("ix_audit_record_company_occurred_at", "company_id", "occurred_at"),
        Index("ix_audit_record_actor_occurred_at", "actor_id", "occurred_at"),
        Index("ix_audit_record_action_occurred_at", "action", "occurred_at"),
        {"schema": "touche", "comment": "Append-only security audit trail."},
    )

    id: Mapped[UUID] = mapped_column(
        PG_UUID(as_uuid=True), primary_key=True, server_default=func.gen_random_uuid()
    )
    actor_type: Mapped[str] = mapped_column(
        String(16), nullable=False, server_default=text("'user'")
    )
    # No FK: an audit row must outlive the identity it describes (and the table
    # is append-only, so ON DELETE SET NULL would be impossible).
    actor_id: Mapped[UUID | None] = mapped_column(PG_UUID(as_uuid=True), nullable=True)
    company_id: Mapped[UUID | None] = mapped_column(
        PG_UUID(as_uuid=True),
        ForeignKey(
            "touche.company.id", name="fk_audit_record_company_id_company", ondelete="RESTRICT"
        ),
        nullable=True,
    )
    action: Mapped[str] = mapped_column(String(80), nullable=False)
    outcome: Mapped[str] = mapped_column(String(16), nullable=False)
    request_id: Mapped[str | None] = mapped_column(String(128), nullable=True)
    occurred_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now()
    )
    ip_address: Mapped[str | None] = mapped_column(INET, nullable=True)
    user_agent: Mapped[str | None] = mapped_column(Text, nullable=True)
    resource_type: Mapped[str | None] = mapped_column(String(64), nullable=True)
    resource_id: Mapped[str | None] = mapped_column(String(64), nullable=True)
    details: Mapped[dict[str, Any]] = mapped_column(
        JSONB, nullable=False, server_default=text("'{}'::jsonb")
    )

    def __repr__(self) -> str:  # pragma: no cover - debugging helper
        return f"<AuditRecord {self.action} {self.outcome}>"


__all__ = ["AuditAction", "AuditActorType", "AuditOutcome", "AuditRecord"]

"""Stage 6 AI Trade Director persistence.

These tables hold conversation history, run metadata (provider, model, prompt
version, token usage, cost), one row per tool call and the human-approval
proposals. They never store a prompt sent to a provider, a credential, a raw tool
result or a document body: a tool call keeps its validated arguments and a small
result summary, and an assistant message keeps the *validated* structured answer
with the evidence it cites.

Every child row uses a composite ``(id, company_id)`` foreign key, so a cross-tenant
link is rejected by PostgreSQL even if a service check were wrong. A proposal is a
suggestion for a person; nothing here posts, sends, signs, pays or accepts.
"""

from __future__ import annotations

from datetime import datetime
from decimal import Decimal
from enum import StrEnum
from typing import Any
from uuid import UUID

from sqlalchemy import (
    Boolean,
    CheckConstraint,
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


class ConversationStatus(StrEnum):
    ACTIVE = "ACTIVE"
    ARCHIVED = "ARCHIVED"


class MessageRole(StrEnum):
    USER = "USER"
    ASSISTANT = "ASSISTANT"


class RunStatus(StrEnum):
    RUNNING = "RUNNING"
    COMPLETED = "COMPLETED"
    FAILED = "FAILED"
    CANCELLED = "CANCELLED"


class ToolCallStatus(StrEnum):
    OK = "OK"
    DENIED = "DENIED"
    INVALID = "INVALID"
    ERROR = "ERROR"
    LIMITED = "LIMITED"


class ProposalKind(StrEnum):
    DRAFT = "DRAFT"
    TASK = "TASK"


class ProposalActionType(StrEnum):
    """The only actions a proposal can ever request. Anything else is BLOCKED."""

    DRAFT_REVIEW = "DRAFT_REVIEW"
    OPERATOR_TASK = "OPERATOR_TASK"


class ProposalStatus(StrEnum):
    PROPOSED = "PROPOSED"
    APPROVED = "APPROVED"
    REJECTED = "REJECTED"


def _in_list(column: str, values: type[StrEnum]) -> str:
    rendered = ", ".join(f"'{item.value}'" for item in values)
    return f"{column} IN ({rendered})"


_ACTION_CLASSES = "'DRAFT_PROPOSAL', 'REQUIRES_HUMAN_APPROVAL'"


class AiConversation(Base):
    """A conversation belongs to one user inside one company."""

    __tablename__ = "ai_conversation"
    __table_args__ = (
        UniqueConstraint("id", "company_id", name="uq_ai_conversation_id_company_id"),
        CheckConstraint(_in_list("status", ConversationStatus), name="ck_ai_conversation_status"),
        CheckConstraint(
            "char_length(btrim(title)) BETWEEN 1 AND 160", name="ck_ai_conversation_title"
        ),
        CheckConstraint("version >= 1", name="ck_ai_conversation_version"),
        Index("ix_ai_conversation_company_user_updated", "company_id", "user_id", "updated_at"),
        {"schema": "touche", "comment": "AI Office conversations (RLS protected)."},
    )

    id: Mapped[UUID] = mapped_column(
        PG_UUID(as_uuid=True), primary_key=True, server_default=func.gen_random_uuid()
    )
    company_id: Mapped[UUID] = mapped_column(
        PG_UUID(as_uuid=True),
        ForeignKey("touche.company.id", name="fk_ai_conversation_company_id_company"),
        nullable=False,
    )
    user_id: Mapped[UUID] = mapped_column(
        PG_UUID(as_uuid=True),
        ForeignKey("touche.app_user.id", name="fk_ai_conversation_user_id_app_user"),
        nullable=False,
    )
    title: Mapped[str] = mapped_column(String(160), nullable=False)
    status: Mapped[str] = mapped_column(String(16), nullable=False, server_default=text("'ACTIVE'"))
    prompt_version: Mapped[str] = mapped_column(String(40), nullable=False)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now()
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now()
    )
    version: Mapped[int] = mapped_column(Integer, nullable=False, server_default=text("1"))


class AiRun(Base):
    """One question answered by the Trade Director (metadata only)."""

    __tablename__ = "ai_run"
    __table_args__ = (
        UniqueConstraint("id", "company_id", name="uq_ai_run_id_company_id"),
        ForeignKeyConstraint(
            ["conversation_id", "company_id"],
            ["touche.ai_conversation.id", "touche.ai_conversation.company_id"],
            name="fk_ai_run_conversation_company",
            ondelete="RESTRICT",
        ),
        CheckConstraint(_in_list("status", RunStatus), name="ck_ai_run_status"),
        CheckConstraint(
            "input_tokens >= 0 AND output_tokens >= 0 AND model_steps >= 0 "
            "AND tool_call_count >= 0 AND provider_calls >= 0",
            name="ck_ai_run_counters",
        ),
        CheckConstraint("cost_usd >= 0", name="ck_ai_run_cost"),
        CheckConstraint("reserved_cost_usd >= 0", name="ck_ai_run_reserved_cost"),
        CheckConstraint(
            "jsonb_typeof(validation_warnings) = 'array' AND jsonb_typeof(safety_flags) = 'array'",
            name="ck_ai_run_flags_array",
        ),
        CheckConstraint(
            "(status = 'RUNNING') = (finished_at IS NULL)", name="ck_ai_run_finished_pair"
        ),
        Index("ix_ai_run_company_started", "company_id", "started_at"),
        Index("ix_ai_run_company_user_started", "company_id", "user_id", "started_at"),
        Index("ix_ai_run_conversation", "company_id", "conversation_id", "started_at"),
        {"schema": "touche", "comment": "AI run metadata, usage and cost (RLS protected)."},
    )

    id: Mapped[UUID] = mapped_column(
        PG_UUID(as_uuid=True), primary_key=True, server_default=func.gen_random_uuid()
    )
    company_id: Mapped[UUID] = mapped_column(PG_UUID(as_uuid=True), nullable=False)
    conversation_id: Mapped[UUID] = mapped_column(PG_UUID(as_uuid=True), nullable=False)
    user_id: Mapped[UUID] = mapped_column(
        PG_UUID(as_uuid=True),
        ForeignKey("touche.app_user.id", name="fk_ai_run_user_id_app_user"),
        nullable=False,
    )
    status: Mapped[str] = mapped_column(String(16), nullable=False)
    provider: Mapped[str] = mapped_column(String(32), nullable=False)
    model: Mapped[str] = mapped_column(String(120), nullable=False)
    prompt_version: Mapped[str] = mapped_column(String(40), nullable=False)
    is_external: Mapped[bool] = mapped_column(Boolean, nullable=False)
    input_tokens: Mapped[int] = mapped_column(Integer, nullable=False, server_default=text("0"))
    output_tokens: Mapped[int] = mapped_column(Integer, nullable=False, server_default=text("0"))
    estimated_usage: Mapped[bool] = mapped_column(
        Boolean, nullable=False, server_default=text("false")
    )
    cost_usd: Mapped[Decimal] = mapped_column(
        Numeric(12, 6), nullable=False, server_default=text("0")
    )
    reserved_cost_usd: Mapped[Decimal] = mapped_column(
        Numeric(12, 6), nullable=False, server_default=text("0")
    )
    model_steps: Mapped[int] = mapped_column(Integer, nullable=False, server_default=text("0"))
    tool_call_count: Mapped[int] = mapped_column(Integer, nullable=False, server_default=text("0"))
    provider_calls: Mapped[int] = mapped_column(Integer, nullable=False, server_default=text("0"))
    error_code: Mapped[str | None] = mapped_column(String(64), nullable=True)
    validation_warnings: Mapped[list[Any]] = mapped_column(
        JSONB, nullable=False, server_default=text("'[]'::jsonb")
    )
    safety_flags: Mapped[list[Any]] = mapped_column(
        JSONB, nullable=False, server_default=text("'[]'::jsonb")
    )
    request_id: Mapped[str | None] = mapped_column(String(128), nullable=True)
    started_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now()
    )
    finished_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)


class AiMessage(Base):
    """A user turn or the validated assistant answer."""

    __tablename__ = "ai_message"
    __table_args__ = (
        UniqueConstraint("id", "company_id", name="uq_ai_message_id_company_id"),
        ForeignKeyConstraint(
            ["conversation_id", "company_id"],
            ["touche.ai_conversation.id", "touche.ai_conversation.company_id"],
            name="fk_ai_message_conversation_company",
            ondelete="RESTRICT",
        ),
        ForeignKeyConstraint(
            ["run_id", "company_id"],
            ["touche.ai_run.id", "touche.ai_run.company_id"],
            name="fk_ai_message_run_company",
            ondelete="RESTRICT",
        ),
        CheckConstraint(_in_list("role", MessageRole), name="ck_ai_message_role"),
        CheckConstraint("char_length(content) BETWEEN 1 AND 20000", name="ck_ai_message_content"),
        CheckConstraint("jsonb_typeof(evidence) = 'array'", name="ck_ai_message_evidence_array"),
        CheckConstraint(
            "structured IS NULL OR jsonb_typeof(structured) = 'object'",
            name="ck_ai_message_structured_object",
        ),
        Index("ix_ai_message_conversation", "company_id", "conversation_id", "created_at"),
        {"schema": "touche", "comment": "AI conversation messages, append-only (RLS protected)."},
    )

    id: Mapped[UUID] = mapped_column(
        PG_UUID(as_uuid=True), primary_key=True, server_default=func.gen_random_uuid()
    )
    company_id: Mapped[UUID] = mapped_column(PG_UUID(as_uuid=True), nullable=False)
    conversation_id: Mapped[UUID] = mapped_column(PG_UUID(as_uuid=True), nullable=False)
    run_id: Mapped[UUID | None] = mapped_column(PG_UUID(as_uuid=True), nullable=True)
    role: Mapped[str] = mapped_column(String(12), nullable=False)
    content: Mapped[str] = mapped_column(Text, nullable=False)
    structured: Mapped[dict[str, Any] | None] = mapped_column(JSONB, nullable=True)
    evidence: Mapped[list[Any]] = mapped_column(
        JSONB, nullable=False, server_default=text("'[]'::jsonb")
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now()
    )


class AiToolCall(Base):
    """One tool call: validated arguments and a result summary, never the result."""

    __tablename__ = "ai_tool_call"
    __table_args__ = (
        ForeignKeyConstraint(
            ["run_id", "company_id"],
            ["touche.ai_run.id", "touche.ai_run.company_id"],
            name="fk_ai_tool_call_run_company",
            ondelete="RESTRICT",
        ),
        UniqueConstraint("run_id", "ordinal", name="uq_ai_tool_call_run_ordinal"),
        CheckConstraint(_in_list("status", ToolCallStatus), name="ck_ai_tool_call_status"),
        CheckConstraint(
            "tool_class IN ('READ_ONLY', 'DRAFT_PROPOSAL', 'REQUIRES_HUMAN_APPROVAL', 'BLOCKED')",
            name="ck_ai_tool_call_class",
        ),
        CheckConstraint(
            "jsonb_typeof(arguments) = 'object' AND jsonb_typeof(result_meta) = 'object'",
            name="ck_ai_tool_call_json_object",
        ),
        CheckConstraint("result_chars >= 0 AND duration_ms >= 0", name="ck_ai_tool_call_counters"),
        Index("ix_ai_tool_call_company_run", "company_id", "run_id", "ordinal"),
        {"schema": "touche", "comment": "AI tool-call log, append-only (RLS protected)."},
    )

    id: Mapped[UUID] = mapped_column(
        PG_UUID(as_uuid=True), primary_key=True, server_default=func.gen_random_uuid()
    )
    company_id: Mapped[UUID] = mapped_column(PG_UUID(as_uuid=True), nullable=False)
    run_id: Mapped[UUID] = mapped_column(PG_UUID(as_uuid=True), nullable=False)
    ordinal: Mapped[int] = mapped_column(Integer, nullable=False)
    tool_name: Mapped[str] = mapped_column(String(64), nullable=False)
    tool_class: Mapped[str] = mapped_column(String(32), nullable=False)
    status: Mapped[str] = mapped_column(String(12), nullable=False)
    arguments: Mapped[dict[str, Any]] = mapped_column(JSONB, nullable=False)
    result_meta: Mapped[dict[str, Any]] = mapped_column(
        JSONB, nullable=False, server_default=text("'{}'::jsonb")
    )
    result_chars: Mapped[int] = mapped_column(Integer, nullable=False, server_default=text("0"))
    duration_ms: Mapped[int] = mapped_column(Integer, nullable=False, server_default=text("0"))
    error_code: Mapped[str | None] = mapped_column(String(64), nullable=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now()
    )


class AiProposal(Base):
    """A draft or task the model proposed; only a person can approve or reject it."""

    __tablename__ = "ai_proposal"
    __table_args__ = (
        UniqueConstraint("id", "company_id", name="uq_ai_proposal_id_company_id"),
        ForeignKeyConstraint(
            ["conversation_id", "company_id"],
            ["touche.ai_conversation.id", "touche.ai_conversation.company_id"],
            name="fk_ai_proposal_conversation_company",
            ondelete="RESTRICT",
        ),
        ForeignKeyConstraint(
            ["run_id", "company_id"],
            ["touche.ai_run.id", "touche.ai_run.company_id"],
            name="fk_ai_proposal_run_company",
            ondelete="RESTRICT",
        ),
        CheckConstraint(_in_list("kind", ProposalKind), name="ck_ai_proposal_kind"),
        CheckConstraint(
            _in_list("action_type", ProposalActionType), name="ck_ai_proposal_action_type"
        ),
        CheckConstraint(f"action_class IN ({_ACTION_CLASSES})", name="ck_ai_proposal_action_class"),
        CheckConstraint(_in_list("status", ProposalStatus), name="ck_ai_proposal_status"),
        CheckConstraint("char_length(btrim(title)) BETWEEN 1 AND 200", name="ck_ai_proposal_title"),
        CheckConstraint(
            "jsonb_typeof(payload) = 'object' AND jsonb_typeof(evidence) = 'array' "
            "AND jsonb_typeof(warnings) = 'array'",
            name="ck_ai_proposal_json_shapes",
        ),
        CheckConstraint(
            "edited_payload IS NULL OR jsonb_typeof(edited_payload) = 'object'",
            name="ck_ai_proposal_edited_object",
        ),
        CheckConstraint(
            "(status = 'PROPOSED') = (decided_by IS NULL AND decided_at IS NULL)",
            name="ck_ai_proposal_decision_pair",
        ),
        CheckConstraint(
            "decision_notes IS NULL OR char_length(decision_notes) <= 2000",
            name="ck_ai_proposal_decision_notes",
        ),
        CheckConstraint("version >= 1", name="ck_ai_proposal_version"),
        Index("ix_ai_proposal_company_status", "company_id", "status", "created_at"),
        Index("ix_ai_proposal_conversation", "company_id", "conversation_id", "created_at"),
        {"schema": "touche", "comment": "Human-approval proposals from the AI (RLS protected)."},
    )

    id: Mapped[UUID] = mapped_column(
        PG_UUID(as_uuid=True), primary_key=True, server_default=func.gen_random_uuid()
    )
    company_id: Mapped[UUID] = mapped_column(PG_UUID(as_uuid=True), nullable=False)
    conversation_id: Mapped[UUID] = mapped_column(PG_UUID(as_uuid=True), nullable=False)
    run_id: Mapped[UUID] = mapped_column(PG_UUID(as_uuid=True), nullable=False)
    created_by: Mapped[UUID] = mapped_column(
        PG_UUID(as_uuid=True),
        ForeignKey("touche.app_user.id", name="fk_ai_proposal_created_by_app_user"),
        nullable=False,
    )
    kind: Mapped[str] = mapped_column(String(8), nullable=False)
    action_type: Mapped[str] = mapped_column(String(24), nullable=False)
    action_class: Mapped[str] = mapped_column(String(32), nullable=False)
    title: Mapped[str] = mapped_column(String(200), nullable=False)
    payload: Mapped[dict[str, Any]] = mapped_column(JSONB, nullable=False)
    edited_payload: Mapped[dict[str, Any] | None] = mapped_column(JSONB, nullable=True)
    evidence: Mapped[list[Any]] = mapped_column(
        JSONB, nullable=False, server_default=text("'[]'::jsonb")
    )
    warnings: Mapped[list[Any]] = mapped_column(
        JSONB, nullable=False, server_default=text("'[]'::jsonb")
    )
    status: Mapped[str] = mapped_column(
        String(12), nullable=False, server_default=text("'PROPOSED'")
    )
    decided_by: Mapped[UUID | None] = mapped_column(
        PG_UUID(as_uuid=True),
        ForeignKey("touche.app_user.id", name="fk_ai_proposal_decided_by_app_user"),
        nullable=True,
    )
    decided_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    decision_notes: Mapped[str | None] = mapped_column(Text, nullable=True)
    execution_result: Mapped[dict[str, Any] | None] = mapped_column(JSONB, nullable=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now()
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now()
    )
    version: Mapped[int] = mapped_column(Integer, nullable=False, server_default=text("1"))


__all__ = [
    "AiConversation",
    "AiMessage",
    "AiProposal",
    "AiRun",
    "AiToolCall",
    "ConversationStatus",
    "MessageRole",
    "ProposalActionType",
    "ProposalKind",
    "ProposalStatus",
    "RunStatus",
    "ToolCallStatus",
]

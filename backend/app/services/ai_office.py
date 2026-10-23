"""AI Office persistence: conversations, runs, tool-call log, usage and proposals.

Every method opens its own transaction, binds the tenant context first and filters by
``company_id`` as well (RLS and the service both apply). A conversation belongs to the
user who started it: another member of the same company gets ``404``. Proposals are
company-visible so a second person can review what a colleague's conversation produced.
Nothing here executes a business action; approving a proposal only records the human
decision (see :mod:`app.ai.proposals`).
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import UTC, datetime, timedelta
from decimal import Decimal
from typing import Any
from uuid import UUID, uuid4

from sqlalchemy import func, select, update
from sqlalchemy.orm import Session

from app.ai.errors import ActionNotSupportedError, ProposalStateError
from app.ai.proposals import ACTIONS, BLOCKING_WARNINGS, NewProposal, apply_edit
from app.ai.tools.registry import ToolClass, ToolExecution, ToolOutcome
from app.core.errors import ConflictError, ForbiddenError, NotFoundError, VersionConflictError
from app.db.engine import Database
from app.db.models import (
    AiConversation,
    AiMessage,
    AiProposal,
    AiRun,
    AiToolCall,
    AuditAction,
    AuditActorType,
    AuditOutcome,
    Company,
    CompanyStatus,
    Counterparty,
    Deal,
    FinanceDiscrepancy,
    Membership,
    MembershipStatus,
    PricingScenario,
    Product,
    PurchaseOrder,
    SalesOrder,
    Shipment,
    SupplierQuote,
)
from app.db.models.ai import (
    ConversationStatus,
    MessageRole,
    ProposalStatus,
    RunStatus,
    ToolCallStatus,
)
from app.db.tenant import apply_actor_context, apply_company_context
from app.security.permissions import Permission, permissions_for
from app.services.audit import record_audit

_COST_QUANTUM = Decimal("0.000001")
DEFAULT_TITLE = "New conversation"

_TARGET_MODELS: dict[str, Any] = {
    "DEAL": Deal,
    "SALES_ORDER": SalesOrder,
    "ORDER_PROFITABILITY": SalesOrder,
    "ORDER_FINANCE": SalesOrder,
    "SUPPLIER_QUOTE": SupplierQuote,
    "PRICING_SCENARIO": PricingScenario,
    "PURCHASE_ORDER": PurchaseOrder,
    "SHIPMENT": Shipment,
    "COUNTERPARTY": Counterparty,
    "PRODUCT": Product,
    "DISCREPANCY": FinanceDiscrepancy,
}

_TOOL_STATUS = {
    ToolOutcome.OK: ToolCallStatus.OK,
    ToolOutcome.DENIED: ToolCallStatus.DENIED,
    ToolOutcome.INVALID: ToolCallStatus.INVALID,
    ToolOutcome.ERROR: ToolCallStatus.ERROR,
    ToolOutcome.LIMITED: ToolCallStatus.LIMITED,
}


def current_permissions(
    database: Database, user_id: UUID, company_id: UUID
) -> frozenset[Permission]:
    """Permissions of the user's *current* active membership (empty once revoked)."""
    with database.transaction() as session:
        apply_actor_context(session, user_id)
        row = session.execute(
            select(Membership.role, Company.status)
            .join(Company, Company.id == Membership.company_id)
            .where(
                Membership.user_id == user_id,
                Membership.company_id == company_id,
                Membership.status == MembershipStatus.ACTIVE.value,
            )
        ).first()
    if row is None or row.status != CompanyStatus.ACTIVE.value:
        return frozenset()
    return permissions_for(row.role)


# ------------------------------------------------------------------- records
@dataclass(frozen=True)
class ConversationRecord:
    id: UUID
    title: str
    status: str
    prompt_version: str
    created_at: datetime
    updated_at: datetime
    version: int


@dataclass(frozen=True)
class MessageRecord:
    id: UUID
    role: str
    content: str
    structured: dict[str, Any] | None
    evidence: list[dict[str, Any]]
    run_id: UUID | None
    created_at: datetime


@dataclass(frozen=True)
class ToolCallRecord:
    ordinal: int
    tool_name: str
    tool_class: str
    status: str
    arguments: dict[str, Any]
    result_meta: dict[str, Any]
    result_chars: int
    duration_ms: int
    error_code: str | None
    created_at: datetime


@dataclass(frozen=True)
class RunRecord:
    id: UUID
    conversation_id: UUID
    conversation_title: str | None
    status: str
    provider: str
    model: str
    prompt_version: str
    is_external: bool
    input_tokens: int
    output_tokens: int
    estimated_usage: bool
    cost_usd: Decimal
    model_steps: int
    tool_call_count: int
    provider_calls: int
    error_code: str | None
    validation_warnings: list[str]
    safety_flags: list[str]
    started_at: datetime
    finished_at: datetime | None
    tool_calls: tuple[ToolCallRecord, ...] = ()


@dataclass(frozen=True)
class ProposalRecord:
    id: UUID
    conversation_id: UUID
    run_id: UUID
    kind: str
    action_type: str
    action_class: str
    title: str
    payload: dict[str, Any]
    edited_payload: dict[str, Any] | None
    evidence: list[dict[str, Any]]
    warnings: list[str]
    status: str
    created_by: UUID
    decided_by: UUID | None
    decided_at: datetime | None
    decision_notes: str | None
    execution_result: dict[str, Any] | None
    created_at: datetime
    updated_at: datetime
    version: int

    @property
    def effective_payload(self) -> dict[str, Any]:
        return self.edited_payload if self.edited_payload is not None else self.payload


@dataclass(frozen=True)
class UsageToday:
    tokens: int
    cost_usd: Decimal
    runs: int


@dataclass(frozen=True)
class ConversationDetail:
    conversation: ConversationRecord
    messages: tuple[MessageRecord, ...]
    proposals: tuple[ProposalRecord, ...]
    runs: tuple[RunRecord, ...] = field(default_factory=tuple)


@dataclass(frozen=True)
class RunFinish:
    status: RunStatus
    input_tokens: int
    output_tokens: int
    estimated_usage: bool
    cost_usd: Decimal
    model_steps: int
    tool_call_count: int
    provider_calls: int
    error_code: str | None
    validation_warnings: list[str]
    safety_flags: list[str]
    assistant_text: str | None = None
    structured: dict[str, Any] | None = None
    evidence: list[dict[str, Any]] = field(default_factory=list)
    proposals: list[NewProposal] = field(default_factory=list)


# --------------------------------------------------------------- row mapping
def _conversation(row: AiConversation) -> ConversationRecord:
    return ConversationRecord(
        id=row.id,
        title=row.title,
        status=row.status,
        prompt_version=row.prompt_version,
        created_at=row.created_at,
        updated_at=row.updated_at,
        version=row.version,
    )


def _message(row: AiMessage) -> MessageRecord:
    return MessageRecord(
        id=row.id,
        role=row.role,
        content=row.content,
        structured=row.structured,
        evidence=list(row.evidence),
        run_id=row.run_id,
        created_at=row.created_at,
    )


def _tool_call(row: AiToolCall) -> ToolCallRecord:
    return ToolCallRecord(
        ordinal=row.ordinal,
        tool_name=row.tool_name,
        tool_class=row.tool_class,
        status=row.status,
        arguments=dict(row.arguments),
        result_meta=dict(row.result_meta),
        result_chars=row.result_chars,
        duration_ms=row.duration_ms,
        error_code=row.error_code,
        created_at=row.created_at,
    )


def _run(row: AiRun, title: str | None, calls: tuple[ToolCallRecord, ...] = ()) -> RunRecord:
    return RunRecord(
        id=row.id,
        conversation_id=row.conversation_id,
        conversation_title=title,
        status=row.status,
        provider=row.provider,
        model=row.model,
        prompt_version=row.prompt_version,
        is_external=row.is_external,
        input_tokens=row.input_tokens,
        output_tokens=row.output_tokens,
        estimated_usage=row.estimated_usage,
        cost_usd=row.cost_usd,
        model_steps=row.model_steps,
        tool_call_count=row.tool_call_count,
        provider_calls=row.provider_calls,
        error_code=row.error_code,
        validation_warnings=[str(w) for w in row.validation_warnings],
        safety_flags=[str(f) for f in row.safety_flags],
        started_at=row.started_at,
        finished_at=row.finished_at,
        tool_calls=calls,
    )


def _proposal(row: AiProposal) -> ProposalRecord:
    return ProposalRecord(
        id=row.id,
        conversation_id=row.conversation_id,
        run_id=row.run_id,
        kind=row.kind,
        action_type=row.action_type,
        action_class=row.action_class,
        title=row.title,
        payload=dict(row.payload),
        edited_payload=dict(row.edited_payload) if row.edited_payload is not None else None,
        evidence=[dict(e) for e in row.evidence],
        warnings=[str(w) for w in row.warnings],
        status=row.status,
        created_by=row.created_by,
        decided_by=row.decided_by,
        decided_at=row.decided_at,
        decision_notes=row.decision_notes,
        execution_result=dict(row.execution_result) if row.execution_result else None,
        created_at=row.created_at,
        updated_at=row.updated_at,
        version=row.version,
    )


def _title_from(text: str) -> str:
    cleaned = " ".join(text.split())
    return (cleaned[:77] + "...") if len(cleaned) > 80 else (cleaned or DEFAULT_TITLE)


class AiOfficeService:
    def __init__(self, database: Database) -> None:
        self._database = database

    # ------------------------------------------------------------ conversations
    def create_conversation(
        self,
        *,
        company_id: UUID,
        user_id: UUID,
        title: str | None,
        prompt_version: str,
        request_id: str | None,
    ) -> ConversationRecord:
        with self._database.transaction() as session:
            apply_company_context(session, company_id)
            row = AiConversation(
                id=uuid4(),
                company_id=company_id,
                user_id=user_id,
                title=_title_from(title or "") if title else DEFAULT_TITLE,
                status=ConversationStatus.ACTIVE.value,
                prompt_version=prompt_version,
            )
            session.add(row)
            session.flush()
            record_audit(
                session,
                action=AuditAction.AI_CONVERSATION_CREATED,
                outcome=AuditOutcome.SUCCESS,
                actor_id=user_id,
                company_id=company_id,
                request_id=request_id,
                resource_type="ai_conversation",
                resource_id=str(row.id),
            )
            session.refresh(row)
            return _conversation(row)

    def list_conversations(
        self, *, company_id: UUID, user_id: UUID, limit: int = 30
    ) -> tuple[ConversationRecord, ...]:
        with self._database.transaction() as session:
            apply_company_context(session, company_id)
            rows = session.scalars(
                select(AiConversation)
                .where(
                    AiConversation.company_id == company_id,
                    AiConversation.user_id == user_id,
                    AiConversation.status == ConversationStatus.ACTIVE.value,
                )
                .order_by(AiConversation.updated_at.desc(), AiConversation.id.desc())
                .limit(limit)
            )
            return tuple(_conversation(r) for r in rows)

    def _owned_conversation(
        self, session: Session, *, company_id: UUID, user_id: UUID, conversation_id: UUID
    ) -> AiConversation:
        row = session.execute(
            select(AiConversation).where(
                AiConversation.id == conversation_id,
                AiConversation.company_id == company_id,
                AiConversation.user_id == user_id,
            )
        ).scalar_one_or_none()
        if row is None:
            raise NotFoundError("The conversation does not exist.")
        return row

    def get_conversation(
        self, *, company_id: UUID, user_id: UUID, conversation_id: UUID
    ) -> ConversationDetail:
        with self._database.transaction() as session:
            apply_company_context(session, company_id)
            conversation = self._owned_conversation(
                session, company_id=company_id, user_id=user_id, conversation_id=conversation_id
            )
            messages = session.scalars(
                select(AiMessage)
                .where(
                    AiMessage.company_id == company_id,
                    AiMessage.conversation_id == conversation_id,
                )
                .order_by(AiMessage.created_at, AiMessage.id)
            )
            proposals = session.scalars(
                select(AiProposal)
                .where(
                    AiProposal.company_id == company_id,
                    AiProposal.conversation_id == conversation_id,
                )
                .order_by(AiProposal.created_at, AiProposal.id)
            )
            return ConversationDetail(
                conversation=_conversation(conversation),
                messages=tuple(_message(m) for m in messages),
                proposals=tuple(_proposal(p) for p in proposals),
            )

    def recent_messages(
        self, *, company_id: UUID, conversation_id: UUID, limit: int
    ) -> list[tuple[str, str]]:
        """The last ``limit`` messages, oldest first, as (role, text) for the context."""
        with self._database.transaction() as session:
            apply_company_context(session, company_id)
            rows = list(
                session.scalars(
                    select(AiMessage)
                    .where(
                        AiMessage.company_id == company_id,
                        AiMessage.conversation_id == conversation_id,
                    )
                    .order_by(AiMessage.created_at.desc(), AiMessage.id.desc())
                    .limit(limit)
                )
            )
        return [(r.role, r.content) for r in reversed(rows)]

    # ------------------------------------------------------------------- usage
    def usage_today(self, *, company_id: UUID) -> UsageToday:
        start = datetime.now(UTC).replace(hour=0, minute=0, second=0, microsecond=0)
        with self._database.transaction() as session:
            apply_company_context(session, company_id)
            tokens, cost, runs = session.execute(
                select(
                    func.coalesce(func.sum(AiRun.input_tokens + AiRun.output_tokens), 0),
                    func.coalesce(func.sum(AiRun.cost_usd), 0),
                    func.count(AiRun.id),
                ).where(AiRun.company_id == company_id, AiRun.started_at >= start)
            ).one()
        return UsageToday(tokens=int(tokens), cost_usd=Decimal(cost), runs=int(runs))

    def recent_run_count(self, *, company_id: UUID, user_id: UUID, seconds: int = 60) -> int:
        since = datetime.now(UTC) - timedelta(seconds=seconds)
        with self._database.transaction() as session:
            apply_company_context(session, company_id)
            return int(
                session.execute(
                    select(func.count(AiRun.id)).where(
                        AiRun.company_id == company_id,
                        AiRun.user_id == user_id,
                        AiRun.started_at >= since,
                    )
                ).scalar_one()
            )

    def expire_stale_runs(self, *, company_id: UUID, older_than_seconds: int) -> int:
        """Mark a run that never finished (a restart, a crash) as failed."""
        cutoff = datetime.now(UTC) - timedelta(seconds=older_than_seconds)
        with self._database.transaction() as session:
            apply_company_context(session, company_id)
            result = session.execute(
                update(AiRun)
                .where(
                    AiRun.company_id == company_id,
                    AiRun.status == RunStatus.RUNNING.value,
                    AiRun.started_at < cutoff,
                )
                .values(
                    status=RunStatus.FAILED.value,
                    error_code="AI_RUN_ABANDONED",
                    finished_at=datetime.now(UTC),
                )
            )
            return int(result.rowcount or 0)  # type: ignore[attr-defined]

    # -------------------------------------------------------------------- runs
    def start_run(
        self,
        *,
        company_id: UUID,
        user_id: UUID,
        conversation_id: UUID,
        user_text: str,
        provider: str,
        model: str,
        prompt_version: str,
        is_external: bool,
        request_id: str | None,
    ) -> tuple[RunRecord, MessageRecord]:
        with self._database.transaction() as session:
            apply_company_context(session, company_id)
            conversation = self._owned_conversation(
                session, company_id=company_id, user_id=user_id, conversation_id=conversation_id
            )
            run = AiRun(
                id=uuid4(),
                company_id=company_id,
                conversation_id=conversation_id,
                user_id=user_id,
                status=RunStatus.RUNNING.value,
                provider=provider,
                model=model,
                prompt_version=prompt_version,
                is_external=is_external,
                request_id=request_id,
            )
            session.add(run)
            session.flush()
            message = AiMessage(
                id=uuid4(),
                company_id=company_id,
                conversation_id=conversation_id,
                run_id=run.id,
                role=MessageRole.USER.value,
                content=user_text,
            )
            session.add(message)
            if conversation.title == DEFAULT_TITLE:
                conversation.title = _title_from(user_text)
            conversation.updated_at = datetime.now(UTC)
            conversation.version += 1
            session.flush()
            session.refresh(run)
            session.refresh(message)
            return _run(run, conversation.title), _message(message)

    def record_tool_call(
        self,
        *,
        company_id: UUID,
        user_id: UUID,
        run_id: UUID,
        ordinal: int,
        execution: ToolExecution,
        request_id: str | None,
    ) -> None:
        with self._database.transaction() as session:
            apply_company_context(session, company_id)
            session.add(
                AiToolCall(
                    id=uuid4(),
                    company_id=company_id,
                    run_id=run_id,
                    ordinal=ordinal,
                    tool_name=execution.tool_name,
                    tool_class=str(execution.tool_class),
                    status=str(_TOOL_STATUS[execution.outcome]),
                    arguments=execution.arguments,
                    result_meta=execution.result_meta,
                    result_chars=execution.result_chars,
                    duration_ms=execution.duration_ms,
                    error_code=execution.error_code,
                )
            )
            blocked = execution.tool_class is ToolClass.BLOCKED
            denied = execution.outcome in {ToolOutcome.DENIED, ToolOutcome.INVALID}
            record_audit(
                session,
                action=(
                    AuditAction.AI_ACTION_BLOCKED
                    if blocked
                    else AuditAction.AI_TOOL_DENIED
                    if denied
                    else AuditAction.AI_TOOL_EXECUTED
                ),
                outcome=(
                    AuditOutcome.DENIED
                    if blocked or execution.outcome is ToolOutcome.DENIED
                    else AuditOutcome.SUCCESS
                    if execution.outcome is ToolOutcome.OK
                    else AuditOutcome.FAILURE
                ),
                actor_type=AuditActorType.AGENT,
                actor_id=user_id,
                company_id=company_id,
                request_id=request_id,
                resource_type="ai_run",
                resource_id=str(run_id),
                details={
                    "tool": execution.tool_name,
                    "tool_class": str(execution.tool_class),
                    "status": str(execution.outcome),
                    "error": execution.error_code,
                    "arguments": execution.arguments,
                    "result_chars": execution.result_chars,
                    "safety_flags": list(execution.safety_flags),
                    "on_behalf_of": str(user_id),
                },
            )

    def finish_run(
        self,
        *,
        company_id: UUID,
        user_id: UUID,
        run_id: UUID,
        finish: RunFinish,
        request_id: str | None,
    ) -> None:
        now = datetime.now(UTC)
        with self._database.transaction() as session:
            apply_company_context(session, company_id)
            run = session.execute(
                select(AiRun)
                .where(AiRun.id == run_id, AiRun.company_id == company_id)
                .with_for_update()
            ).scalar_one_or_none()
            if run is None:
                raise NotFoundError("The run does not exist.")
            if run.status != RunStatus.RUNNING.value:
                return
            run.status = finish.status.value
            run.input_tokens = finish.input_tokens
            run.output_tokens = finish.output_tokens
            run.estimated_usage = finish.estimated_usage
            run.cost_usd = finish.cost_usd.quantize(_COST_QUANTUM)
            run.model_steps = finish.model_steps
            run.tool_call_count = finish.tool_call_count
            run.provider_calls = finish.provider_calls
            run.error_code = finish.error_code
            run.validation_warnings = finish.validation_warnings
            run.safety_flags = finish.safety_flags
            run.finished_at = now
            if finish.status is RunStatus.COMPLETED and finish.assistant_text is not None:
                session.add(
                    AiMessage(
                        id=uuid4(),
                        company_id=company_id,
                        conversation_id=run.conversation_id,
                        run_id=run.id,
                        role=MessageRole.ASSISTANT.value,
                        content=finish.assistant_text or "(no summary)",
                        structured=finish.structured,
                        evidence=finish.evidence,
                    )
                )
                for proposal in finish.proposals:
                    session.add(
                        AiProposal(
                            id=uuid4(),
                            company_id=company_id,
                            conversation_id=run.conversation_id,
                            run_id=run.id,
                            created_by=user_id,
                            kind=proposal.kind.value,
                            action_type=proposal.action_type.value,
                            action_class=str(proposal.action_class),
                            title=proposal.title,
                            payload=proposal.payload,
                            evidence=proposal.evidence,
                            warnings=proposal.warnings,
                        )
                    )
            conversation = session.get(AiConversation, run.conversation_id)
            if conversation is not None:
                conversation.updated_at = now
                conversation.version += 1
            action = {
                RunStatus.COMPLETED: AuditAction.AI_RUN_COMPLETED,
                RunStatus.CANCELLED: AuditAction.AI_RUN_CANCELLED,
            }.get(finish.status, AuditAction.AI_RUN_FAILED)
            record_audit(
                session,
                action=action,
                outcome=(
                    AuditOutcome.SUCCESS
                    if finish.status is RunStatus.COMPLETED
                    else AuditOutcome.FAILURE
                ),
                actor_type=AuditActorType.AGENT,
                actor_id=user_id,
                company_id=company_id,
                request_id=request_id,
                resource_type="ai_run",
                resource_id=str(run_id),
                details={
                    "provider": run.provider,
                    "model": run.model,
                    "prompt_version": run.prompt_version,
                    "input_tokens": finish.input_tokens,
                    "output_tokens": finish.output_tokens,
                    "tool_calls": finish.tool_call_count,
                    "error": finish.error_code,
                    "safety_flags": finish.safety_flags,
                    "validation_warnings": finish.validation_warnings,
                    "proposals": len(finish.proposals),
                },
            )

    def get_run(self, *, company_id: UUID, user_id: UUID, run_id: UUID) -> RunRecord:
        with self._database.transaction() as session:
            apply_company_context(session, company_id)
            row = session.execute(
                select(AiRun, AiConversation.title)
                .join(
                    AiConversation,
                    (AiConversation.id == AiRun.conversation_id)
                    & (AiConversation.company_id == AiRun.company_id),
                )
                .where(
                    AiRun.id == run_id,
                    AiRun.company_id == company_id,
                    AiRun.user_id == user_id,
                )
            ).one_or_none()
            if row is None:
                raise NotFoundError("The run does not exist.")
            run, title = row
            calls = tuple(
                _tool_call(c)
                for c in session.scalars(
                    select(AiToolCall)
                    .where(AiToolCall.company_id == company_id, AiToolCall.run_id == run_id)
                    .order_by(AiToolCall.ordinal)
                )
            )
            return _run(run, title, calls)

    def assistant_message_for_run(self, *, company_id: UUID, run_id: UUID) -> MessageRecord | None:
        with self._database.transaction() as session:
            apply_company_context(session, company_id)
            row = session.scalars(
                select(AiMessage).where(
                    AiMessage.company_id == company_id,
                    AiMessage.run_id == run_id,
                    AiMessage.role == MessageRole.ASSISTANT.value,
                )
            ).first()
            return _message(row) if row is not None else None

    def list_activity(
        self, *, company_id: UUID, user_id: UUID, limit: int = 25
    ) -> tuple[RunRecord, ...]:
        with self._database.transaction() as session:
            apply_company_context(session, company_id)
            rows = session.execute(
                select(AiRun, AiConversation.title)
                .join(
                    AiConversation,
                    (AiConversation.id == AiRun.conversation_id)
                    & (AiConversation.company_id == AiRun.company_id),
                )
                .where(AiRun.company_id == company_id, AiRun.user_id == user_id)
                .order_by(AiRun.started_at.desc(), AiRun.id.desc())
                .limit(limit)
            ).all()
            return tuple(_run(run, title) for run, title in rows)

    # --------------------------------------------------------------- proposals
    def list_proposals(
        self,
        *,
        company_id: UUID,
        status: str | None,
        conversation_id: UUID | None,
        run_id: UUID | None = None,
        limit: int = 50,
    ) -> tuple[ProposalRecord, ...]:
        with self._database.transaction() as session:
            apply_company_context(session, company_id)
            query = select(AiProposal).where(AiProposal.company_id == company_id)
            if status:
                query = query.where(AiProposal.status == status)
            if conversation_id:
                query = query.where(AiProposal.conversation_id == conversation_id)
            if run_id:
                query = query.where(AiProposal.run_id == run_id)
            rows = session.scalars(
                query.order_by(AiProposal.created_at.desc(), AiProposal.id.desc()).limit(limit)
            )
            return tuple(_proposal(r) for r in rows)

    def get_proposal(self, *, company_id: UUID, proposal_id: UUID) -> ProposalRecord:
        with self._database.transaction() as session:
            apply_company_context(session, company_id)
            return _proposal(self._load_proposal(session, company_id, proposal_id))

    @staticmethod
    def _load_proposal(
        session: Session, company_id: UUID, proposal_id: UUID, *, lock: bool = False
    ) -> AiProposal:
        query = select(AiProposal).where(
            AiProposal.id == proposal_id, AiProposal.company_id == company_id
        )
        if lock:
            query = query.with_for_update()
        row = session.execute(query).scalar_one_or_none()
        if row is None:
            raise NotFoundError("The proposal does not exist.")
        return row

    def edit_proposal(
        self,
        *,
        company_id: UUID,
        user_id: UUID,
        proposal_id: UUID,
        expected_version: int,
        patch: dict[str, Any],
        request_id: str | None,
    ) -> ProposalRecord:
        permissions = current_permissions(self._database, user_id, company_id)
        if Permission.TRADE_WRITE not in permissions:
            raise ForbiddenError()
        with self._database.transaction() as session:
            apply_company_context(session, company_id)
            row = self._load_proposal(session, company_id, proposal_id, lock=True)
            if row.status != ProposalStatus.PROPOSED.value:
                raise ProposalStateError("Only a proposal that is still pending can be edited.")
            if row.version != expected_version:
                raise VersionConflictError()
            current = row.edited_payload if row.edited_payload is not None else row.payload
            row.edited_payload = apply_edit(row.kind, dict(current), patch)
            row.title = str(row.edited_payload.get("title", row.title))[:200]
            if "EDITED_BY_USER" not in row.warnings:
                row.warnings = [*row.warnings, "EDITED_BY_USER"]
            row.updated_at = datetime.now(UTC)
            row.version += 1
            session.flush()
            record_audit(
                session,
                action=AuditAction.AI_PROPOSAL_EDITED,
                outcome=AuditOutcome.SUCCESS,
                actor_id=user_id,
                company_id=company_id,
                request_id=request_id,
                resource_type="ai_proposal",
                resource_id=str(row.id),
                details={"fields": sorted(patch), "version": row.version},
            )
            return _proposal(row)

    def decide_proposal(
        self,
        *,
        company_id: UUID,
        user_id: UUID,
        proposal_id: UUID,
        expected_version: int,
        approve: bool,
        notes: str | None,
        acknowledge_warnings: bool,
        request_id: str | None,
    ) -> ProposalRecord:
        """Approve or reject. Permissions, state, version and target are re-validated here."""
        spec = None
        if approve:
            # Looked up before any change so an unsupported action never half-executes.
            row_peek = self.get_proposal(company_id=company_id, proposal_id=proposal_id)
            if row_peek.action_type not in ACTIONS:
                raise ActionNotSupportedError()
            spec = ACTIONS[row_peek.action_type]
        permissions = current_permissions(self._database, user_id, company_id)
        required = spec.permission if spec else Permission.TRADE_WRITE
        if required not in permissions:
            self._audit_denied(company_id, user_id, proposal_id, request_id)
            raise ForbiddenError()
        with self._database.transaction() as session:
            apply_company_context(session, company_id)
            row = self._load_proposal(session, company_id, proposal_id, lock=True)
            if row.status != ProposalStatus.PROPOSED.value:
                raise ProposalStateError("This proposal has already been decided.")
            if row.version != expected_version:
                raise VersionConflictError()
            result: dict[str, Any]
            if approve:
                if BLOCKING_WARNINGS & set(row.warnings) and not acknowledge_warnings:
                    raise ProposalStateError(
                        "This proposal contains figures that no source supports. "
                        "Review it and confirm with acknowledge_warnings to approve."
                    )
                payload = row.edited_payload if row.edited_payload is not None else row.payload
                self._revalidate_target(session, company_id, payload)
                result = self._execute(row)
            else:
                result = {"effect": "NONE", "note": "Rejected by a person; nothing was changed."}
            now = datetime.now(UTC)
            row.status = (ProposalStatus.APPROVED if approve else ProposalStatus.REJECTED).value
            row.decided_by = user_id
            row.decided_at = now
            row.decision_notes = (notes or "").strip()[:2000] or None
            row.execution_result = result
            row.updated_at = now
            row.version += 1
            session.flush()
            record_audit(
                session,
                action=(
                    AuditAction.AI_PROPOSAL_APPROVED
                    if approve
                    else AuditAction.AI_PROPOSAL_REJECTED
                ),
                outcome=AuditOutcome.SUCCESS,
                actor_id=user_id,
                company_id=company_id,
                request_id=request_id,
                resource_type="ai_proposal",
                resource_id=str(row.id),
                details={
                    "kind": row.kind,
                    "action_type": row.action_type,
                    "effect": result.get("effect"),
                    "acknowledged_warnings": bool(acknowledge_warnings),
                },
            )
            return _proposal(row)

    def _audit_denied(
        self, company_id: UUID, user_id: UUID, proposal_id: UUID, request_id: str | None
    ) -> None:
        with self._database.transaction() as session:
            apply_company_context(session, company_id)
            record_audit(
                session,
                action=AuditAction.ACCESS_DENIED,
                outcome=AuditOutcome.DENIED,
                actor_id=user_id,
                company_id=company_id,
                request_id=request_id,
                resource_type="ai_proposal",
                resource_id=str(proposal_id),
                details={"reason": "permission_required"},
            )

    @staticmethod
    def _revalidate_target(session: Session, company_id: UUID, payload: dict[str, Any]) -> None:
        target = payload.get("target")
        if not isinstance(target, dict):
            return
        model = _TARGET_MODELS.get(str(target.get("entity_type")))
        if model is None:
            raise ConflictError("The task refers to a record type that cannot be verified.")
        try:
            target_id = UUID(str(target.get("entity_id")))
        except ValueError:
            raise ConflictError("The task refers to an invalid record.") from None
        exists = session.execute(
            select(model.id).where(model.id == target_id, model.company_id == company_id)
        ).first()
        if exists is None:
            raise ConflictError("The record this task refers to no longer exists.")

    @staticmethod
    def _execute(row: AiProposal) -> dict[str, Any]:
        """Run the one registered, side-effect-free executor for the action type."""
        spec = ACTIONS.get(row.action_type)
        if spec is None:
            raise ActionNotSupportedError()
        if spec.action_type.value == "DRAFT_REVIEW":
            return {
                "effect": "DRAFT_APPROVED_FOR_HUMAN_USE",
                "sent": False,
                "note": "A person approved the wording. No message was sent.",
            }
        return {
            "effect": "OPERATOR_TASK_RECORDED",
            "note": "Recorded as a follow-up for the team. No business record was changed.",
        }

"""Presenters from AI Office service records to API schemas."""

from __future__ import annotations

from typing import Any

from pydantic import ValidationError

from app.api.v1.schemas.ai import (
    ConversationResponse,
    EvidenceResponse,
    MessageResponse,
    ProposalResponse,
    RunResponse,
    StructuredAnswerResponse,
    ToolCallResponse,
)
from app.services.ai_office import (
    ConversationRecord,
    MessageRecord,
    ProposalRecord,
    RunRecord,
    ToolCallRecord,
)

_EFFECTS = {
    "DRAFT": (
        "Approving records that a person reviewed this wording. Nothing is sent, "
        "and the customer or supplier is not contacted."
    ),
    "TASK": (
        "Approving records this follow-up for the team. No deal, order, payment "
        "or accounting record is created or changed."
    ),
}


def _evidence(items: list[dict[str, Any]]) -> list[EvidenceResponse]:
    result: list[EvidenceResponse] = []
    for item in items:
        try:
            result.append(EvidenceResponse.model_validate(item))
        except ValidationError:
            continue
    return result


def conversation_response(record: ConversationRecord) -> ConversationResponse:
    return ConversationResponse(
        id=record.id,
        title=record.title,
        status=record.status,
        prompt_version=record.prompt_version,
        created_at=record.created_at,
        updated_at=record.updated_at,
        version=record.version,
    )


def message_response(record: MessageRecord) -> MessageResponse:
    structured: StructuredAnswerResponse | None = None
    if record.structured is not None:
        try:
            structured = StructuredAnswerResponse.model_validate(record.structured)
        except ValidationError:
            structured = None
    return MessageResponse(
        id=record.id,
        role=record.role,
        content=record.content,
        structured=structured,
        evidence=_evidence(record.evidence),
        run_id=record.run_id,
        created_at=record.created_at,
    )


def tool_call_response(record: ToolCallRecord) -> ToolCallResponse:
    raw_ids = record.result_meta.get("evidence")
    return ToolCallResponse(
        ordinal=record.ordinal,
        tool_name=record.tool_name,
        tool_class=record.tool_class,
        status=record.status,
        arguments=record.arguments,
        evidence_ids=[str(i) for i in raw_ids] if isinstance(raw_ids, list) else [],
        result_chars=record.result_chars,
        duration_ms=record.duration_ms,
        error_code=record.error_code,
        created_at=record.created_at,
    )


def proposal_response(record: ProposalRecord) -> ProposalResponse:
    return ProposalResponse(
        id=record.id,
        conversation_id=record.conversation_id,
        run_id=record.run_id,
        kind=record.kind,
        action_type=record.action_type,
        action_class=record.action_class,
        title=record.title,
        payload=record.effective_payload,
        edited=record.edited_payload is not None,
        evidence=_evidence(record.evidence),
        warnings=record.warnings,
        status=record.status,
        created_by=record.created_by,
        decided_by=record.decided_by,
        decided_at=record.decided_at,
        decision_notes=record.decision_notes,
        execution_result=record.execution_result,
        effect_summary=_EFFECTS[record.kind],
        created_at=record.created_at,
        updated_at=record.updated_at,
        version=record.version,
    )


def run_response(
    record: RunRecord,
    *,
    message: MessageRecord | None = None,
    proposals: tuple[ProposalRecord, ...] = (),
) -> RunResponse:
    return RunResponse(
        id=record.id,
        conversation_id=record.conversation_id,
        conversation_title=record.conversation_title,
        status=record.status,
        provider=record.provider,
        model=record.model,
        prompt_version=record.prompt_version,
        is_external=record.is_external,
        input_tokens=record.input_tokens,
        output_tokens=record.output_tokens,
        estimated_usage=record.estimated_usage,
        cost_usd=str(record.cost_usd),
        model_steps=record.model_steps,
        tool_call_count=record.tool_call_count,
        provider_calls=record.provider_calls,
        error_code=record.error_code,
        validation_warnings=record.validation_warnings,
        safety_flags=record.safety_flags,
        started_at=record.started_at,
        finished_at=record.finished_at,
        tool_calls=[tool_call_response(c) for c in record.tool_calls],
        message=message_response(message) if message is not None else None,
        proposals=[proposal_response(p) for p in proposals],
    )

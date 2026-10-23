"""Stage 6 AI Office API schemas.

Amounts that originate from business records are decimal *strings* inside evidence
facts, exactly as the deterministic services produced them. ``read_only`` style
guarantees are literals so a client can rely on them: the AI Office never posts,
sends, signs, pays or accepts anything.
"""

from __future__ import annotations

from datetime import datetime
from typing import Any, Literal
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field

BasisValue = Literal["CONFIRMED_SOURCE", "ESTIMATED", "INCOMPLETE", "AI_INFERENCE", "NOT_AVAILABLE"]
RunStatusValue = Literal["RUNNING", "COMPLETED", "FAILED", "CANCELLED"]
ToolClassValue = Literal["READ_ONLY", "DRAFT_PROPOSAL", "REQUIRES_HUMAN_APPROVAL", "BLOCKED"]
ProposalStatusValue = Literal["PROPOSED", "APPROVED", "REJECTED"]
ProposalKindValue = Literal["DRAFT", "TASK"]
PriorityValue = Literal["HIGH", "MEDIUM", "LOW"]
DraftKindValue = Literal["RFQ_EMAIL", "SUPPLIER_FOLLOW_UP", "CUSTOMER_UPDATE", "OTHER"]
ProviderModeValue = Literal["DISABLED", "MOCK", "REAL"]


class AiModel(BaseModel):
    # Fields with defaults are always present in a response, so the contract (and the
    # generated TypeScript types) mark them required instead of optional.
    model_config = ConfigDict(extra="ignore", json_schema_serialization_defaults_required=True)


class AiRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")


# ------------------------------------------------------------------ evidence
class EvidenceResponse(AiModel):
    id: str
    entity_type: str
    entity_id: str
    reference: str
    label: str
    basis: BasisValue
    as_of: str | None = None
    completeness: str
    facts: dict[str, str] = Field(default_factory=dict)
    warnings: list[str] = Field(default_factory=list)
    tool: str
    href: str | None = Field(
        default=None, description="Application route of the cited record, computed by the server."
    )


class FigureResponse(AiModel):
    label: str
    value: str
    currency: str | None = None
    evidence: str | None = None


class FindingResponse(AiModel):
    claim: str
    basis: BasisValue
    evidence: list[str] = Field(default_factory=list)
    figures: list[FigureResponse] = Field(default_factory=list)
    warnings: list[str] = Field(default_factory=list)


class RecommendationResponse(AiModel):
    action: str
    priority: PriorityValue
    rationale: str = ""
    evidence: list[str] = Field(default_factory=list)
    warnings: list[str] = Field(default_factory=list)


class MissingInputResponse(AiModel):
    item: str
    evidence: list[str] = Field(default_factory=list)


class DraftResponse(AiModel):
    kind: DraftKindValue
    title: str
    body: str
    evidence: list[str] = Field(default_factory=list)
    warnings: list[str] = Field(default_factory=list)


class TaskTargetResponse(AiModel):
    entity_type: str
    entity_id: str


class TaskProposalResponse(AiModel):
    title: str
    rationale: str = ""
    priority: PriorityValue
    target: TaskTargetResponse | None = None
    evidence: list[str] = Field(default_factory=list)
    warnings: list[str] = Field(default_factory=list)


class StructuredAnswerResponse(AiModel):
    summary: str = ""
    findings: list[FindingResponse] = Field(default_factory=list)
    recommendations: list[RecommendationResponse] = Field(default_factory=list)
    missing_inputs: list[MissingInputResponse] = Field(default_factory=list)
    drafts: list[DraftResponse] = Field(default_factory=list)
    task_proposals: list[TaskProposalResponse] = Field(default_factory=list)
    warnings: list[str] = Field(default_factory=list)


# ----------------------------------------------------------------- messaging
class MessageResponse(AiModel):
    id: UUID
    role: Literal["USER", "ASSISTANT"]
    content: str
    structured: StructuredAnswerResponse | None = None
    evidence: list[EvidenceResponse] = Field(default_factory=list)
    run_id: UUID | None = None
    created_at: datetime


class ConversationResponse(AiModel):
    id: UUID
    title: str
    status: Literal["ACTIVE", "ARCHIVED"]
    prompt_version: str
    created_at: datetime
    updated_at: datetime
    version: int


class ConversationListResponse(AiModel):
    items: list[ConversationResponse]


class CreateConversationRequest(AiRequest):
    title: str | None = Field(default=None, max_length=160)


class SendMessageRequest(AiRequest):
    content: str = Field(min_length=1, max_length=20_000)


class ToolCallResponse(AiModel):
    ordinal: int
    tool_name: str
    tool_class: ToolClassValue
    status: Literal["OK", "DENIED", "INVALID", "ERROR", "LIMITED"]
    arguments: dict[str, Any] = Field(default_factory=dict)
    evidence_ids: list[str] = Field(default_factory=list)
    result_chars: int
    duration_ms: int
    error_code: str | None = None
    created_at: datetime


class ProposalResponse(AiModel):
    id: UUID
    conversation_id: UUID
    run_id: UUID
    kind: ProposalKindValue
    action_type: Literal["DRAFT_REVIEW", "OPERATOR_TASK"]
    action_class: ToolClassValue
    title: str
    payload: dict[str, Any]
    edited: bool
    evidence: list[EvidenceResponse] = Field(default_factory=list)
    warnings: list[str] = Field(default_factory=list)
    status: ProposalStatusValue
    created_by: UUID
    decided_by: UUID | None = None
    decided_at: datetime | None = None
    decision_notes: str | None = None
    execution_result: dict[str, Any] | None = None
    effect_summary: str = Field(
        description="What approving this proposal does. Never sends, signs, pays or posts."
    )
    created_at: datetime
    updated_at: datetime
    version: int


class ProposalListResponse(AiModel):
    items: list[ProposalResponse]


class ConversationDetailResponse(AiModel):
    conversation: ConversationResponse
    messages: list[MessageResponse]
    proposals: list[ProposalResponse]


class RunResponse(AiModel):
    id: UUID
    conversation_id: UUID
    conversation_title: str | None = None
    status: RunStatusValue
    provider: str
    model: str
    prompt_version: str
    is_external: bool
    input_tokens: int
    output_tokens: int
    estimated_usage: bool
    cost_usd: str
    model_steps: int
    tool_call_count: int
    provider_calls: int
    error_code: str | None = None
    validation_warnings: list[str] = Field(default_factory=list)
    safety_flags: list[str] = Field(default_factory=list)
    started_at: datetime
    finished_at: datetime | None = None
    tool_calls: list[ToolCallResponse] = Field(default_factory=list)
    message: MessageResponse | None = None
    proposals: list[ProposalResponse] = Field(default_factory=list)


class SendMessageResponse(AiModel):
    run: RunResponse
    message: MessageResponse


class ActivityResponse(AiModel):
    items: list[RunResponse]


class ProposalEditRequest(AiRequest):
    title: str | None = Field(default=None, max_length=200)
    body: str | None = Field(default=None, max_length=6_000)
    draft_kind: DraftKindValue | None = None
    rationale: str | None = Field(default=None, max_length=1_200)
    priority: PriorityValue | None = None


class ProposalDecisionRequest(AiRequest):
    notes: str | None = Field(default=None, max_length=2_000)
    acknowledge_warnings: bool = False


# ---------------------------------------------------------------- status/tools
class AiLimitsResponse(AiModel):
    max_model_steps: int
    max_tool_calls_per_request: int
    max_output_tokens: int
    max_request_tokens: int
    max_user_message_chars: int
    max_tool_result_chars: int
    max_concurrent_runs: int
    max_runs_per_user_per_minute: int
    request_timeout_seconds: float
    run_deadline_seconds: float


class AiUsageResponse(AiModel):
    tokens_today: int
    cost_usd_today: str
    runs_today: int
    daily_token_budget: int
    daily_cost_budget_usd: str


class AiStatusResponse(AiModel):
    enabled: bool
    mode: ProviderModeValue
    provider: str | None = None
    model: str | None = None
    external_processing: bool
    prompt_version: str
    limits: AiLimitsResponse
    usage: AiUsageResponse
    notice: str
    can_approve: bool
    read_only_tools: Literal[True] = True
    accounting_writes_enabled: Literal[False] = False
    sends_messages: Literal[False] = False


class AiToolResponse(AiModel):
    name: str
    description: str
    tool_class: ToolClassValue
    permission: str
    available: bool
    parameters: dict[str, Any]


class BlockedActionResponse(AiModel):
    name: str
    reason: str


class ActionClassResponse(AiModel):
    name: ToolClassValue
    description: str


class AiToolListResponse(AiModel):
    tools: list[AiToolResponse]
    blocked_actions: list[BlockedActionResponse]
    classes: list[ActionClassResponse]


class SuggestionResponse(AiModel):
    id: str
    title: str
    prompt: str


class SuggestionListResponse(AiModel):
    items: list[SuggestionResponse]

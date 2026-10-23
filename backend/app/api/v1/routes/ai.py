"""AI Office endpoints — the Trade Director.

* Every route needs a session, an active company and ``company.view``; deciding on a
  proposal needs ``trade.write`` (re-checked against the live membership by the service).
* A question is accepted with ``202`` and answered in the background: the client polls
  ``GET /ai/runs/{id}`` for tool progress and the validated answer, and may cancel.
* The company is always the session's active company; no request field names one.
* The AI Office is read-only toward the business. Approving a proposal records a human
  decision; it never sends, signs, pays, posts or accepts anything.
"""

from __future__ import annotations

import threading
from typing import Annotated
from uuid import UUID

from fastapi import APIRouter, BackgroundTasks, Depends, Header, Request, Response, status

from app.ai.director import AIRuntime, RunRequest
from app.ai.prompts import PROMPT_VERSION
from app.ai.proposals import ACTIONS
from app.ai.tools.registry import BLOCKED_ACTIONS, ToolClass
from app.api.deps import app_settings, get_database
from app.api.security import active_company_id, require_company_permission
from app.api.v1.etag import etag_for, require_if_match
from app.api.v1.presenters_ai import (
    conversation_response,
    message_response,
    proposal_response,
    run_response,
)
from app.api.v1.schemas.ai import (
    ActionClassResponse,
    ActivityResponse,
    AiLimitsResponse,
    AiStatusResponse,
    AiToolListResponse,
    AiToolResponse,
    AiUsageResponse,
    BlockedActionResponse,
    ConversationDetailResponse,
    ConversationListResponse,
    ConversationResponse,
    CreateConversationRequest,
    ProposalDecisionRequest,
    ProposalEditRequest,
    ProposalListResponse,
    ProposalResponse,
    ProposalStatusValue,
    RunResponse,
    SendMessageRequest,
    SendMessageResponse,
    SuggestionListResponse,
    SuggestionResponse,
)
from app.api.v1.schemas.errors import ErrorEnvelope
from app.core.config import Settings
from app.core.context import get_request_id
from app.core.errors import ConflictError
from app.db.engine import Database
from app.security.permissions import Permission
from app.services.ai_office import ProposalRecord
from app.services.auth import SessionContext

router = APIRouter(prefix="/ai", tags=["ai"])

_RUNTIME_LOCK = threading.Lock()

_CLASS_DESCRIPTIONS: dict[ToolClass, str] = {
    ToolClass.READ_ONLY: (
        "Reads existing records through the same services and permissions as the API."
    ),
    ToolClass.DRAFT_PROPOSAL: "Produces a written draft for a person to review. Nothing is sent.",
    ToolClass.REQUIRES_HUMAN_APPROVAL: (
        "A suggested follow-up that only a person can approve; no business record changes."
    ),
    ToolClass.BLOCKED: "Never available to the AI, whatever the user's role.",
}

_SUGGESTIONS = (
    ("deals", "Analyse active deals", "Analyse my active deals and tell me which need attention."),
    (
        "quotes",
        "Compare supplier quotes",
        "Compare the supplier quotes for my most recent deal and explain the differences.",
    ),
    (
        "pricing",
        "Explain pricing and missing inputs",
        "Explain the landed cost and margin of my latest pricing scenario and list missing inputs.",
    ),
    (
        "shipments",
        "Check order and shipment progress",
        "Which sales orders have delayed or incomplete shipments?",
    ),
    (
        "finance",
        "Review financial exceptions",
        "Explain the open financial reconciliation exceptions and what evidence is missing.",
    ),
    (
        "draft",
        "Draft a supplier follow-up",
        "Draft a follow-up message to suppliers about the quotes for my latest deal.",
    ),
)


def get_ai_runtime(
    request: Request,
    settings: Annotated[Settings, Depends(app_settings)],
    database: Annotated[Database, Depends(get_database)],
) -> AIRuntime:
    runtime: AIRuntime | None = getattr(request.app.state, "ai_runtime", None)
    if runtime is None:
        with _RUNTIME_LOCK:
            runtime = getattr(request.app.state, "ai_runtime", None)
            if runtime is None:
                runtime = AIRuntime(settings, database)
                request.app.state.ai_runtime = runtime
    return runtime


Runtime = Annotated[AIRuntime, Depends(get_ai_runtime)]
ViewContext = Annotated[
    SessionContext, Depends(require_company_permission(Permission.COMPANY_VIEW))
]
WriteContext = Annotated[
    SessionContext, Depends(require_company_permission(Permission.TRADE_WRITE))
]


def _no_store(response: Response) -> None:
    response.headers["Cache-Control"] = "no-store"
    response.headers["Vary"] = "Cookie"


def _caller(context: SessionContext) -> RunRequest:
    membership = context.active_membership
    assert membership is not None  # noqa: S101 - guaranteed by require_company_permission
    return RunRequest(
        company_id=active_company_id(context),
        user_id=context.user.user_id,
        company_name=membership.company_name,
        company_currency=membership.default_currency,
        role=str(membership.role),
        request_id=get_request_id(),
    )


# --------------------------------------------------------------------- status
@router.get(
    "/status",
    response_model=AiStatusResponse,
    summary="AI provider status, limits and today's usage",
    description=(
        "Never returns a credential or the provider URL. ``mode`` says whether answers "
        "come from the offline mock, a real provider or nothing (disabled)."
    ),
)
def ai_status(response: Response, context: ViewContext, runtime: Runtime) -> AiStatusResponse:
    _no_store(response)
    settings = runtime.settings
    provider = runtime.provider if runtime.enabled else None
    usage = runtime.office.usage_today(company_id=active_company_id(context))
    if provider is None:
        mode, notice = "DISABLED", "The AI Office is disabled for this deployment."
    elif provider.name == "mock":
        mode = "MOCK"
        notice = (
            "Answers come from a deterministic offline test provider, not a language model. "
            "Records and figures are real; the wording is templated."
        )
    else:
        mode = "REAL"
        notice = (
            "Your questions and the business records the tools return are sent to the "
            f"configured provider ({provider.name}). No data leaves for any other purpose."
        )
    return AiStatusResponse(
        enabled=provider is not None,
        mode=mode,
        provider=provider.name if provider else None,
        model=provider.model if provider else None,
        external_processing=bool(provider and provider.is_external),
        prompt_version=PROMPT_VERSION,
        limits=AiLimitsResponse(
            max_model_steps=settings.ai_max_model_steps,
            max_tool_calls_per_request=settings.ai_max_tool_calls_per_request,
            max_output_tokens=settings.ai_max_output_tokens,
            max_request_tokens=settings.ai_max_request_tokens,
            max_user_message_chars=settings.ai_max_user_message_chars,
            max_tool_result_chars=settings.ai_max_tool_result_chars,
            max_concurrent_runs=settings.ai_max_concurrent_runs,
            max_runs_per_user_per_minute=settings.ai_max_runs_per_user_per_minute,
            request_timeout_seconds=settings.ai_request_timeout_seconds,
            run_deadline_seconds=settings.ai_run_deadline_seconds,
        ),
        usage=AiUsageResponse(
            tokens_today=usage.tokens,
            cost_usd_today=str(usage.cost_usd),
            runs_today=usage.runs,
            daily_token_budget=settings.ai_daily_token_budget,
            daily_cost_budget_usd=str(settings.ai_daily_cost_budget_usd),
        ),
        notice=notice,
        can_approve=Permission.TRADE_WRITE in context.permissions,
    )


@router.get(
    "/tools",
    response_model=AiToolListResponse,
    summary="The tool registry, approval classes and blocked actions",
)
def ai_tools(response: Response, context: ViewContext, runtime: Runtime) -> AiToolListResponse:
    _no_store(response)
    permissions = context.permissions
    return AiToolListResponse(
        tools=[
            AiToolResponse(
                name=tool.name,
                description=tool.description,
                tool_class=tool.tool_class.value,
                permission=str(tool.permission),
                available=tool.permission in permissions,
                parameters=tool.parameters,
            )
            for tool in runtime.tools.all()
        ],
        blocked_actions=[
            BlockedActionResponse(name=name, reason=reason)
            for name, reason in sorted(BLOCKED_ACTIONS.items())
        ],
        classes=[
            ActionClassResponse(name=cls.value, description=text)
            for cls, text in _CLASS_DESCRIPTIONS.items()
        ],
    )


@router.get(
    "/suggestions",
    response_model=SuggestionListResponse,
    summary="Suggested starting questions",
)
def ai_suggestions(response: Response, context: ViewContext) -> SuggestionListResponse:
    _no_store(response)
    return SuggestionListResponse(
        items=[SuggestionResponse(id=i, title=t, prompt=p) for i, t, p in _SUGGESTIONS]
    )


# -------------------------------------------------------------- conversations
@router.post(
    "/conversations",
    response_model=ConversationResponse,
    status_code=status.HTTP_201_CREATED,
    summary="Start a conversation",
)
def create_conversation(
    payload: CreateConversationRequest,
    response: Response,
    context: ViewContext,
    runtime: Runtime,
) -> ConversationResponse:
    _no_store(response)
    record = runtime.office.create_conversation(
        company_id=active_company_id(context),
        user_id=context.user.user_id,
        title=payload.title,
        prompt_version=PROMPT_VERSION,
        request_id=get_request_id(),
    )
    return conversation_response(record)


@router.get(
    "/conversations",
    response_model=ConversationListResponse,
    summary="The signed-in user's conversations in the active company",
)
def list_conversations(
    response: Response, context: ViewContext, runtime: Runtime
) -> ConversationListResponse:
    _no_store(response)
    records = runtime.office.list_conversations(
        company_id=active_company_id(context), user_id=context.user.user_id
    )
    return ConversationListResponse(items=[conversation_response(r) for r in records])


@router.get(
    "/conversations/{conversation_id}",
    response_model=ConversationDetailResponse,
    summary="One conversation with its messages and proposals",
    responses={404: {"model": ErrorEnvelope, "description": "Not your conversation."}},
)
def get_conversation(
    conversation_id: UUID, response: Response, context: ViewContext, runtime: Runtime
) -> ConversationDetailResponse:
    _no_store(response)
    detail = runtime.office.get_conversation(
        company_id=active_company_id(context),
        user_id=context.user.user_id,
        conversation_id=conversation_id,
    )
    return ConversationDetailResponse(
        conversation=conversation_response(detail.conversation),
        messages=[message_response(m) for m in detail.messages],
        proposals=[proposal_response(p) for p in detail.proposals],
    )


@router.post(
    "/conversations/{conversation_id}/messages",
    response_model=SendMessageResponse,
    status_code=status.HTTP_202_ACCEPTED,
    summary="Ask the Trade Director",
    description=(
        "Accepted with 202; the model runs in the background. Poll the returned run. "
        "Refused with 503 when the AI Office is disabled, 413 for an oversized message, "
        "429 for the per-user rate limit, the daily budget or too many concurrent runs."
    ),
    responses={
        413: {"model": ErrorEnvelope, "description": "Message too large."},
        429: {"model": ErrorEnvelope, "description": "Rate limit or budget reached."},
        503: {"model": ErrorEnvelope, "description": "AI Office disabled."},
    },
)
def send_message(
    conversation_id: UUID,
    payload: SendMessageRequest,
    background: BackgroundTasks,
    response: Response,
    context: ViewContext,
    runtime: Runtime,
) -> SendMessageResponse:
    _no_store(response)
    caller = _caller(context)
    run, message, token = runtime.submit(
        caller, conversation_id=conversation_id, text=payload.content
    )
    background.add_task(runtime.execute, caller, run, message.content, token)
    return SendMessageResponse(run=run_response(run), message=message_response(message))


# ----------------------------------------------------------------------- runs
@router.get(
    "/runs/{run_id}",
    response_model=RunResponse,
    summary="Progress and result of one request",
    responses={404: {"model": ErrorEnvelope, "description": "Not your run."}},
)
def get_run(
    run_id: UUID, response: Response, context: ViewContext, runtime: Runtime
) -> RunResponse:
    _no_store(response)
    company_id = active_company_id(context)
    record = runtime.office.get_run(
        company_id=company_id, user_id=context.user.user_id, run_id=run_id
    )
    message = None
    proposals: tuple[ProposalRecord, ...] = ()
    if record.status == "COMPLETED":
        message = runtime.office.assistant_message_for_run(company_id=company_id, run_id=run_id)
        proposals = runtime.office.list_proposals(
            company_id=company_id, status=None, conversation_id=None, run_id=run_id
        )
    return run_response(record, message=message, proposals=proposals)


@router.post(
    "/runs/{run_id}/cancel",
    response_model=RunResponse,
    status_code=status.HTTP_202_ACCEPTED,
    summary="Cancel a running request",
    responses={409: {"model": ErrorEnvelope, "description": "The run is not running."}},
)
def cancel_run(
    run_id: UUID, response: Response, context: ViewContext, runtime: Runtime
) -> RunResponse:
    _no_store(response)
    company_id = active_company_id(context)
    record = runtime.office.get_run(
        company_id=company_id, user_id=context.user.user_id, run_id=run_id
    )
    if record.status != "RUNNING":
        raise ConflictError("The request has already finished.")
    if not runtime.runs.cancel(run_id, company_id=company_id, user_id=context.user.user_id):
        raise ConflictError("The request can no longer be cancelled.")
    return run_response(record)


@router.get(
    "/activity",
    response_model=ActivityResponse,
    summary="Recent requests with usage and tool counts",
)
def activity(response: Response, context: ViewContext, runtime: Runtime) -> ActivityResponse:
    _no_store(response)
    runs = runtime.office.list_activity(
        company_id=active_company_id(context), user_id=context.user.user_id
    )
    return ActivityResponse(items=[run_response(r) for r in runs])


# ------------------------------------------------------------------ proposals
@router.get(
    "/proposals",
    response_model=ProposalListResponse,
    summary="Drafts and task proposals awaiting a human decision",
)
def list_proposals(
    response: Response,
    context: ViewContext,
    runtime: Runtime,
    proposal_status: ProposalStatusValue | None = None,
    conversation_id: UUID | None = None,
) -> ProposalListResponse:
    _no_store(response)
    records = runtime.office.list_proposals(
        company_id=active_company_id(context),
        status=proposal_status,
        conversation_id=conversation_id,
    )
    return ProposalListResponse(items=[proposal_response(r) for r in records])


def _etagged(response: Response, proposal: ProposalResponse) -> ProposalResponse:
    _no_store(response)
    response.headers["ETag"] = etag_for(proposal.version)
    return proposal


@router.get(
    "/proposals/{proposal_id}",
    response_model=ProposalResponse,
    summary="One proposal",
)
def get_proposal(
    proposal_id: UUID, response: Response, context: ViewContext, runtime: Runtime
) -> ProposalResponse:
    record = runtime.office.get_proposal(
        company_id=active_company_id(context), proposal_id=proposal_id
    )
    return _etagged(response, proposal_response(record))


@router.patch(
    "/proposals/{proposal_id}",
    response_model=ProposalResponse,
    summary="Edit the wording of a pending proposal",
    description=(
        "Requires If-Match. Only wording can change; the target and cited evidence stay "
        "as produced. An edited proposal is marked EDITED_BY_USER."
    ),
    responses={
        409: {"model": ErrorEnvelope, "description": "Not pending, or stale version."},
        428: {"model": ErrorEnvelope, "description": "If-Match is required."},
    },
)
def edit_proposal(
    proposal_id: UUID,
    payload: ProposalEditRequest,
    response: Response,
    context: WriteContext,
    runtime: Runtime,
    if_match: Annotated[str | None, Header(alias="If-Match")] = None,
) -> ProposalResponse:
    record = runtime.office.edit_proposal(
        company_id=active_company_id(context),
        user_id=context.user.user_id,
        proposal_id=proposal_id,
        expected_version=require_if_match(if_match),
        patch=payload.model_dump(exclude_none=True),
        request_id=get_request_id(),
    )
    return _etagged(response, proposal_response(record))


def _decide(
    proposal_id: UUID,
    payload: ProposalDecisionRequest,
    response: Response,
    context: SessionContext,
    runtime: AIRuntime,
    if_match: str | None,
    *,
    approve: bool,
) -> ProposalResponse:
    record = runtime.office.decide_proposal(
        company_id=active_company_id(context),
        user_id=context.user.user_id,
        proposal_id=proposal_id,
        expected_version=require_if_match(if_match),
        approve=approve,
        notes=payload.notes,
        acknowledge_warnings=payload.acknowledge_warnings,
        request_id=get_request_id(),
    )
    return _etagged(response, proposal_response(record))


@router.post(
    "/proposals/{proposal_id}/approve",
    response_model=ProposalResponse,
    summary="Approve a proposal (a human decision; nothing is sent or posted)",
    description=(
        "Requires If-Match and ``trade.write``. Permissions, state, version and the target "
        "record are re-validated here. Supported actions: "
        + ", ".join(sorted(ACTIONS))
        + ". Proposals with unverified figures need ``acknowledge_warnings``."
    ),
    responses={
        409: {"model": ErrorEnvelope, "description": "Already decided, stale or unsupported."},
        428: {"model": ErrorEnvelope, "description": "If-Match is required."},
    },
)
def approve_proposal(
    proposal_id: UUID,
    payload: ProposalDecisionRequest,
    response: Response,
    context: WriteContext,
    runtime: Runtime,
    if_match: Annotated[str | None, Header(alias="If-Match")] = None,
) -> ProposalResponse:
    return _decide(proposal_id, payload, response, context, runtime, if_match, approve=True)


@router.post(
    "/proposals/{proposal_id}/reject",
    response_model=ProposalResponse,
    summary="Reject a proposal",
    responses={409: {"model": ErrorEnvelope, "description": "Already decided or stale."}},
)
def reject_proposal(
    proposal_id: UUID,
    payload: ProposalDecisionRequest,
    response: Response,
    context: WriteContext,
    runtime: Runtime,
    if_match: Annotated[str | None, Header(alias="If-Match")] = None,
) -> ProposalResponse:
    return _decide(proposal_id, payload, response, context, runtime, if_match, approve=False)

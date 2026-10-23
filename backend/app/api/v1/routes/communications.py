"""Stage 7A communications API: discover AI drafts without sending messages.

No provider SDK, SMTP client, external URL or write endpoint is imported here.
Reviewing an AI proposal in Stage 6 does not dispatch a message.
"""

from __future__ import annotations

import re
from typing import Annotated

from email_validator import EmailNotValidError, validate_email
from fastapi import APIRouter, Depends, Query, Request, Response
from fastapi.responses import JSONResponse
from sqlalchemy import select

from app.api.deps import app_settings, get_database
from app.api.security import active_company_id, require_company_permission, require_csrf
from app.api.v1.schemas.communications import (
    ChannelStatus,
    CommunicationDraftListResponse,
    CommunicationDraftResponse,
    CommunicationPreflightRequest,
    CommunicationPreflightResponse,
    CommunicationsStatusResponse,
    PreflightBlocker,
    RecordSuppressionRequest,
    SuppressionListResponse,
    SuppressionResponse,
)
from app.api.v1.trade_helpers import idempotent_call, replay_response, write_meta
from app.core.config import Settings
from app.core.errors import NotFoundError
from app.db.engine import Database
from app.db.models.ai import AiProposal, ProposalKind
from app.db.models.audit import AuditAction, AuditOutcome
from app.db.models.communications import CommunicationSuppression
from app.db.tenant import apply_company_context
from app.security.permissions import Permission
from app.services.ai_office import AiOfficeService
from app.services.audit import record_audit
from app.services.auth import SessionContext
from app.services.communications import crm_recipient_matches, is_suppressed, record_suppression

router = APIRouter(prefix="/communications", tags=["communications"])

_PHONE_E164 = re.compile(r"^\+[1-9][0-9]{6,14}$")

ViewContext = Annotated[
    SessionContext, Depends(require_company_permission(Permission.COMPANY_VIEW))
]


def _no_store(response: Response) -> None:
    response.headers["Cache-Control"] = "no-store"
    response.headers["Vary"] = "Cookie"


@router.get("/status", response_model=CommunicationsStatusResponse)
def communications_status(
    response: Response, context: ViewContext
) -> CommunicationsStatusResponse:
    """Report actual capabilities, never infer a configured provider."""
    _no_store(response)
    return CommunicationsStatusResponse(
        can_review_drafts=Permission.TRADE_WRITE in context.permissions,
        can_manage_suppressions=Permission.COMMUNICATIONS_SUPPRESS in context.permissions,
        channels=[
            ChannelStatus(channel="EMAIL"),
            ChannelStatus(channel="WHATSAPP_BUSINESS"),
        ],
    )


@router.get("/drafts", response_model=CommunicationDraftListResponse)
def list_communication_drafts(
    response: Response,
    context: ViewContext,
    database: Annotated[Database, Depends(get_database)],
    limit: Annotated[int, Query(ge=1, le=50)] = 20,
) -> CommunicationDraftListResponse:
    """Read existing company-scoped AI drafts; no side effects or external calls.

    These rows are company-visible by the Stage 6 contract. A human approval
    means 'reviewed', never 'delivered'. Return no address or contact details.
    """
    company_id = active_company_id(context)
    with database.transaction() as session:
        apply_company_context(session, company_id)
        rows = session.scalars(
            select(AiProposal)
            .where(
                AiProposal.company_id == company_id,
                AiProposal.kind == ProposalKind.DRAFT.value,
            )
            .order_by(AiProposal.created_at.desc(), AiProposal.id.desc())
            .limit(limit + 1)
        ).all()
        items = []
        for proposal in rows[:limit]:
            payload = (
                proposal.edited_payload
                if proposal.edited_payload is not None
                else proposal.payload
            )
            items.append(
                CommunicationDraftResponse(
                    id=proposal.id,
                    conversation_id=proposal.conversation_id,
                    title=proposal.title,
                    body=str(payload.get("body", "")),
                    draft_kind=str(payload.get("kind", "OTHER")),
                    status=proposal.status,
                    version=proposal.version,
                    created_at=proposal.created_at,
                    updated_at=proposal.updated_at,
                )
            )
    _no_store(response)
    return CommunicationDraftListResponse(items=items, truncated=len(rows) > limit)


@router.post(
    "/preflight",
    response_model=CommunicationPreflightResponse,
    dependencies=[Depends(require_csrf)],
)
def communication_preflight(
    payload: CommunicationPreflightRequest,
    response: Response,
    context: Annotated[
        SessionContext, Depends(require_company_permission(Permission.TRADE_WRITE))
    ],
    database: Annotated[Database, Depends(get_database)],
) -> CommunicationPreflightResponse:
    """Validate operator-entered recipient and draft state without sending.

    No recipient is persisted, returned, logged or dispatched. A successful
    preflight is deliberately impossible until a separately approved outbound
    transport, dedicated sender role and independent human send approval exist.
    """
    draft = AiOfficeService(database).get_proposal(
        company_id=active_company_id(context), proposal_id=payload.draft_id
    )
    if draft.kind != ProposalKind.DRAFT.value:
        raise NotFoundError("This communication draft does not exist.")

    blockers: list[PreflightBlocker] = []
    if draft.status != "APPROVED":
        blockers.append("DRAFT_NOT_APPROVED")
    if draft.version != payload.draft_version:
        blockers.append("DRAFT_VERSION_MISMATCH")
    normalized_recipient: str | None = None
    if payload.channel == "EMAIL":
        try:
            normalized_recipient = validate_email(
                payload.recipient, check_deliverability=False
            ).normalized
        except EmailNotValidError:
            blockers.append("RECIPIENT_INVALID")
    elif _PHONE_E164.fullmatch(payload.recipient):
        normalized_recipient = payload.recipient
    else:
        blockers.append("RECIPIENT_INVALID")

    if (
        normalized_recipient is None
        or not crm_recipient_matches(
            database,
            company_id=active_company_id(context),
            counterparty_id=payload.counterparty_id,
            channel=payload.channel,
            normalized_recipient=normalized_recipient,
        )
    ):
        blockers.append("CRM_RECIPIENT_MISMATCH")

    # CRM possession is NOT recipient authorization or channel-specific consent.
    # No structured opt-in/permission evidence exists in Commerce yet.
    blockers.append("CONSENT_UNDOCUMENTED")
    if payload.counterparty_id is not None and is_suppressed(
        database, company_id=active_company_id(context),
        counterparty_id=payload.counterparty_id, channel=payload.channel,
    ):
        blockers.append("RECIPIENT_SUPPRESSED")
    blockers.append("CHANNEL_NOT_CONFIGURED")
    if Permission.COMMUNICATIONS_SEND not in context.permissions:
        blockers.append("SEND_PERMISSION_UNAVAILABLE")

    _no_store(response)
    return CommunicationPreflightResponse(
        draft_id=draft.id,
        channel=payload.channel,
        blockers=blockers,
    )



def _suppression_body(record: CommunicationSuppression) -> SuppressionResponse:
    return SuppressionResponse(
        id=record.id,
        counterparty_id=record.counterparty_id,
        channel=record.channel,
        reason=record.reason,
        recorded_by=record.recorded_by,
        created_at=record.created_at,
    )


@router.get("/suppressions", response_model=SuppressionListResponse)
def list_suppressions(
    response: Response,
    context: Annotated[
        SessionContext,
        Depends(require_company_permission(Permission.COMMUNICATIONS_SUPPRESS)),
    ],
    database: Annotated[Database, Depends(get_database)],
    limit: Annotated[int, Query(ge=1, le=100)] = 50,
) -> SuppressionListResponse:
    """Administrator-only, tenant-scoped, bounded, address-free ledger view."""
    company_id = active_company_id(context)
    with database.transaction() as session:
        apply_company_context(session, company_id)
        records = session.scalars(
            select(CommunicationSuppression)
            .where(CommunicationSuppression.company_id == company_id)
            .order_by(
                CommunicationSuppression.created_at.desc(),
                CommunicationSuppression.id.desc(),
            )
            .limit(limit + 1)
        ).all()
        items = [_suppression_body(row) for row in records[:limit]]
    _no_store(response)
    return SuppressionListResponse(items=items, truncated=len(records) > limit)


@router.post(
    "/suppressions",
    response_model=SuppressionResponse,
    status_code=201,
    dependencies=[Depends(require_csrf)],
)
def create_suppression(
    payload: RecordSuppressionRequest,
    request: Request,
    response: Response,
    context: Annotated[
        SessionContext,
        Depends(require_company_permission(Permission.COMMUNICATIONS_SUPPRESS)),
    ],
    database: Annotated[Database, Depends(get_database)],
    settings: Annotated[Settings, Depends(app_settings)],
) -> SuppressionResponse | JSONResponse:
    """Record a permanent safety block, never an opt-in or delivery permission.

    An idempotency key is mandatory, and the audit row commits atomically with
    the suppression. Duplicate blocks do not generate additional audit events.
    """
    meta = write_meta(context, request)
    with idempotent_call(database, settings, context, request, payload, required=True) as call:
        if call.replay is not None:
            return replay_response(call.replay)
        entry, created = record_suppression(
            call.session,
            company_id=meta.company_id,
            counterparty_id=payload.counterparty_id,
            channel=payload.channel,
            reason=payload.reason,
            recorded_by=meta.actor_id,
        )
        if created:
            record_audit(
                call.session,
                action=AuditAction.COMMUNICATION_SUPPRESSION_RECORDED,
                outcome=AuditOutcome.SUCCESS,
                actor_id=meta.actor_id,
                company_id=meta.company_id,
                request_id=meta.request_id,
                ip_address=meta.ip_address,
                user_agent=meta.user_agent,
                resource_type="communication_suppression",
                resource_id=str(entry.id),
                details={
                    "counterparty_id": str(payload.counterparty_id),
                    "channel": payload.channel,
                    "reason": payload.reason,
                },
            )
        body = _suppression_body(entry)
        http_status = 201 if created else 200
        call.complete(status_code=http_status, body=body.model_dump(mode="json"))
    response.status_code = http_status
    _no_store(response)
    return body

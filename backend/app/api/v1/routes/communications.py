"""Stage 7A communications API: discover AI drafts without sending messages.

No provider SDK, SMTP client, external URL or write endpoint is imported here.
Reviewing an AI proposal in Stage 6 does not dispatch a message.
"""

from __future__ import annotations

import re
from typing import Annotated

from email_validator import EmailNotValidError, validate_email
from fastapi import APIRouter, Depends, Query, Response
from sqlalchemy import select

from app.api.deps import get_database
from app.api.security import active_company_id, require_company_permission, require_csrf
from app.api.v1.schemas.communications import (
    ChannelStatus,
    CommunicationDraftListResponse,
    CommunicationDraftResponse,
    CommunicationPreflightRequest,
    CommunicationPreflightResponse,
    CommunicationsStatusResponse,
    PreflightBlocker,
)
from app.core.errors import NotFoundError
from app.db.engine import Database
from app.db.models.ai import AiProposal, ProposalKind
from app.db.tenant import apply_company_context
from app.security.permissions import Permission
from app.services.ai_office import AiOfficeService
from app.services.auth import SessionContext
from app.services.communications import crm_recipient_matches

router = APIRouter(prefix="/communications", tags=["communications"])

_PHONE_E164 = re.compile(r"^\\+[1-9][0-9]{6,14}$")

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
    blockers.append("CHANNEL_NOT_CONFIGURED")
    if Permission.COMMUNICATIONS_SEND not in context.permissions:
        blockers.append("SEND_PERMISSION_UNAVAILABLE")

    _no_store(response)
    return CommunicationPreflightResponse(
        draft_id=draft.id,
        channel=payload.channel,
        blockers=blockers,
    )

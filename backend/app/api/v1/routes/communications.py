"""Stage 7A communications API: discover AI drafts without sending messages.

No provider SDK, SMTP client, external URL or write endpoint is imported here.
Reviewing an AI proposal in Stage 6 does not dispatch a message.
"""

from __future__ import annotations

from typing import Annotated

from fastapi import APIRouter, Depends, Query, Response
from sqlalchemy import select

from app.api.deps import get_database
from app.api.security import active_company_id, require_company_permission
from app.api.v1.schemas.communications import (
    ChannelStatus,
    CommunicationDraftListResponse,
    CommunicationDraftResponse,
    CommunicationsStatusResponse,
)
from app.db.engine import Database
from app.db.models.ai import AiProposal, ProposalKind
from app.db.tenant import apply_company_context
from app.security.permissions import Permission
from app.services.auth import SessionContext

router = APIRouter(prefix="/communications", tags=["communications"])

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
            payload = proposal.edited_payload if proposal.edited_payload is not None else proposal.payload
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

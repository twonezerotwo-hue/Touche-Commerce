"""Generated trade documents: RFQ, quotation, proforma, confirmation, PO, packing list ...

``GET /generated-documents/{kind}?entity_id=...&format=pdf|docx|xlsx|csv&locale=en|tr``
renders a document from stored records in the requested language. Customer-facing documents
are an outbound business act, so the caller needs ``trade.write`` (traders) or
``finance.approve`` (finance reviewers); each generation is audited with the kind, format
and language only. Nothing is stored and nothing is sent: the file is returned to the caller.
"""

from __future__ import annotations

from typing import Annotated, Literal
from uuid import UUID

from fastapi import APIRouter, Depends, Query, Request, Response

from app.api.deps import get_database
from app.api.security import (
    active_company_id,
    client_ip,
    request_user_agent,
    require_company_context,
)
from app.api.v1.schemas.errors import ErrorEnvelope
from app.core.context import get_request_id
from app.core.errors import BadRequestError, ForbiddenError
from app.db.engine import Database
from app.db.models import AuditAction, AuditOutcome
from app.db.tenant import apply_actor_context, apply_company_context
from app.render.spec import Locale
from app.render.writers import MEDIA_TYPES, OutputFormat, render
from app.security.permissions import Permission
from app.services.audit import record_audit
from app.services.auth import SessionContext
from app.services.document_builders import (
    KINDS_WITH_ENTITY,
    DocumentKind,
    build_document,
    company_locale,
)

router = APIRouter(prefix="/generated-documents", tags=["generated-documents"])

Db = Annotated[Database, Depends(get_database)]


def _document_context(
    context: Annotated[SessionContext, Depends(require_company_context)],
) -> SessionContext:
    if not {Permission.TRADE_WRITE, Permission.FINANCE_APPROVE} & context.permissions:
        raise ForbiddenError()
    return context


@router.get(
    "/{kind}",
    summary="Render a trade document",
    description=(
        "Returns the file itself. Commerce invoices are always drafts and say they are not "
        "tax invoices. Rejected, withdrawn or cancelled records produce 409, never a document."
    ),
    responses={
        200: {"description": "The rendered document.", "content": {"application/pdf": {}}},
        403: {"model": ErrorEnvelope, "description": "Needs trade.write or finance.approve."},
        404: {"model": ErrorEnvelope, "description": "Unknown record."},
        409: {"model": ErrorEnvelope, "description": "The record's state forbids a document."},
        400: {"model": ErrorEnvelope, "description": "Missing entity_id."},
        422: {"model": ErrorEnvelope, "description": "Bad parameter."},
    },
)
def generate_document(
    kind: DocumentKind,
    request: Request,
    context: Annotated[SessionContext, Depends(_document_context)],
    database: Db,
    entity_id: Annotated[UUID | None, Query()] = None,
    output: Annotated[Literal["pdf", "docx", "xlsx", "csv"], Query(alias="format")] = "pdf",
    locale: Annotated[Locale | None, Query()] = None,
) -> Response:
    if kind in KINDS_WITH_ENTITY and entity_id is None:
        raise BadRequestError("entity_id is required for this document.")
    company_id = active_company_id(context)
    with database.transaction() as session:
        apply_company_context(session, company_id)
        # The company row itself is visible only to a member (actor-scoped policy).
        apply_actor_context(session, context.user.user_id)
        resolved: Locale = locale or company_locale(session, company_id)
        spec = build_document(
            session, company_id=company_id, kind=kind, entity_id=entity_id, locale=resolved
        )
        record_audit(
            session,
            action=AuditAction.DOCUMENT_GENERATED,
            outcome=AuditOutcome.SUCCESS,
            actor_id=context.user.user_id,
            company_id=company_id,
            request_id=get_request_id(),
            ip_address=client_ip(request),
            user_agent=request_user_agent(request),
            resource_type="generated_document",
            resource_id=str(entity_id) if entity_id else kind,
            details={
                "kind": kind,
                "format": output,
                "locale": resolved,
                "draft": spec.draft,
                "number": spec.number,
            },
        )
    payload = render(spec, output)
    return Response(
        content=payload,
        media_type=MEDIA_TYPES[output],
        headers={
            "Content-Disposition": f'attachment; filename="{spec.filename}.{output}"',
            "Cache-Control": "no-store",
            "Vary": "Cookie",
            "X-Content-Type-Options": "nosniff",
        },
    )


__all__ = ["OutputFormat", "router"]

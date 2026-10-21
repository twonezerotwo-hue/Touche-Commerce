"""Company discovery and active-company selection endpoints."""

from __future__ import annotations

from typing import Annotated

from fastapi import APIRouter, Depends, Request, Response

from app.api.deps import app_settings
from app.api.security import (
    client_ip,
    current_session,
    get_auth_service,
    request_user_agent,
    require_csrf,
)
from app.api.v1.cookies import mark_no_store, set_session_cookie
from app.api.v1.presenters import auth_session_response, company_access
from app.api.v1.schemas.auth import (
    AuthSessionResponse,
    CompanyListResponse,
    CompanySwitchRequest,
)
from app.api.v1.schemas.errors import ErrorEnvelope
from app.core.config import Settings
from app.core.context import get_request_id
from app.services.auth import AuthService, SessionContext

router = APIRouter(tags=["companies"])


@router.get(
    "/companies",
    response_model=CompanyListResponse,
    summary="Companies the signed-in user may access",
    description=(
        "Returns only companies with an active membership for the caller, together "
        "with the role and permissions held in each. The list is derived from the "
        "database on every request, so a revoked membership disappears immediately."
    ),
    responses={
        200: {"description": "Accessible companies."},
        401: {"model": ErrorEnvelope, "description": "No valid session."},
    },
)
def list_companies(
    response: Response,
    context: Annotated[SessionContext, Depends(current_session)],
) -> CompanyListResponse:
    mark_no_store(response)
    return CompanyListResponse(
        companies=[company_access(membership) for membership in context.memberships],
        active_company_id=context.company_id,
    )


@router.post(
    "/session/company",
    response_model=AuthSessionResponse,
    summary="Select the active company and rotate the session token",
    description=(
        "Requires a CSRF header and an active membership for the requested company. "
        "The company id supplied by the client is only used as a lookup key: an "
        "unauthorised id returns 403 and writes an ACCESS_DENIED audit record. On "
        "success the session token and CSRF token are rotated and the absolute "
        "expiry is preserved."
    ),
    responses={
        200: {"description": "Active company changed."},
        401: {"model": ErrorEnvelope, "description": "No valid session."},
        403: {"model": ErrorEnvelope, "description": "No membership, CSRF or origin rejected."},
    },
)
def switch_company(
    payload: CompanySwitchRequest,
    request: Request,
    response: Response,
    settings: Annotated[Settings, Depends(app_settings)],
    service: Annotated[AuthService, Depends(get_auth_service)],
    context: Annotated[SessionContext, Depends(require_csrf)],
) -> AuthSessionResponse:
    issued = service.switch_company(
        context,
        payload.company_id,
        request_id=get_request_id(),
        ip_address=client_ip(request),
        user_agent=request_user_agent(request),
    )
    set_session_cookie(response, settings, token=issued.token)
    mark_no_store(response)
    return auth_session_response(issued.context, csrf_token=issued.csrf_token, settings=settings)

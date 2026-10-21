"""Authentication endpoints: login, logout and the current session profile."""

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
from app.api.v1.cookies import clear_session_cookie, mark_no_store, set_session_cookie
from app.api.v1.presenters import auth_session_response
from app.api.v1.schemas.auth import AuthSessionResponse, LoginRequest, LogoutResponse
from app.api.v1.schemas.errors import ErrorEnvelope
from app.core.config import Settings
from app.core.context import get_request_id
from app.services.auth import AuthService, SessionContext

router = APIRouter(tags=["auth"])


@router.post(
    "/auth/login",
    response_model=AuthSessionResponse,
    summary="Sign in and open a server-side session",
    description=(
        "Verifies the credentials with Argon2id, applies the login rate limit and "
        "creates a server-side session. The opaque session token is delivered in an "
        "HttpOnly cookie; the body never contains the token or the password hash. "
        "All failures return the same 401 message so account existence is not "
        "revealed. The active company is auto-selected only when the user has "
        "exactly one active membership."
    ),
    responses={
        200: {"description": "Session created."},
        401: {"model": ErrorEnvelope, "description": "Invalid credentials (generic)."},
        403: {"model": ErrorEnvelope, "description": "Origin not allowed."},
        429: {"model": ErrorEnvelope, "description": "Too many attempts; honour Retry-After."},
    },
)
def login(
    payload: LoginRequest,
    request: Request,
    response: Response,
    settings: Annotated[Settings, Depends(app_settings)],
    service: Annotated[AuthService, Depends(get_auth_service)],
) -> AuthSessionResponse:
    issued = service.login(
        email=str(payload.email),
        password=payload.password,
        ip_address=client_ip(request),
        user_agent=request_user_agent(request),
        request_id=get_request_id(),
    )
    set_session_cookie(response, settings, token=issued.token)
    mark_no_store(response)
    return auth_session_response(issued.context, csrf_token=issued.csrf_token, settings=settings)


@router.get(
    "/auth/me",
    response_model=AuthSessionResponse,
    summary="Current user, active company and memberships",
    description=(
        "Re-validates the session and the active membership on every call and returns "
        "the CSRF token the client must send on state-changing requests."
    ),
    responses={
        200: {"description": "Authenticated session."},
        401: {"model": ErrorEnvelope, "description": "No valid session."},
    },
)
def me(
    response: Response,
    settings: Annotated[Settings, Depends(app_settings)],
    context: Annotated[SessionContext, Depends(current_session)],
) -> AuthSessionResponse:
    mark_no_store(response)
    return auth_session_response(context, csrf_token=context.csrf_token, settings=settings)


@router.post(
    "/auth/logout",
    response_model=LogoutResponse,
    summary="Revoke the current session",
    description=(
        "Revokes the session row immediately (the cookie alone would be useless "
        "afterwards) and clears the cookie. Requires the CSRF header."
    ),
    responses={
        200: {"description": "Session revoked."},
        401: {"model": ErrorEnvelope, "description": "No valid session."},
        403: {"model": ErrorEnvelope, "description": "CSRF token or origin rejected."},
    },
)
def logout(
    request: Request,
    response: Response,
    settings: Annotated[Settings, Depends(app_settings)],
    service: Annotated[AuthService, Depends(get_auth_service)],
    context: Annotated[SessionContext, Depends(require_csrf)],
) -> LogoutResponse:
    service.logout(
        context,
        request_id=get_request_id(),
        ip_address=client_ip(request),
        user_agent=request_user_agent(request),
    )
    clear_session_cookie(response, settings)
    mark_no_store(response)
    return LogoutResponse()

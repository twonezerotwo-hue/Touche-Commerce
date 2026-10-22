"""Request-level authentication, CSRF and authorization dependencies.

The session cookie is the only credential the browser holds. Every dependency
here re-derives authorization from the database — a client-supplied company id
is never trusted (`docs/ARCHITECTURE.md` §7).
"""

from __future__ import annotations

from collections.abc import Callable
from typing import Annotated
from uuid import UUID

from fastapi import Depends, Request

from app.api.deps import app_settings, get_database
from app.core.config import Settings
from app.core.context import get_request_id
from app.core.errors import CsrfRejectedError, ForbiddenError, UnauthorizedError
from app.security.permissions import Permission
from app.services.auth import AuthService, SessionContext


def get_auth_service(request: Request) -> AuthService:
    """Return the process-wide auth service (keeps one Argon2 hasher/dummy hash)."""
    service: AuthService | None = getattr(request.app.state, "auth_service", None)
    if service is None:
        service = AuthService(get_database(request), app_settings(request))
        request.app.state.auth_service = service
    return service


def client_ip(request: Request) -> str | None:
    """Client address for audit/rate limiting.

    ``X-Forwarded-For`` is deliberately ignored: it is trivially spoofable unless
    a trusted proxy strips it, which no environment has yet.
    """
    return request.client.host if request.client else None


def request_user_agent(request: Request) -> str | None:
    return request.headers.get("user-agent")


def current_session(
    request: Request,
    settings: Annotated[Settings, Depends(app_settings)],
    service: Annotated[AuthService, Depends(get_auth_service)],
) -> SessionContext:
    """Resolve the session cookie or raise ``401 UNAUTHORIZED``."""
    token = request.cookies.get(settings.effective_session_cookie_name)
    if not token:
        raise UnauthorizedError()
    return service.resolve(
        token,
        request_id=get_request_id(),
        ip_address=client_ip(request),
        user_agent=request_user_agent(request),
    )


def require_csrf(
    request: Request,
    settings: Annotated[Settings, Depends(app_settings)],
    context: Annotated[SessionContext, Depends(current_session)],
) -> SessionContext:
    """Enforce the double-submit CSRF header for state-changing requests."""
    presented = request.headers.get(settings.csrf_header_name)
    if not context.verify_csrf(presented):
        raise CsrfRejectedError()
    return context


def require_permission(permission: Permission) -> Callable[..., SessionContext]:
    """Build a dependency that enforces a permission on the active company."""

    def dependency(
        context: Annotated[SessionContext, Depends(current_session)],
    ) -> SessionContext:
        if permission not in context.permissions:
            raise ForbiddenError()
        return context

    return dependency


def require_company_context(
    context: Annotated[SessionContext, Depends(current_session)],
) -> SessionContext:
    """Require an active company and a still-valid membership for it."""
    if context.company_id is None or context.active_membership is None:
        raise ForbiddenError("Select a company before using this resource.")
    return context


def require_company_permission(permission: Permission) -> Callable[..., SessionContext]:
    """Enforce a permission *inside* an active company (trade endpoints)."""

    def dependency(
        context: Annotated[SessionContext, Depends(require_company_context)],
    ) -> SessionContext:
        if permission not in context.permissions:
            raise ForbiddenError()
        return context

    return dependency


def active_company_id(context: SessionContext) -> UUID:
    """Return the verified company id; the dependency has already checked it."""
    company_id = context.company_id
    if company_id is None:  # pragma: no cover - guarded by require_company_context
        raise ForbiddenError("Select a company before using this resource.")
    return company_id

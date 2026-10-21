"""Presentation helpers that turn a service context into API schemas."""

from __future__ import annotations

from datetime import timedelta

from app.api.v1.schemas.auth import (
    AuthSessionResponse,
    CompanyAccess,
    SessionUser,
    SessionView,
)
from app.core.config import Settings
from app.services.auth import MembershipSummary, SessionContext


def company_access(membership: MembershipSummary) -> CompanyAccess:
    return CompanyAccess(
        company_id=membership.company_id,
        name=membership.company_name,
        country=membership.country,
        default_currency=membership.default_currency,
        status=membership.company_status,
        role=str(membership.role),
        permissions=sorted(str(permission) for permission in membership.permissions),
    )


def auth_session_response(
    context: SessionContext, *, csrf_token: str, settings: Settings
) -> AuthSessionResponse:
    active = next(
        (
            company_access(membership)
            for membership in context.memberships
            if membership.company_id == context.company_id
        ),
        None,
    )
    return AuthSessionResponse(
        user=SessionUser(
            user_id=context.user.user_id,
            email=context.user.email,
            display_name=context.user.display_name,
            status=context.user.status,
        ),
        session=SessionView(
            session_id=context.session_id,
            company=active,
            created_at=context.created_at,
            last_activity_at=context.last_activity_at,
            idle_expires_at=context.last_activity_at
            + timedelta(seconds=settings.session_idle_timeout_seconds),
            expires_at=context.expires_at,
            csrf_token=csrf_token,
            ip_address=context.ip_address,
            user_agent=context.user_agent,
        ),
        memberships=[company_access(membership) for membership in context.memberships],
    )

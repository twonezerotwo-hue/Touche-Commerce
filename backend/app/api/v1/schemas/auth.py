"""Request/response schemas for authentication and company selection.

These classes are the OpenAPI source of truth: the frontend DTOs are generated
from them (`docs/API_CONTRACTS.md`). Nothing here exposes a password hash, a
session token or a CSRF hash.
"""

from __future__ import annotations

from datetime import datetime
from typing import Literal
from uuid import UUID

from pydantic import BaseModel, ConfigDict, EmailStr, Field


class LoginRequest(BaseModel):
    """Credentials submitted from the sign-in screen."""

    model_config = ConfigDict(
        json_schema_extra={
            "example": {"email": "amina@touche.example", "password": "correct horse battery"}
        }
    )

    email: EmailStr = Field(description="Account email (case-insensitive).")
    # The policy is not advertised here on purpose: a login form must not reveal
    # whether a password is "too short" for an existing account.
    password: str = Field(min_length=1, max_length=512, description="Account password.")


class CompanyAccess(BaseModel):
    """One company the signed-in user may access, with their role there."""

    company_id: UUID
    name: str
    country: str = Field(description="ISO 3166-1 alpha-2 country code.")
    default_currency: str = Field(description="ISO 4217 currency code.")
    status: str = Field(description="Company status: active, suspended or archived.")
    role: str = Field(description="viewer, trader, approver or admin.")
    permissions: list[str] = Field(description="Permissions granted by this membership.")


class SessionUser(BaseModel):
    """The authenticated actor."""

    user_id: UUID
    email: str
    display_name: str
    status: str


class SessionView(BaseModel):
    """Server-side session metadata. The token itself is only ever in the cookie."""

    session_id: UUID
    company: CompanyAccess | None = Field(
        default=None, description="Active company, or null when a choice is required."
    )
    created_at: datetime
    last_activity_at: datetime
    idle_expires_at: datetime
    expires_at: datetime = Field(description="Absolute expiry, fixed at login.")
    csrf_token: str = Field(
        description="Send as the CSRF header on every state-changing request."
    )
    ip_address: str | None = None
    user_agent: str | None = None


class AuthSessionResponse(BaseModel):
    """Body returned by login, company switch and ``GET /auth/me``."""

    user: SessionUser
    session: SessionView
    memberships: list[CompanyAccess] = Field(
        description="Every company this user may still access."
    )


class CompanyListResponse(BaseModel):
    """Companies available to the caller and the currently active one."""

    companies: list[CompanyAccess]
    active_company_id: UUID | None


class CompanySwitchRequest(BaseModel):
    """Select the active company for this session."""

    company_id: UUID


class LogoutResponse(BaseModel):
    status: Literal["signed_out"] = "signed_out"

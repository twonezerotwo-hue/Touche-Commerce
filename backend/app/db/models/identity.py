"""Identity models: users, companies, memberships, sessions and login attempts.

Table naming note (ADR-019): ``user`` and ``session`` are avoided as table names
because ``USER`` is fully reserved in SQL and both collide with Python/SQLAlchemy
concepts. The tables are ``app_user`` and ``auth_session``; the API and docs use
the domain words "user" and "session".
"""

from __future__ import annotations

from datetime import datetime
from enum import StrEnum
from uuid import UUID

from sqlalchemy import (
    CheckConstraint,
    DateTime,
    ForeignKey,
    Index,
    String,
    Text,
    UniqueConstraint,
    func,
    text,
)
from sqlalchemy.dialects.postgresql import INET
from sqlalchemy.dialects.postgresql import UUID as PG_UUID
from sqlalchemy.orm import Mapped, mapped_column

from app.db.models.base import Base
from app.security.permissions import Role


class UserStatus(StrEnum):
    ACTIVE = "active"
    DISABLED = "disabled"


class CompanyStatus(StrEnum):
    ACTIVE = "active"
    SUSPENDED = "suspended"
    ARCHIVED = "archived"


class MembershipStatus(StrEnum):
    ACTIVE = "active"
    REVOKED = "revoked"


def _in_list(column: str, values: tuple[str, ...]) -> str:
    rendered = ", ".join(f"'{value}'" for value in values)
    return f"{column} IN ({rendered})"


_USER_STATUSES = tuple(status.value for status in UserStatus)
_COMPANY_STATUSES = tuple(status.value for status in CompanyStatus)
_MEMBERSHIP_STATUSES = tuple(status.value for status in MembershipStatus)
_ROLES = tuple(role.value for role in Role)


class User(Base):
    """A person who can sign in. Global identity, not owned by a company."""

    __tablename__ = "app_user"
    __table_args__ = (
        UniqueConstraint("email", name="uq_app_user_email"),
        CheckConstraint("email = lower(email)", name="ck_app_user_email_normalised"),
        CheckConstraint("char_length(email) BETWEEN 3 AND 320", name="ck_app_user_email_length"),
        CheckConstraint(
            "char_length(display_name) BETWEEN 1 AND 120", name="ck_app_user_name_length"
        ),
        CheckConstraint(_in_list("status", _USER_STATUSES), name="ck_app_user_status"),
        {"schema": "touche", "comment": "Application users (global identity)."},
    )

    id: Mapped[UUID] = mapped_column(
        PG_UUID(as_uuid=True), primary_key=True, server_default=func.gen_random_uuid()
    )
    email: Mapped[str] = mapped_column(Text, nullable=False)
    display_name: Mapped[str] = mapped_column(Text, nullable=False)
    password_hash: Mapped[str] = mapped_column(Text, nullable=False)
    status: Mapped[str] = mapped_column(String(16), nullable=False, server_default=text("'active'"))
    last_login_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now()
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now(), onupdate=func.now()
    )

    def __repr__(self) -> str:  # pragma: no cover - debugging helper
        return f"<User {self.email}>"


class Company(Base):
    """Tenant root. Every tenant-owned record carries this ``id`` as ``company_id``."""

    __tablename__ = "company"
    __table_args__ = (
        CheckConstraint("char_length(name) BETWEEN 1 AND 160", name="ck_company_name_length"),
        CheckConstraint("country ~ '^[A-Z]{2}$'", name="ck_company_country_iso"),
        CheckConstraint("default_currency ~ '^[A-Z]{3}$'", name="ck_company_currency_iso"),
        CheckConstraint(_in_list("status", _COMPANY_STATUSES), name="ck_company_status"),
        {"schema": "touche", "comment": "Tenant roots (trading companies)."},
    )

    id: Mapped[UUID] = mapped_column(
        PG_UUID(as_uuid=True), primary_key=True, server_default=func.gen_random_uuid()
    )
    name: Mapped[str] = mapped_column(Text, nullable=False)
    country: Mapped[str] = mapped_column(String(2), nullable=False)
    default_currency: Mapped[str] = mapped_column(String(3), nullable=False)
    status: Mapped[str] = mapped_column(String(16), nullable=False, server_default=text("'active'"))
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now()
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now(), onupdate=func.now()
    )

    def __repr__(self) -> str:  # pragma: no cover - debugging helper
        return f"<Company {self.name}>"


class Membership(Base):
    """Authorization link between a user and a company, with exactly one role."""

    __tablename__ = "membership"
    __table_args__ = (
        UniqueConstraint("user_id", "company_id", name="uq_membership_user_id_company_id"),
        # Composite key used by future child tables so a child can never point at
        # a membership in another tenant (ADR-004).
        UniqueConstraint("id", "company_id", name="uq_membership_id_company_id"),
        CheckConstraint(_in_list("role", _ROLES), name="ck_membership_role"),
        CheckConstraint(_in_list("status", _MEMBERSHIP_STATUSES), name="ck_membership_status"),
        CheckConstraint(
            "(status = 'revoked') = (revoked_at IS NOT NULL)", name="ck_membership_revoked_at"
        ),
        Index("ix_membership_company_id_status", "company_id", "status"),
        Index("ix_membership_user_id_status", "user_id", "status"),
        {"schema": "touche", "comment": "Per-company membership and role."},
    )

    id: Mapped[UUID] = mapped_column(
        PG_UUID(as_uuid=True), primary_key=True, server_default=func.gen_random_uuid()
    )
    user_id: Mapped[UUID] = mapped_column(
        PG_UUID(as_uuid=True),
        ForeignKey("touche.app_user.id", name="fk_membership_user_id_app_user", ondelete="CASCADE"),
        nullable=False,
    )
    company_id: Mapped[UUID] = mapped_column(
        PG_UUID(as_uuid=True),
        ForeignKey(
            "touche.company.id", name="fk_membership_company_id_company", ondelete="CASCADE"
        ),
        nullable=False,
    )
    role: Mapped[str] = mapped_column(String(16), nullable=False)
    status: Mapped[str] = mapped_column(String(16), nullable=False, server_default=text("'active'"))
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now()
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now(), onupdate=func.now()
    )
    revoked_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)

    def __repr__(self) -> str:  # pragma: no cover - debugging helper
        return f"<Membership {self.user_id}@{self.company_id} {self.role}>"


class UserSession(Base):
    """Server-side session. The session token is stored only as a SHA-256 digest.

    ``csrf_token`` is stored in clear text on purpose: it is not a credential on
    its own (it is useless without the HttpOnly session cookie) and the browser
    must be able to receive it again after a reload. The session token, which *is*
    a credential, never exists in the database in plaintext.
    """

    __tablename__ = "auth_session"
    __table_args__ = (
        UniqueConstraint("token_hash", name="uq_auth_session_token_hash"),
        CheckConstraint("expires_at > created_at", name="ck_auth_session_expiry_order"),
        CheckConstraint(
            "(revoked_at IS NULL) OR (revoked_at >= created_at)",
            name="ck_auth_session_revoked_order",
        ),
        CheckConstraint("char_length(token_hash) = 64", name="ck_auth_session_token_hash_sha256"),
        CheckConstraint("char_length(csrf_token) BETWEEN 32 AND 64", name="ck_auth_session_csrf"),
        Index("ix_auth_session_user_id", "user_id"),
        Index("ix_auth_session_company_id", "company_id"),
        Index("ix_auth_session_expires_at", "expires_at"),
        {"schema": "touche", "comment": "Server-side sessions with hashed tokens."},
    )

    id: Mapped[UUID] = mapped_column(
        PG_UUID(as_uuid=True), primary_key=True, server_default=func.gen_random_uuid()
    )
    token_hash: Mapped[str] = mapped_column(String(64), nullable=False)
    csrf_token: Mapped[str] = mapped_column(String(64), nullable=False)
    user_id: Mapped[UUID] = mapped_column(
        PG_UUID(as_uuid=True),
        ForeignKey(
            "touche.app_user.id", name="fk_auth_session_user_id_app_user", ondelete="CASCADE"
        ),
        nullable=False,
    )
    company_id: Mapped[UUID | None] = mapped_column(
        PG_UUID(as_uuid=True),
        ForeignKey(
            "touche.company.id", name="fk_auth_session_company_id_company", ondelete="CASCADE"
        ),
        nullable=True,
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now()
    )
    last_activity_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now()
    )
    expires_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    revoked_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    revoked_reason: Mapped[str | None] = mapped_column(String(64), nullable=True)
    ip_address: Mapped[str | None] = mapped_column(INET, nullable=True)
    user_agent: Mapped[str | None] = mapped_column(Text, nullable=True)

    def __repr__(self) -> str:  # pragma: no cover - debugging helper
        return f"<UserSession {self.id} user={self.user_id}>"


class LoginAttempt(Base):
    """Every login attempt, successful or not, for rate limiting and forensics.

    This table is the only place an email address is recorded for a *failed*
    attempt; it is never exposed through the API and never copied into the audit
    log (docs/DECISIONS.md #21).
    """

    __tablename__ = "login_attempt"
    __table_args__ = (
        CheckConstraint("char_length(email_normalized) BETWEEN 3 AND 320", name="ck_login_email"),
        Index("ix_login_attempt_email_attempted_at", "email_normalized", "attempted_at"),
        Index("ix_login_attempt_ip_attempted_at", "ip_address", "attempted_at"),
        Index("ix_login_attempt_attempted_at", "attempted_at"),
        {"schema": "touche", "comment": "Login attempts for rate limiting and forensics."},
    )

    id: Mapped[UUID] = mapped_column(
        PG_UUID(as_uuid=True), primary_key=True, server_default=func.gen_random_uuid()
    )
    email_normalized: Mapped[str] = mapped_column(Text, nullable=False)
    ip_address: Mapped[str | None] = mapped_column(INET, nullable=True)
    succeeded: Mapped[bool] = mapped_column(nullable=False)
    reason: Mapped[str | None] = mapped_column(String(64), nullable=True)
    attempted_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now()
    )

    def __repr__(self) -> str:  # pragma: no cover - debugging helper
        return f"<LoginAttempt {self.email_normalized} succeeded={self.succeeded}>"


__all__ = [
    "Company",
    "CompanyStatus",
    "LoginAttempt",
    "Membership",
    "MembershipStatus",
    "User",
    "UserSession",
    "UserStatus",
]

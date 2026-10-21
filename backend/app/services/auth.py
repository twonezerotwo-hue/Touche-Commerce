"""Authentication, session lifecycle and company switching (Stage 1A).

Rules enforced here (see docs/DECISIONS.md #2, #3, #4):

* login failures are indistinguishable to the caller (generic message, dummy
  Argon2 work for unknown accounts);
* every authenticated request re-validates the membership bound to the session;
* the session token is rotated on company switch and never stored in plaintext;
* idle and absolute timeouts are enforced server-side, not in the browser;
* the active company lives in the session row, never in a client-supplied value.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
from uuid import UUID

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.core.config import Settings
from app.core.errors import (
    ForbiddenError,
    RateLimitedError,
    SessionExpiredError,
    UnauthorizedError,
)
from app.db.engine import Database
from app.db.models import (
    AuditAction,
    AuditActorType,
    AuditOutcome,
    Company,
    LoginAttempt,
    Membership,
    MembershipStatus,
    User,
    UserSession,
    UserStatus,
)
from app.db.tenant import apply_actor_context, apply_company_context
from app.security.passwords import PasswordService
from app.security.permissions import Permission, Role, permissions_for
from app.security.tokens import (
    constant_time_equals,
    generate_csrf_token,
    generate_session_token,
    hash_token,
)
from app.services.audit import normalise_ip, record_audit

GENERIC_LOGIN_ERROR = "Email or password is incorrect."
MAX_USER_AGENT_LENGTH = 400


def utcnow() -> datetime:
    """Single clock entry point so tests can reason about expiry precisely."""
    return datetime.now(tz=UTC)


def normalize_email(value: str) -> str:
    """Normalise for storage and lookup (case-insensitive unique identity)."""
    return value.strip().lower()


@dataclass(frozen=True)
class ActorSummary:
    user_id: UUID
    email: str
    display_name: str
    status: str


@dataclass(frozen=True)
class MembershipSummary:
    membership_id: UUID
    company_id: UUID
    company_name: str
    country: str
    default_currency: str
    company_status: str
    role: Role

    @property
    def permissions(self) -> frozenset[Permission]:
        return permissions_for(self.role)


@dataclass(frozen=True)
class SessionContext:
    """Everything the request layer needs, rebuilt on every request."""

    session_id: UUID
    csrf_token: str
    user: ActorSummary
    company_id: UUID | None
    created_at: datetime
    last_activity_at: datetime
    expires_at: datetime
    ip_address: str | None
    user_agent: str | None
    memberships: tuple[MembershipSummary, ...]

    def membership_for(self, company_id: UUID) -> MembershipSummary | None:
        for membership in self.memberships:
            if membership.company_id == company_id:
                return membership
        return None

    @property
    def active_membership(self) -> MembershipSummary | None:
        if self.company_id is None:
            return None
        return self.membership_for(self.company_id)

    @property
    def role(self) -> Role | None:
        membership = self.active_membership
        return membership.role if membership else None

    @property
    def permissions(self) -> frozenset[Permission]:
        membership = self.active_membership
        return membership.permissions if membership else frozenset()

    def verify_csrf(self, presented: str | None) -> bool:
        """Double-submit token bound to this session (ADR-002)."""
        if not presented:
            return False
        return constant_time_equals(presented, self.csrf_token)


@dataclass(frozen=True)
class IssuedSession:
    """Returned to the route layer so it can set cookies."""

    token: str
    csrf_token: str
    context: SessionContext


class AuthService:
    """All identity operations. Owns its transaction boundaries."""

    def __init__(self, database: Database, settings: Settings) -> None:
        self._database = database
        self._settings = settings
        self._passwords = PasswordService(settings)

    # ------------------------------------------------------------------ login
    def login(
        self,
        *,
        email: str,
        password: str,
        ip_address: str | None = None,
        user_agent: str | None = None,
        request_id: str | None = None,
    ) -> IssuedSession:
        normalized = normalize_email(email)
        now = utcnow()
        with self._database.session() as session:
            self._enforce_login_rate_limit(
                session,
                email=normalized,
                ip_address=ip_address,
                now=now,
                request_id=request_id,
                user_agent=user_agent,
            )

            user = session.execute(
                select(User).where(User.email == normalized)
            ).scalar_one_or_none()

            verified = False
            if user is None:
                # Burn comparable CPU for unknown accounts (no timing oracle).
                self._passwords.verify_dummy(password)
            else:
                verified = self._passwords.verify(user.password_hash, password)

            if user is None or not verified or user.status != UserStatus.ACTIVE.value:
                reason = "unknown_user"
                if user is not None:
                    reason = "invalid_password" if not verified else "user_disabled"
                self._record_attempt(
                    session,
                    email=normalized,
                    ip_address=ip_address,
                    succeeded=False,
                    reason=reason,
                    now=now,
                )
                record_audit(
                    session,
                    action=AuditAction.LOGIN_FAILURE,
                    outcome=AuditOutcome.FAILURE,
                    actor_type=AuditActorType.USER if user else AuditActorType.SYSTEM,
                    actor_id=user.id if user else None,
                    request_id=request_id,
                    ip_address=ip_address,
                    user_agent=user_agent,
                    details={"reason": reason},
                )
                session.commit()
                raise UnauthorizedError(GENERIC_LOGIN_ERROR)

            if self._passwords.needs_rehash(user.password_hash):
                user.password_hash = self._passwords.hash(password)
            user.last_login_at = now
            self._record_attempt(
                session,
                email=normalized,
                ip_address=ip_address,
                succeeded=True,
                reason=None,
                now=now,
            )

            apply_actor_context(session, user.id)
            memberships = self._load_memberships(session, user.id)
            # A single membership is unambiguous; several require an explicit
            # choice on /select-company.
            company_id = memberships[0].company_id if len(memberships) == 1 else None
            if company_id is not None:
                apply_company_context(session, company_id)

            token = generate_session_token()
            csrf_token = generate_csrf_token()
            row = UserSession(
                token_hash=hash_token(token),
                csrf_token=csrf_token,
                user_id=user.id,
                company_id=company_id,
                created_at=now,
                last_activity_at=now,
                expires_at=now
                + timedelta(seconds=self._settings.session_absolute_timeout_seconds),
                ip_address=normalise_ip(ip_address),
                user_agent=user_agent[:MAX_USER_AGENT_LENGTH] if user_agent else None,
            )
            session.add(row)
            session.flush()

            record_audit(
                session,
                action=AuditAction.LOGIN_SUCCESS,
                outcome=AuditOutcome.SUCCESS,
                actor_id=user.id,
                company_id=company_id,
                request_id=request_id,
                ip_address=ip_address,
                user_agent=user_agent,
                resource_type="auth_session",
                resource_id=str(row.id),
                details={
                    "membership_count": len(memberships),
                    "company_auto_selected": company_id is not None,
                },
            )
            session.commit()

            return IssuedSession(
                token=token,
                csrf_token=csrf_token,
                context=self._build_context(user, row, memberships),
            )

    # ---------------------------------------------------------------- resolve
    def resolve(
        self,
        token: str,
        *,
        request_id: str | None = None,
        ip_address: str | None = None,
        user_agent: str | None = None,
    ) -> SessionContext:
        """Validate a cookie token and rebuild the request context.

        The membership referenced by the session is re-validated on every call,
        so revocation takes effect on the next request rather than at the next
        login.
        """
        now = utcnow()
        idle_window = timedelta(seconds=self._settings.session_idle_timeout_seconds)
        with self._database.session() as session:
            row = session.execute(
                select(UserSession).where(UserSession.token_hash == hash_token(token))
            ).scalar_one_or_none()
            if row is None or row.revoked_at is not None:
                raise UnauthorizedError()

            user = session.get(User, row.user_id)
            if user is None:
                raise UnauthorizedError()

            if now >= row.expires_at:
                self._revoke_and_audit(
                    session,
                    row,
                    user,
                    reason="absolute_timeout",
                    now=now,
                    request_id=request_id,
                    ip_address=ip_address,
                    user_agent=user_agent,
                )
                session.commit()
                raise SessionExpiredError()

            if now - row.last_activity_at >= idle_window:
                self._revoke_and_audit(
                    session,
                    row,
                    user,
                    reason="idle_timeout",
                    now=now,
                    request_id=request_id,
                    ip_address=ip_address,
                    user_agent=user_agent,
                )
                session.commit()
                raise SessionExpiredError()

            if user.status != UserStatus.ACTIVE.value:
                self._revoke_and_audit(
                    session,
                    row,
                    user,
                    reason="user_disabled",
                    now=now,
                    request_id=request_id,
                    ip_address=ip_address,
                    user_agent=user_agent,
                )
                session.commit()
                raise UnauthorizedError()

            apply_actor_context(session, user.id)
            if row.company_id is not None:
                apply_company_context(session, row.company_id)
            memberships = self._load_memberships(session, user.id)

            if row.company_id is not None and not any(
                membership.company_id == row.company_id for membership in memberships
            ):
                self._revoke(row, reason="membership_revoked", now=now)
                record_audit(
                    session,
                    action=AuditAction.SESSION_REVOKED,
                    outcome=AuditOutcome.FAILURE,
                    actor_id=user.id,
                    company_id=row.company_id,
                    request_id=request_id,
                    ip_address=ip_address,
                    user_agent=user_agent,
                    resource_type="auth_session",
                    resource_id=str(row.id),
                    details={"reason": "membership_revoked"},
                )
                record_audit(
                    session,
                    action=AuditAction.ACCESS_DENIED,
                    outcome=AuditOutcome.DENIED,
                    actor_id=user.id,
                    company_id=row.company_id,
                    request_id=request_id,
                    ip_address=ip_address,
                    user_agent=user_agent,
                    details={"reason": "membership_revoked"},
                )
                session.commit()
                raise UnauthorizedError(
                    "Your access to this company was revoked. Sign in again to continue."
                )

            if user_agent and row.user_agent is None:
                row.user_agent = user_agent[:MAX_USER_AGENT_LENGTH]
            row.last_activity_at = now
            session.commit()
            return self._build_context(user, row, memberships)

    # --------------------------------------------------------- switch company
    def switch_company(
        self,
        context: SessionContext,
        company_id: UUID,
        *,
        request_id: str | None = None,
        ip_address: str | None = None,
        user_agent: str | None = None,
    ) -> IssuedSession:
        """Change the active company, rotate the token and re-issue cookies."""
        now = utcnow()
        with self._database.session() as session:
            row = session.get(UserSession, context.session_id)
            if row is None or row.revoked_at is not None:
                raise UnauthorizedError()

            # Only the actor context is needed to prove membership; the target
            # company id is never trusted before that proof succeeds.
            apply_actor_context(session, context.user.user_id)
            membership = session.execute(
                select(Membership).where(
                    Membership.user_id == context.user.user_id,
                    Membership.company_id == company_id,
                    Membership.status == MembershipStatus.ACTIVE.value,
                )
            ).scalar_one_or_none()

            if membership is None:
                record_audit(
                    session,
                    action=AuditAction.ACCESS_DENIED,
                    outcome=AuditOutcome.DENIED,
                    actor_id=context.user.user_id,
                    company_id=None,
                    request_id=request_id,
                    ip_address=ip_address,
                    user_agent=user_agent,
                    details={
                        "reason": "company_switch_without_membership",
                        "requested_company_id": str(company_id),
                    },
                )
                session.commit()
                raise ForbiddenError("You are not authorised to access that company.")

            previous_company_id = row.company_id
            token = generate_session_token()
            csrf_token = generate_csrf_token()
            row.token_hash = hash_token(token)
            row.csrf_token = csrf_token
            row.company_id = company_id
            row.last_activity_at = now
            if user_agent:
                row.user_agent = user_agent[:MAX_USER_AGENT_LENGTH]

            apply_company_context(session, company_id)
            record_audit(
                session,
                action=AuditAction.COMPANY_SWITCH,
                outcome=AuditOutcome.SUCCESS,
                actor_id=context.user.user_id,
                company_id=company_id,
                request_id=request_id,
                ip_address=ip_address,
                user_agent=user_agent,
                resource_type="company",
                resource_id=str(company_id),
                details={
                    "previous_company_id": (
                        str(previous_company_id) if previous_company_id else None
                    ),
                    "role": membership.role,
                },
            )
            user = session.get(User, context.user.user_id)
            if user is None:
                raise UnauthorizedError()
            memberships = self._load_memberships(session, user.id)
            session.commit()

            return IssuedSession(
                token=token,
                csrf_token=csrf_token,
                context=self._build_context(user, row, memberships),
            )

    # ----------------------------------------------------------------- logout
    def logout(
        self,
        context: SessionContext,
        *,
        request_id: str | None = None,
        ip_address: str | None = None,
        user_agent: str | None = None,
    ) -> None:
        """Revoke the current session; safe to call on an already-revoked row."""
        now = utcnow()
        with self._database.session() as session:
            row = session.get(UserSession, context.session_id)
            if row is None or row.revoked_at is not None:
                return
            apply_actor_context(session, context.user.user_id)
            if context.company_id is not None:
                apply_company_context(session, context.company_id)
            self._revoke(row, reason="logout", now=now)
            record_audit(
                session,
                action=AuditAction.LOGOUT,
                outcome=AuditOutcome.SUCCESS,
                actor_id=context.user.user_id,
                company_id=context.company_id,
                request_id=request_id,
                ip_address=ip_address,
                user_agent=user_agent,
                resource_type="auth_session",
                resource_id=str(row.id),
                details={"reason": "logout"},
            )
            session.commit()

    # ---------------------------------------------------------------- helpers
    def _load_memberships(
        self, session: Session, user_id: UUID
    ) -> tuple[MembershipSummary, ...]:
        """Active memberships with their company, ordered deterministically.

        Requires the actor context: both ``membership`` and ``company`` are RLS
        protected and would otherwise return nothing (fail closed).
        """
        rows = session.execute(
            select(Membership, Company)
            .join(Company, Company.id == Membership.company_id)
            .where(
                Membership.user_id == user_id,
                Membership.status == MembershipStatus.ACTIVE.value,
            )
            .order_by(Company.name, Company.id)
        ).all()
        return tuple(
            MembershipSummary(
                membership_id=membership.id,
                company_id=company.id,
                company_name=company.name,
                country=company.country,
                default_currency=company.default_currency,
                company_status=company.status,
                role=Role(membership.role),
            )
            for membership, company in rows
        )

    def _build_context(
        self,
        user: User,
        row: UserSession,
        memberships: tuple[MembershipSummary, ...],
    ) -> SessionContext:
        return SessionContext(
            session_id=row.id,
            csrf_token=row.csrf_token,
            user=ActorSummary(
                user_id=user.id,
                email=user.email,
                display_name=user.display_name,
                status=user.status,
            ),
            company_id=row.company_id,
            created_at=row.created_at,
            last_activity_at=row.last_activity_at,
            expires_at=row.expires_at,
            ip_address=str(row.ip_address) if row.ip_address else None,
            user_agent=row.user_agent,
            memberships=memberships,
        )

    def _record_attempt(
        self,
        session: Session,
        *,
        email: str,
        ip_address: str | None,
        succeeded: bool,
        reason: str | None,
        now: datetime,
    ) -> None:
        session.add(
            LoginAttempt(
                email_normalized=email,
                ip_address=normalise_ip(ip_address),
                succeeded=succeeded,
                reason=reason,
                attempted_at=now,
            )
        )

    def _enforce_login_rate_limit(
        self,
        session: Session,
        *,
        email: str,
        ip_address: str | None,
        now: datetime,
        request_id: str | None,
        user_agent: str | None,
    ) -> None:
        """Database-backed counter: 10 per account and 30 per source per window."""
        window = self._settings.login_rate_limit_window_seconds
        window_start = now - timedelta(seconds=window)

        email_count, email_oldest = session.execute(
            select(func.count(), func.min(LoginAttempt.attempted_at)).where(
                LoginAttempt.email_normalized == email,
                LoginAttempt.succeeded.is_(False),
                LoginAttempt.attempted_at >= window_start,
            )
        ).one()

        scope: str | None = None
        oldest: datetime | None = None
        if email_count >= self._settings.login_rate_limit_attempts:
            scope, oldest = "account", email_oldest

        ip_normalized = normalise_ip(ip_address)
        if scope is None and ip_normalized:
            ip_count, ip_oldest = session.execute(
                select(func.count(), func.min(LoginAttempt.attempted_at)).where(
                    LoginAttempt.ip_address == ip_normalized,
                    LoginAttempt.succeeded.is_(False),
                    LoginAttempt.attempted_at >= window_start,
                )
            ).one()
            if ip_count >= self._settings.login_rate_limit_ip_attempts:
                scope, oldest = "source", ip_oldest

        if scope is None:
            return

        retry_after = window
        if oldest is not None:
            retry_after = max(1, int((oldest + timedelta(seconds=window) - now).total_seconds()))
        record_audit(
            session,
            action=AuditAction.ACCESS_DENIED,
            outcome=AuditOutcome.DENIED,
            actor_type=AuditActorType.SYSTEM,
            request_id=request_id,
            ip_address=ip_address,
            user_agent=user_agent,
            details={
                "reason": "login_rate_limited",
                "scope": scope,
                "retry_after_seconds": retry_after,
            },
        )
        session.commit()
        raise RateLimitedError(
            details={"retry_after_seconds": retry_after},
            headers={"Retry-After": str(retry_after)},
        )

    def _revoke(self, row: UserSession, *, reason: str, now: datetime) -> None:
        if row.revoked_at is None:
            row.revoked_at = now
            row.revoked_reason = reason[:64]

    def _revoke_and_audit(
        self,
        session: Session,
        row: UserSession,
        user: User,
        *,
        reason: str,
        now: datetime,
        request_id: str | None,
        ip_address: str | None,
        user_agent: str | None,
    ) -> None:
        apply_actor_context(session, user.id)
        if row.company_id is not None:
            apply_company_context(session, row.company_id)
        self._revoke(row, reason=reason, now=now)
        record_audit(
            session,
            action=AuditAction.SESSION_REVOKED,
            outcome=AuditOutcome.FAILURE,
            actor_id=user.id,
            company_id=row.company_id,
            request_id=request_id,
            ip_address=ip_address,
            user_agent=user_agent,
            resource_type="auth_session",
            resource_id=str(row.id),
            details={"reason": reason},
        )


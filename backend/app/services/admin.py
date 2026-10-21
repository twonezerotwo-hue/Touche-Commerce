"""Privileged identity administration (used by the CLI and tests).

These functions operate on a caller-provided :class:`~sqlalchemy.orm.Session` and
expect the caller to own the transaction. The CLI connects with the **migration**
role because bootstrapping the first company/user happens before any tenant
context can exist; the API runtime role is deliberately unable to insert company
rows (see ADR-004 and ADR-019).
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import UTC, datetime
from typing import Any
from uuid import UUID

from sqlalchemy import select, update
from sqlalchemy.orm import Session

from app.db.models import (
    AuditAction,
    AuditActorType,
    AuditOutcome,
    Company,
    CompanySettingEntry,
    CompanySettings,
    Membership,
    MembershipStatus,
    User,
    UserSession,
    UserStatus,
)
from app.db.tenant import apply_company_context
from app.security.permissions import Role
from app.services.audit import record_audit


@dataclass(frozen=True)
class RevocationResult:
    membership_id: UUID
    user_id: UUID
    company_id: UUID
    revoked_sessions: int
    already_revoked: bool


def find_user(session: Session, email: str) -> User | None:
    return session.execute(
        select(User).where(User.email == email.strip().lower())
    ).scalar_one_or_none()


def find_company_by_name(session: Session, name: str) -> Company | None:
    return session.execute(select(Company).where(Company.name == name.strip())).scalar_one_or_none()


def create_user(
    session: Session,
    *,
    email: str,
    display_name: str,
    password_hash: str,
    status: str = UserStatus.ACTIVE.value,
) -> User:
    user = User(
        email=email.strip().lower(),
        display_name=display_name.strip(),
        password_hash=password_hash,
        status=status,
    )
    session.add(user)
    session.flush()
    return user


def create_company(
    session: Session,
    *,
    name: str,
    country: str,
    default_currency: str,
    timezone: str = "UTC",
    locale: str = "en",
) -> Company:
    company = Company(
        name=name.strip(),
        country=country.strip().upper(),
        default_currency=default_currency.strip().upper(),
    )
    session.add(company)
    session.flush()

    settings = CompanySettings(company_id=company.id, timezone=timezone, locale=locale)
    session.add(settings)
    session.flush()
    # Two real tenant-owned rows so RLS isolation can be demonstrated end to end.
    session.add_all(
        [
            CompanySettingEntry(
                company_id=company.id,
                settings_id=settings.id,
                key="notifications.email",
                value={"enabled": False, "digest": "daily"},
            ),
            CompanySettingEntry(
                company_id=company.id,
                settings_id=settings.id,
                key="security.session_notice",
                value={"enabled": True},
            ),
        ]
    )
    session.flush()
    return company

def grant_membership(
    session: Session,
    *,
    user_id: UUID,
    company_id: UUID,
    role: Role | str,
    actor_id: UUID | None = None,
    request_id: str | None = None,
) -> Membership:
    """Create or re-activate a membership (one row per user/company pair)."""
    resolved_role = role if isinstance(role, Role) else Role(role)
    membership = session.execute(
        select(Membership).where(
            Membership.user_id == user_id, Membership.company_id == company_id
        )
    ).scalar_one_or_none()
    apply_company_context(session, company_id)

    if membership is None:
        membership = Membership(
            user_id=user_id,
            company_id=company_id,
            role=str(resolved_role),
            status=MembershipStatus.ACTIVE.value,
        )
        session.add(membership)
        session.flush()
        change = "created"
    else:
        change = (
            "reactivated" if membership.status == MembershipStatus.REVOKED.value else "updated"
        )
        membership.role = str(resolved_role)
        membership.status = MembershipStatus.ACTIVE.value
        membership.revoked_at = None
        session.flush()

    record_audit(
        session,
        action=AuditAction.MEMBERSHIP_CHANGED,
        outcome=AuditOutcome.SUCCESS,
        actor_type=AuditActorType.USER if actor_id else AuditActorType.SYSTEM,
        actor_id=actor_id,
        company_id=company_id,
        request_id=request_id,
        resource_type="membership",
        resource_id=str(membership.id),
        details={
            "user_id": str(user_id),
            "role": str(resolved_role),
            "status": MembershipStatus.ACTIVE.value,
            "change": change,
        },
    )
    return membership


def list_memberships(session: Session, company_id: UUID) -> list[tuple[Membership, User]]:
    apply_company_context(session, company_id)
    return list(
        session.execute(
            select(Membership, User)
            .join(User, User.id == Membership.user_id)
            .where(Membership.company_id == company_id)
            .order_by(User.email)
        ).all()
    )


def membership_for_user(
    session: Session, *, user_id: UUID, company_id: UUID
) -> Membership | None:
    return session.execute(
        select(Membership).where(
            Membership.user_id == user_id, Membership.company_id == company_id
        )
    ).scalar_one_or_none()
def revoke_membership(
    session: Session,
    membership: Membership,
    *,
    reason: str = "administrative_action",
    actor_id: UUID | None = None,
    request_id: str | None = None,
) -> RevocationResult:
    """Revoke a membership and immediately kill sessions bound to that company.

    Sessions with no active company (or bound to another company) survive, so an
    unrelated valid membership is preserved.
    """
    if membership.status == MembershipStatus.REVOKED.value:
        return RevocationResult(
            membership_id=membership.id,
            user_id=membership.user_id,
            company_id=membership.company_id,
            revoked_sessions=0,
            already_revoked=True,
        )

    now = datetime.now(tz=UTC)
    apply_company_context(session, membership.company_id)
    membership.status = MembershipStatus.REVOKED.value
    membership.revoked_at = now
    session.flush()

    revoked_session_ids = (
        session.execute(
            update(UserSession)
            .where(
                UserSession.user_id == membership.user_id,
                UserSession.company_id == membership.company_id,
                UserSession.revoked_at.is_(None),
            )
            .values(revoked_at=now, revoked_reason="membership_revoked")
            .returning(UserSession.id)
        )
        .scalars()
        .all()
    )
    revoked_sessions = len(revoked_session_ids)

    details: dict[str, Any] = {
        "user_id": str(membership.user_id),
        "role": membership.role,
        "status": MembershipStatus.REVOKED.value,
        "change": "revoked",
        "reason": reason,
        "revoked_sessions": revoked_sessions,
    }
    record_audit(
        session,
        action=AuditAction.MEMBERSHIP_CHANGED,
        outcome=AuditOutcome.SUCCESS,
        actor_type=AuditActorType.USER if actor_id else AuditActorType.SYSTEM,
        actor_id=actor_id,
        company_id=membership.company_id,
        request_id=request_id,
        resource_type="membership",
        resource_id=str(membership.id),
        details=details,
    )
    if revoked_sessions:
        record_audit(
            session,
            action=AuditAction.SESSION_REVOKED,
            outcome=AuditOutcome.SUCCESS,
            actor_type=AuditActorType.SYSTEM,
            actor_id=None,
            company_id=membership.company_id,
            request_id=request_id,
            resource_type="auth_session",
            resource_id=None,
            details={"reason": "membership_revoked", "count": revoked_sessions},
        )

    return RevocationResult(
        membership_id=membership.id,
        user_id=membership.user_id,
        company_id=membership.company_id,
        revoked_sessions=revoked_sessions,
        already_revoked=False,
    )


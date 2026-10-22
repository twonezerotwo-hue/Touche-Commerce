"""Roles, permissions and the role → permission matrix (ADR-003).

Roles describe a *job* inside one company. Permissions describe a *capability*.
Code checks permissions, never roles, so the matrix can evolve without touching
call sites.

Separation of duties is the point: ``admin`` administers people and settings and
deliberately **cannot** approve financial documents, while ``approver`` can
approve money but cannot manage memberships.
"""

from __future__ import annotations

from enum import StrEnum


class Role(StrEnum):
    """Membership role values stored in ``touche.membership.role``."""

    VIEWER = "viewer"
    TRADER = "trader"
    APPROVER = "approver"
    ADMIN = "admin"


class Permission(StrEnum):
    """Capability identifiers used by ``require_permission(...)``."""

    COMPANY_VIEW = "company.view"
    SETTINGS_VIEW = "settings.view"
    SETTINGS_MANAGE = "settings.manage"
    MEMBERSHIP_MANAGE = "membership.manage"
    AUDIT_VIEW = "audit.view"
    TRADE_WRITE = "trade.write"
    FINANCE_APPROVE = "finance.approve"
    # Stage 5D: a distinct financial-review capability. Admin never inherits it.
    FINANCE_RECONCILE = "finance.reconcile"


ROLE_PERMISSIONS: dict[Role, frozenset[Permission]] = {
    Role.VIEWER: frozenset({Permission.COMPANY_VIEW, Permission.SETTINGS_VIEW}),
    Role.TRADER: frozenset(
        {Permission.COMPANY_VIEW, Permission.SETTINGS_VIEW, Permission.TRADE_WRITE}
    ),
    Role.APPROVER: frozenset(
        {
            Permission.COMPANY_VIEW,
            Permission.SETTINGS_VIEW,
            Permission.FINANCE_APPROVE,
            Permission.FINANCE_RECONCILE,
        }
    ),
    Role.ADMIN: frozenset(
        {
            Permission.COMPANY_VIEW,
            Permission.SETTINGS_VIEW,
            Permission.SETTINGS_MANAGE,
            Permission.MEMBERSHIP_MANAGE,
            Permission.AUDIT_VIEW,
        }
    ),
}

assert not (  # noqa: S101
    ROLE_PERMISSIONS[Role.ADMIN] & {Permission.FINANCE_APPROVE, Permission.FINANCE_RECONCILE}
), "ADR-003: admin never inherits financial approval or reconciliation review"


def coerce_role(value: str) -> Role:
    """Parse a stored role value, raising ``ValueError`` for unknown roles."""
    try:
        return Role(value)
    except ValueError as exc:
        raise ValueError(f"Unknown role: {value!r}") from exc


def permissions_for(role: Role | str) -> frozenset[Permission]:
    """Return the capability set for a role (empty for unknown values)."""
    try:
        resolved = role if isinstance(role, Role) else Role(role)
    except ValueError:
        return frozenset()
    return ROLE_PERMISSIONS[resolved]


def has_permission(role: Role | str, permission: Permission | str) -> bool:
    """True when ``role`` grants ``permission``."""
    try:
        required = permission if isinstance(permission, Permission) else Permission(permission)
    except ValueError:
        return False
    return required in permissions_for(role)


def sorted_permission_values(role: Role | str) -> list[str]:
    """Stable ordering for API responses and tests."""
    return sorted(str(permission) for permission in permissions_for(role))

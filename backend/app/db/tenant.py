"""Transaction-scoped tenant context primitives.

Multi-company isolation relies on PostgreSQL row level security.  Policies read
``current_setting('touche.company_id', true)`` which is set with SET LOCAL
semantics so it can never leak across pooled connections or transactions.

Stage 0 provides the primitive only: membership verification, session handling
and the actual RLS policies land in Stage 1A (see docs/PROGRESS.md).
"""

from __future__ import annotations

from uuid import UUID

from sqlalchemy import text
from sqlalchemy.orm import Session

COMPANY_SETTING = "touche.company_id"
ACTOR_SETTING = "touche.actor_id"


class TenantContextError(RuntimeError):
    """Raised when a tenant context cannot be applied safely."""


class InvalidTenantTransactionError(TenantContextError):
    """Raised when ``SET LOCAL`` is attempted outside a transaction."""


def _apply_setting(session: Session, setting: str, value: UUID) -> None:
    if not isinstance(value, UUID):
        raise TenantContextError(f"{setting} must be provided as a UUID instance.")
    if not session.in_transaction():
        raise InvalidTenantTransactionError(
            "Tenant context requires an active transaction; SET LOCAL has no effect outside one."
        )
    session.execute(
        text("SELECT set_config(:setting, :value, true)"),
        {"setting": setting, "value": str(value)},
    )


def apply_company_context(session: Session, company_id: UUID) -> None:
    """Bind ``company_id`` to the current transaction for RLS evaluation.

    Must be called inside an active transaction because ``SET LOCAL`` is reset
    at COMMIT/ROLLBACK; that is exactly what prevents cross-tenant leakage on
    pooled connections.
    """
    _apply_setting(session, COMPANY_SETTING, company_id)


def apply_actor_context(session: Session, actor_id: UUID) -> None:
    """Bind the authenticated user for actor-scoped RLS policies."""
    _apply_setting(session, ACTOR_SETTING, actor_id)


def clear_tenant_context(session: Session) -> None:
    """Reset both settings inside the current transaction (defensive/diagnostics)."""
    session.execute(
        text("SELECT set_config(:company, '', true), set_config(:actor, '', true)"),
        {"company": COMPANY_SETTING, "actor": ACTOR_SETTING},
    )


def current_company_setting(session: Session) -> str | None:
    """Read back the transaction-scoped company id (diagnostics/tests)."""
    value = session.execute(
        text("SELECT current_setting(:setting, true)"), {"setting": COMPANY_SETTING}
    ).scalar_one()
    return str(value) if value else None


def current_actor_setting(session: Session) -> str | None:
    """Read back the transaction-scoped actor id (diagnostics/tests)."""
    value = session.execute(
        text("SELECT current_setting(:setting, true)"), {"setting": ACTOR_SETTING}
    ).scalar_one()
    return str(value) if value else None

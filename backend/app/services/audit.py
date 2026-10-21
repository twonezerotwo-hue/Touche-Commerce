"""The single audit writer (ADR-009).

Every security-relevant action goes through :func:`record_audit`. It never raises
on redaction problems and it never stores credentials: known sensitive keys are
replaced with ``"[redacted]"`` and values are bounded in size, so a careless
caller cannot leak a password or a session token into the audit trail.
"""

from __future__ import annotations

import ipaddress
from datetime import UTC, datetime
from enum import Enum
from typing import Any
from uuid import UUID, uuid4

from sqlalchemy import insert
from sqlalchemy.orm import Session

from app.db.models import AuditAction, AuditActorType, AuditOutcome, AuditRecord

REDACTED = "[redacted]"
MAX_DETAIL_STRING = 512
MAX_USER_AGENT = 400

_SENSITIVE_FRAGMENTS = (
    "password",
    "passwd",
    "secret",
    "token",
    "csrf",
    "cookie",
    "authorization",
    "api_key",
    "credential",
)


def is_sensitive_key(key: str) -> bool:
    lowered = key.lower()
    return any(fragment in lowered for fragment in _SENSITIVE_FRAGMENTS)


def redact_details(value: Any, *, depth: int = 0) -> Any:
    """Recursively redact sensitive keys and bound string length."""
    if depth > 6:
        return "[truncated]"
    if isinstance(value, dict):
        redacted: dict[str, Any] = {}
        for key, item in value.items():
            name = str(key)
            redacted[name] = (
                REDACTED if is_sensitive_key(name) else redact_details(item, depth=depth + 1)
            )
        return redacted
    if isinstance(value, (list, tuple, set)):
        return [redact_details(item, depth=depth + 1) for item in value]
    if isinstance(value, str):
        return value[:MAX_DETAIL_STRING]
    if isinstance(value, (UUID, datetime, Enum)):
        return str(value)
    if isinstance(value, (int, float, bool)) or value is None:
        return value
    return str(value)[:MAX_DETAIL_STRING]


def normalise_ip(value: str | None) -> str | None:
    """Return a canonical IP literal, or ``None`` when the value is not an IP."""
    if not value:
        return None
    try:
        return str(ipaddress.ip_address(value))
    except ValueError:
        return None


def record_audit(
    session: Session,
    *,
    action: AuditAction,
    outcome: AuditOutcome,
    actor_type: AuditActorType = AuditActorType.USER,
    actor_id: UUID | None = None,
    company_id: UUID | None = None,
    request_id: str | None = None,
    ip_address: str | None = None,
    user_agent: str | None = None,
    resource_type: str | None = None,
    resource_id: str | None = None,
    details: dict[str, Any] | None = None,
    occurred_at: datetime | None = None,
) -> None:
    """Append one audit row to the caller's transaction.

    A Core ``INSERT`` (not ``session.add``) is used deliberately: PostgreSQL
    applies the SELECT policy to ``INSERT ... RETURNING``, and the audit read
    policy is tenant-scoped. Inserting without RETURNING lets a system-level
    event (``company_id IS NULL``) be written while keeping reads locked down.
    """
    session.execute(
        insert(AuditRecord).values(
            # Client-side id: the insert must not use RETURNING (see docstring).
            id=uuid4(),
            actor_type=str(actor_type),
            actor_id=actor_id,
            company_id=company_id,
            action=str(action),
            outcome=str(outcome),
            request_id=request_id,
            occurred_at=occurred_at or datetime.now(tz=UTC),
            ip_address=normalise_ip(ip_address),
            user_agent=user_agent[:MAX_USER_AGENT] if user_agent else None,
            resource_type=resource_type,
            resource_id=resource_id,
            details=redact_details(details or {}),
        )
    )

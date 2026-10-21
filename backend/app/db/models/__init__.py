"""ORM model registry.

Importing this package registers every model on ``Base.metadata`` so Alembic
(and tests) see the complete schema.
"""

from app.db.models.audit import AuditAction, AuditActorType, AuditOutcome, AuditRecord
from app.db.models.base import SCHEMA, Base
from app.db.models.identity import (
    Company,
    CompanyStatus,
    LoginAttempt,
    Membership,
    MembershipStatus,
    User,
    UserSession,
    UserStatus,
)
from app.db.models.outbox import OutboxEvent
from app.db.models.tenant_data import CompanySettingEntry, CompanySettings, IdempotencyRecord

__all__ = [
    "SCHEMA",
    "AuditAction",
    "AuditActorType",
    "AuditOutcome",
    "AuditRecord",
    "Base",
    "Company",
    "CompanySettingEntry",
    "CompanySettings",
    "CompanyStatus",
    "IdempotencyRecord",
    "LoginAttempt",
    "Membership",
    "MembershipStatus",
    "OutboxEvent",
    "User",
    "UserSession",
    "UserStatus",
]


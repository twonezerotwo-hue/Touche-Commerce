"""Company profile: the legal details printed on customer-facing trade documents.

One optional row per company. Reads need only an active membership; the route layer
restricts writes to ``settings.manage``. A write is optimistic (``If-Match``), audited with
the *names* of the changed fields only (a tax number or IBAN never enters the audit log) and
atomic with the audit row.
"""

from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass
from datetime import datetime
from uuid import UUID

from sqlalchemy import select
from sqlalchemy.exc import IntegrityError

from app.core.errors import PreconditionRequiredError, VersionConflictError
from app.db.engine import Database
from app.db.models import AuditAction, AuditOutcome, CompanyProfile
from app.db.tenant import apply_company_context
from app.services.audit import record_audit
from app.services.trade_meta import WriteMeta, clean_optional

FIELDS: tuple[str, ...] = (
    "legal_name",
    "tax_office",
    "tax_number",
    "address",
    "city",
    "postal_code",
    "phone",
    "email",
    "website",
    "bank_name",
    "iban",
    "swift_bic",
)
#: Facts a customer expects on a quotation or invoice; a document warns when one is empty.
DOCUMENT_ESSENTIALS: tuple[str, ...] = ("legal_name", "tax_number", "address")


@dataclass(frozen=True)
class ProfileRecord:
    company_id: UUID
    values: Mapping[str, str | None]
    version: int
    updated_at: datetime

    @property
    def missing_essentials(self) -> tuple[str, ...]:
        return tuple(field for field in DOCUMENT_ESSENTIALS if not self.values.get(field))


def empty_values() -> dict[str, str | None]:
    return dict.fromkeys(FIELDS)


def _record(row: CompanyProfile) -> ProfileRecord:
    return ProfileRecord(
        company_id=row.company_id,
        values={field: getattr(row, field) for field in FIELDS},
        version=row.version,
        updated_at=row.updated_at,
    )


class CompanyProfileService:
    def __init__(self, database: Database) -> None:
        self._database = database

    def get(self, company_id: UUID) -> ProfileRecord | None:
        with self._database.transaction() as session:  # SET LOCAL needs a transaction
            apply_company_context(session, company_id)
            row = session.get(CompanyProfile, company_id)
            return _record(row) if row is not None else None

    def save(
        self,
        *,
        meta: WriteMeta,
        expected_version: int | None,
        values: Mapping[str, str | None],
    ) -> ProfileRecord:
        """Create the profile (``expected_version`` ``None``) or replace it (current version)."""
        cleaned = {field: clean_optional(values.get(field)) for field in FIELDS}
        try:
            with self._database.transaction() as session:
                apply_company_context(session, meta.company_id)
                row = session.execute(
                    select(CompanyProfile)
                    .where(CompanyProfile.company_id == meta.company_id)
                    .with_for_update()
                ).scalar_one_or_none()
                if row is None:
                    if expected_version is not None:
                        raise VersionConflictError(
                            "The company profile does not exist yet.",
                            details={"current_version": 0},
                        )
                    row = CompanyProfile(
                        company_id=meta.company_id, updated_by=meta.actor_id, version=1, **cleaned
                    )
                    session.add(row)
                    changed = [field for field in FIELDS if cleaned[field] is not None]
                else:
                    if expected_version is None:
                        raise PreconditionRequiredError()
                    if row.version != expected_version:
                        raise VersionConflictError(
                            "The company profile was modified by another request.",
                            details={"current_version": row.version},
                            headers={"ETag": f'"v{row.version}"'},
                        )
                    changed = [field for field in FIELDS if getattr(row, field) != cleaned[field]]
                    for field in FIELDS:
                        setattr(row, field, cleaned[field])
                    row.updated_by = meta.actor_id
                    row.version += 1
                session.flush()
                session.refresh(row)
                record_audit(
                    session,
                    action=AuditAction.COMPANY_PROFILE_UPDATED,
                    outcome=AuditOutcome.SUCCESS,
                    actor_id=meta.actor_id,
                    company_id=meta.company_id,
                    request_id=meta.request_id,
                    ip_address=meta.ip_address,
                    user_agent=meta.user_agent,
                    resource_type="company_profile",
                    resource_id=str(meta.company_id),
                    details={"changed_fields": changed, "version": row.version},
                )
                return _record(row)
        except IntegrityError as exc:  # two first-time saves raced on the primary key
            raise VersionConflictError(
                "The company profile was created by another request.",
                details={"current_version": 1},
            ) from exc

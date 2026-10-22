"""Explicit Commerce → Finance company mapping reads and privileged writes.

The API runtime only reads this table. Configuration changes happen through the
privileged CLI, which owns the transaction and records an audit row. No function
here guesses a mapping from names, currencies or counterparties.
"""

from __future__ import annotations

from datetime import UTC, datetime
from typing import Any
from uuid import UUID

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.db.models import Company, FinanceCompanyMapping, FinanceMappingStatus
from app.integrations.finance.connector import FinanceMappingSnapshot


def load_mapping(session: Session, company_id: UUID) -> FinanceCompanyMapping | None:
    """Read the active company's explicit mapping (RLS applies to the runtime)."""
    return session.execute(
        select(FinanceCompanyMapping).where(
            FinanceCompanyMapping.company_id == company_id
        )
    ).scalar_one_or_none()


def snapshot(mapping: FinanceCompanyMapping | None) -> FinanceMappingSnapshot | None:
    """Return a detached, secret-free mapping snapshot for the HTTP connector."""
    if mapping is None:
        return None
    return FinanceMappingSnapshot(
        finance_company_id=mapping.finance_company_id,
        finance_company_name=mapping.finance_company_name,
        status=mapping.status,
        configured_at=mapping.configured_at,
        last_verified_at=mapping.last_verified_at,
    )


def set_verified_mapping(
    session: Session,
    *,
    company_id: UUID,
    finance_company_id: str,
    finance_company_name: str | None,
    configured_by: UUID | None,
    verification_details: dict[str, Any],
) -> FinanceCompanyMapping:
    """Create or replace the single mapping after live Finance verification."""
    mapping = load_mapping(session, company_id)
    now = datetime.now(tz=UTC)
    if mapping is None:
        mapping = FinanceCompanyMapping(
            company_id=company_id,
            finance_company_id=finance_company_id,
            finance_company_name=finance_company_name,
            status=FinanceMappingStatus.VERIFIED.value,
            source="manual_cli",
            configured_by=configured_by,
            configured_at=now,
            last_verified_at=now,
            last_verification_error=None,
            verification_details=verification_details,
        )
        session.add(mapping)
    else:
        mapping.finance_company_id = finance_company_id
        mapping.finance_company_name = finance_company_name
        mapping.status = FinanceMappingStatus.VERIFIED.value
        mapping.source = "manual_cli"
        mapping.configured_by = configured_by
        mapping.configured_at = now
        mapping.last_verified_at = now
        mapping.last_verification_error = None
        mapping.verification_details = verification_details
    session.flush()
    return mapping


def disable_mapping(session: Session, *, company_id: UUID) -> FinanceCompanyMapping | None:
    """Disable the mapping without deleting its audit context."""
    mapping = load_mapping(session, company_id)
    if mapping is None:
        return None
    mapping.status = FinanceMappingStatus.DISABLED.value
    mapping.last_verification_error = None
    mapping.verification_details = {}
    session.flush()
    return mapping


def all_mappings(session: Session) -> list[tuple[FinanceCompanyMapping, Company]]:
    """Privileged CLI listing: mappings joined to their Commerce company."""
    rows = session.execute(
        select(FinanceCompanyMapping, Company)
        .join(Company, Company.id == FinanceCompanyMapping.company_id)
        .order_by(Company.name)
    ).all()
    return [(mapping, company) for mapping, company in rows]

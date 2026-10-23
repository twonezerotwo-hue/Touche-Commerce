"""Stage 7C recipient provenance checks, always read-only and tenant-scoped.

A matching CRM record is not evidence of consent, address ownership or permission
to send. The service never persists, logs or echoes contact details.
"""

from __future__ import annotations

from uuid import UUID

from sqlalchemy import select

from app.db.engine import Database
from app.db.models.trade import Counterparty, RecordStatus
from app.db.tenant import apply_company_context


def crm_recipient_matches(
    database: Database,
    *,
    company_id: UUID,
    counterparty_id: UUID | None,
    channel: str,
    normalized_recipient: str,
) -> bool:
    """Compare with one active counterparty; no cross-tenant row or address returned."""
    if counterparty_id is None:
        return False

    with database.transaction() as session:
        apply_company_context(session, company_id)
        result = session.execute(
            select(Counterparty.email, Counterparty.phone)
            .where(
                Counterparty.id == counterparty_id,
                Counterparty.company_id == company_id,
                Counterparty.status == RecordStatus.ACTIVE.value,
            )
        ).one_or_none()
        if result is None:
            return False
        email, phone = result

    if channel == "EMAIL":
        return isinstance(email, str) and email.casefold() == normalized_recipient.casefold()
    if channel == "WHATSAPP_BUSINESS":
        # Intentionally strict; formatted CRM phone numbers must be normalized
        # and independently verified before future send authorization.
        return isinstance(phone, str) and phone == normalized_recipient
    return False

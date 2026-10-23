"""Stage 7C recipient provenance checks, always read-only and tenant-scoped.

A matching CRM record is not evidence of consent, address ownership or permission
to send. The service never persists, logs or echoes contact details.
"""

from __future__ import annotations

from uuid import UUID

from sqlalchemy import select
from sqlalchemy.dialects.postgresql import insert as pg_insert
from sqlalchemy.orm import Session

from app.core.errors import NotFoundError
from app.db.engine import Database
from app.db.models.communications import CommunicationSuppression
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


def is_suppressed(
    database: Database, *, company_id: UUID, counterparty_id: UUID, channel: str
) -> bool:
    """Read the immutable block list, independent of draft approval or consent."""
    with database.transaction() as session:
        apply_company_context(session, company_id)
        return session.scalar(
            select(CommunicationSuppression.id).where(
                CommunicationSuppression.company_id == company_id,
                CommunicationSuppression.counterparty_id == counterparty_id,
                CommunicationSuppression.channel == channel,
            )
        ) is not None


def record_suppression(
    session: Session, *,
    company_id: UUID, counterparty_id: UUID, channel: str,
    reason: str, recorded_by: UUID,
) -> tuple[CommunicationSuppression, bool]:
    """Append an opt-out/block; duplicates return the immutable first record.

    Caller owns an idempotent transaction, tenant context and audit insertion.
    Never accepts or stores a recipient address or marks anything opted in.
    """
    exists = session.scalar(
        select(Counterparty.id).where(
            Counterparty.company_id == company_id,
            Counterparty.id == counterparty_id,
        )
    )
    if exists is None:
        raise NotFoundError("The CRM record does not exist.")

    created_id = session.execute(
        pg_insert(CommunicationSuppression)
        .values(
            company_id=company_id,
            counterparty_id=counterparty_id,
            channel=channel,
            reason=reason,
            recorded_by=recorded_by,
        )
        .on_conflict_do_nothing(
            index_elements=["company_id", "counterparty_id", "channel"]
        )
        .returning(CommunicationSuppression.id)
    ).scalar_one_or_none()

    row = session.scalars(
        select(CommunicationSuppression).where(
            CommunicationSuppression.company_id == company_id,
            CommunicationSuppression.counterparty_id == counterparty_id,
            CommunicationSuppression.channel == channel,
        )
    ).one()
    return row, created_id is not None

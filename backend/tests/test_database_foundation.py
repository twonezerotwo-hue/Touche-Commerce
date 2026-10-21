"""Integration tests for the database foundation (requires live PostgreSQL).

Run with the local cluster up:
    backend\\.venv\\Scripts\\python -m pytest -m integration
"""

from __future__ import annotations

import uuid

import pytest
from sqlalchemy import func, select, text

from app.db.engine import Database
from app.db.models import OutboxEvent
from app.db.tenant import (
    InvalidTenantTransactionError,
    apply_company_context,
    current_company_setting,
)

pytestmark = pytest.mark.integration


def test_initial_migration_is_applied(live_database: Database) -> None:
    with live_database.session() as session:
        revision = session.execute(text("SELECT version_num FROM alembic_version")).scalar_one()

    assert revision == "0001_foundation"


def test_runtime_role_has_no_elevated_privileges(live_database: Database) -> None:
    with live_database.session() as session:
        row = (
            session.execute(
                text(
                    "SELECT current_user AS role_name, rolsuper, rolbypassrls "
                    "FROM pg_roles WHERE rolname = current_user"
                )
            )
            .mappings()
            .one()
        )

    assert row["role_name"] == "touche_app"
    assert row["rolsuper"] is False
    assert row["rolbypassrls"] is False


def test_runtime_role_cannot_create_objects_in_application_schema(
    live_database: Database,
) -> None:
    with live_database.session() as session:
        can_create = session.execute(
            text("SELECT has_schema_privilege(current_user, 'touche', 'CREATE')")
        ).scalar_one()

    assert can_create is False


def test_outbox_table_accepts_writes_from_runtime_role(live_database: Database) -> None:
    """Proves DML grants work, then rolls back so the database stays clean."""
    event_type = f"stage0.smoke.{uuid.uuid4().hex}"

    with live_database.session() as session:
        transaction = session.begin()
        event = OutboxEvent(
            company_id=uuid.uuid4(),
            event_type=event_type,
            aggregate_type="system",
            aggregate_id="stage0",
            payload={"stage": 0, "verified": True},
        )
        session.add(event)
        session.flush()
        assert event.id is not None
        transaction.rollback()

    with live_database.session() as session:
        remaining = session.scalar(
            select(func.count())
            .select_from(OutboxEvent)
            .where(OutboxEvent.event_type == event_type)
        )

    assert remaining == 0


def test_company_context_requires_an_active_transaction(live_database: Database) -> None:
    with live_database.session() as session, pytest.raises(InvalidTenantTransactionError):
        apply_company_context(session, uuid.uuid4())


def test_company_context_is_transaction_scoped(live_database: Database) -> None:
    """SET LOCAL must not survive the transaction (no cross-tenant leakage)."""
    company_id = uuid.uuid4()

    with live_database.session() as session, session.begin():
        apply_company_context(session, company_id)
        assert current_company_setting(session) == str(company_id)

    with live_database.session() as session:
        assert current_company_setting(session) in (None, "")

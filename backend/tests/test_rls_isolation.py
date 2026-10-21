"""PostgreSQL row level security: tenant isolation proven at the database level.

Every test here talks directly to PostgreSQL with the **runtime** role
(``touche_app``). Nothing relies on API-level filtering: if a future endpoint
forgets a ``WHERE company_id = ...`` clause, these policies still refuse the rows.
"""

from __future__ import annotations

from collections.abc import Iterator
from typing import Any
from uuid import UUID

import pytest
from sqlalchemy import text
from sqlalchemy.exc import DBAPIError, IntegrityError
from sqlalchemy.orm import Session

from app.core.config import Settings
from app.db.engine import Database
from tests.conftest import IdentityWorld

pytestmark = pytest.mark.integration


@pytest.fixture(scope="session")
def runtime_database(test_settings: Settings) -> Iterator[Database]:
    """Application-role handle (NOBYPASSRLS) against the isolated test database."""
    database = Database(test_settings)
    yield database
    database.dispose()


def apply_context(
    session: Session, *, company_id: UUID | None = None, actor_id: UUID | None = None
) -> None:
    if company_id is not None:
        session.execute(
            text("SELECT set_config('touche.company_id', :value, true)"),
            {"value": str(company_id)},
        )
    if actor_id is not None:
        session.execute(
            text("SELECT set_config('touche.actor_id', :value, true)"),
            {"value": str(actor_id)},
        )


def scalar(session: Session, statement: str, **params: Any) -> Any:
    return session.execute(text(statement), params).scalar_one()


def count(session: Session, table: str) -> int:
    # ``table`` is always one of the literal names in this test module.
    return int(scalar(session, f"SELECT count(*) FROM touche.{table}"))  # noqa: S608


def company_ids(session: Session) -> set[str]:
    return {
        str(value) for value in session.execute(text("SELECT id FROM touche.company")).scalars()
    }


def setting_entry_companies(session: Session) -> set[str]:
    return {
        str(value)
        for value in session.execute(
            text("SELECT company_id FROM touche.company_setting_entry")
        ).scalars()
    }


class TestApplicationRole:
    def test_runtime_role_is_least_privileged(self, runtime_database: Database) -> None:
        with runtime_database.session() as session:
            role = (
                session.execute(
                    text(
                        "SELECT rolbypassrls, rolsuper, rolcreatedb FROM pg_roles "
                        "WHERE rolname = current_user"
                    )
                )
                .mappings()
                .one()
            )
        assert role["rolbypassrls"] is False
        assert role["rolsuper"] is False
        assert role["rolcreatedb"] is False

    def test_runtime_role_cannot_switch_rls_off(self, runtime_database: Database) -> None:
        with pytest.raises(DBAPIError) as excinfo, runtime_database.session() as session:
            session.execute(text("SET LOCAL row_security = off"))
            session.execute(text("SELECT count(*) FROM touche.company_settings")).scalar_one()
        assert "row-level security" in str(excinfo.value).lower()

    def test_runtime_role_has_no_ddl_rights(self, runtime_database: Database) -> None:
        with pytest.raises(DBAPIError), runtime_database.session() as session:
            session.execute(text("CREATE TABLE touche.rogue_table (id int)"))


class TestFailClosed:
    def test_missing_tenant_context_returns_no_rows(
        self, identity_world: IdentityWorld, runtime_database: Database
    ) -> None:
        with runtime_database.session() as session:
            for table in (
                "company",
                "membership",
                "company_settings",
                "company_setting_entry",
                "audit_record",
            ):
                assert count(session, table) == 0, table

    def test_context_is_cleared_after_commit(
        self, identity_world: IdentityWorld, runtime_database: Database
    ) -> None:
        with runtime_database.session() as session:
            apply_context(session, company_id=identity_world.company_a)
            assert count(session, "company_setting_entry") == 2
            session.commit()

            remaining = scalar(session, "SELECT current_setting('touche.company_id', true)")
            assert remaining in (None, "")
            assert count(session, "company_setting_entry") == 0

    def test_two_connections_never_share_context(
        self, identity_world: IdentityWorld, runtime_database: Database
    ) -> None:
        with runtime_database.session() as first, runtime_database.session() as second:
            apply_context(first, company_id=identity_world.company_a)
            apply_context(second, company_id=identity_world.company_b)

            first_ids = setting_entry_companies(first)
            second_ids = setting_entry_companies(second)

            assert first_ids == {str(identity_world.company_a)}
            assert second_ids == {str(identity_world.company_b)}
            assert first_ids.isdisjoint(second_ids)


class TestTenantReads:
    def test_settings_are_scoped_to_the_active_company(
        self, identity_world: IdentityWorld, runtime_database: Database
    ) -> None:
        with runtime_database.session() as session:
            apply_context(session, company_id=identity_world.company_a)
            rows = session.execute(
                text("SELECT company_id, key FROM touche.company_setting_entry ORDER BY key")
            ).all()

        assert [row.key for row in rows] == [
            "notifications.email",
            "security.session_notice",
        ]
        assert {str(row.company_id) for row in rows} == {str(identity_world.company_a)}

    def test_company_rows_require_a_membership(
        self, identity_world: IdentityWorld, runtime_database: Database
    ) -> None:
        with runtime_database.session() as session:
            apply_context(session, actor_id=identity_world.user_a)
            visible = company_ids(session)

        assert visible == {str(identity_world.company_a), str(identity_world.company_b)}
        assert str(identity_world.company_c) not in visible

    def test_user_b_sees_only_their_own_membership(
        self, identity_world: IdentityWorld, runtime_database: Database
    ) -> None:
        with runtime_database.session() as session:
            apply_context(session, actor_id=identity_world.user_b)
            rows = session.execute(
                text("SELECT user_id, company_id, role FROM touche.membership")
            ).all()

        assert len(rows) == 1
        assert str(rows[0].user_id) == str(identity_world.user_b)
        assert rows[0].role == "trader"

    def test_audit_rows_are_scoped_to_the_active_company(
        self,
        identity_world: IdentityWorld,
        migration_database: Database,
        runtime_database: Database,
    ) -> None:
        with migration_database.transaction() as session:
            for company_id in (identity_world.company_a, identity_world.company_b):
                session.execute(
                    text(
                        "INSERT INTO touche.audit_record "
                        "(actor_type, action, outcome, company_id, details) "
                        "VALUES ('user', 'auth.logout', 'success', :company, '{}'::jsonb)"
                    ),
                    {"company": company_id},
                )

        with runtime_database.session() as session:
            apply_context(session, company_id=identity_world.company_a)
            rows = session.execute(text("SELECT company_id FROM touche.audit_record")).all()

        with migration_database.session() as session:
            expected_for_a = int(
                session.execute(
                    text(
                        "SELECT count(*) FROM touche.audit_record WHERE company_id = :company"
                    ),
                    {"company": identity_world.company_a},
                ).scalar_one()
            )
            expected_total = int(
                session.execute(text("SELECT count(*) FROM touche.audit_record")).scalar_one()
            )

        assert len(rows) == expected_for_a
        assert expected_for_a < expected_total
        assert {str(row.company_id) for row in rows} == {str(identity_world.company_a)}



class TestTenantWrites:
    def test_cross_tenant_insert_is_rejected(
        self,
        identity_world: IdentityWorld,
        migration_database: Database,
        runtime_database: Database,
    ) -> None:
        with migration_database.session() as session:
            settings_a = session.execute(
                text("SELECT id FROM touche.company_settings WHERE company_id = :company"),
                {"company": identity_world.company_a},
            ).scalar_one()

        with pytest.raises(DBAPIError) as excinfo, runtime_database.session() as session:
            apply_context(session, company_id=identity_world.company_b)
            session.execute(
                text(
                    "INSERT INTO touche.company_setting_entry "
                    "(company_id, settings_id, key, value) "
                    "VALUES (:company, :settings, 'rogue', '1'::jsonb)"
                ),
                {"company": identity_world.company_a, "settings": settings_a},
            )
            session.flush()
        assert "row-level security" in str(excinfo.value).lower()

    def test_cross_tenant_update_changes_nothing(
        self, identity_world: IdentityWorld, runtime_database: Database
    ) -> None:
        with runtime_database.session() as session:
            apply_context(session, company_id=identity_world.company_b)
            updated = session.execute(
                text(
                    "UPDATE touche.company_setting_entry SET key = 'hijacked' "
                    "WHERE company_id = :company RETURNING id"
                ),
                {"company": identity_world.company_a},
            ).all()
            assert updated == []

    def test_cross_tenant_delete_changes_nothing(
        self, identity_world: IdentityWorld, runtime_database: Database
    ) -> None:
        with runtime_database.session() as session:
            apply_context(session, company_id=identity_world.company_b)
            deleted = session.execute(
                text(
                    "DELETE FROM touche.company_setting_entry "
                    "WHERE company_id = :company RETURNING id"
                ),
                {"company": identity_world.company_a},
            ).all()
            assert deleted == []

        with runtime_database.session() as session:
            apply_context(session, company_id=identity_world.company_a)
            assert count(session, "company_setting_entry") == 2

    def test_composite_foreign_key_blocks_a_cross_tenant_child(
        self, identity_world: IdentityWorld, migration_database: Database
    ) -> None:
        with migration_database.session() as session:
            settings_a = session.execute(
                text("SELECT id FROM touche.company_settings WHERE company_id = :company"),
                {"company": identity_world.company_a},
            ).scalar_one()

        with pytest.raises(IntegrityError), migration_database.session() as session:
            session.execute(
                text(
                    "INSERT INTO touche.company_setting_entry "
                    "(company_id, settings_id, key, value) "
                    "VALUES (:company, :settings, 'mismatched', '1'::jsonb)"
                ),
                {"company": identity_world.company_b, "settings": settings_a},
            )
            session.flush()


class TestAuditImmutability:
    def _seed_audit_row(self, identity_world: IdentityWorld, database: Database) -> None:
        with database.transaction() as session:
            session.execute(
                text(
                    "INSERT INTO touche.audit_record "
                    "(actor_type, action, outcome, company_id, details) "
                    "VALUES ('system', 'auth.logout', 'success', :company, '{}'::jsonb)"
                ),
                {"company": identity_world.company_a},
            )

    def test_runtime_role_cannot_update_or_delete_audit_rows(
        self,
        identity_world: IdentityWorld,
        migration_database: Database,
        runtime_database: Database,
    ) -> None:
        self._seed_audit_row(identity_world, migration_database)

        for statement in (
            "UPDATE touche.audit_record SET outcome = 'failure'",
            "DELETE FROM touche.audit_record",
        ):
            with (
                pytest.raises(DBAPIError) as excinfo,
                runtime_database.session() as session,
            ):
                session.execute(text(statement))
                session.flush()
            assert "permission denied" in str(excinfo.value).lower()

    def test_trigger_also_protects_the_table_from_the_owner(
        self, identity_world: IdentityWorld, migration_database: Database
    ) -> None:
        self._seed_audit_row(identity_world, migration_database)

        with pytest.raises(DBAPIError) as excinfo, migration_database.session() as session:
            session.execute(text("UPDATE touche.audit_record SET outcome = 'failure'"))
            session.flush()
        assert "append-only" in str(excinfo.value).lower()


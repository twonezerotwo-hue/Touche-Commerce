"""Shared pytest fixtures.

Unit tests never require a database: the app is built with an explicit settings
object pointing at an unused port, and readiness is monkeypatched.  Integration
tests (``@pytest.mark.integration``) use an isolated test database
(``touche_commerce_test``) derived from the configured DSNs, so a development or
production database is never touched.  When no DSN is configured the integration
tests skip with an explicit reason instead of pretending to pass.
"""

from __future__ import annotations

import os
import subprocess
import sys
from collections.abc import Callable, Iterator
from dataclasses import dataclass
from pathlib import Path
from uuid import UUID

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient
from pydantic import SecretStr
from sqlalchemy import create_engine, text
from sqlalchemy.engine import Engine
from sqlalchemy.exc import OperationalError

from app.core.config import Settings
from app.db.engine import Database
from app.main import create_app
from app.security.passwords import PasswordService
from app.security.permissions import Role
from app.services import admin
from tests.support import ORIGIN, TEST_PASSWORD

BACKEND_ROOT = Path(__file__).resolve().parents[1]


@pytest.hookimpl(tryfirst=True)
def pytest_configure(config: pytest.Config) -> None:
    """Keep pytest scratch files inside the git-ignored ``backend/var`` directory.

    On Windows a stale or ACL-restricted ``pytest-of-<user>`` folder in the temp
    directory (left behind by another tool that ran with a different security context)
    makes every ``tmp_path`` test fail with ``PermissionError``. A repository-local base
    directory is private to this checkout, cleaned at the start of each session and
    never committed.
    """
    if config.option.basetemp is None:
        # pytest creates the base directory but not its parent, which a fresh checkout lacks.
        (BACKEND_ROOT / "var").mkdir(parents=True, exist_ok=True)
        config.option.basetemp = BACKEND_ROOT / "var" / "pytest-tmp"
UNREACHABLE_DSN = "postgresql+psycopg://touche_app:unused_password@127.0.0.1:59999/touche_test"


@pytest.fixture()
def settings() -> Settings:
    """Settings for unit tests: real code paths, unreachable database."""
    return Settings(
        environment="test",
        database_url=SecretStr(UNREACHABLE_DSN),
        database_connect_timeout_seconds=1,
        database_pool_timeout_seconds=1,
        log_format="json",
        log_level="INFO",
    )


@pytest.fixture()
def app(settings: Settings) -> FastAPI:
    return create_app(settings)


@pytest.fixture()
def client(app: FastAPI) -> Iterator[TestClient]:
    # raise_server_exceptions=False lets us assert on the 500 envelope contract.
    with TestClient(app, raise_server_exceptions=False) as test_client:
        yield test_client


@pytest.fixture(scope="session")
def live_settings() -> Settings:
    """Settings loaded from the real environment/.env file."""
    loaded = Settings()
    if loaded.database_dsn is None:
        pytest.skip("TOUCHE_DATABASE_URL is not configured; integration test skipped.")
    return loaded


@pytest.fixture(scope="session")
def live_database(live_settings: Settings) -> Iterator[Database]:
    """A verified live database handle, or a skip with a precise reason."""
    database = Database(live_settings)
    readiness = database.check_readiness()
    if not readiness.ok:
        database.dispose()
        pytest.skip(
            "PostgreSQL is not reachable "
            f"({readiness.error_code}: {readiness.error_message}); integration test skipped."
        )
    yield database
    database.dispose()



# ---------------------------------------------------------------------------
# Stage 1A identity fixtures — isolated test database only
# ---------------------------------------------------------------------------
@dataclass(frozen=True)
class IdentityWorld:
    """Two companies, two users and the memberships that connect them."""

    company_a: UUID
    company_b: UUID
    company_c: UUID
    user_a: UUID
    user_b: UUID
    membership_a_admin: UUID
    membership_b_viewer: UUID
    membership_b_trader: UUID
    email_a: str
    email_b: str


@pytest.fixture(scope="session")
def test_settings(live_settings: Settings) -> Settings:
    """App-role settings for ``touche_commerce_test`` (never the dev database)."""
    runtime_dsn = live_settings.test_database_dsn
    migration_dsn = live_settings.test_migration_dsn
    if runtime_dsn is None or migration_dsn is None:
        pytest.skip("No database DSN configured; identity integration tests skipped.")
    return Settings(
        environment="test",
        database_url=SecretStr(runtime_dsn),
        database_migration_url=SecretStr(migration_dsn),
        log_level="WARNING",
        # Cheap Argon2 profile: the hashing code path is identical, the suite stays fast.
        argon2_time_cost=1,
        argon2_memory_cost_kib=8192,
        argon2_parallelism=1,
    )


@pytest.fixture(scope="session")
def test_engine(test_settings: Settings) -> Iterator[Engine]:
    """Prove the isolated database exists before running any schema work."""
    dsn = test_settings.test_database_dsn
    assert dsn is not None
    engine = create_engine(dsn, pool_pre_ping=True)
    try:
        with engine.connect() as connection:
            connection.execute(text("SELECT 1"))
    except OperationalError as exc:
        engine.dispose()
        if "does not exist" in str(exc):
            pytest.fail(
                "The isolated test database does not exist. Create it with "
                "scripts\\db\\setup-test-database.ps1, then re-run pytest. "
                f"Underlying error: {exc}"
            )
        pytest.skip(f"Test database unreachable ({exc.__class__.__name__}); skipping.")
    yield engine
    engine.dispose()


@pytest.fixture(scope="session")
def migration_database(test_settings: Settings, test_engine: Engine) -> Iterator[Database]:
    """Migration-role handle: runs Alembic and seeds fixtures (bypasses RLS)."""
    migration_dsn = test_settings.test_migration_dsn
    assert migration_dsn is not None
    env = {
        **os.environ,
        "TOUCHE_ENVIRONMENT": "test",
        "TOUCHE_DATABASE_MIGRATION_URL": migration_dsn,
    }
    result = subprocess.run(
        [sys.executable, "-m", "alembic", "upgrade", "head"],
        cwd=BACKEND_ROOT,
        env=env,
        capture_output=True,
        text=True,
        check=False,
    )
    if result.returncode != 0:
        pytest.fail(
            "alembic upgrade head failed against the test database:\n"
            f"{result.stdout}\n{result.stderr}"
        )
    database = Database(test_settings, dsn_override=migration_dsn)
    yield database
    database.dispose()



def _reset_identity_tables(database: Database) -> None:
    with database.transaction() as session:
        # The audit trigger blocks TRUNCATE by design; the owner disables it for
        # this explicit, test-only reset (the runtime role cannot do this).
        session.execute(text("ALTER TABLE touche.audit_record DISABLE TRIGGER USER"))
        session.execute(
            text(
                "TRUNCATE TABLE touche.company_setting_entry, touche.company_settings, "
                "touche.idempotency_record, touche.audit_record, touche.login_attempt, "
                "touche.auth_session, touche.membership, touche.company, touche.app_user "
                "RESTART IDENTITY CASCADE"
            )
        )
        session.execute(text("ALTER TABLE touche.audit_record ENABLE TRIGGER USER"))


@pytest.fixture()
def identity_world(
    migration_database: Database, test_settings: Settings
) -> Iterator[IdentityWorld]:
    """Reset identity tables and seed two companies + two users per test."""
    _reset_identity_tables(migration_database)
    hasher = PasswordService(test_settings)
    password_hash = hasher.hash(TEST_PASSWORD)

    with migration_database.transaction() as session:
        company_a = admin.create_company(
            session, name="TOUCHE Trading", country="GB", default_currency="GBP"
        )
        company_b = admin.create_company(
            session, name="Meridian Commodities", country="AE", default_currency="USD"
        )
        company_c = admin.create_company(
            session, name="Northwind Metals", country="DE", default_currency="EUR"
        )
        user_a = admin.create_user(
            session,
            email="amina@touche.example",
            display_name="Amina Haddad",
            password_hash=password_hash,
        )
        user_b = admin.create_user(
            session,
            email="bilal@touche.example",
            display_name="Bilal Rahman",
            password_hash=password_hash,
        )
        membership_a_admin = admin.grant_membership(
            session, user_id=user_a.id, company_id=company_a.id, role=Role.ADMIN
        )
        membership_b_viewer = admin.grant_membership(
            session, user_id=user_a.id, company_id=company_b.id, role=Role.VIEWER
        )
        membership_b_trader = admin.grant_membership(
            session, user_id=user_b.id, company_id=company_b.id, role=Role.TRADER
        )
        world = IdentityWorld(
            company_a=company_a.id,
            company_b=company_b.id,
            company_c=company_c.id,
            user_a=user_a.id,
            user_b=user_b.id,
            membership_a_admin=membership_a_admin.id,
            membership_b_viewer=membership_b_viewer.id,
            membership_b_trader=membership_b_trader.id,
            email_a=user_a.email,
            email_b=user_b.email,
        )
    yield world


@pytest.fixture(scope="session")
def identity_app(test_settings: Settings) -> FastAPI:
    """FastAPI app wired to the isolated test database (runtime role)."""
    return create_app(test_settings)


@pytest.fixture()
def client_factory(identity_app: FastAPI) -> Iterator[Callable[..., TestClient]]:
    """Create several independent cookie jars inside one test."""
    clients: list[TestClient] = []

    def make(
        *, origin: str | None = ORIGIN, headers: dict[str, str] | None = None
    ) -> TestClient:
        default_headers = {"User-Agent": "pytest-touche", **(headers or {})}
        if origin is not None:
            default_headers["Origin"] = origin
        client = TestClient(identity_app, headers=default_headers, raise_server_exceptions=False)
        client.__enter__()
        clients.append(client)
        return client

    yield make
    for created in clients:
        created.__exit__(None, None, None)


@pytest.fixture()
def api_client(client_factory: Callable[..., TestClient]) -> TestClient:
    return client_factory()


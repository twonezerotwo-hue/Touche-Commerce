"""Shared pytest fixtures.

Unit tests never require a database: the app is built with an explicit settings
object pointing at an unused port, and readiness is monkeypatched.  Integration
tests (``@pytest.mark.integration``) use the database configured in ``.env`` and
skip with an explicit reason when it is unreachable.
"""

from __future__ import annotations

from collections.abc import Iterator

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient
from pydantic import SecretStr

from app.core.config import Settings
from app.db.engine import Database
from app.main import create_app

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

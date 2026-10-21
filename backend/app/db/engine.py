"""Database connectivity, session factory and readiness checks."""

from __future__ import annotations

import re
from collections.abc import Iterator
from contextlib import contextmanager
from time import perf_counter
from typing import Any

from sqlalchemy import create_engine, text
from sqlalchemy.engine import Engine, make_url
from sqlalchemy.orm import Session, sessionmaker

from app.core.config import Settings
from app.core.logging import get_logger
from app.db.health import DatabaseReadiness

logger = get_logger("app.db")

# Matches "scheme://user:password@host" so credentials never reach logs.
_CONNECTION_SECRET_PATTERN = re.compile(
    r"(?P<scheme>[a-zA-Z][a-zA-Z0-9+.\-]*://)(?P<user>[^:/@\s]+):(?P<password>[^@/\s]+)@"
)


def redact_dsn(value: str) -> str:
    """Remove credentials from a connection string."""
    return _CONNECTION_SECRET_PATTERN.sub(
        lambda match: f"{match.group('scheme')}{match.group('user')}:***@", value
    )


def sanitise_error_message(message: str, *, limit: int = 400) -> str:
    """Make a driver error safe to log/return (no DSN, single line, bounded)."""
    collapsed = " ".join(redact_dsn(message).split())
    return collapsed[:limit]


class Database:
    """Owns the SQLAlchemy engine and session lifecycle for the application."""

    def __init__(self, settings: Settings, *, dsn_override: str | None = None) -> None:
        self._settings = settings
        self._engine: Engine | None = None
        self._session_factory: sessionmaker[Session] | None = None
        dsn = dsn_override or settings.database_dsn
        if dsn is not None:
            self._engine = self._build_engine(dsn)
            self._session_factory = sessionmaker(
                bind=self._engine,
                autoflush=False,
                expire_on_commit=False,
                class_=Session,
            )

    def _build_engine(self, dsn: str) -> Engine:
        settings = self._settings
        url = make_url(dsn)
        logger.info(
            "database.engine.initialising",
            extra={
                "database_host": url.host,
                "database_name": url.database,
                "database_role": url.username,
            },
        )
        connect_args: dict[str, Any] = {
            "connect_timeout": settings.database_connect_timeout_seconds,
            "application_name": settings.database_application_name,
            "sslmode": settings.database_ssl_mode,
            "options": (
                f"-c statement_timeout={settings.database_statement_timeout_ms}"
                " -c idle_in_transaction_session_timeout=15000"
            ),
        }
        return create_engine(
            dsn,
            pool_pre_ping=True,
            pool_size=settings.database_pool_size,
            max_overflow=settings.database_pool_max_overflow,
            pool_timeout=settings.database_pool_timeout_seconds,
            pool_recycle=1800,
            connect_args=connect_args,
        )

    # --- Accessors ---------------------------------------------------------
    @property
    def is_configured(self) -> bool:
        return self._engine is not None

    @property
    def engine(self) -> Engine:
        if self._engine is None:
            raise RuntimeError("Database is not configured (TOUCHE_DATABASE_URL is missing).")
        return self._engine

    def _require_session_factory(self) -> sessionmaker[Session]:
        if self._session_factory is None:
            raise RuntimeError("Database is not configured (TOUCHE_DATABASE_URL is missing).")
        return self._session_factory

    # --- Session / transaction management ---------------------------------
    @contextmanager
    def session(self) -> Iterator[Session]:
        """Yield a session, rolling back on error and always closing it."""
        session = self._require_session_factory()()
        try:
            yield session
        except Exception:
            session.rollback()
            raise
        finally:
            session.close()

    @contextmanager
    def transaction(self) -> Iterator[Session]:
        """Yield a session bound to an explicit transaction (commit on exit)."""
        with self.session() as session, session.begin():
            yield session

    # --- Health ------------------------------------------------------------
    def check_readiness(self) -> DatabaseReadiness:
        """Verify the runtime role can open a connection and execute a query."""
        if self._engine is None:
            return DatabaseReadiness(
                ok=False,
                latency_ms=0.0,
                error_code="DATABASE_NOT_CONFIGURED",
                error_message="TOUCHE_DATABASE_URL is not configured for this environment.",
            )

        started_at = perf_counter()
        try:
            with self._engine.connect() as connection:
                row = (
                    connection.execute(
                        text(
                            "SELECT current_setting('server_version') AS server_version,"
                            " current_user AS role_name"
                        )
                    )
                    .mappings()
                    .one()
                )
                connection.execute(text("SELECT 1"))
        except Exception as exc:
            latency_ms = round((perf_counter() - started_at) * 1000, 2)
            safe_message = sanitise_error_message(str(exc))
            logger.warning(
                "database.readiness.failed",
                extra={
                    "error_type": type(exc).__name__,
                    "error_message": safe_message,
                    "latency_ms": latency_ms,
                },
            )
            return DatabaseReadiness(
                ok=False,
                latency_ms=latency_ms,
                error_code="DATABASE_UNAVAILABLE",
                error_message=safe_message,
            )

        latency_ms = round((perf_counter() - started_at) * 1000, 2)
        readiness = DatabaseReadiness(
            ok=True,
            latency_ms=latency_ms,
            server_version=str(row["server_version"]),
            role=str(row["role_name"]),
        )
        logger.info(
            "database.readiness.ok",
            extra={
                "database_server_version": readiness.server_version,
                "database_role": readiness.role,
                "latency_ms": latency_ms,
            },
        )
        return readiness

    def dispose(self) -> None:
        """Dispose the connection pool (called on shutdown)."""
        if self._engine is not None:
            self._engine.dispose()

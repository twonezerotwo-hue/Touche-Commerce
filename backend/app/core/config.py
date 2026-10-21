"""Explicit, validated configuration for the TOUCHE COMMERCE API.

All runtime configuration comes from environment variables prefixed with
``TOUCHE_`` (optionally supplied through a local ``.env`` file).  Values that
would silently weaken security outside local development are rejected at
start-up instead of failing later at request time.
"""

from __future__ import annotations

from functools import lru_cache
from pathlib import Path
from typing import Literal

from pydantic import Field, SecretStr, field_validator, model_validator
from pydantic_settings import BaseSettings, SettingsConfigDict

REPO_ROOT = Path(__file__).resolve().parents[3]
BACKEND_ROOT = REPO_ROOT / "backend"

Environment = Literal["local", "test", "ci", "staging", "production"]
LogFormat = Literal["json", "text"]
SslMode = Literal["disable", "allow", "prefer", "require", "verify-ca", "verify-full"]

_VALID_LOG_LEVELS = frozenset({"CRITICAL", "ERROR", "WARNING", "INFO", "DEBUG"})
_LOOPBACK_HOST_MARKERS = ("localhost", "127.0.0.1", "0.0.0.0", "::1")
_NON_LOCAL_ENVIRONMENTS = frozenset({"staging", "production"})


class ConfigurationError(RuntimeError):
    """Raised when the service is misconfigured or a required value is absent."""


class Settings(BaseSettings):
    """Validated application settings.

    Secrets are wrapped in :class:`~pydantic.SecretStr` so that accidental
    ``repr()``/log output never exposes credentials.
    """

    model_config = SettingsConfigDict(
        env_prefix="TOUCHE_",
        env_file=(REPO_ROOT / ".env", BACKEND_ROOT / ".env"),
        env_file_encoding="utf-8",
        extra="ignore",
        case_sensitive=False,
    )

    # --- Application identity ---------------------------------------------
    app_name: str = "TOUCHE COMMERCE API"
    service_name: str = "touche-commerce-api"
    app_version: str = "0.1.0"
    environment: Environment = "local"
    debug: bool = False
    api_prefix: str = "/api/v1"

    # --- Observability -----------------------------------------------------
    log_level: str = "INFO"
    log_format: LogFormat = "json"
    request_id_header: str = "X-Request-ID"

    # --- Database ----------------------------------------------------------
    # Two DSNs on purpose: the runtime role cannot run DDL (docs/DECISIONS.md #4).
    database_url: SecretStr | None = None
    database_migration_url: SecretStr | None = None
    database_pool_size: int = Field(default=5, ge=1, le=50)
    database_pool_max_overflow: int = Field(default=5, ge=0, le=50)
    database_pool_timeout_seconds: int = Field(default=5, ge=1, le=60)
    database_connect_timeout_seconds: int = Field(default=3, ge=1, le=60)
    database_statement_timeout_ms: int = Field(default=5000, ge=100, le=120_000)
    database_ssl_mode: SslMode = "prefer"
    database_application_name: str = "touche-commerce-api"

    # --- HTTP --------------------------------------------------------------
    cors_allowed_origins: list[str] = Field(
        default_factory=lambda: ["http://localhost:3000", "http://127.0.0.1:3000"]
    )
    cors_allow_credentials: bool = True

    # --- Session policy (initial values; enforced from Stage 1A) -----------
    session_idle_timeout_seconds: int = Field(default=1800, ge=60)
    session_absolute_timeout_seconds: int = Field(default=43_200, ge=300)
    session_cookie_name: str = "touche_session"
    session_cookie_secure: bool = False
    csrf_header_name: str = "X-CSRF-Token"

    # --- Login rate limiting (Stage 1A) ------------------------------------
    login_rate_limit_attempts: int = Field(default=10, ge=1)
    login_rate_limit_window_seconds: int = Field(default=300, ge=1)

    # --- Contracts ---------------------------------------------------------
    idempotency_ttl_hours: int = Field(default=24, ge=1)
    pagination_default_limit: int = Field(default=25, ge=1)
    pagination_max_limit: int = Field(default=100, ge=1)

    # --- Derived helpers ---------------------------------------------------
    @property
    def docs_enabled(self) -> bool:
        """Interactive docs stay available everywhere except production."""
        return self.environment != "production"

    @property
    def database_dsn(self) -> str | None:
        """Runtime DSN, or ``None`` when the database is not configured."""
        return self.database_url.get_secret_value() if self.database_url else None

    @property
    def migration_dsn(self) -> str:
        """DSN used by Alembic (migration role); raises when unavailable."""
        secret = self.database_migration_url or self.database_url
        if secret is None:
            raise ConfigurationError(
                "TOUCHE_DATABASE_MIGRATION_URL (or TOUCHE_DATABASE_URL) must be set "
                "to run database migrations."
            )
        return secret.get_secret_value()

    @property
    def api_openapi_url(self) -> str:
        return f"{self.api_prefix}/openapi.json"

    # --- Validation --------------------------------------------------------
    @field_validator("log_level")
    @classmethod
    def _validate_log_level(cls, value: str) -> str:
        normalised = value.strip().upper()
        if normalised not in _VALID_LOG_LEVELS:
            raise ValueError(
                f"log_level must be one of {sorted(_VALID_LOG_LEVELS)}, got {value!r}"
            )
        return normalised

    @field_validator("api_prefix")
    @classmethod
    def _validate_api_prefix(cls, value: str) -> str:
        if not value.startswith("/"):
            raise ValueError("api_prefix must start with '/'")
        return value.rstrip("/") or "/api/v1"

    @field_validator("cors_allowed_origins")
    @classmethod
    def _validate_origins(cls, value: list[str]) -> list[str]:
        cleaned: list[str] = []
        for origin in value:
            origin = origin.strip().rstrip("/")
            if not origin.startswith(("http://", "https://")):
                raise ValueError(f"CORS origin must be an absolute http(s) origin, got {origin!r}")
            cleaned.append(origin)
        if not cleaned:
            raise ValueError("cors_allowed_origins must contain at least one origin")
        return cleaned

    @model_validator(mode="after")
    def _validate_policies(self) -> Settings:
        if self.session_idle_timeout_seconds >= self.session_absolute_timeout_seconds:
            raise ValueError(
                "session_idle_timeout_seconds must be smaller than "
                "session_absolute_timeout_seconds"
            )
        if self.pagination_default_limit > self.pagination_max_limit:
            raise ValueError("pagination_default_limit must not exceed pagination_max_limit")
        if self.database_pool_size + self.database_pool_max_overflow > 45:
            raise ValueError("database pool size + overflow must stay below 45 connections")

        if self.environment in _NON_LOCAL_ENVIRONMENTS:
            self._validate_non_local()
        elif self.environment != "test":
            # The test harness may intentionally omit the DSN to exercise the
            # "database not configured" readiness branch.
            self._require_database_url()
        return self

    def _require_database_url(self) -> None:
        if self.database_url is None:
            raise ValueError(
                f"TOUCHE_DATABASE_URL is required when TOUCHE_ENVIRONMENT={self.environment!r}"
            )

    def _validate_non_local(self) -> None:
        self._require_database_url()
        if self.debug:
            raise ValueError("debug must be disabled outside local development")
        if not self.session_cookie_secure:
            raise ValueError("session_cookie_secure must be true outside local development")
        if self.log_format != "json":
            raise ValueError("log_format must be 'json' outside local development")
        for origin in self.cors_allowed_origins:
            if not origin.startswith("https://"):
                raise ValueError(f"CORS origin must use https outside local development: {origin}")
            if any(marker in origin for marker in _LOOPBACK_HOST_MARKERS):
                raise ValueError(f"CORS origin must not point at a loopback host: {origin}")


@lru_cache(maxsize=1)
def get_settings() -> Settings:
    """Return the process-wide settings instance (cached)."""
    return Settings()


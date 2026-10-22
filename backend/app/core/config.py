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
from sqlalchemy.engine import make_url

REPO_ROOT = Path(__file__).resolve().parents[3]
BACKEND_ROOT = REPO_ROOT / "backend"

Environment = Literal["local", "test", "ci", "staging", "production"]
LogFormat = Literal["json", "text"]
SslMode = Literal["disable", "allow", "prefer", "require", "verify-ca", "verify-full"]
SameSite = Literal["lax", "strict"]

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

    # --- Session policy (Stage 1A) -----------------------------------------
    session_idle_timeout_seconds: int = Field(default=1800, ge=60)
    session_absolute_timeout_seconds: int = Field(default=43_200, ge=300)
    session_cookie_name: str = "touche_session"
    session_cookie_secure: bool = False
    session_cookie_samesite: SameSite = "lax"
    session_cookie_path: str = "/"
    session_cookie_domain: str | None = None
    csrf_header_name: str = "X-CSRF-Token"

    # --- Password hashing (Argon2id, OWASP baseline) -----------------------
    password_min_length: int = Field(default=12, ge=8, le=128)
    argon2_time_cost: int = Field(default=2, ge=1, le=10)
    argon2_memory_cost_kib: int = Field(default=19_456, ge=8192, le=262_144)
    argon2_parallelism: int = Field(default=1, ge=1, le=8)

    # --- Login rate limiting -----------------------------------------------
    login_rate_limit_attempts: int = Field(default=10, ge=1)
    login_rate_limit_window_seconds: int = Field(default=300, ge=1)
    login_rate_limit_ip_attempts: int = Field(default=30, ge=1)

    # --- Test harness ------------------------------------------------------
    # Derived from the runtime DSNs by swapping the database name, so the
    # integration suite can never point at a development database.
    test_database_name: str = "touche_commerce_test"

    # --- Documents ---------------------------------------------------------
    # Files live outside every served directory; the API streams them only after
    # authorising both the company and the linked business entity.
    document_storage_path: Path = BACKEND_ROOT / "var" / "documents"
    document_max_bytes: int = Field(default=10 * 1024 * 1024, ge=1024, le=100 * 1024 * 1024)

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

    @property
    def secure_cookies(self) -> bool:
        """Cookies are Secure whenever the deployment is not local development."""
        return self.session_cookie_secure or self.environment in _NON_LOCAL_ENVIRONMENTS

    @property
    def effective_session_cookie_name(self) -> str:
        """``__Host-`` prefixed cookie name outside local development (ADR-002)."""
        if self.environment in _NON_LOCAL_ENVIRONMENTS:
            return f"__Host-{self.session_cookie_name}"
        return self.session_cookie_name

    @property
    def session_cookie_max_age(self) -> int:
        """Browser-side lifetime: the idle window, never the absolute window."""
        return self.session_idle_timeout_seconds

    @property
    def trusted_origins(self) -> tuple[str, ...]:
        """Origins allowed to send state-changing requests (Origin validation)."""
        return tuple(self.cors_allowed_origins)

    def _resolved_dsn(self, secret: SecretStr | None, database_name: str) -> str | None:
        """Return ``secret``'s DSN with the database name replaced."""
        if secret is None:
            return None
        return make_url(secret.get_secret_value()).set(database=database_name).render_as_string(
            hide_password=False
        )

    @property
    def test_database_dsn(self) -> str | None:
        """Runtime DSN pointing at the isolated test database, when configured."""
        return self._resolved_dsn(self.database_url, self.test_database_name)

    @property
    def test_migration_dsn(self) -> str | None:
        """Migration DSN pointing at the isolated test database, when configured."""
        secret = self.database_migration_url or self.database_url
        return self._resolved_dsn(secret, self.test_database_name)

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

    @field_validator("session_cookie_path")
    @classmethod
    def _validate_cookie_path(cls, value: str) -> str:
        if not value.startswith("/"):
            raise ValueError("session_cookie_path must start with '/'")
        return value

    @field_validator("session_cookie_name")
    @classmethod
    def _validate_cookie_name(cls, value: str) -> str:
        if not value or any(character in value for character in " ;,=\"\\"):
            raise ValueError("session_cookie_name must be a valid cookie name")
        return value

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
        if self.session_cookie_domain:
            raise ValueError(
                "session_cookie_domain must be unset outside local development: "
                "the __Host- cookie prefix forbids a Domain attribute"
            )
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


"""Explicit, validated configuration for the TOUCHE COMMERCE API.

All runtime configuration comes from environment variables prefixed with
``TOUCHE_`` (optionally supplied through a local ``.env`` file).  Values that
would silently weaken security outside local development are rejected at
start-up instead of failing later at request time.
"""

from __future__ import annotations

import re
from decimal import Decimal
from functools import lru_cache
from pathlib import Path
from typing import Literal
from urllib.parse import urlsplit

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

    # --- Finance integration (Stage 5C, read-only) --------------------------
    # Disabled by default: no probe, no network I/O, no accounting write path.
    # The dedicated service credentials stay server-side and are never exposed
    # through the browser or OpenAPI. The URL remains a literal loopback address
    # until a separate TLS/reverse-proxy security review exists (ADR-039).
    finance_integration_enabled: bool = False
    finance_integration_base_url: str = "http://127.0.0.1:8765"
    finance_integration_key_id: SecretStr | None = None
    finance_integration_secret: SecretStr | None = None
    finance_integration_timeout_seconds: float = Field(default=2.0, ge=0.1, le=10.0)
    finance_integration_max_response_bytes: int = Field(
        default=1_048_576, ge=1_024, le=4_194_304
    )

    # --- E-YAY market context (Stage 8; read-only, loopback-only) ----------
    eyay_enabled: bool = False
    eyay_base_url: str = "http://127.0.0.1:9000"
    eyay_timeout_seconds: float = Field(default=2.0, ge=0.1, le=5.0)
    eyay_max_response_bytes: int = Field(default=131_072, ge=8_192, le=524_288)

    # --- AI Office (Stage 6) ------------------------------------------------
    # Disabled by default. The provider credential stays server-side and is never
    # returned by any endpoint. A non-mock provider receives commercial data, so
    # it additionally requires an explicit acknowledgement (ADR-048). The mock
    # provider is deterministic, offline and allowed in local/test/ci only.
    ai_enabled: bool = False
    ai_provider: Literal["mock", "openai_compatible", "anthropic"] = "mock"
    ai_local_fallback_enabled: bool = False
    ai_local_fallback_base_url: str = "http://127.0.0.1:11434/v1"
    ai_local_fallback_model: str = Field(default="qwen3:8b", min_length=1, max_length=120)
    ai_model: str = Field(default="mock-trade-director-1", min_length=1, max_length=120)
    ai_base_url: str | None = None
    ai_api_key: SecretStr | None = None
    ai_external_processing_acknowledged: bool = False
    ai_request_timeout_seconds: float = Field(default=30.0, ge=1.0, le=120.0)
    ai_max_retries: int = Field(default=2, ge=0, le=5)
    ai_retry_backoff_seconds: float = Field(default=0.5, ge=0.0, le=10.0)
    ai_max_model_steps: int = Field(default=6, ge=1, le=12)
    ai_max_tool_calls_per_request: int = Field(default=10, ge=1, le=30)
    ai_max_output_tokens: int = Field(default=1500, ge=64, le=8192)
    ai_max_request_tokens: int = Field(default=40_000, ge=1_000, le=400_000)
    ai_max_context_messages: int = Field(default=12, ge=2, le=50)
    ai_max_user_message_chars: int = Field(default=4_000, ge=50, le=20_000)
    ai_max_tool_result_chars: int = Field(default=12_000, ge=500, le=60_000)
    ai_max_list_items: int = Field(default=20, ge=1, le=50)
    ai_max_concurrent_runs: int = Field(default=4, ge=1, le=32)
    ai_max_runs_per_user_per_minute: int = Field(default=6, ge=1, le=120)
    ai_run_deadline_seconds: float = Field(default=120.0, ge=5.0, le=900.0)
    ai_daily_token_budget: int = Field(default=500_000, ge=1_000)
    ai_daily_cost_budget_usd: Decimal = Field(default=Decimal("5.00"), ge=0)
    ai_monthly_cost_cap_enabled: bool = False
    ai_monthly_cost_cap_usd: Decimal = Field(default=Decimal("10.00"), ge=0)
    ai_price_input_per_million_usd: Decimal = Field(default=Decimal("0"), ge=0)
    ai_price_output_per_million_usd: Decimal = Field(default=Decimal("0"), ge=0)

    # --- Derived helpers ---------------------------------------------------
    @property
    def ai_effective_base_url(self) -> str | None:
        """Provider base URL with the documented default for each adapter."""
        if self.ai_base_url:
            return self.ai_base_url.rstrip("/")
        if self.ai_provider == "anthropic":
            return "https://api.anthropic.com"
        return None

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

    @field_validator("finance_integration_key_id")
    @classmethod
    def _validate_finance_key_id(cls, value: SecretStr | None) -> SecretStr | None:
        """Require the Finance key-id shape without ever logging the value."""
        if value is None:
            return None
        candidate = value.get_secret_value().strip()
        if not candidate:
            return None
        if not re.fullmatch(r"key_[0-9a-f]{16}", candidate):
            raise ValueError("finance_integration_key_id must match key_<16 hex characters>")
        return SecretStr(candidate)

    @field_validator("finance_integration_secret")
    @classmethod
    def _validate_finance_secret(cls, value: SecretStr | None) -> SecretStr | None:
        """Bound the service secret and reject trivially small values."""
        if value is None:
            return None
        candidate = value.get_secret_value().strip()
        if not candidate:
            return None
        if len(candidate) < 32 or len(candidate) > 512:
            raise ValueError("finance_integration_secret must be between 32 and 512 characters")
        return SecretStr(candidate)

    @field_validator("finance_integration_base_url")
    @classmethod
    def _validate_finance_base_url(cls, value: str) -> str:
        """Keep the Stage 5A connector on a literal loopback endpoint.

        Finance's health endpoint is unauthenticated, but its business endpoints
        trust a local session.  Allowing a remote URL here would invite a future
        adapter to reuse that shortcut; a dedicated service credential is a
        prerequisite for anything beyond loopback (ADR-039).
        """

        candidate = value.strip()
        parsed = urlsplit(candidate)
        if parsed.scheme != "http":
            raise ValueError("finance_integration_base_url must use http on a loopback address")
        if parsed.username is not None or parsed.password is not None:
            raise ValueError("finance_integration_base_url must not contain credentials")
        if parsed.hostname not in {"127.0.0.1", "::1"}:
            raise ValueError("finance_integration_base_url must point at 127.0.0.1 or ::1")
        if parsed.path not in {"", "/"} or parsed.query or parsed.fragment:
            raise ValueError(
                "finance_integration_base_url must not contain a path, query or fragment"
            )
        try:
            _ = parsed.port
        except ValueError as exc:
            raise ValueError("finance_integration_base_url contains an invalid port") from exc
        return candidate.rstrip("/")

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

        self._validate_ai()
        if self.environment in _NON_LOCAL_ENVIRONMENTS:
            self._validate_non_local()
        elif self.environment != "test":
            # The test harness may intentionally omit the DSN to exercise the
            # "database not configured" readiness branch.
            self._require_database_url()
        return self

    def _validate_ai(self) -> None:
        """Refuse an AI configuration that could leak data or credentials."""
        base = self.ai_effective_base_url
        if base is not None:
            parts = urlsplit(base)
            if parts.scheme not in {"http", "https"} or not parts.hostname:
                raise ValueError("ai_base_url must be an http(s) URL with a host")
            if parts.username or parts.password:
                raise ValueError("ai_base_url must not contain credentials")
            if parts.query or parts.fragment:
                raise ValueError("ai_base_url must not contain a query or fragment")
            loopback = parts.hostname in {"localhost", "127.0.0.1", "::1"}
            if parts.scheme == "http" and not loopback:
                raise ValueError("ai_base_url must use https unless it is a loopback address")
        if self.ai_local_fallback_enabled:
            if self.ai_provider != "openai_compatible" or not self.ai_enabled:
                raise ValueError("local AI fallback requires an enabled OpenAI-compatible API")
            local = urlsplit(self.ai_local_fallback_base_url)
            if (
                local.scheme != "http"
                or local.hostname not in {"127.0.0.1", "::1"}
                or local.username is not None
                or local.password is not None
                or local.path != "/v1"
                or local.query
                or local.fragment
            ):
                raise ValueError(
                    "ai_local_fallback_base_url must be http://127.0.0.1:<port>/v1"
                )
            try:
                port = local.port
            except ValueError as exc:
                raise ValueError("local AI fallback port is invalid") from exc
            if port is None or not 1 <= port <= 65535:
                raise ValueError("local AI fallback must have an explicit TCP port")
        if not self.ai_enabled:
            return
        if self.ai_provider == "mock":
            if self.environment in _NON_LOCAL_ENVIRONMENTS:
                raise ValueError("the mock AI provider is not allowed in staging or production")
            return
        if self.environment == "production" and not self.ai_monthly_cost_cap_enabled:
            raise ValueError("real production AI requires ai_monthly_cost_cap_enabled")
        if self.ai_monthly_cost_cap_enabled:
            if (
                self.ai_monthly_cost_cap_usd <= 0
                or self.ai_price_input_per_million_usd <= 0
                or self.ai_price_output_per_million_usd <= 0
            ):
                raise ValueError("monthly AI cap requires positive cap and token prices")
        if self.ai_api_key is None or not self.ai_api_key.get_secret_value().strip():
            raise ValueError("ai_api_key is required for a real AI provider")
        if base is None:
            raise ValueError("ai_base_url is required for the openai_compatible provider")
        if not self.ai_external_processing_acknowledged:
            raise ValueError(
                "a real AI provider receives commercial data: set "
                "TOUCHE_AI_EXTERNAL_PROCESSING_ACKNOWLEDGED=true only after reviewing ADR-048"
            )

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


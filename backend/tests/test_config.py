"""Configuration validation tests ("fail safely" behaviour)."""

from __future__ import annotations

import pytest
from pydantic import SecretStr, ValidationError

from app.core.config import ConfigurationError, Settings

_DSN = "postgresql+psycopg://touche_app:secret_pw@127.0.0.1:5432/touche_commerce"


def _settings(**overrides: object) -> Settings:
    values: dict[str, object] = {
        "environment": "local",
        "database_url": SecretStr(_DSN),
        "_env_file": None,
    }
    values.update(overrides)
    return Settings(**values)  # type: ignore[arg-type]


def test_initial_security_policies_have_documented_defaults() -> None:
    settings = _settings()

    assert settings.session_idle_timeout_seconds == 1800
    assert settings.session_absolute_timeout_seconds == 43_200
    assert settings.idempotency_ttl_hours == 24
    assert settings.pagination_default_limit == 25
    assert settings.pagination_max_limit == 100
    assert settings.login_rate_limit_attempts == 10
    assert settings.api_prefix == "/api/v1"
    assert settings.docs_enabled is True


def test_database_url_is_required_outside_test_harness() -> None:
    with pytest.raises(ValidationError, match="TOUCHE_DATABASE_URL is required"):
        _settings(database_url=None)


def test_missing_migration_dsn_raises_configuration_error() -> None:
    # Both DSNs are explicitly cleared: the test must not inherit them from the
    # developer's environment or .env file.
    settings = Settings(
        environment="test",
        database_url=None,
        database_migration_url=None,
        _env_file=None,
    )

    with pytest.raises(ConfigurationError):
        _ = settings.migration_dsn


def test_secrets_are_not_exposed_by_repr() -> None:
    settings = _settings()

    assert "secret_pw" not in repr(settings)
    assert settings.database_dsn is not None
    assert "secret_pw" in settings.database_dsn  # only via explicit accessor


def test_production_requires_secure_settings() -> None:
    with pytest.raises(ValidationError, match="session_cookie_secure"):
        _settings(
            environment="production",
            cors_allowed_origins=["https://app.touche.example"],
        )

    with pytest.raises(ValidationError, match="https"):
        _settings(
            environment="production",
            session_cookie_secure=True,
            cors_allowed_origins=["http://app.touche.example"],
        )

    with pytest.raises(ValidationError, match="loopback"):
        _settings(
            environment="production",
            session_cookie_secure=True,
            cors_allowed_origins=["https://localhost:3000"],
        )

    with pytest.raises(ValidationError, match="debug"):
        _settings(
            environment="production",
            session_cookie_secure=True,
            debug=True,
            cors_allowed_origins=["https://app.touche.example"],
        )


def test_idle_timeout_must_be_shorter_than_absolute_timeout() -> None:
    with pytest.raises(ValidationError, match="session_idle_timeout_seconds"):
        _settings(session_idle_timeout_seconds=43_200, session_absolute_timeout_seconds=1800)


def test_pagination_default_must_not_exceed_maximum() -> None:
    with pytest.raises(ValidationError, match="pagination_default_limit"):
        _settings(pagination_default_limit=250, pagination_max_limit=100)


def test_invalid_log_level_is_rejected() -> None:
    with pytest.raises(ValidationError, match="log_level"):
        _settings(log_level="VERBOSE")


def test_cors_origin_must_be_absolute() -> None:
    with pytest.raises(ValidationError, match="CORS origin"):
        _settings(cors_allowed_origins=["localhost:3000"])


def test_api_prefix_must_start_with_slash() -> None:
    with pytest.raises(ValidationError, match="api_prefix"):
        _settings(api_prefix="api/v1")

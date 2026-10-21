"""Structured logging and secret redaction smoke tests."""

from __future__ import annotations

import io
import json
import logging
from collections.abc import Iterator
from typing import Any

import pytest
from pydantic import SecretStr

from app.core.config import Settings
from app.core.context import reset_request_id, set_request_id
from app.core.logging import configure_logging, redact
from app.db.engine import redact_dsn, sanitise_error_message

_DSN = "postgresql+psycopg://touche_app:super_secret_pw@127.0.0.1:5432/touche_commerce"


def _settings() -> Settings:
    return Settings(
        environment="test",
        database_url=SecretStr(_DSN),
        log_format="json",
        log_level="INFO",
    )


@pytest.fixture(autouse=True)
def _restore_root_logging() -> Iterator[None]:
    """Otherwise configure_logging() would leak into the rest of the suite."""
    root = logging.getLogger()
    original_handlers = list(root.handlers)
    original_level = root.level
    try:
        yield
    finally:
        for handler in list(root.handlers):
            root.removeHandler(handler)
        for handler in original_handlers:
            root.addHandler(handler)
        root.setLevel(original_level)


def _last_record(stream: io.StringIO) -> dict[str, Any]:
    lines = [line for line in stream.getvalue().splitlines() if line.strip()]
    assert lines, "no log output captured"
    parsed = json.loads(lines[-1])
    assert isinstance(parsed, dict)
    return parsed


def test_json_formatter_emits_structured_record() -> None:
    stream = io.StringIO()
    configure_logging(_settings(), stream=stream)
    logger = logging.getLogger("tests.structured")

    logger.info(
        "unit.test.event",
        extra={"duration_ms": 3.5, "aggregate_id": "deal-1", "document_body": "TOP SECRET"},
    )

    record = _last_record(stream)
    assert record["message"] == "unit.test.event"
    assert record["level"] == "INFO"
    assert record["logger"] == "tests.structured"
    assert record["service"] == "touche-commerce-api"
    assert record["environment"] == "test"
    assert record["duration_ms"] == 3.5
    assert record["aggregate_id"] == "deal-1"
    assert record["document_body"] == "[redacted]"
    assert record["timestamp"].endswith("+00:00")


def test_request_id_is_injected_from_request_context() -> None:
    stream = io.StringIO()
    configure_logging(_settings(), stream=stream)
    logger = logging.getLogger("tests.correlation")

    token = set_request_id("req-12345678")
    try:
        logger.info("correlated.event")
    finally:
        reset_request_id(token)

    record = _last_record(stream)
    assert record["request_id"] == "req-12345678"


def test_redact_masks_sensitive_keys_recursively() -> None:
    payload = redact(
        {
            "password": "p",
            "nested": {"session_token": "abc", "safe": 1},
            "items": [{"api_key": "k", "amount": "10.50"}],
        }
    )

    assert payload["password"] == "[redacted]"
    assert payload["nested"]["session_token"] == "[redacted]"
    assert payload["nested"]["safe"] == 1
    assert payload["items"][0]["api_key"] == "[redacted]"
    assert payload["items"][0]["amount"] == "10.50"


def test_dsn_credentials_are_redacted() -> None:
    redacted = redact_dsn(_DSN)

    assert "super_secret_pw" not in redacted
    assert redacted == "postgresql+psycopg://touche_app:***@127.0.0.1:5432/touche_commerce"


def test_sanitise_error_message_removes_credentials_and_newlines() -> None:
    message = f"connection failed for {_DSN}\nsecond line"

    sanitised = sanitise_error_message(message)

    assert "super_secret_pw" not in sanitised
    assert "\n" not in sanitised

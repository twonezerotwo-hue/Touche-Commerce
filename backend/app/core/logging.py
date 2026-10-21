"""Structured JSON logging with mandatory secret redaction.

Log records are emitted as single-line JSON objects so that they can be shipped
to any log aggregator without a custom parser.  Request-scoped correlation ids
are injected automatically from :mod:`app.core.context`.

Hard rules (docs/DECISIONS.md #15):
* never log credentials, session tokens, cookies, document bodies or raw
  request/response payloads;
* any field whose *name* looks sensitive is redacted defensively, even if a
  caller accidentally passes it.
"""

from __future__ import annotations

import json
import logging
import re
import sys
from collections.abc import Mapping
from datetime import UTC, datetime
from typing import Any

from app.core.config import Settings
from app.core.context import get_company_id, get_request_id

REDACTED = "[redacted]"
_MAX_REDACTION_DEPTH = 6

_SENSITIVE_KEY_PATTERN = re.compile(
    r"(pass(word|wd)?|secret|token|authoriz|cookie|credential|api[_-]?key|private[_-]?key"
    r"|session[_-]?id|bearer|signature|document[_-]?body|request[_-]?body|response[_-]?body)",
    re.IGNORECASE,
)

# Attributes that are part of every LogRecord and must not be copied verbatim.
_RESERVED_RECORD_KEYS = frozenset(
    {
        "args",
        "asctime",
        "created",
        "exc_info",
        "exc_text",
        "filename",
        "funcName",
        "levelname",
        "levelno",
        "lineno",
        "message",
        "module",
        "msecs",
        "msg",
        "name",
        "pathname",
        "process",
        "processName",
        "relativeCreated",
        "stack_info",
        "taskName",
        "thread",
        "threadName",
    }
)


def is_sensitive_key(key: str) -> bool:
    """Return ``True`` when a field name must never be logged verbatim."""
    return bool(_SENSITIVE_KEY_PATTERN.search(key))


def redact(value: Any, *, _depth: int = 0) -> Any:
    """Recursively redact sensitive mapping keys and coerce exotic values."""
    if _depth > _MAX_REDACTION_DEPTH:
        return "[depth-limit]"
    if isinstance(value, Mapping):
        return {
            str(key): (
                REDACTED if is_sensitive_key(str(key)) else redact(item, _depth=_depth + 1)
            )
            for key, item in value.items()
        }
    if isinstance(value, (list, tuple, set, frozenset)):
        return [redact(item, _depth=_depth + 1) for item in value]
    if isinstance(value, (str, int, float, bool)) or value is None:
        return value
    if isinstance(value, (datetime,)):
        return value.isoformat()
    return str(value)


class JsonFormatter(logging.Formatter):
    """Render a :class:`logging.LogRecord` as a single JSON line."""

    def __init__(self, *, service: str, environment: str, version: str) -> None:
        super().__init__()
        self._service = service
        self._environment = environment
        self._version = version

    def format(self, record: logging.LogRecord) -> str:
        payload: dict[str, Any] = {
            "timestamp": datetime.fromtimestamp(record.created, tz=UTC).isoformat(),
            "level": record.levelname,
            "logger": record.name,
            "message": record.getMessage(),
            "service": self._service,
            "environment": self._environment,
            "version": self._version,
        }

        request_id = get_request_id()
        if request_id:
            payload["request_id"] = request_id
        company_id = get_company_id()
        if company_id:
            payload["company_id"] = company_id

        for key, value in record.__dict__.items():
            if key in _RESERVED_RECORD_KEYS or key.startswith("_"):
                continue
            if key in {"service", "environment", "version"}:
                continue
            payload[key] = value

        if record.exc_info:
            payload["exception"] = self.formatException(record.exc_info)
        if record.stack_info:
            payload["stack"] = self.formatStack(record.stack_info)

        return json.dumps(redact(payload), ensure_ascii=False, default=str)


def configure_logging(settings: Settings, *, stream: Any | None = None) -> None:
    """Install the process-wide logging configuration (idempotent)."""
    output = stream if stream is not None else sys.stdout
    handler = logging.StreamHandler(stream=output)
    if settings.log_format == "json":
        handler.setFormatter(
            JsonFormatter(
                service=settings.service_name,
                environment=settings.environment,
                version=settings.app_version,
            )
        )
    else:  # pragma: no cover - local convenience only
        handler.setFormatter(
            logging.Formatter("%(asctime)s %(levelname)-8s %(name)s :: %(message)s")
        )

    root = logging.getLogger()
    for existing in list(root.handlers):
        root.removeHandler(existing)
    root.addHandler(handler)
    root.setLevel(settings.log_level)

    # Uvicorn installs its own handlers; route them through the same JSON sink.
    for logger_name in ("uvicorn", "uvicorn.error", "uvicorn.access"):
        uvicorn_logger = logging.getLogger(logger_name)
        uvicorn_logger.handlers.clear()
        uvicorn_logger.propagate = True


def get_logger(name: str) -> logging.Logger:
    """Return a namespaced application logger."""
    return logging.getLogger(name)

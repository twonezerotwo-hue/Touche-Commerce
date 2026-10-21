"""Request-scoped context values (request id correlation).

The request id is stored in a :mod:`contextvars` variable so that every log
line emitted while handling a request is correlated without threading the value
through business code.
"""

from __future__ import annotations

import re
import uuid
from contextvars import ContextVar, Token

_request_id: ContextVar[str | None] = ContextVar("touche_request_id", default=None)
_company_id: ContextVar[str | None] = ContextVar("touche_company_id", default=None)

_REQUEST_ID_MAX_LENGTH = 128
_REQUEST_ID_PATTERN = re.compile(r"^[A-Za-z0-9._:-]{8,128}$")


def new_request_id() -> str:
    """Generate a fresh, URL-safe request id."""
    return uuid.uuid4().hex


def normalise_request_id(candidate: str | None) -> str | None:
    """Accept a caller supplied request id only when it is safe to log/echo."""
    if candidate is None:
        return None
    value = candidate.strip()
    if len(value) > _REQUEST_ID_MAX_LENGTH or not _REQUEST_ID_PATTERN.match(value):
        return None
    return value


def set_request_id(value: str) -> Token[str | None]:
    return _request_id.set(value)


def reset_request_id(token: Token[str | None]) -> None:
    _request_id.reset(token)


def get_request_id() -> str | None:
    return _request_id.get()


def set_company_id(value: str | None) -> Token[str | None]:
    """Bind the active company for log correlation (set by Stage 1A auth)."""
    return _company_id.set(value)


def get_company_id() -> str | None:
    return _company_id.get()

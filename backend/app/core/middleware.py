"""Request correlation and access logging middleware.

Implemented as a raw ASGI middleware (instead of ``BaseHTTPMiddleware``) so the
request id is available for *every* log line, including those emitted by
exception handlers, and so streaming responses are not buffered.
"""

from __future__ import annotations

import time
from collections.abc import Sequence
from typing import Any

from starlette.datastructures import Headers, MutableHeaders
from starlette.types import ASGIApp, Message, Receive, Scope, Send

from app.core.context import (
    new_request_id,
    normalise_request_id,
    reset_request_id,
    set_request_id,
)
from app.core.errors import ErrorCode, error_response
from app.core.logging import get_logger

logger = get_logger("app.http")

REQUEST_ID_HEADER = b"x-request-id"

# Methods that change state and therefore require Origin + CSRF protection.
MUTATING_METHODS = frozenset({"POST", "PUT", "PATCH", "DELETE"})


class OriginValidationMiddleware:
    """Reject state-changing requests whose ``Origin`` is not trusted (ADR-002).

    Browsers attach ``Origin`` to every non-GET request, including same-origin
    ones, so a missing header on a mutation means either a non-browser client or
    a stripped header. Both fail closed: CSRF protection that only checks
    "when present" protects nothing.
    """

    def __init__(self, app: ASGIApp, *, allowed_origins: Sequence[str]) -> None:
        self.app = app
        self._allowed = frozenset(origin.rstrip("/") for origin in allowed_origins)

    async def __call__(self, scope: Scope, receive: Receive, send: Send) -> None:
        if scope["type"] != "http" or scope.get("method", "").upper() not in MUTATING_METHODS:
            await self.app(scope, receive, send)
            return

        origin = Headers(scope=scope).get("origin")
        if origin is not None and origin.rstrip("/") in self._allowed:
            await self.app(scope, receive, send)
            return

        logger.warning(
            "http.origin_rejected",
            extra={
                "http_method": scope.get("method"),
                "http_path": scope.get("path"),
                "origin_present": origin is not None,
            },
        )
        response = error_response(
            status_code=403,
            code=ErrorCode.ORIGIN_REJECTED,
            message="The request origin is not allowed.",
        )
        await response(scope, receive, send)



class RequestContextMiddleware:
    """Attach an ``X-Request-ID`` to every request/response and log the call."""

    def __init__(self, app: ASGIApp) -> None:
        self.app = app

    async def __call__(self, scope: Scope, receive: Receive, send: Send) -> None:
        if scope["type"] != "http":
            await self.app(scope, receive, send)
            return

        incoming = Headers(scope=scope).get("x-request-id")
        request_id = normalise_request_id(incoming) or new_request_id()

        state: dict[str, Any] = scope.setdefault("state", {})
        state["request_id"] = request_id
        token = set_request_id(request_id)

        started_at = time.perf_counter()
        status_code = 500

        async def send_wrapper(message: Message) -> None:
            nonlocal status_code
            if message["type"] == "http.response.start":
                status_code = int(message["status"])
                headers = MutableHeaders(scope=message)
                headers["X-Request-ID"] = request_id
                headers.setdefault("X-Content-Type-Options", "nosniff")
            await send(message)

        try:
            await self.app(scope, receive, send_wrapper)
        finally:
            duration_ms = round((time.perf_counter() - started_at) * 1000, 2)
            log = logger.warning if status_code >= 500 else logger.info
            log(
                "http.request.completed",
                extra={
                    "http_method": scope.get("method"),
                    "http_path": scope.get("path"),
                    "http_status": status_code,
                    "duration_ms": duration_ms,
                },
            )
            reset_request_id(token)

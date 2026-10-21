"""Standard API error model, error codes and exception handlers.

Every error returned by the API uses the same envelope::

    {
      "error": {
        "code": "NOT_FOUND",
        "message": "The requested resource does not exist.",
        "request_id": "8d2f...",
        "timestamp": "2026-10-22T10:00:00+00:00",
        "details": null
      }
    }

The ``code`` values are part of the public contract (docs/API_CONTRACTS.md);
clients branch on the code, never on the human readable message.
"""

from __future__ import annotations

from collections.abc import Mapping, Sequence
from datetime import UTC, datetime
from enum import StrEnum
from typing import Any, cast

from fastapi import FastAPI, Request
from fastapi.encoders import jsonable_encoder
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse
from starlette.exceptions import HTTPException as StarletteHTTPException

from app.core.context import get_request_id
from app.core.logging import get_logger

logger = get_logger("app.errors")


class ErrorCode(StrEnum):
    """Stable machine-readable error codes."""

    BAD_REQUEST = "BAD_REQUEST"
    VALIDATION_ERROR = "VALIDATION_ERROR"
    UNAUTHORIZED = "UNAUTHORIZED"
    SESSION_EXPIRED = "SESSION_EXPIRED"
    ORIGIN_REJECTED = "ORIGIN_REJECTED"
    CSRF_REJECTED = "CSRF_REJECTED"
    FORBIDDEN = "FORBIDDEN"
    NOT_FOUND = "NOT_FOUND"
    METHOD_NOT_ALLOWED = "METHOD_NOT_ALLOWED"
    CONFLICT = "CONFLICT"
    VERSION_CONFLICT = "VERSION_CONFLICT"
    PRECONDITION_REQUIRED = "PRECONDITION_REQUIRED"
    IDEMPOTENCY_CONFLICT = "IDEMPOTENCY_CONFLICT"
    ALREADY_WON = "ALREADY_WON"
    RATE_LIMITED = "RATE_LIMITED"
    PAYLOAD_TOO_LARGE = "PAYLOAD_TOO_LARGE"
    NOT_READY = "NOT_READY"
    SERVICE_UNAVAILABLE = "SERVICE_UNAVAILABLE"
    INTERNAL_ERROR = "INTERNAL_ERROR"
    HTTP_ERROR = "HTTP_ERROR"


_STATUS_TO_CODE: dict[int, ErrorCode] = {
    400: ErrorCode.BAD_REQUEST,
    401: ErrorCode.UNAUTHORIZED,
    403: ErrorCode.FORBIDDEN,
    404: ErrorCode.NOT_FOUND,
    405: ErrorCode.METHOD_NOT_ALLOWED,
    409: ErrorCode.CONFLICT,
    413: ErrorCode.PAYLOAD_TOO_LARGE,
    422: ErrorCode.VALIDATION_ERROR,
    428: ErrorCode.PRECONDITION_REQUIRED,
    429: ErrorCode.RATE_LIMITED,
    500: ErrorCode.INTERNAL_ERROR,
    503: ErrorCode.SERVICE_UNAVAILABLE,
}

_DEFAULT_MESSAGES: dict[int, str] = {
    400: "The request could not be processed.",
    401: "Authentication is required.",
    403: "You do not have permission to perform this action.",
    404: "The requested resource does not exist.",
    405: "The HTTP method is not allowed for this resource.",
    409: "The request conflicts with the current state of the resource.",
    413: "The request payload is too large.",
    422: "Request validation failed.",
    428: "This request requires an If-Match header with the current version.",
    429: "Too many requests. Please retry later.",
    500: "An unexpected error occurred.",
    503: "A required dependency is unavailable.",
}


class ApiError(Exception):
    """Base class for all errors that are safe to expose to API clients."""

    status_code: int = 500
    code: ErrorCode = ErrorCode.INTERNAL_ERROR
    default_message: str = "An unexpected error occurred."

    def __init__(
        self,
        message: str | None = None,
        *,
        details: Any | None = None,
        headers: Mapping[str, str] | None = None,
        code: ErrorCode | None = None,
        status_code: int | None = None,
    ) -> None:
        self.message = message or self.default_message
        self.details = details
        self.headers: dict[str, str] = dict(headers or {})
        if code is not None:
            self.code = code
        if status_code is not None:
            self.status_code = status_code
        super().__init__(self.message)


class BadRequestError(ApiError):
    status_code = 400
    code = ErrorCode.BAD_REQUEST
    default_message = "The request could not be processed."


class NotFoundError(ApiError):
    status_code = 404
    code = ErrorCode.NOT_FOUND
    default_message = "The requested resource does not exist."


class UnauthorizedError(ApiError):
    """No valid session. The message is deliberately generic (ADR-002)."""

    status_code = 401
    code = ErrorCode.UNAUTHORIZED
    default_message = "Authentication is required."


class SessionExpiredError(UnauthorizedError):
    """The session existed but reached its idle or absolute timeout."""

    code = ErrorCode.SESSION_EXPIRED
    default_message = "Your session has expired. Sign in again to continue."


class ForbiddenError(ApiError):
    status_code = 403
    code = ErrorCode.FORBIDDEN
    default_message = "You do not have permission to perform this action."


class CsrfRejectedError(ApiError):
    status_code = 403
    code = ErrorCode.CSRF_REJECTED
    default_message = "The CSRF token is missing or invalid. Reload the page and try again."


class OriginRejectedError(ApiError):
    status_code = 403
    code = ErrorCode.ORIGIN_REJECTED
    default_message = "The request origin is not allowed."


class RateLimitedError(ApiError):
    status_code = 429
    code = ErrorCode.RATE_LIMITED
    default_message = "Too many attempts. Please retry later."


class PreconditionRequiredError(ApiError):
    status_code = 428
    code = ErrorCode.PRECONDITION_REQUIRED
    default_message = "This request requires an If-Match header with the current version."


class VersionConflictError(ApiError):
    status_code = 409
    code = ErrorCode.VERSION_CONFLICT
    default_message = "The resource was modified by another request."


class IdempotencyConflictError(ApiError):
    status_code = 409
    code = ErrorCode.IDEMPOTENCY_CONFLICT
    default_message = "The Idempotency-Key was already used with a different request."


class AlreadyWonError(ApiError):
    status_code = 409
    code = ErrorCode.ALREADY_WON
    default_message = "The deal was already marked as WON."


class NotReadyError(ApiError):
    status_code = 503
    code = ErrorCode.NOT_READY
    default_message = "The service is not ready to handle requests."


def build_error_payload(
    *,
    code: ErrorCode | str,
    message: str,
    details: Any | None = None,
) -> dict[str, Any]:
    """Build the standard error envelope body."""
    return {
        "error": {
            "code": str(code),
            "message": message,
            "request_id": get_request_id(),
            "timestamp": datetime.now(tz=UTC).isoformat(),
            "details": jsonable_encoder(details) if details is not None else None,
        }
    }


def error_response(
    *,
    status_code: int,
    code: ErrorCode | str,
    message: str,
    details: Any | None = None,
    headers: Mapping[str, str] | None = None,
) -> JSONResponse:
    """Create a JSON error response with the standard envelope."""
    response_headers = {
        "Cache-Control": "no-store",
        "X-Content-Type-Options": "nosniff",
    }
    if headers:
        response_headers.update(headers)
    return JSONResponse(
        status_code=status_code,
        content=build_error_payload(code=code, message=message, details=details),
        headers=response_headers,
    )


def _validation_details(exc: RequestValidationError) -> list[dict[str, Any]]:
    details: list[dict[str, Any]] = []
    for error in exc.errors():
        location: Sequence[Any] = error.get("loc", ())
        details.append(
            {
                "field": ".".join(str(part) for part in location) or "(body)",
                "message": error.get("msg", "Invalid value."),
                "type": error.get("type", "value_error"),
            }
        )
    return details


async def handle_api_error(_request: Request, exc: Exception) -> JSONResponse:
    """Render :class:`ApiError` (and subclasses) using the envelope."""
    api_error = cast(ApiError, exc)
    log = logger.warning if api_error.status_code >= 500 else logger.info
    log(
        "api.error",
        extra={
            "error_code": str(api_error.code),
            "status_code": api_error.status_code,
            "error_details": api_error.details,
        },
    )
    return error_response(
        status_code=api_error.status_code,
        code=api_error.code,
        message=api_error.message,
        details=api_error.details,
        headers=api_error.headers,
    )


async def handle_validation_error(_request: Request, exc: Exception) -> JSONResponse:
    """Render FastAPI/Pydantic validation failures with per-field detail."""
    details = _validation_details(cast(RequestValidationError, exc))
    return error_response(
        status_code=422,
        code=ErrorCode.VALIDATION_ERROR,
        message=_DEFAULT_MESSAGES[422],
        details=details,
    )


async def handle_http_exception(_request: Request, exc: Exception) -> JSONResponse:
    """Render Starlette/FastAPI HTTP exceptions (404, 405, ...) as envelopes."""
    http_exc = cast(StarletteHTTPException, exc)
    code = _STATUS_TO_CODE.get(http_exc.status_code, ErrorCode.HTTP_ERROR)
    detail = http_exc.detail if isinstance(http_exc.detail, str) else None
    message = detail or _DEFAULT_MESSAGES.get(
        http_exc.status_code, "The request could not be completed."
    )
    headers: dict[str, str] = {}
    if http_exc.headers:
        headers.update({str(key): str(value) for key, value in http_exc.headers.items()})
    return error_response(
        status_code=http_exc.status_code,
        code=code,
        message=message,
        headers=headers,
    )


async def handle_unexpected_error(_request: Request, exc: Exception) -> JSONResponse:
    """Log the failure with a stack trace and return an opaque envelope."""
    logger.exception("api.unhandled_error", extra={"error_type": type(exc).__name__})
    return error_response(
        status_code=500,
        code=ErrorCode.INTERNAL_ERROR,
        message=_DEFAULT_MESSAGES[500],
    )


def register_exception_handlers(app: FastAPI) -> None:
    """Attach the API error handlers to the application."""
    app.add_exception_handler(ApiError, handle_api_error)
    app.add_exception_handler(RequestValidationError, handle_validation_error)
    app.add_exception_handler(StarletteHTTPException, handle_http_exception)
    app.add_exception_handler(Exception, handle_unexpected_error)


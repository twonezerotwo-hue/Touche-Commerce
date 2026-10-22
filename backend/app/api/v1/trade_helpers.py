"""Shared plumbing for the trade routes.

Every mutating trade endpoint follows the same sequence:

1. authenticated session + active company + ``trade.write`` (dependency);
2. optional/required ``Idempotency-Key`` validated *before* any SQL runs;
3. one transaction that writes the idempotency row, the business change, the
   audit row and the response snapshot together;
4. replay returns the stored body byte-for-byte with ``Idempotent-Replay``.
"""

from __future__ import annotations

from collections.abc import Iterator
from contextlib import contextmanager
from typing import Any

from fastapi import Request
from fastapi.responses import JSONResponse

from app.api.security import active_company_id, client_ip, request_user_agent
from app.core.config import Settings
from app.core.context import get_request_id
from app.core.errors import ApiError, ErrorCode
from app.db.engine import Database
from app.services.auth import SessionContext
from app.services.idempotency import (
    IdempotentCall,
    Replay,
    idempotent_transaction,
    read_idempotency_key,
    request_fingerprint,
)
from app.services.trade_meta import WriteMeta


def write_meta(context: SessionContext, request: Request) -> WriteMeta:
    """Capture the audited-write metadata exactly once per request."""
    return WriteMeta(
        company_id=active_company_id(context),
        actor_id=context.user.user_id,
        request_id=get_request_id(),
        ip_address=client_ip(request),
        user_agent=request_user_agent(request),
    )


@contextmanager
def idempotent_call(
    database: Database,
    settings: Settings,
    context: SessionContext,
    request: Request,
    payload: Any,
    *,
    required: bool = False,
    endpoint: str | None = None,
) -> Iterator[IdempotentCall]:
    """Open the transaction for a mutating trade request."""
    key = read_idempotency_key(request.headers.get("Idempotency-Key"), required=required)
    resolved_endpoint = endpoint or f"{request.method.upper()} {request.url.path}"
    fingerprint = request_fingerprint(
        method=request.method,
        path=request.url.path,
        payload=payload.model_dump(mode="json") if hasattr(payload, "model_dump") else payload,
    )
    with idempotent_transaction(
        database,
        company_id=active_company_id(context),
        actor_id=context.user.user_id,
        endpoint=resolved_endpoint,
        key=key,
        fingerprint=fingerprint,
        ttl_hours=settings.idempotency_ttl_hours,
    ) as call:
        yield call


def resolve_limit(limit: int | None, settings: Settings) -> int:
    """Apply the configured default and maximum page size (contract §3)."""
    resolved = limit if limit is not None else settings.pagination_default_limit
    if resolved < 1 or resolved > settings.pagination_max_limit:
        raise ApiError(
            status_code=422,
            code=ErrorCode.VALIDATION_ERROR,
            message="Request validation failed.",
            details=[
                {
                    "field": "query.limit",
                    "message": f"limit must be between 1 and {settings.pagination_max_limit}.",
                    "type": "less_than_equal",
                }
            ],
        )
    return resolved


def replay_response(replay: Replay) -> JSONResponse:
    """Return the original response without re-running the operation."""
    return JSONResponse(
        content=replay.body,
        status_code=replay.status_code,
        headers={
            "Idempotent-Replay": "true",
            "Cache-Control": "no-store",
            "Vary": "Cookie",
        },
    )


__all__ = ["idempotent_call", "replay_response", "resolve_limit", "write_meta"]

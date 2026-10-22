"""Counterparty (CRM) endpoints — list, create, read, update.

Authorization: reads need ``company.view``, writes need ``trade.write`` inside an
active company (a viewer can read the CRM; only a trader can change it). Every
write supports ``Idempotency-Key``; every update requires ``If-Match`` and
answers with the new ``ETag``.
"""

from __future__ import annotations

from typing import Annotated
from uuid import UUID

from fastapi import APIRouter, Depends, Query, Request, Response, status
from fastapi.responses import JSONResponse

from app.api.deps import app_settings, get_database
from app.api.security import active_company_id, require_company_permission
from app.api.v1.etag import etag_for, require_if_match
from app.api.v1.presenters_trade import counterparty_list_response, counterparty_response
from app.api.v1.schemas.errors import ErrorEnvelope
from app.api.v1.schemas.trade import (
    CounterpartyCreateRequest,
    CounterpartyListResponse,
    CounterpartyResponse,
    CounterpartyTypeValue,
    CounterpartyUpdateRequest,
    RecordStatusValue,
)
from app.api.v1.trade_helpers import (
    idempotent_call,
    replay_response,
    resolve_limit,
    write_meta,
)
from app.core.config import Settings
from app.db.engine import Database
from app.security.permissions import Permission
from app.services.auth import SessionContext
from app.services.crm import CounterpartyFilters, CounterpartyService

router = APIRouter(tags=["counterparties"])


def get_counterparty_service(
    database: Annotated[Database, Depends(get_database)],
) -> CounterpartyService:
    return CounterpartyService(database)


@router.get(
    "/counterparties",
    response_model=CounterpartyListResponse,
    summary="List counterparties",
    description=(
        "Cursor-paginated, newest first. Filters are bound to the cursor: reusing a "
        "cursor with a different filter set is rejected with 422 instead of returning "
        "a misleading page."
    ),
    responses={
        200: {"description": "A page of counterparties."},
        401: {"model": ErrorEnvelope, "description": "No valid session."},
        403: {"model": ErrorEnvelope, "description": "No active company or permission."},
        422: {"model": ErrorEnvelope, "description": "Invalid cursor, limit or filter."},
    },
)
def list_counterparties(
    response: Response,
    context: Annotated[
        SessionContext, Depends(require_company_permission(Permission.COMPANY_VIEW))
    ],
    service: Annotated[CounterpartyService, Depends(get_counterparty_service)],
    settings: Annotated[Settings, Depends(app_settings)],
    search: Annotated[str | None, Query(max_length=160)] = None,
    counterparty_status: Annotated[
        RecordStatusValue | None, Query(alias="status")
    ] = None,
    kind: Annotated[CounterpartyTypeValue | None, Query(alias="type")] = None,
    limit: Annotated[int | None, Query(ge=1)] = None,
    cursor: Annotated[str | None, Query(max_length=512)] = None,
) -> CounterpartyListResponse:
    response.headers["Cache-Control"] = "no-store"
    response.headers["Vary"] = "Cookie"
    page = service.list(
        company_id=active_company_id(context),
        filters=CounterpartyFilters(search=search, status=counterparty_status, kind=kind),
        limit=resolve_limit(limit, settings),
        cursor=cursor,
    )
    return counterparty_list_response(page)


@router.post(
    "/counterparties",
    response_model=CounterpartyResponse,
    status_code=status.HTTP_201_CREATED,
    summary="Create a counterparty",
    responses={
        201: {"description": "Created."},
        400: {"model": ErrorEnvelope, "description": "Invalid idempotency key."},
        403: {"model": ErrorEnvelope, "description": "Missing trade.write."},
        409: {"model": ErrorEnvelope, "description": "Duplicate name or key conflict."},
        422: {"model": ErrorEnvelope, "description": "Invalid payload."},
    },
)
def create_counterparty(
    payload: CounterpartyCreateRequest,
    request: Request,
    response: Response,
    context: Annotated[
        SessionContext, Depends(require_company_permission(Permission.TRADE_WRITE))
    ],
    service: Annotated[CounterpartyService, Depends(get_counterparty_service)],
    database: Annotated[Database, Depends(get_database)],
    settings: Annotated[Settings, Depends(app_settings)],
) -> CounterpartyResponse | JSONResponse:
    meta = write_meta(context, request)
    with idempotent_call(database, settings, context, request, payload) as call:
        if call.replay is not None:
            return replay_response(call.replay)
        record = service.create(
            call.session, meta=meta, data=payload.model_dump(exclude_none=True)
        )
        body = counterparty_response(record)
        call.complete(status_code=201, body=body.model_dump(mode="json"))
    response.headers["ETag"] = etag_for(record.version)
    response.headers["Cache-Control"] = "no-store"
    return body


@router.get(
    "/counterparties/{counterparty_id}",
    response_model=CounterpartyResponse,
    summary="Read one counterparty",
    responses={
        200: {"description": "The counterparty."},
        404: {"model": ErrorEnvelope, "description": "Unknown counterparty."},
    },
)
def get_counterparty(
    counterparty_id: UUID,
    response: Response,
    context: Annotated[
        SessionContext, Depends(require_company_permission(Permission.COMPANY_VIEW))
    ],
    service: Annotated[CounterpartyService, Depends(get_counterparty_service)],
) -> CounterpartyResponse:
    record = service.get(
        company_id=active_company_id(context), counterparty_id=counterparty_id
    )
    response.headers["ETag"] = etag_for(record.version)
    response.headers["Cache-Control"] = "no-store"
    response.headers["Vary"] = "Cookie"
    return counterparty_response(record)


@router.patch(
    "/counterparties/{counterparty_id}",
    response_model=CounterpartyResponse,
    summary="Update a counterparty (If-Match required)",
    description=(
        "Requires If-Match with the ETag from the last read. A stale version returns "
        "409 VERSION_CONFLICT including the current ETag; a missing header returns "
        "428 PRECONDITION_REQUIRED. Unknown fields (for example status) are rejected."
    ),
    responses={
        200: {"description": "Updated; the new ETag is returned."},
        400: {"model": ErrorEnvelope, "description": "Malformed If-Match or key."},
        404: {"model": ErrorEnvelope, "description": "Unknown counterparty."},
        409: {"model": ErrorEnvelope, "description": "Version or key conflict."},
        422: {"model": ErrorEnvelope, "description": "Invalid payload."},
        428: {"model": ErrorEnvelope, "description": "If-Match header missing."},
    },
)
def update_counterparty(
    counterparty_id: UUID,
    payload: CounterpartyUpdateRequest,
    request: Request,
    response: Response,
    context: Annotated[
        SessionContext, Depends(require_company_permission(Permission.TRADE_WRITE))
    ],
    service: Annotated[CounterpartyService, Depends(get_counterparty_service)],
    database: Annotated[Database, Depends(get_database)],
    settings: Annotated[Settings, Depends(app_settings)],
) -> CounterpartyResponse | JSONResponse:
    expected_version = require_if_match(request.headers.get("If-Match"))
    meta = write_meta(context, request)
    with idempotent_call(database, settings, context, request, payload) as call:
        if call.replay is not None:
            return replay_response(call.replay)
        record = service.update(
            call.session,
            meta=meta,
            counterparty_id=counterparty_id,
            expected_version=expected_version,
            changes=payload.model_dump(exclude_unset=True),
        )
        body = counterparty_response(record)
        call.complete(status_code=200, body=body.model_dump(mode="json"))
    response.headers["ETag"] = etag_for(record.version)
    response.headers["Cache-Control"] = "no-store"
    return body



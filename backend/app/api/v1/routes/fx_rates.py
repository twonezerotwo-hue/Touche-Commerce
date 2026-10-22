"""FX snapshot endpoints.

Rates are recorded, never inferred: a POST stores base/quote/rate/effective time
and the source it came from, and every later conversion points at this row. The
table is immutable, so a correction is a new snapshot instead of an edit.
"""

from __future__ import annotations

from typing import Annotated
from uuid import UUID

from fastapi import APIRouter, Depends, Query, Request, Response, status
from fastapi.responses import JSONResponse

from app.api.deps import app_settings, get_database
from app.api.security import active_company_id, require_company_permission
from app.api.v1.presenters_sourcing import fx_rate_list_response, fx_rate_response
from app.api.v1.schemas.errors import ErrorEnvelope
from app.api.v1.schemas.sourcing import FxRateCreateRequest, FxRateListResponse, FxRateResponse
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
from app.services.fx import FxRateFilters, FxRateService

router = APIRouter(tags=["fx-rates"])


def get_fx_rate_service(database: Annotated[Database, Depends(get_database)]) -> FxRateService:
    return FxRateService(database)


@router.get(
    "/fx-rates",
    response_model=FxRateListResponse,
    summary="List recorded FX snapshots",
    description=(
        "Cursor-paginated, newest recording first. Filter by the currency pair. "
        "No endpoint returns a 'current' rate: pricing always refers to a stored "
        "snapshot so a landed cost stays reproducible."
    ),
    responses={
        200: {"description": "A page of FX snapshots."},
        422: {"model": ErrorEnvelope, "description": "Invalid cursor or limit."},
    },
)
def list_fx_rates(
    response: Response,
    context: Annotated[
        SessionContext, Depends(require_company_permission(Permission.COMPANY_VIEW))
    ],
    service: Annotated[FxRateService, Depends(get_fx_rate_service)],
    settings: Annotated[Settings, Depends(app_settings)],
    base_currency: Annotated[str | None, Query(max_length=3)] = None,
    quote_currency: Annotated[str | None, Query(max_length=3)] = None,
    limit: Annotated[int | None, Query(ge=1)] = None,
    cursor: Annotated[str | None, Query(max_length=512)] = None,
) -> FxRateListResponse:
    response.headers["Cache-Control"] = "no-store"
    response.headers["Vary"] = "Cookie"
    page = service.list(
        company_id=active_company_id(context),
        filters=FxRateFilters(
            base_currency=base_currency.strip().upper() if base_currency else None,
            quote_currency=quote_currency.strip().upper() if quote_currency else None,
        ),
        limit=resolve_limit(limit, settings),
        cursor=cursor,
    )
    return fx_rate_list_response(page)


@router.post(
    "/fx-rates",
    response_model=FxRateResponse,
    status_code=status.HTTP_201_CREATED,
    summary="Record an FX snapshot",
    description=(
        "Stores one sourced observation. The pair and effective time are unique per "
        "company, so recording the same observation twice is a 409 instead of a "
        "duplicate rate that could be picked arbitrarily."
    ),
    responses={
        201: {"description": "Recorded."},
        400: {"model": ErrorEnvelope, "description": "Missing/invalid Idempotency-Key."},
        409: {"model": ErrorEnvelope, "description": "Duplicate snapshot."},
        422: {"model": ErrorEnvelope, "description": "Invalid payload."},
    },
)
def create_fx_rate(
    payload: FxRateCreateRequest,
    request: Request,
    response: Response,
    context: Annotated[
        SessionContext, Depends(require_company_permission(Permission.TRADE_WRITE))
    ],
    service: Annotated[FxRateService, Depends(get_fx_rate_service)],
    database: Annotated[Database, Depends(get_database)],
    settings: Annotated[Settings, Depends(app_settings)],
) -> FxRateResponse | JSONResponse:
    meta = write_meta(context, request)
    with idempotent_call(database, settings, context, request, payload) as call:
        if call.replay is not None:
            return replay_response(call.replay)
        record = service.create(
            call.session, meta=meta, data=payload.model_dump(exclude_none=False)
        )
        body = fx_rate_response(record)
        call.complete(status_code=201, body=body.model_dump(mode="json"))
    response.headers["Cache-Control"] = "no-store"
    return body


@router.get(
    "/fx-rates/{fx_rate_id}",
    response_model=FxRateResponse,
    summary="Read one FX snapshot",
    responses={404: {"model": ErrorEnvelope, "description": "Unknown snapshot."}},
)
def get_fx_rate(
    fx_rate_id: UUID,
    response: Response,
    context: Annotated[
        SessionContext, Depends(require_company_permission(Permission.COMPANY_VIEW))
    ],
    service: Annotated[FxRateService, Depends(get_fx_rate_service)],
) -> FxRateResponse:
    record = service.get(company_id=active_company_id(context), snapshot_id=fx_rate_id)
    response.headers["Cache-Control"] = "no-store"
    response.headers["Vary"] = "Cookie"
    return fx_rate_response(record)

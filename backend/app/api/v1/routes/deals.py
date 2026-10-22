"""Deal endpoints — list, create, read, update and the state-machine transition.

The only way to change ``status`` is ``POST /deals/{id}/transitions``:

* an ``Idempotency-Key`` is **required** (ADR-012) and the replay is byte-identical;
* ``WON`` is disabled (``409 TRANSITION_DISABLED``) until sales orders exist;
* ``LOST``/``CANCELLED`` require a reason (``422 REASON_REQUIRED``);
* an impossible edge returns ``409 INVALID_TRANSITION`` with the allowed targets;
* the deal row, the history row and the audit row commit together (ADR-025).
"""

from __future__ import annotations

from typing import Annotated
from uuid import UUID

from fastapi import APIRouter, Depends, Query, Request, Response, status
from fastapi.responses import JSONResponse

from app.api.deps import app_settings, get_database
from app.api.security import active_company_id, require_company_permission
from app.api.v1.etag import etag_for, parse_if_match, require_if_match
from app.api.v1.presenters_trade import deal_list_response, deal_response
from app.api.v1.schemas.errors import ErrorEnvelope
from app.api.v1.schemas.trade import (
    DealCreateRequest,
    DealListResponse,
    DealResponse,
    DealStatusValue,
    DealTransitionRequest,
    DealUpdateRequest,
)
from app.api.v1.trade_helpers import (
    idempotent_call,
    replay_response,
    resolve_limit,
    write_meta,
)
from app.core.config import Settings
from app.db.engine import Database
from app.db.models import DealStatus
from app.security.permissions import Permission
from app.services.auth import SessionContext
from app.services.trade import (
    DealCreateData,
    DealFilters,
    DealItemInput,
    DealService,
)

router = APIRouter(tags=["deals"])


def get_deal_service(database: Annotated[Database, Depends(get_database)]) -> DealService:
    return DealService(database)


@router.get(
    "/deals",
    response_model=DealListResponse,
    summary="List deals",
    description=(
        "Cursor-paginated, newest first. Every row carries its total value computed "
        "from the deal lines, so a table never has to sum client-side."
    ),
    responses={
        200: {"description": "A page of deals."},
        422: {"model": ErrorEnvelope, "description": "Invalid cursor, limit or filter."},
    },
)
def list_deals(
    response: Response,
    context: Annotated[
        SessionContext, Depends(require_company_permission(Permission.COMPANY_VIEW))
    ],
    service: Annotated[DealService, Depends(get_deal_service)],
    settings: Annotated[Settings, Depends(app_settings)],
    search: Annotated[str | None, Query(max_length=160)] = None,
    deal_status: Annotated[DealStatusValue | None, Query(alias="status")] = None,
    counterparty_id: Annotated[UUID | None, Query()] = None,
    limit: Annotated[int | None, Query(ge=1)] = None,
    cursor: Annotated[str | None, Query(max_length=512)] = None,
) -> DealListResponse:
    response.headers["Cache-Control"] = "no-store"
    response.headers["Vary"] = "Cookie"
    page = service.list(
        company_id=active_company_id(context),
        filters=DealFilters(
            search=search, status=deal_status, counterparty_id=counterparty_id
        ),
        limit=resolve_limit(limit, settings),
        cursor=cursor,
    )
    return deal_list_response(page)


@router.post(
    "/deals",
    response_model=DealResponse,
    status_code=status.HTTP_201_CREATED,
    summary="Create a deal with its lines",
    description=(
        "Creates the deal, every line, the initial DRAFT history entry and the audit "
        "record in one transaction. A deal cannot reference a counterparty or product "
        "belonging to another company (composite foreign keys plus RLS)."
    ),
    responses={
        201: {"description": "Created."},
        400: {"model": ErrorEnvelope, "description": "Unknown counterparty/product."},
        409: {"model": ErrorEnvelope, "description": "Duplicate reference or key conflict."},
        422: {"model": ErrorEnvelope, "description": "Invalid payload."},
    },
)
def create_deal(
    payload: DealCreateRequest,
    request: Request,
    response: Response,
    context: Annotated[
        SessionContext, Depends(require_company_permission(Permission.TRADE_WRITE))
    ],
    service: Annotated[DealService, Depends(get_deal_service)],
    database: Annotated[Database, Depends(get_database)],
    settings: Annotated[Settings, Depends(app_settings)],
) -> DealResponse | JSONResponse:
    meta = write_meta(context, request)
    reference = payload.reference.strip().upper() if payload.reference else None
    data = DealCreateData(
        title=" ".join(payload.title.split()),
        counterparty_id=payload.counterparty_id,
        currency=payload.currency.strip().upper(),
        expected_close_date=payload.expected_close_date,
        notes=payload.notes,
        reference=reference,
        items=tuple(
            DealItemInput(
                product_id=item.product_id,
                quantity=item.quantity,
                unit_price=item.unit_price,
            )
            for item in payload.items
        ),
    )
    with idempotent_call(database, settings, context, request, payload) as call:
        if call.replay is not None:
            return replay_response(call.replay)
        record = service.create(call.session, meta=meta, data=data)
        body = deal_response(record)
        call.complete(status_code=201, body=body.model_dump(mode="json"))
    response.headers["ETag"] = etag_for(record.version)
    response.headers["Cache-Control"] = "no-store"
    return body


@router.get(
    "/deals/{deal_id}",
    response_model=DealResponse,
    summary="Read one deal with lines, history and allowed transitions",
    responses={
        200: {"description": "The deal."},
        404: {"model": ErrorEnvelope, "description": "Unknown deal for this company."},
    },
)
def get_deal(
    deal_id: UUID,
    response: Response,
    context: Annotated[
        SessionContext, Depends(require_company_permission(Permission.COMPANY_VIEW))
    ],
    service: Annotated[DealService, Depends(get_deal_service)],
) -> DealResponse:
    record = service.get(company_id=active_company_id(context), deal_id=deal_id)
    response.headers["ETag"] = etag_for(record.version)
    response.headers["Cache-Control"] = "no-store"
    response.headers["Vary"] = "Cookie"
    return deal_response(record)


@router.patch(
    "/deals/{deal_id}",
    response_model=DealResponse,
    summary="Update deal header fields (If-Match required)",
    description=(
        "Header fields only: title, counterparty, currency, expected close date and "
        "notes. Sending status is rejected with 422 because status changes belong to "
        "the transition endpoint. Closed deals cannot be edited. Lines are immutable."
    ),
    responses={
        200: {"description": "Updated; the new ETag is returned."},
        400: {"model": ErrorEnvelope, "description": "Malformed If-Match."},
        404: {"model": ErrorEnvelope, "description": "Unknown deal."},
        409: {"model": ErrorEnvelope, "description": "Closed deal, version or key conflict."},
        422: {"model": ErrorEnvelope, "description": "Invalid payload, including status."},
        428: {"model": ErrorEnvelope, "description": "If-Match header missing."},
    },
)
def update_deal(
    deal_id: UUID,
    payload: DealUpdateRequest,
    request: Request,
    response: Response,
    context: Annotated[
        SessionContext, Depends(require_company_permission(Permission.TRADE_WRITE))
    ],
    service: Annotated[DealService, Depends(get_deal_service)],
    database: Annotated[Database, Depends(get_database)],
    settings: Annotated[Settings, Depends(app_settings)],
) -> DealResponse | JSONResponse:
    expected_version = require_if_match(request.headers.get("If-Match"))
    meta = write_meta(context, request)
    changes = payload.model_dump(exclude_unset=True)
    if "currency" in changes and changes["currency"] is not None:
        changes["currency"] = str(changes["currency"]).upper()
    with idempotent_call(database, settings, context, request, payload) as call:
        if call.replay is not None:
            return replay_response(call.replay)
        record = service.update(
            call.session,
            meta=meta,
            deal_id=deal_id,
            expected_version=expected_version,
            changes=changes,
        )
        body = deal_response(record)
        call.complete(status_code=200, body=body.model_dump(mode="json"))
    response.headers["ETag"] = etag_for(record.version)
    response.headers["Cache-Control"] = "no-store"
    return body


@router.post(
    "/deals/{deal_id}/transitions",
    response_model=DealResponse,
    summary="Move a deal through the state machine",
    description=(
        "Requires Idempotency-Key. The optional If-Match header adds optimistic "
        "concurrency on top of row locking. The deal update, the deal_transition "
        "history row and the audit row commit in one transaction."
    ),
    responses={
        200: {"description": "Transition accepted; the new ETag is returned."},
        400: {"model": ErrorEnvelope, "description": "Missing/invalid Idempotency-Key."},
        404: {"model": ErrorEnvelope, "description": "Unknown deal."},
        409: {
            "model": ErrorEnvelope,
            "description": (
                "INVALID_TRANSITION, TRANSITION_DISABLED, ALREADY_WON, "
                "VERSION_CONFLICT, IDEMPOTENCY_CONFLICT or IDEMPOTENCY_IN_PROGRESS."
            ),
        },
        422: {"model": ErrorEnvelope, "description": "Unknown target or missing reason."},
    },
)
def transition_deal(
    deal_id: UUID,
    payload: DealTransitionRequest,
    request: Request,
    response: Response,
    context: Annotated[
        SessionContext, Depends(require_company_permission(Permission.TRADE_WRITE))
    ],
    service: Annotated[DealService, Depends(get_deal_service)],
    database: Annotated[Database, Depends(get_database)],
    settings: Annotated[Settings, Depends(app_settings)],
) -> DealResponse | JSONResponse:
    expected_version = parse_if_match(request.headers.get("If-Match"), required=False)
    target = DealStatus(payload.to)
    meta = write_meta(context, request)
    with idempotent_call(
        database, settings, context, request, payload, required=True
    ) as call:
        if call.replay is not None:
            return replay_response(call.replay)
        record = service.transition(
            call.session,
            meta=meta,
            deal_id=deal_id,
            target=target,
            reason=payload.reason,
            expected_version=expected_version,
        )
        body = deal_response(record)
        call.complete(status_code=200, body=body.model_dump(mode="json"))
    response.headers["ETag"] = etag_for(record.version)
    response.headers["Cache-Control"] = "no-store"
    return body



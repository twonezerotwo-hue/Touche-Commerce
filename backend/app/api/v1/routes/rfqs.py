"""RFQ endpoints: batch creation, editing, prepared snapshots and dispatch.

``POST /rfqs`` takes a list of suppliers and creates one RFQ per supplier in one
transaction; the response therefore contains a list. Status changes go through
``POST /rfqs/{id}/transitions`` only, so an update can never quietly mark an RFQ
as sent without a channel and evidence.
"""

from __future__ import annotations

from typing import Annotated
from uuid import UUID

from fastapi import APIRouter, Depends, Query, Request, Response, status
from fastapi.responses import JSONResponse

from app.api.deps import app_settings, get_database
from app.api.security import active_company_id, require_company_permission
from app.api.v1.etag import etag_for, parse_if_match, require_if_match
from app.api.v1.presenters_sourcing import (
    rfq_batch_response,
    rfq_list_response,
    rfq_response,
    rfq_revision_detail_response,
)
from app.api.v1.schemas.errors import ErrorEnvelope
from app.api.v1.schemas.sourcing import (
    RfqBatchResponse,
    RfqCreateRequest,
    RfqListResponse,
    RfqResponse,
    RfqRevisionDetailResponse,
    RfqStatusValue,
    RfqTransitionRequest,
    RfqUpdateRequest,
)
from app.api.v1.trade_helpers import (
    idempotent_call,
    replay_response,
    resolve_limit,
    write_meta,
)
from app.core.config import Settings
from app.db.engine import Database
from app.db.models import RfqStatus
from app.security.permissions import Permission
from app.services.auth import SessionContext
from app.services.rfqs import RfqCreateData, RfqFilters, RfqItemInput, RfqService

router = APIRouter(tags=["rfqs"])


def get_rfq_service(database: Annotated[Database, Depends(get_database)]) -> RfqService:
    return RfqService(database)


@router.get(
    "/rfqs",
    response_model=RfqListResponse,
    summary="List supplier RFQs",
    description=(
        "Cursor-paginated, newest first. Each row carries its line and quote counts "
        "so a comparison table never has to fan out per row."
    ),
    responses={
        200: {"description": "A page of RFQs."},
        422: {"model": ErrorEnvelope, "description": "Invalid cursor, limit or filter."},
    },
)
def list_rfqs(
    response: Response,
    context: Annotated[
        SessionContext, Depends(require_company_permission(Permission.COMPANY_VIEW))
    ],
    service: Annotated[RfqService, Depends(get_rfq_service)],
    settings: Annotated[Settings, Depends(app_settings)],
    search: Annotated[str | None, Query(max_length=160)] = None,
    rfq_status: Annotated[RfqStatusValue | None, Query(alias="status")] = None,
    deal_id: Annotated[UUID | None, Query()] = None,
    supplier_counterparty_id: Annotated[UUID | None, Query()] = None,
    limit: Annotated[int | None, Query(ge=1)] = None,
    cursor: Annotated[str | None, Query(max_length=512)] = None,
) -> RfqListResponse:
    response.headers["Cache-Control"] = "no-store"
    response.headers["Vary"] = "Cookie"
    page = service.list(
        company_id=active_company_id(context),
        filters=RfqFilters(
            search=search,
            status=rfq_status,
            deal_id=deal_id,
            supplier_counterparty_id=supplier_counterparty_id,
        ),
        limit=resolve_limit(limit, settings),
        cursor=cursor,
    )
    return rfq_list_response(page)


@router.post(
    "/rfqs",
    response_model=RfqBatchResponse,
    status_code=status.HTTP_201_CREATED,
    summary="Create one RFQ per supplier",
    description=(
        "Every supplier receives its own RFQ with the same lines, created in one "
        "transaction. A buyer counterparty is rejected: an RFQ is addressed to a "
        "supplier. References are generated per RFQ."
    ),
    responses={
        201: {"description": "Created; one entry per supplier."},
        400: {"model": ErrorEnvelope, "description": "Unknown deal, supplier or product."},
        409: {"model": ErrorEnvelope, "description": "Duplicate reference or key conflict."},
        422: {"model": ErrorEnvelope, "description": "Invalid payload."},
    },
)
def create_rfq(
    payload: RfqCreateRequest,
    request: Request,
    response: Response,
    context: Annotated[
        SessionContext, Depends(require_company_permission(Permission.TRADE_WRITE))
    ],
    service: Annotated[RfqService, Depends(get_rfq_service)],
    database: Annotated[Database, Depends(get_database)],
    settings: Annotated[Settings, Depends(app_settings)],
) -> RfqBatchResponse | JSONResponse:
    meta = write_meta(context, request)
    data = RfqCreateData(
        deal_id=payload.deal_id,
        supplier_ids=tuple(payload.supplier_ids),
        requested_currency=payload.requested_currency.strip().upper(),
        requested_delivery_terms=payload.requested_delivery_terms,
        delivery_location=payload.delivery_location,
        response_due_date=payload.response_due_date,
        notes=payload.notes,
        items=tuple(
            RfqItemInput(
                product_id=item.product_id,
                description=item.description,
                quantity=item.quantity,
                unit=item.unit,
                notes=item.notes,
            )
            for item in payload.items
        ),
    )
    with idempotent_call(database, settings, context, request, payload) as call:
        if call.replay is not None:
            return replay_response(call.replay)
        records = service.create(call.session, meta=meta, data=data)
        body = rfq_batch_response(records)
        call.complete(status_code=201, body=body.model_dump(mode="json"))
    response.headers["Cache-Control"] = "no-store"
    return body


@router.get(
    "/rfqs/{rfq_id}",
    response_model=RfqResponse,
    summary="Read one RFQ with lines, quotes and prepared revisions",
    responses={404: {"model": ErrorEnvelope, "description": "Unknown RFQ."}},
)
def get_rfq(
    rfq_id: UUID,
    response: Response,
    context: Annotated[
        SessionContext, Depends(require_company_permission(Permission.COMPANY_VIEW))
    ],
    service: Annotated[RfqService, Depends(get_rfq_service)],
) -> RfqResponse:
    record = service.get(company_id=active_company_id(context), rfq_id=rfq_id)
    response.headers["ETag"] = etag_for(record.version)
    response.headers["Cache-Control"] = "no-store"
    response.headers["Vary"] = "Cookie"
    return rfq_response(record)



@router.patch(
    "/rfqs/{rfq_id}",
    response_model=RfqResponse,
    summary="Update an RFQ (If-Match required)",
    description=(
        "Draft and prepared RFQs are editable. Editing a prepared RFQ returns it to "
        "DRAFT and opens the next revision, so the prepared snapshot stays intact. "
        "Status is not writable here: use the transitions endpoint."
    ),
    responses={
        200: {"description": "Updated; the new ETag is returned."},
        400: {"model": ErrorEnvelope, "description": "Malformed If-Match or unknown product."},
        404: {"model": ErrorEnvelope, "description": "Unknown RFQ."},
        409: {"model": ErrorEnvelope, "description": "Sent/closed RFQ or version conflict."},
        422: {"model": ErrorEnvelope, "description": "Invalid payload."},
        428: {"model": ErrorEnvelope, "description": "If-Match header missing."},
    },
)
def update_rfq(
    rfq_id: UUID,
    payload: RfqUpdateRequest,
    request: Request,
    response: Response,
    context: Annotated[
        SessionContext, Depends(require_company_permission(Permission.TRADE_WRITE))
    ],
    service: Annotated[RfqService, Depends(get_rfq_service)],
    database: Annotated[Database, Depends(get_database)],
    settings: Annotated[Settings, Depends(app_settings)],
) -> RfqResponse | JSONResponse:
    expected_version = require_if_match(request.headers.get("If-Match"))
    meta = write_meta(context, request)
    changes = payload.model_dump(exclude_unset=True)
    if changes.get("requested_currency"):
        changes["requested_currency"] = str(changes["requested_currency"]).upper()
    if changes.get("items") is not None:
        changes["items"] = tuple(
            RfqItemInput(
                product_id=item.product_id,
                description=item.description,
                quantity=item.quantity,
                unit=item.unit,
                notes=item.notes,
            )
            for item in payload.items or []
        )
    with idempotent_call(database, settings, context, request, payload) as call:
        if call.replay is not None:
            return replay_response(call.replay)
        record = service.update(
            call.session,
            meta=meta,
            rfq_id=rfq_id,
            expected_version=expected_version,
            changes=changes,
        )
        body = rfq_response(record)
        call.complete(status_code=200, body=body.model_dump(mode="json"))
    response.headers["ETag"] = etag_for(record.version)
    response.headers["Cache-Control"] = "no-store"
    return body


@router.post(
    "/rfqs/{rfq_id}/transitions",
    response_model=RfqResponse,
    summary="Move an RFQ through its lifecycle",
    description=(
        "Requires Idempotency-Key. PREPARED writes an immutable revision snapshot; "
        "SENT requires channel and evidence; CANCELLED requires a reason."
    ),
    responses={
        200: {"description": "Transition accepted; the new ETag is returned."},
        400: {"model": ErrorEnvelope, "description": "Missing key, channel or evidence."},
        404: {"model": ErrorEnvelope, "description": "Unknown RFQ."},
        409: {"model": ErrorEnvelope, "description": "Invalid transition or version conflict."},
        422: {"model": ErrorEnvelope, "description": "Unknown target or missing reason."},
    },
)
def transition_rfq(
    rfq_id: UUID,
    payload: RfqTransitionRequest,
    request: Request,
    response: Response,
    context: Annotated[
        SessionContext, Depends(require_company_permission(Permission.TRADE_WRITE))
    ],
    service: Annotated[RfqService, Depends(get_rfq_service)],
    database: Annotated[Database, Depends(get_database)],
    settings: Annotated[Settings, Depends(app_settings)],
) -> RfqResponse | JSONResponse:
    expected_version = parse_if_match(request.headers.get("If-Match"), required=False)
    meta = write_meta(context, request)
    target = RfqStatus(payload.to)
    with idempotent_call(database, settings, context, request, payload, required=True) as call:
        if call.replay is not None:
            return replay_response(call.replay)
        record = service.transition(
            call.session,
            meta=meta,
            rfq_id=rfq_id,
            target=target,
            channel=payload.channel,
            evidence=payload.evidence,
            reason=payload.reason,
            expected_version=expected_version,
        )
        body = rfq_response(record)
        call.complete(status_code=200, body=body.model_dump(mode="json"))
    response.headers["ETag"] = etag_for(record.version)
    response.headers["Cache-Control"] = "no-store"
    return body


@router.get(
    "/rfqs/{rfq_id}/revisions/{revision}",
    response_model=RfqRevisionDetailResponse,
    summary="Read a prepared RFQ snapshot",
    description="Prepared snapshots are append-only; this returns the stored JSON as written.",
    responses={404: {"model": ErrorEnvelope, "description": "Unknown RFQ or revision."}},
)
def get_rfq_revision(
    rfq_id: UUID,
    revision: int,
    response: Response,
    context: Annotated[
        SessionContext, Depends(require_company_permission(Permission.COMPANY_VIEW))
    ],
    service: Annotated[RfqService, Depends(get_rfq_service)],
) -> RfqRevisionDetailResponse:
    record, snapshot = service.get_revision(
        company_id=active_company_id(context), rfq_id=rfq_id, revision=revision
    )
    response.headers["Cache-Control"] = "no-store"
    response.headers["Vary"] = "Cookie"
    return rfq_revision_detail_response(record, snapshot)


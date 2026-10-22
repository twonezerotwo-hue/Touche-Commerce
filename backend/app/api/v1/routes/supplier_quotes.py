"""Supplier quote endpoints: recording, revising, withdrawing and reading.

A quote is always recorded against an RFQ (``POST /rfqs/{rfq_id}/quotes``), which
is what guarantees the supplier, deal and line descriptions come from the request
the supplier answered rather than from the payload.
"""

from __future__ import annotations

from typing import Annotated
from uuid import UUID

from fastapi import APIRouter, Depends, Query, Request, Response, status
from fastapi.responses import JSONResponse

from app.api.deps import app_settings, get_database
from app.api.security import active_company_id, require_company_permission
from app.api.v1.etag import etag_for, require_if_match
from app.api.v1.presenters_sourcing import (
    supplier_quote_list_response,
    supplier_quote_response,
    supplier_quote_revision_detail_response,
)
from app.api.v1.schemas.errors import ErrorEnvelope
from app.api.v1.schemas.sourcing import (
    SupplierQuoteCreateRequest,
    SupplierQuoteListResponse,
    SupplierQuoteResponse,
    SupplierQuoteReviseRequest,
    SupplierQuoteRevisionDetailResponse,
    SupplierQuoteStatusValue,
    SupplierQuoteWithdrawRequest,
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
from app.services.supplier_quotes import (
    QuoteCreateData,
    QuoteFilters,
    QuoteItemInput,
    SupplierQuoteService,
)

router = APIRouter(tags=["supplier-quotes"])


def get_supplier_quote_service(
    database: Annotated[Database, Depends(get_database)],
) -> SupplierQuoteService:
    return SupplierQuoteService(database)


def _create_data(
    payload: SupplierQuoteCreateRequest | SupplierQuoteReviseRequest,
) -> QuoteCreateData:
    return QuoteCreateData(
        supplier_reference=payload.supplier_reference,
        currency=payload.currency.strip().upper(),
        incoterm=payload.incoterm,
        named_delivery_place=payload.named_delivery_place,
        payment_terms=payload.payment_terms,
        shipping_conditions=payload.shipping_conditions,
        lead_time_days=payload.lead_time_days,
        valid_until=payload.valid_until,
        source_reference=payload.source_reference,
        notes=payload.notes,
        received_at=payload.received_at,
        items=tuple(
            QuoteItemInput(
                product_id=item.product_id,
                quantity=item.quantity,
                unit_price=item.unit_price,
                moq=item.moq,
                notes=item.notes,
            )
            for item in payload.items
        ),
    )


@router.get(
    "/supplier-quotes",
    response_model=SupplierQuoteListResponse,
    summary="List supplier quotes",
    description=(
        "Cursor-paginated by receipt time, newest first. Superseded revisions stay "
        "visible with their ``superseded_by_quote_id`` set, so a price history is "
        "never lost."
    ),
    responses={
        200: {"description": "A page of supplier quotes."},
        422: {"model": ErrorEnvelope, "description": "Invalid cursor, limit or filter."},
    },
)
def list_supplier_quotes(
    response: Response,
    context: Annotated[
        SessionContext, Depends(require_company_permission(Permission.COMPANY_VIEW))
    ],
    service: Annotated[SupplierQuoteService, Depends(get_supplier_quote_service)],
    settings: Annotated[Settings, Depends(app_settings)],
    search: Annotated[str | None, Query(max_length=160)] = None,
    quote_status: Annotated[SupplierQuoteStatusValue | None, Query(alias="status")] = None,
    rfq_id: Annotated[UUID | None, Query()] = None,
    deal_id: Annotated[UUID | None, Query()] = None,
    supplier_counterparty_id: Annotated[UUID | None, Query()] = None,
    currency: Annotated[str | None, Query(max_length=3)] = None,
    limit: Annotated[int | None, Query(ge=1)] = None,
    cursor: Annotated[str | None, Query(max_length=512)] = None,
) -> SupplierQuoteListResponse:
    response.headers["Cache-Control"] = "no-store"
    response.headers["Vary"] = "Cookie"
    page = service.list(
        company_id=active_company_id(context),
        filters=QuoteFilters(
            search=search,
            status=quote_status,
            rfq_id=rfq_id,
            deal_id=deal_id,
            supplier_counterparty_id=supplier_counterparty_id,
            currency=currency.strip().upper() if currency else None,
        ),
        limit=resolve_limit(limit, settings),
        cursor=cursor,
    )
    return supplier_quote_list_response(page)


@router.post(
    "/rfqs/{rfq_id}/quotes",
    response_model=SupplierQuoteResponse,
    status_code=status.HTTP_201_CREATED,
    summary="Record a supplier's quote against a sent RFQ",
    description=(
        "The quote inherits its supplier, deal and line descriptions from the RFQ. "
        "Only a SENT (or re-quoted RESPONDED) RFQ accepts a quote, and only one "
        "received quote may be active at a time: later prices are revisions."
    ),
    responses={
        201: {"description": "Recorded; the RFQ becomes RESPONDED."},
        400: {
            "model": ErrorEnvelope,
            "description": "Unknown product, invalid Incoterm or missing key.",
        },
        404: {"model": ErrorEnvelope, "description": "Unknown RFQ."},
        409: {
            "model": ErrorEnvelope,
            "description": "RFQ not sent, or a quote is already active.",
        },
        422: {"model": ErrorEnvelope, "description": "Invalid payload."},
    },
)
def record_supplier_quote(
    rfq_id: UUID,
    payload: SupplierQuoteCreateRequest,
    request: Request,
    response: Response,
    context: Annotated[
        SessionContext, Depends(require_company_permission(Permission.TRADE_WRITE))
    ],
    service: Annotated[SupplierQuoteService, Depends(get_supplier_quote_service)],
    database: Annotated[Database, Depends(get_database)],
    settings: Annotated[Settings, Depends(app_settings)],
) -> SupplierQuoteResponse | JSONResponse:
    meta = write_meta(context, request)
    with idempotent_call(database, settings, context, request, payload) as call:
        if call.replay is not None:
            return replay_response(call.replay)
        record = service.record(
            call.session, meta=meta, rfq_id=rfq_id, data=_create_data(payload)
        )
        body = supplier_quote_response(record)
        call.complete(status_code=201, body=body.model_dump(mode="json"))
    response.headers["ETag"] = etag_for(record.version)
    response.headers["Cache-Control"] = "no-store"
    return body



@router.get(
    "/supplier-quotes/{quote_id}",
    response_model=SupplierQuoteResponse,
    summary="Read one supplier quote with lines and revisions",
    responses={404: {"model": ErrorEnvelope, "description": "Unknown quote."}},
)
def get_supplier_quote(
    quote_id: UUID,
    response: Response,
    context: Annotated[
        SessionContext, Depends(require_company_permission(Permission.COMPANY_VIEW))
    ],
    service: Annotated[SupplierQuoteService, Depends(get_supplier_quote_service)],
) -> SupplierQuoteResponse:
    record = service.get(company_id=active_company_id(context), quote_id=quote_id)
    response.headers["ETag"] = etag_for(record.version)
    response.headers["Cache-Control"] = "no-store"
    response.headers["Vary"] = "Cookie"
    return supplier_quote_response(record)


@router.post(
    "/supplier-quotes/{quote_id}/revisions",
    response_model=SupplierQuoteResponse,
    status_code=status.HTTP_201_CREATED,
    summary="Record a new revision of a supplier quote (If-Match required)",
    description=(
        "Creates a new quote row that supersedes the given one. The previous "
        "revision is never modified, so both prices remain readable and only the "
        "newest revision can be priced."
    ),
    responses={
        201: {"description": "Revision recorded."},
        400: {"model": ErrorEnvelope, "description": "Unknown product or invalid payload."},
        404: {"model": ErrorEnvelope, "description": "Unknown quote."},
        409: {
            "model": ErrorEnvelope,
            "description": "Not received, already superseded or version conflict.",
        },
        428: {"model": ErrorEnvelope, "description": "If-Match header missing."},
    },
)
def revise_supplier_quote(
    quote_id: UUID,
    payload: SupplierQuoteReviseRequest,
    request: Request,
    response: Response,
    context: Annotated[
        SessionContext, Depends(require_company_permission(Permission.TRADE_WRITE))
    ],
    service: Annotated[SupplierQuoteService, Depends(get_supplier_quote_service)],
    database: Annotated[Database, Depends(get_database)],
    settings: Annotated[Settings, Depends(app_settings)],
) -> SupplierQuoteResponse | JSONResponse:
    expected_version = require_if_match(request.headers.get("If-Match"))
    meta = write_meta(context, request)
    with idempotent_call(database, settings, context, request, payload) as call:
        if call.replay is not None:
            return replay_response(call.replay)
        record = service.revise(
            call.session,
            meta=meta,
            quote_id=quote_id,
            expected_version=expected_version,
            data=_create_data(payload),
            reason=payload.reason,
        )
        body = supplier_quote_response(record)
        call.complete(status_code=201, body=body.model_dump(mode="json"))
    response.headers["ETag"] = etag_for(record.version)
    response.headers["Cache-Control"] = "no-store"
    return body


@router.post(
    "/supplier-quotes/{quote_id}/withdraw",
    response_model=SupplierQuoteResponse,
    summary="Withdraw a received quote (If-Match required)",
    description=(
        "A withdrawn quote keeps its data and revision history but can no longer be "
        "priced; a reason is required and recorded in the audit trail."
    ),
    responses={
        200: {"description": "Withdrawn; the new ETag is returned."},
        404: {"model": ErrorEnvelope, "description": "Unknown quote."},
        409: {"model": ErrorEnvelope, "description": "Not received, superseded or conflict."},
        422: {"model": ErrorEnvelope, "description": "Missing or short reason."},
        428: {"model": ErrorEnvelope, "description": "If-Match header missing."},
    },
)
def withdraw_supplier_quote(
    quote_id: UUID,
    payload: SupplierQuoteWithdrawRequest,
    request: Request,
    response: Response,
    context: Annotated[
        SessionContext, Depends(require_company_permission(Permission.TRADE_WRITE))
    ],
    service: Annotated[SupplierQuoteService, Depends(get_supplier_quote_service)],
    database: Annotated[Database, Depends(get_database)],
    settings: Annotated[Settings, Depends(app_settings)],
) -> SupplierQuoteResponse | JSONResponse:
    expected_version = require_if_match(request.headers.get("If-Match"))
    meta = write_meta(context, request)
    with idempotent_call(database, settings, context, request, payload) as call:
        if call.replay is not None:
            return replay_response(call.replay)
        record = service.withdraw(
            call.session,
            meta=meta,
            quote_id=quote_id,
            expected_version=expected_version,
            reason=payload.reason,
        )
        body = supplier_quote_response(record)
        call.complete(status_code=200, body=body.model_dump(mode="json"))
    response.headers["ETag"] = etag_for(record.version)
    response.headers["Cache-Control"] = "no-store"
    return body


@router.get(
    "/supplier-quotes/{quote_id}/revisions/{revision}",
    response_model=SupplierQuoteRevisionDetailResponse,
    summary="Read a stored quote revision snapshot",
    responses={404: {"model": ErrorEnvelope, "description": "Unknown quote or revision."}},
)
def get_supplier_quote_revision(
    quote_id: UUID,
    revision: int,
    response: Response,
    context: Annotated[
        SessionContext, Depends(require_company_permission(Permission.COMPANY_VIEW))
    ],
    service: Annotated[SupplierQuoteService, Depends(get_supplier_quote_service)],
) -> SupplierQuoteRevisionDetailResponse:
    record, snapshot = service.get_revision(
        company_id=active_company_id(context), quote_id=quote_id, revision=revision
    )
    response.headers["Cache-Control"] = "no-store"
    response.headers["Vary"] = "Cookie"
    return supplier_quote_revision_detail_response(record, snapshot)


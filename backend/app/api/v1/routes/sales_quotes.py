"""Sales quote endpoints and the approval workflow.

``POST /sales-quotes`` turns a pricing scenario into a customer quotation.
Everything after that is an explicit action guarded by ``If-Match`` and an
``Idempotency-Key``: submitting for approval, approving, rejecting, withdrawing,
and opening a new revision. Approval requires ``finance.approve`` and refuses the
person who submitted the quote (segregation of duties).
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
    sales_quote_list_response,
    sales_quote_response,
    sales_quote_revision_detail_response,
)
from app.api.v1.schemas.errors import ErrorEnvelope
from app.api.v1.schemas.sourcing import (
    SalesQuoteApproveRequest,
    SalesQuoteCreateRequest,
    SalesQuoteListResponse,
    SalesQuoteRejectRequest,
    SalesQuoteResponse,
    SalesQuoteReviseRequest,
    SalesQuoteRevisionDetailResponse,
    SalesQuoteStatusValue,
    SalesQuoteWithdrawRequest,
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
from app.services.sales_quotes import (
    SalesQuoteCreateData,
    SalesQuoteFilters,
    SalesQuoteReviseData,
    SalesQuoteService,
)

router = APIRouter(tags=["sales-quotes"])


def get_sales_quote_service(
    database: Annotated[Database, Depends(get_database)],
) -> SalesQuoteService:
    return SalesQuoteService(database)


@router.get(
    "/sales-quotes",
    response_model=SalesQuoteListResponse,
    summary="List sales quotes",
    description=(
        "Cursor-paginated, newest first. Each row includes the scenario status so a "
        "reviewer can see whether the underlying inputs were verified."
    ),
    responses={
        200: {"description": "A page of sales quotes."},
        422: {"model": ErrorEnvelope, "description": "Invalid cursor, limit or filter."},
    },
)
def list_sales_quotes(
    response: Response,
    context: Annotated[
        SessionContext, Depends(require_company_permission(Permission.COMPANY_VIEW))
    ],
    service: Annotated[SalesQuoteService, Depends(get_sales_quote_service)],
    settings: Annotated[Settings, Depends(app_settings)],
    search: Annotated[str | None, Query(max_length=160)] = None,
    quote_status: Annotated[SalesQuoteStatusValue | None, Query(alias="status")] = None,
    deal_id: Annotated[UUID | None, Query()] = None,
    customer_id: Annotated[UUID | None, Query()] = None,
    currency: Annotated[str | None, Query(max_length=3)] = None,
    limit: Annotated[int | None, Query(ge=1)] = None,
    cursor: Annotated[str | None, Query(max_length=512)] = None,
) -> SalesQuoteListResponse:
    response.headers["Cache-Control"] = "no-store"
    response.headers["Vary"] = "Cookie"
    page = service.list(
        company_id=active_company_id(context),
        filters=SalesQuoteFilters(
            search=search,
            status=quote_status,
            deal_id=deal_id,
            customer_id=customer_id,
            currency=currency.strip().upper() if currency else None,
        ),
        limit=resolve_limit(limit, settings),
        cursor=cursor,
    )
    return sales_quote_list_response(page)


@router.post(
    "/sales-quotes",
    response_model=SalesQuoteResponse,
    status_code=status.HTTP_201_CREATED,
    summary="Draft a sales quote from a pricing scenario",
    description=(
        "Prices are copied from the scenario's stored results, so the quote matches "
        "the calculation that was reviewed. A supplier counterparty cannot be a "
        "customer. The new quote starts in DRAFT."
    ),
    responses={
        201: {"description": "Drafted."},
        400: {"model": ErrorEnvelope, "description": "Unknown customer, Incoterm or date."},
        404: {"model": ErrorEnvelope, "description": "Unknown scenario."},
        409: {"model": ErrorEnvelope, "description": "Scenario has no priced lines."},
        422: {"model": ErrorEnvelope, "description": "Invalid payload."},
    },
)
def create_sales_quote(
    payload: SalesQuoteCreateRequest,
    request: Request,
    response: Response,
    context: Annotated[
        SessionContext, Depends(require_company_permission(Permission.TRADE_WRITE))
    ],
    service: Annotated[SalesQuoteService, Depends(get_sales_quote_service)],
    database: Annotated[Database, Depends(get_database)],
    settings: Annotated[Settings, Depends(app_settings)],
) -> SalesQuoteResponse | JSONResponse:
    meta = write_meta(context, request)
    data = SalesQuoteCreateData(
        scenario_id=payload.scenario_id,
        customer_id=payload.customer_id,
        valid_until=payload.valid_until,
        incoterm=payload.incoterm,
        named_delivery_place=payload.named_delivery_place,
        payment_terms=payload.payment_terms,
        notes=payload.notes,
    )
    with idempotent_call(database, settings, context, request, payload) as call:
        if call.replay is not None:
            return replay_response(call.replay)
        record = service.create(call.session, meta=meta, data=data)
        body = sales_quote_response(record)
        call.complete(status_code=201, body=body.model_dump(mode="json"))
    response.headers["ETag"] = etag_for(record.version)
    response.headers["Cache-Control"] = "no-store"
    return body


@router.get(
    "/sales-quotes/{sales_quote_id}",
    response_model=SalesQuoteResponse,
    summary="Read one sales quote with lines, revisions and allowed actions",
    responses={404: {"model": ErrorEnvelope, "description": "Unknown sales quote."}},
)
def get_sales_quote(
    sales_quote_id: UUID,
    response: Response,
    context: Annotated[
        SessionContext, Depends(require_company_permission(Permission.COMPANY_VIEW))
    ],
    service: Annotated[SalesQuoteService, Depends(get_sales_quote_service)],
) -> SalesQuoteResponse:
    record = service.get(
        company_id=active_company_id(context), sales_quote_id=sales_quote_id
    )
    response.headers["ETag"] = etag_for(record.version)
    response.headers["Cache-Control"] = "no-store"
    response.headers["Vary"] = "Cookie"
    return sales_quote_response(record)


@router.post(
    "/sales-quotes/{sales_quote_id}/submit",
    response_model=SalesQuoteResponse,
    summary="Submit a draft for approval (If-Match + Idempotency-Key required)",
    description=(
        "Only a scenario with VERIFIED_INPUTS may be submitted: an estimate can be "
        "drafted and discussed, never approved as if it were verified."
    ),
    responses={
        200: {"description": "Submitted; the new ETag is returned."},
        404: {"model": ErrorEnvelope, "description": "Unknown sales quote."},
        409: {
            "model": ErrorEnvelope,
            "description": "Invalid transition, unverified scenario or version conflict.",
        },
        428: {"model": ErrorEnvelope, "description": "If-Match header missing."},
    },
)
def submit_sales_quote(
    sales_quote_id: UUID,
    request: Request,
    response: Response,
    context: Annotated[
        SessionContext, Depends(require_company_permission(Permission.TRADE_WRITE))
    ],
    service: Annotated[SalesQuoteService, Depends(get_sales_quote_service)],
    database: Annotated[Database, Depends(get_database)],
    settings: Annotated[Settings, Depends(app_settings)],
) -> SalesQuoteResponse | JSONResponse:
    expected_version = require_if_match(request.headers.get("If-Match"))
    meta = write_meta(context, request)
    with idempotent_call(database, settings, context, request, None, required=True) as call:
        if call.replay is not None:
            return replay_response(call.replay)
        record = service.submit(
            call.session,
            meta=meta,
            sales_quote_id=sales_quote_id,
            expected_version=expected_version,
        )
        body = sales_quote_response(record)
        call.complete(status_code=200, body=body.model_dump(mode="json"))
    response.headers["ETag"] = etag_for(record.version)
    response.headers["Cache-Control"] = "no-store"
    return body



@router.post(
    "/sales-quotes/{sales_quote_id}/approve",
    response_model=SalesQuoteResponse,
    summary="Approve a submitted quote (finance.approve)",
    description=(
        "Requires the ``finance.approve`` permission (traders and admins never hold "
        "it) and refuses the submitter, so approval is always a second pair of eyes."
    ),
    responses={
        200: {"description": "Approved; the new ETag is returned."},
        403: {"model": ErrorEnvelope, "description": "Missing permission or self-approval."},
        404: {"model": ErrorEnvelope, "description": "Unknown sales quote."},
        409: {"model": ErrorEnvelope, "description": "Invalid transition or version conflict."},
        428: {"model": ErrorEnvelope, "description": "If-Match header missing."},
    },
)
def approve_sales_quote(
    sales_quote_id: UUID,
    request: Request,
    response: Response,
    context: Annotated[
        SessionContext, Depends(require_company_permission(Permission.FINANCE_APPROVE))
    ],
    service: Annotated[SalesQuoteService, Depends(get_sales_quote_service)],
    database: Annotated[Database, Depends(get_database)],
    settings: Annotated[Settings, Depends(app_settings)],
    payload: SalesQuoteApproveRequest | None = None,
) -> SalesQuoteResponse | JSONResponse:
    expected_version = require_if_match(request.headers.get("If-Match"))
    meta = write_meta(context, request)
    note = payload.note if payload is not None else None
    with idempotent_call(
        database, settings, context, request, payload, required=True
    ) as call:
        if call.replay is not None:
            return replay_response(call.replay)
        record = service.approve(
            call.session,
            meta=meta,
            sales_quote_id=sales_quote_id,
            expected_version=expected_version,
            reason=note,
        )
        body = sales_quote_response(record)
        call.complete(status_code=200, body=body.model_dump(mode="json"))
    response.headers["ETag"] = etag_for(record.version)
    response.headers["Cache-Control"] = "no-store"
    return body


@router.post(
    "/sales-quotes/{sales_quote_id}/reject",
    response_model=SalesQuoteResponse,
    summary="Reject a submitted quote (finance.approve)",
    description="A rejection explains itself: the reason is stored and audited.",
    responses={
        200: {"description": "Rejected; the new ETag is returned."},
        403: {"model": ErrorEnvelope, "description": "Missing permission."},
        404: {"model": ErrorEnvelope, "description": "Unknown sales quote."},
        409: {"model": ErrorEnvelope, "description": "Invalid transition or version conflict."},
        422: {"model": ErrorEnvelope, "description": "Missing reason."},
        428: {"model": ErrorEnvelope, "description": "If-Match header missing."},
    },
)
def reject_sales_quote(
    sales_quote_id: UUID,
    payload: SalesQuoteRejectRequest,
    request: Request,
    response: Response,
    context: Annotated[
        SessionContext, Depends(require_company_permission(Permission.FINANCE_APPROVE))
    ],
    service: Annotated[SalesQuoteService, Depends(get_sales_quote_service)],
    database: Annotated[Database, Depends(get_database)],
    settings: Annotated[Settings, Depends(app_settings)],
) -> SalesQuoteResponse | JSONResponse:
    expected_version = require_if_match(request.headers.get("If-Match"))
    meta = write_meta(context, request)
    with idempotent_call(database, settings, context, request, payload) as call:
        if call.replay is not None:
            return replay_response(call.replay)
        record = service.reject(
            call.session,
            meta=meta,
            sales_quote_id=sales_quote_id,
            expected_version=expected_version,
            reason=payload.reason,
        )
        body = sales_quote_response(record)
        call.complete(status_code=200, body=body.model_dump(mode="json"))
    response.headers["ETag"] = etag_for(record.version)
    response.headers["Cache-Control"] = "no-store"
    return body



@router.post(
    "/sales-quotes/{sales_quote_id}/withdraw",
    response_model=SalesQuoteResponse,
    summary="Withdraw a draft or submitted quote (If-Match required)",
    description=(
        "Withdrawal is a dead end: an approved quote cannot be withdrawn, it is "
        "superseded by a new revision instead, so the approval trail stays intact."
    ),
    responses={
        200: {"description": "Withdrawn; the new ETag is returned."},
        404: {"model": ErrorEnvelope, "description": "Unknown sales quote."},
        409: {"model": ErrorEnvelope, "description": "Invalid transition or version conflict."},
        428: {"model": ErrorEnvelope, "description": "If-Match header missing."},
    },
)
def withdraw_sales_quote(
    sales_quote_id: UUID,
    payload: SalesQuoteWithdrawRequest,
    request: Request,
    response: Response,
    context: Annotated[
        SessionContext, Depends(require_company_permission(Permission.TRADE_WRITE))
    ],
    service: Annotated[SalesQuoteService, Depends(get_sales_quote_service)],
    database: Annotated[Database, Depends(get_database)],
    settings: Annotated[Settings, Depends(app_settings)],
) -> SalesQuoteResponse | JSONResponse:
    expected_version = require_if_match(request.headers.get("If-Match"))
    meta = write_meta(context, request)
    with idempotent_call(database, settings, context, request, payload) as call:
        if call.replay is not None:
            return replay_response(call.replay)
        record = service.withdraw(
            call.session,
            meta=meta,
            sales_quote_id=sales_quote_id,
            expected_version=expected_version,
            reason=payload.reason,
        )
        body = sales_quote_response(record)
        call.complete(status_code=200, body=body.model_dump(mode="json"))
    response.headers["ETag"] = etag_for(record.version)
    response.headers["Cache-Control"] = "no-store"
    return body


@router.post(
    "/sales-quotes/{sales_quote_id}/revisions",
    response_model=SalesQuoteResponse,
    status_code=status.HTTP_201_CREATED,
    summary="Open a new revision of an approved, rejected or withdrawn quote",
    description=(
        "The new revision starts in DRAFT, carries the next revision number and "
        "supersedes the previous row. Prices are re-read from the pricing scenario."
    ),
    responses={
        201: {"description": "New revision drafted."},
        400: {"model": ErrorEnvelope, "description": "Invalid validity date."},
        404: {"model": ErrorEnvelope, "description": "Unknown sales quote."},
        409: {"model": ErrorEnvelope, "description": "Not revisable or already superseded."},
        428: {"model": ErrorEnvelope, "description": "If-Match header missing."},
    },
)
def revise_sales_quote(
    sales_quote_id: UUID,
    payload: SalesQuoteReviseRequest,
    request: Request,
    response: Response,
    context: Annotated[
        SessionContext, Depends(require_company_permission(Permission.TRADE_WRITE))
    ],
    service: Annotated[SalesQuoteService, Depends(get_sales_quote_service)],
    database: Annotated[Database, Depends(get_database)],
    settings: Annotated[Settings, Depends(app_settings)],
) -> SalesQuoteResponse | JSONResponse:
    expected_version = require_if_match(request.headers.get("If-Match"))
    meta = write_meta(context, request)
    data = SalesQuoteReviseData(
        valid_until=payload.valid_until,
        notes=payload.notes,
        reason=payload.reason,
    )
    with idempotent_call(database, settings, context, request, payload) as call:
        if call.replay is not None:
            return replay_response(call.replay)
        record = service.revise(
            call.session,
            meta=meta,
            sales_quote_id=sales_quote_id,
            expected_version=expected_version,
            data=data,
        )
        body = sales_quote_response(record)
        call.complete(status_code=201, body=body.model_dump(mode="json"))
    response.headers["ETag"] = etag_for(record.version)
    response.headers["Cache-Control"] = "no-store"
    return body


@router.get(
    "/sales-quotes/{sales_quote_id}/revisions/{revision}",
    response_model=SalesQuoteRevisionDetailResponse,
    summary="Read a stored sales quote revision snapshot",
    responses={404: {"model": ErrorEnvelope, "description": "Unknown quote or revision."}},
)
def get_sales_quote_revision(
    sales_quote_id: UUID,
    revision: int,
    response: Response,
    context: Annotated[
        SessionContext, Depends(require_company_permission(Permission.COMPANY_VIEW))
    ],
    service: Annotated[SalesQuoteService, Depends(get_sales_quote_service)],
) -> SalesQuoteRevisionDetailResponse:
    record, snapshot = service.get_revision(
        company_id=active_company_id(context),
        sales_quote_id=sales_quote_id,
        revision=revision,
    )
    response.headers["Cache-Control"] = "no-store"
    response.headers["Vary"] = "Cookie"
    return sales_quote_revision_detail_response(record, snapshot)


"""Sales order endpoints: acceptance, atomic conversion, history and amendments.

``POST /deals/{deal_id}/sales-order`` is the **only** route that makes a deal
``WON``. It requires an ``Idempotency-Key`` so a retried conversion returns the
original order instead of creating a second one, and it refuses to run without
customer acceptance evidence for the accepted revision.
"""

from __future__ import annotations

from typing import Annotated
from uuid import UUID

from fastapi import APIRouter, Depends, Query, Request, Response, status
from fastapi.responses import JSONResponse

from app.api.deps import app_settings, get_database
from app.api.security import active_company_id, require_company_permission
from app.api.v1.etag import etag_for, require_if_match
from app.api.v1.presenters_operations import (
    acceptance_list_response,
    acceptance_response,
    fulfilment_response,
    order_list_response,
    order_response,
)
from app.api.v1.schemas.errors import ErrorEnvelope
from app.api.v1.schemas.operations import (
    CustomerAcceptanceListResponse,
    CustomerAcceptanceRequest,
    CustomerAcceptanceResponse,
    FulfilmentSummaryResponse,
    OrderAmendmentRequest,
    OrderConversionRequest,
    OrderTransitionRequest,
    SalesOrderListResponse,
    SalesOrderResponse,
    SalesOrderStatusValue,
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
from app.services.sales_orders import (
    AcceptanceData,
    AmendmentData,
    AmendmentLine,
    ConversionData,
    OrderFilters,
    SalesOrderService,
)
from app.services.shipments import ShipmentService

router = APIRouter(tags=["sales-orders"])


def get_order_service(
    database: Annotated[Database, Depends(get_database)],
) -> SalesOrderService:
    return SalesOrderService(database)


def get_shipment_service(
    database: Annotated[Database, Depends(get_database)],
) -> ShipmentService:
    return ShipmentService(database)


@router.get(
    "/sales-orders",
    response_model=SalesOrderListResponse,
    summary="List sales orders",
    description=(
        "Cursor-paginated, newest first. A viewer sees only this company's orders; "
        "RLS enforces the boundary even if a filter were wrong."
    ),
    responses={422: {"model": ErrorEnvelope, "description": "Invalid cursor or filter."}},
)
def list_sales_orders(
    response: Response,
    context: Annotated[
        SessionContext, Depends(require_company_permission(Permission.COMPANY_VIEW))
    ],
    service: Annotated[SalesOrderService, Depends(get_order_service)],
    settings: Annotated[Settings, Depends(app_settings)],
    search: Annotated[str | None, Query(max_length=160)] = None,
    order_status: Annotated[SalesOrderStatusValue | None, Query(alias="status")] = None,
    customer_id: Annotated[UUID | None, Query()] = None,
    deal_id: Annotated[UUID | None, Query()] = None,
    currency: Annotated[str | None, Query(max_length=3)] = None,
    limit: Annotated[int | None, Query(ge=1)] = None,
    cursor: Annotated[str | None, Query(max_length=512)] = None,
) -> SalesOrderListResponse:
    response.headers["Cache-Control"] = "no-store"
    response.headers["Vary"] = "Cookie"
    page = service.list(
        company_id=active_company_id(context),
        filters=OrderFilters(
            search=search,
            status=order_status,
            customer_id=customer_id,
            deal_id=deal_id,
            currency=currency,
        ),
        limit=resolve_limit(limit, settings),
        cursor=cursor,
    )
    return order_list_response(page)


@router.post(
    "/deals/{deal_id}/customer-acceptance",
    response_model=CustomerAcceptanceResponse,
    status_code=status.HTTP_201_CREATED,
    summary="Record documented customer acceptance of the approved quote revision",
    description=(
        "Records the customer's acceptance with its channel, timestamp and evidence "
        "reference. Internal approval alone is never treated as acceptance."
    ),
    responses={
        409: {"model": ErrorEnvelope, "description": "No approved quote to accept."},
    },
)
def record_customer_acceptance(
    deal_id: UUID,
    payload: CustomerAcceptanceRequest,
    request: Request,
    response: Response,
    context: Annotated[
        SessionContext, Depends(require_company_permission(Permission.TRADE_WRITE))
    ],
    service: Annotated[SalesOrderService, Depends(get_order_service)],
    database: Annotated[Database, Depends(get_database)],
    settings: Annotated[Settings, Depends(app_settings)],
) -> CustomerAcceptanceResponse | JSONResponse:
    meta = write_meta(context, request)
    data = AcceptanceData(
        channel=payload.channel,
        accepted_at=payload.accepted_at,
        accepted_by_name=payload.accepted_by_name,
        evidence_reference=payload.evidence_reference,
        evidence_document_id=payload.evidence_document_id,
        notes=payload.notes,
    )
    with idempotent_call(database, settings, context, request, payload) as call:
        if call.replay is not None:
            return replay_response(call.replay)
        record = service.record_acceptance(
            call.session, meta=meta, deal_id=deal_id, data=data
        )
        body = acceptance_response(record)
        call.complete(status_code=201, body=body.model_dump(mode="json"))
    response.headers["Cache-Control"] = "no-store"
    response.headers["Vary"] = "Cookie"
    return body


@router.get(
    "/deals/{deal_id}/customer-acceptance",
    response_model=CustomerAcceptanceListResponse,
    summary="List recorded customer acceptances for a deal",
    responses={404: {"model": ErrorEnvelope, "description": "Unknown deal."}},
)
def list_customer_acceptance(
    deal_id: UUID,
    response: Response,
    context: Annotated[
        SessionContext, Depends(require_company_permission(Permission.COMPANY_VIEW))
    ],
    service: Annotated[SalesOrderService, Depends(get_order_service)],
) -> CustomerAcceptanceListResponse:
    response.headers["Cache-Control"] = "no-store"
    response.headers["Vary"] = "Cookie"
    records = service.list_acceptances(
        company_id=active_company_id(context), deal_id=deal_id
    )
    return acceptance_list_response(records)


@router.post(
    "/deals/{deal_id}/sales-order",
    response_model=SalesOrderResponse,
    status_code=status.HTTP_201_CREATED,
    summary="Convert an accepted quote into a sales order and win the deal",
    description=(
        "Atomic: the deal is locked, the approved quote revision and the customer "
        "acceptance evidence are verified, then the order, its immutable lines, the "
        "WON transition and the audit rows are written in one transaction. Requires "
        "an Idempotency-Key; a retry with the same key returns the original order."
    ),
    responses={
        409: {
            "model": ErrorEnvelope,
            "description": "Acceptance missing, quote not approved, or the deal is already WON.",
        },
    },
)
def convert_deal_to_order(
    deal_id: UUID,
    payload: OrderConversionRequest,
    request: Request,
    response: Response,
    context: Annotated[
        SessionContext, Depends(require_company_permission(Permission.TRADE_WRITE))
    ],
    service: Annotated[SalesOrderService, Depends(get_order_service)],
    database: Annotated[Database, Depends(get_database)],
    settings: Annotated[Settings, Depends(app_settings)],
) -> SalesOrderResponse | JSONResponse:
    meta = write_meta(context, request)
    data = ConversionData(
        sales_quote_id=payload.sales_quote_id,
        acceptance_evidence_id=payload.acceptance_evidence_id,
        customer_acceptance=(
            AcceptanceData(
                channel=payload.customer_acceptance.channel,
                accepted_at=payload.customer_acceptance.accepted_at,
                accepted_by_name=payload.customer_acceptance.accepted_by_name,
                evidence_reference=payload.customer_acceptance.evidence_reference,
                evidence_document_id=payload.customer_acceptance.evidence_document_id,
                notes=payload.customer_acceptance.notes,
            )
            if payload.customer_acceptance is not None
            else None
        ),
        fulfilment_model=payload.fulfilment_model,
        expected_delivery_date=payload.expected_delivery_date,
        notes=payload.notes,
        expected_total=payload.expected_total,
        order_number=payload.order_number,
    )
    with idempotent_call(
        database,
        settings,
        context,
        request,
        payload,
        required=True,
        endpoint=f"POST /deals/{deal_id}/sales-order",
    ) as call:
        if call.replay is not None:
            return replay_response(call.replay)
        record = service.convert(call.session, meta=meta, deal_id=deal_id, data=data)
        body = order_response(record)
        call.complete(status_code=201, body=body.model_dump(mode="json"))
    response.headers["ETag"] = etag_for(record.version)
    response.headers["Cache-Control"] = "no-store"
    response.headers["Vary"] = "Cookie"
    return body


@router.get(
    "/sales-orders/{sales_order_id}",
    response_model=SalesOrderResponse,
    summary="Read a sales order with its frozen items and history",
    responses={404: {"model": ErrorEnvelope, "description": "Unknown order."}},
)
def get_sales_order(
    sales_order_id: UUID,
    response: Response,
    context: Annotated[
        SessionContext, Depends(require_company_permission(Permission.COMPANY_VIEW))
    ],
    service: Annotated[SalesOrderService, Depends(get_order_service)],
) -> SalesOrderResponse:
    record = service.get(
        company_id=active_company_id(context), sales_order_id=sales_order_id
    )
    response.headers["ETag"] = etag_for(record.version)
    response.headers["Cache-Control"] = "no-store"
    response.headers["Vary"] = "Cookie"
    return order_response(record)


@router.get(
    "/sales-orders/{sales_order_id}/fulfilment",
    response_model=FulfilmentSummaryResponse,
    summary="Delivered versus ordered quantity per line",
    description=(
        "Derived from shipment allocations and delivered shipments only. A partial "
        "delivery never marks the order fulfilled."
    ),
    responses={404: {"model": ErrorEnvelope, "description": "Unknown order."}},
)
def get_order_fulfilment(
    sales_order_id: UUID,
    response: Response,
    context: Annotated[
        SessionContext, Depends(require_company_permission(Permission.COMPANY_VIEW))
    ],
    service: Annotated[ShipmentService, Depends(get_shipment_service)],
) -> FulfilmentSummaryResponse:
    summary = service.fulfilment(
        company_id=active_company_id(context), sales_order_id=sales_order_id
    )
    response.headers["Cache-Control"] = "no-store"
    response.headers["Vary"] = "Cookie"
    return fulfilment_response(summary)


@router.post(
    "/sales-orders/{sales_order_id}/transitions",
    response_model=SalesOrderResponse,
    summary="Move a sales order through its administrative states",
    description=(
        "FULFILLED is rejected here: it is derived from delivered shipment "
        "quantities. CANCELLED requires a reason and preserves the commercial history."
    ),
    responses={
        409: {"model": ErrorEnvelope, "description": "Invalid transition or stale version."},
        428: {"model": ErrorEnvelope, "description": "If-Match header missing."},
    },
)
def transition_sales_order(
    sales_order_id: UUID,
    payload: OrderTransitionRequest,
    request: Request,
    response: Response,
    context: Annotated[
        SessionContext, Depends(require_company_permission(Permission.TRADE_WRITE))
    ],
    service: Annotated[SalesOrderService, Depends(get_order_service)],
    database: Annotated[Database, Depends(get_database)],
    settings: Annotated[Settings, Depends(app_settings)],
) -> SalesOrderResponse | JSONResponse:
    expected_version = require_if_match(request.headers.get("If-Match"))
    meta = write_meta(context, request)
    with idempotent_call(database, settings, context, request, payload) as call:
        if call.replay is not None:
            return replay_response(call.replay)
        record = service.transition(
            call.session,
            meta=meta,
            sales_order_id=sales_order_id,
            expected_version=expected_version,
            target=payload.target,
            reason=payload.reason,
        )
        body = order_response(record)
        call.complete(status_code=200, body=body.model_dump(mode="json"))
    response.headers["ETag"] = etag_for(record.version)
    response.headers["Cache-Control"] = "no-store"
    return body


@router.post(
    "/sales-orders/{sales_order_id}/amendments",
    response_model=SalesOrderResponse,
    summary="Amend an order with a recorded reason",
    description=(
        "The accepted commercial snapshot is never rewritten. The amendment records "
        "exactly what changed, and a quantity cannot drop below what shipments "
        "already allocate."
    ),
    responses={
        409: {"model": ErrorEnvelope, "description": "Cancelled order or allocated quantity."},
        428: {"model": ErrorEnvelope, "description": "If-Match header missing."},
    },
)
def amend_sales_order(
    sales_order_id: UUID,
    payload: OrderAmendmentRequest,
    request: Request,
    response: Response,
    context: Annotated[
        SessionContext, Depends(require_company_permission(Permission.TRADE_WRITE))
    ],
    service: Annotated[SalesOrderService, Depends(get_order_service)],
    database: Annotated[Database, Depends(get_database)],
    settings: Annotated[Settings, Depends(app_settings)],
) -> SalesOrderResponse | JSONResponse:
    expected_version = require_if_match(request.headers.get("If-Match"))
    meta = write_meta(context, request)
    data = AmendmentData(
        reason=payload.reason,
        payment_terms=payload.payment_terms,
        named_delivery_place=payload.named_delivery_place,
        expected_delivery_date=payload.expected_delivery_date,
        notes=payload.notes,
        lines=tuple(
            AmendmentLine(item_id=line.item_id, quantity=line.quantity)
            for line in payload.lines
        ),
    )
    with idempotent_call(database, settings, context, request, payload) as call:
        if call.replay is not None:
            return replay_response(call.replay)
        record = service.amend(
            call.session,
            meta=meta,
            sales_order_id=sales_order_id,
            expected_version=expected_version,
            data=data,
        )
        body = order_response(record)
        call.complete(status_code=200, body=body.model_dump(mode="json"))
    response.headers["ETag"] = etag_for(record.version)
    response.headers["Cache-Control"] = "no-store"
    return body

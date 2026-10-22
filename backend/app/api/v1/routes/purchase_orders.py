"""Purchase order routes: optional procurement with recorded supplier evidence."""

from __future__ import annotations

from typing import Annotated
from uuid import UUID

from fastapi import APIRouter, Depends, Query, Request, Response, status
from fastapi.responses import JSONResponse

from app.api.deps import app_settings, get_database
from app.api.security import active_company_id, require_company_permission
from app.api.v1.etag import etag_for, require_if_match
from app.api.v1.presenters_operations import po_list_response, po_response
from app.api.v1.schemas.errors import ErrorEnvelope
from app.api.v1.schemas.operations import (
    PurchaseOrderCreateRequest,
    PurchaseOrderListResponse,
    PurchaseOrderResponse,
    PurchaseOrderStatusValue,
    PurchaseOrderTransitionRequest,
)
from app.api.v1.trade_helpers import (
    idempotent_call,
    replay_response,
    resolve_limit,
    write_meta,
)
from app.core.config import Settings
from app.core.errors import ForbiddenError
from app.db.engine import Database
from app.security.permissions import Permission
from app.services.auth import SessionContext
from app.services.procurement import (
    CreatePurchaseOrderData,
    NewPoItem,
    PoTransitionData,
    ProcurementService,
    PurchaseOrderFilters,
)

router = APIRouter(tags=["purchase-orders"])


def get_procurement_service(
    database: Annotated[Database, Depends(get_database)],
) -> ProcurementService:
    return ProcurementService(database)


@router.get(
    "/purchase-orders",
    response_model=PurchaseOrderListResponse,
    summary="List supplier purchase orders",
    responses={422: {"model": ErrorEnvelope, "description": "Invalid cursor or filter."}},
)
def list_purchase_orders(
    response: Response,
    context: Annotated[
        SessionContext, Depends(require_company_permission(Permission.COMPANY_VIEW))
    ],
    service: Annotated[ProcurementService, Depends(get_procurement_service)],
    settings: Annotated[Settings, Depends(app_settings)],
    search: Annotated[str | None, Query(max_length=160)] = None,
    po_status: Annotated[PurchaseOrderStatusValue | None, Query(alias="status")] = None,
    sales_order_id: Annotated[UUID | None, Query()] = None,
    supplier_id: Annotated[UUID | None, Query()] = None,
    limit: Annotated[int | None, Query(ge=1)] = None,
    cursor: Annotated[str | None, Query(max_length=512)] = None,
) -> PurchaseOrderListResponse:
    response.headers["Cache-Control"] = "no-store"
    response.headers["Vary"] = "Cookie"
    page = service.list(
        company_id=active_company_id(context),
        filters=PurchaseOrderFilters(
            search=search,
            status=po_status,
            sales_order_id=sales_order_id,
            supplier_id=supplier_id,
        ),
        limit=resolve_limit(limit, settings),
        cursor=cursor,
    )
    return po_list_response(page)


@router.post(
    "/purchase-orders",
    response_model=PurchaseOrderResponse,
    status_code=status.HTTP_201_CREATED,
    summary="Create a draft supplier purchase order for a sales order",
    description=(
        "Refused for brokerage orders where TOUCHE is not the buyer. The order starts "
        "as DRAFT: nothing is sent to the supplier by this system."
    ),
    responses={
        409: {"model": ErrorEnvelope, "description": "Procurement is not applicable."},
    },
)
def create_purchase_order(
    payload: PurchaseOrderCreateRequest,
    request: Request,
    response: Response,
    context: Annotated[
        SessionContext, Depends(require_company_permission(Permission.TRADE_WRITE))
    ],
    service: Annotated[ProcurementService, Depends(get_procurement_service)],
    database: Annotated[Database, Depends(get_database)],
    settings: Annotated[Settings, Depends(app_settings)],
) -> PurchaseOrderResponse | JSONResponse:
    meta = write_meta(context, request)
    data = CreatePurchaseOrderData(
        sales_order_id=payload.sales_order_id,
        supplier_id=payload.supplier_id,
        supplier_quote_id=payload.supplier_quote_id,
        incoterm=payload.incoterm,
        named_delivery_place=payload.named_delivery_place,
        payment_terms=payload.payment_terms,
        expected_dispatch_date=payload.expected_dispatch_date,
        expected_delivery_date=payload.expected_delivery_date,
        notes=payload.notes,
        items=tuple(
            NewPoItem(
                product_id=item.product_id,
                description=item.description or "",
                quantity=item.quantity,
                unit=item.unit or "",
                unit_cost=item.unit_cost,
            )
            for item in payload.items
        ),
    )
    with idempotent_call(database, settings, context, request, payload) as call:
        if call.replay is not None:
            return replay_response(call.replay)
        record = service.create(call.session, meta=meta, data=data)
        body = po_response(record)
        call.complete(status_code=201, body=body.model_dump(mode="json"))
    response.headers["ETag"] = etag_for(record.version)
    response.headers["Cache-Control"] = "no-store"
    return body


@router.get(
    "/purchase-orders/{purchase_order_id}",
    response_model=PurchaseOrderResponse,
    summary="Read a purchase order with its history and evidence",
    responses={404: {"model": ErrorEnvelope, "description": "Unknown purchase order."}},
)
def get_purchase_order(
    purchase_order_id: UUID,
    response: Response,
    context: Annotated[
        SessionContext, Depends(require_company_permission(Permission.COMPANY_VIEW))
    ],
    service: Annotated[ProcurementService, Depends(get_procurement_service)],
) -> PurchaseOrderResponse:
    record = service.get(
        company_id=active_company_id(context), purchase_order_id=purchase_order_id
    )
    response.headers["ETag"] = etag_for(record.version)
    response.headers["Cache-Control"] = "no-store"
    response.headers["Vary"] = "Cookie"
    return po_response(record)


@router.post(
    "/purchase-orders/{purchase_order_id}/transitions",
    response_model=PurchaseOrderResponse,
    summary="Approve, record dispatch or confirm a purchase order",
    description=(
        "APPROVED needs finance.approve and a different person from the creator. "
        "RECORDED_SENT needs a channel, a timestamp and an external reference. "
        "SUPPLIER_CONFIRMED needs the supplier's confirmation reference."
    ),
    responses={
        403: {"model": ErrorEnvelope, "description": "Missing approval permission."},
        409: {"model": ErrorEnvelope, "description": "Invalid transition or stale version."},
        428: {"model": ErrorEnvelope, "description": "If-Match header missing."},
    },
)
def transition_purchase_order(
    purchase_order_id: UUID,
    payload: PurchaseOrderTransitionRequest,
    request: Request,
    response: Response,
    context: Annotated[
        SessionContext, Depends(require_company_permission(Permission.COMPANY_VIEW))
    ],
    service: Annotated[ProcurementService, Depends(get_procurement_service)],
    database: Annotated[Database, Depends(get_database)],
    settings: Annotated[Settings, Depends(app_settings)],
) -> PurchaseOrderResponse | JSONResponse:
    # Approval is a financial act (finance.approve); every other transition is
    # operational (trade.write). Keeping the split here means an approver never
    # needs trade.write and a trader can never approve, matching Stage 3.
    if payload.target == "APPROVED":
        if Permission.FINANCE_APPROVE not in context.permissions:
            raise ForbiddenError(
                "Approving a purchase order requires finance.approve.",
                details={"permission": "finance.approve"},
            )
    elif Permission.TRADE_WRITE not in context.permissions:
        raise ForbiddenError()
    expected_version = require_if_match(request.headers.get("If-Match"))
    meta = write_meta(context, request)
    data = PoTransitionData(
        target=payload.target,
        reason=payload.reason,
        dispatched_at=payload.dispatched_at,
        dispatch_channel=payload.dispatch_channel,
        dispatch_reference=payload.dispatch_reference,
        supplier_confirmation_reference=payload.supplier_confirmation_reference,
        evidence_reference=payload.evidence_reference,
    )
    with idempotent_call(database, settings, context, request, payload) as call:
        if call.replay is not None:
            return replay_response(call.replay)
        record = service.transition(
            call.session,
            meta=meta,
            purchase_order_id=purchase_order_id,
            expected_version=expected_version,
            data=data,
            actor_can_approve=Permission.FINANCE_APPROVE in context.permissions,
        )
        body = po_response(record)
        call.complete(status_code=200, body=body.model_dump(mode="json"))
    response.headers["ETag"] = etag_for(record.version)
    response.headers["Cache-Control"] = "no-store"
    return body

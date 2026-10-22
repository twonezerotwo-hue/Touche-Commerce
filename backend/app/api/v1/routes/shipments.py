"""Shipment routes: planning, movement milestones, costs and references."""

from __future__ import annotations

from typing import Annotated
from uuid import UUID

from fastapi import APIRouter, Depends, Query, Request, Response, status
from fastapi.responses import JSONResponse

from app.api.deps import app_settings, get_database
from app.api.security import active_company_id, require_company_permission
from app.api.v1.etag import etag_for, require_if_match
from app.api.v1.presenters_operations import shipment_list_response, shipment_response
from app.api.v1.schemas.errors import ErrorEnvelope
from app.api.v1.schemas.operations import (
    ShipmentCostRequest,
    ShipmentCreateRequest,
    ShipmentEventRequest,
    ShipmentListResponse,
    ShipmentReferenceRequest,
    ShipmentResponse,
    ShipmentStatusValue,
    ShipmentTransitionRequest,
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
from app.services.shipments import (
    CostData,
    EventData,
    PlanItem,
    PlanShipmentData,
    ReferenceData,
    ShipmentFilters,
    ShipmentService,
    TransitionShipmentData,
)

router = APIRouter(tags=["shipments"])


def get_shipment_service(
    database: Annotated[Database, Depends(get_database)],
) -> ShipmentService:
    return ShipmentService(database)


@router.get(
    "/shipments",
    response_model=ShipmentListResponse,
    summary="List shipments",
    description=(
        "Delayed means a documented ETA that has passed while the shipment is not "
        "delivered or cancelled. No live carrier feed exists."
    ),
    responses={422: {"model": ErrorEnvelope, "description": "Invalid cursor or filter."}},
)
def list_shipments(
    response: Response,
    context: Annotated[
        SessionContext, Depends(require_company_permission(Permission.COMPANY_VIEW))
    ],
    service: Annotated[ShipmentService, Depends(get_shipment_service)],
    settings: Annotated[Settings, Depends(app_settings)],
    search: Annotated[str | None, Query(max_length=160)] = None,
    shipment_status: Annotated[ShipmentStatusValue | None, Query(alias="status")] = None,
    sales_order_id: Annotated[UUID | None, Query()] = None,
    transport_mode: Annotated[str | None, Query(max_length=16)] = None,
    limit: Annotated[int | None, Query(ge=1)] = None,
    cursor: Annotated[str | None, Query(max_length=512)] = None,
) -> ShipmentListResponse:
    response.headers["Cache-Control"] = "no-store"
    response.headers["Vary"] = "Cookie"
    page = service.list(
        company_id=active_company_id(context),
        filters=ShipmentFilters(
            search=search,
            status=shipment_status,
            sales_order_id=sales_order_id,
            transport_mode=transport_mode,
        ),
        limit=resolve_limit(limit, settings),
        cursor=cursor,
    )
    return shipment_list_response(page)


@router.post(
    "/shipments",
    response_model=ShipmentResponse,
    status_code=status.HTTP_201_CREATED,
    summary="Plan a shipment (partial quantities allowed)",
    description=(
        "Quantities are validated against what is still outstanding per order line, "
        "and the unit must match the order line exactly."
    ),
    responses={
        400: {"model": ErrorEnvelope, "description": "Over-allocation or unit mismatch."},
        409: {"model": ErrorEnvelope, "description": "Order not shippable."},
    },
)
def plan_shipment(
    payload: ShipmentCreateRequest,
    request: Request,
    response: Response,
    context: Annotated[
        SessionContext, Depends(require_company_permission(Permission.TRADE_WRITE))
    ],
    service: Annotated[ShipmentService, Depends(get_shipment_service)],
    database: Annotated[Database, Depends(get_database)],
    settings: Annotated[Settings, Depends(app_settings)],
) -> ShipmentResponse | JSONResponse:
    meta = write_meta(context, request)
    data = PlanShipmentData(
        sales_order_id=payload.sales_order_id,
        purchase_order_id=payload.purchase_order_id,
        transport_mode=payload.transport_mode,
        origin=payload.origin,
        destination=payload.destination,
        carrier=payload.carrier,
        forwarder=payload.forwarder,
        planned_dispatch_at=payload.planned_dispatch_at,
        estimated_arrival_at=payload.estimated_arrival_at,
        tracking_reference=payload.tracking_reference,
        tracking_source=payload.tracking_source,
        notes=payload.notes,
        items=tuple(
            PlanItem(
                sales_order_item_id=item.sales_order_item_id,
                quantity=item.quantity,
            )
            for item in payload.items
        ),
    )
    with idempotent_call(database, settings, context, request, payload) as call:
        if call.replay is not None:
            return replay_response(call.replay)
        record = service.plan(call.session, meta=meta, data=data)
        body = shipment_response(record)
        call.complete(status_code=201, body=body.model_dump(mode="json"))
    response.headers["ETag"] = etag_for(record.version)
    response.headers["Cache-Control"] = "no-store"
    return body


@router.get(
    "/shipments/{shipment_id}",
    response_model=ShipmentResponse,
    summary="Read a shipment with its timeline, references and costs",
    responses={404: {"model": ErrorEnvelope, "description": "Unknown shipment."}},
)
def get_shipment(
    shipment_id: UUID,
    response: Response,
    context: Annotated[
        SessionContext, Depends(require_company_permission(Permission.COMPANY_VIEW))
    ],
    service: Annotated[ShipmentService, Depends(get_shipment_service)],
) -> ShipmentResponse:
    record = service.get(company_id=active_company_id(context), shipment_id=shipment_id)
    response.headers["ETag"] = etag_for(record.version)
    response.headers["Cache-Control"] = "no-store"
    response.headers["Vary"] = "Cookie"
    return shipment_response(record)


@router.post(
    "/shipments/{shipment_id}/transitions",
    response_model=ShipmentResponse,
    summary="Move a shipment through its timeline with evidence",
    description=(
        "DISPATCHED requires an actual dispatch timestamp and a carrier reference. "
        "ARRIVED requires the actual arrival timestamp (an ETA is not an arrival). "
        "DELIVERED requires a delivery evidence reference."
    ),
    responses={
        400: {"model": ErrorEnvelope, "description": "Evidence requirement not met."},
        409: {"model": ErrorEnvelope, "description": "Invalid transition or stale version."},
        428: {"model": ErrorEnvelope, "description": "If-Match header missing."},
    },
)
def transition_shipment(
    shipment_id: UUID,
    payload: ShipmentTransitionRequest,
    request: Request,
    response: Response,
    context: Annotated[
        SessionContext, Depends(require_company_permission(Permission.TRADE_WRITE))
    ],
    service: Annotated[ShipmentService, Depends(get_shipment_service)],
    database: Annotated[Database, Depends(get_database)],
    settings: Annotated[Settings, Depends(app_settings)],
) -> ShipmentResponse | JSONResponse:
    expected_version = require_if_match(request.headers.get("If-Match"))
    meta = write_meta(context, request)
    data = TransitionShipmentData(
        target=payload.target,
        occurred_at=payload.occurred_at,
        location=payload.location,
        notes=payload.notes,
        reason=payload.reason,
        tracking_reference=payload.tracking_reference,
        tracking_source=payload.tracking_source,
        evidence_reference=payload.evidence_reference,
        delivery_evidence_reference=payload.delivery_evidence_reference,
    )
    with idempotent_call(database, settings, context, request, payload) as call:
        if call.replay is not None:
            return replay_response(call.replay)
        record = service.transition(
            call.session,
            meta=meta,
            shipment_id=shipment_id,
            expected_version=expected_version,
            data=data,
        )
        body = shipment_response(record)
        call.complete(status_code=200, body=body.model_dump(mode="json"))
    response.headers["ETag"] = etag_for(record.version)
    response.headers["Cache-Control"] = "no-store"
    return body


@router.post(
    "/shipments/{shipment_id}/events",
    response_model=ShipmentResponse,
    summary="Record an in-transit milestone or a documented delay",
    description=(
        "Only IN_TRANSIT and DELAY_RECORDED milestones can be appended here; status "
        "changes go through the transition endpoint."
    ),
    responses={409: {"model": ErrorEnvelope, "description": "Completed shipment."}},
)
def record_shipment_event(
    shipment_id: UUID,
    payload: ShipmentEventRequest,
    request: Request,
    response: Response,
    context: Annotated[
        SessionContext, Depends(require_company_permission(Permission.TRADE_WRITE))
    ],
    service: Annotated[ShipmentService, Depends(get_shipment_service)],
    database: Annotated[Database, Depends(get_database)],
    settings: Annotated[Settings, Depends(app_settings)],
) -> ShipmentResponse | JSONResponse:
    meta = write_meta(context, request)
    data = EventData(
        event_type=payload.event_type,
        occurred_at=payload.occurred_at,
        location=payload.location,
        notes=payload.notes,
        evidence_reference=payload.evidence_reference,
        tracking_source=payload.tracking_source,
    )
    with idempotent_call(database, settings, context, request, payload) as call:
        if call.replay is not None:
            return replay_response(call.replay)
        record = service.record_event(
            call.session, meta=meta, shipment_id=shipment_id, data=data
        )
        body = shipment_response(record)
        call.complete(status_code=200, body=body.model_dump(mode="json"))
    response.headers["Cache-Control"] = "no-store"
    return body


@router.post(
    "/shipments/{shipment_id}/costs",
    response_model=ShipmentResponse,
    summary="Record a logistics cost with its certainty stage",
    description=(
        "ESTIMATED, QUOTED, INCURRED and DOCUMENTED are separate stages; recording a "
        "cost never rewrites the Stage 3 pricing assumptions."
    ),
)
def record_shipment_cost(
    shipment_id: UUID,
    payload: ShipmentCostRequest,
    request: Request,
    response: Response,
    context: Annotated[
        SessionContext, Depends(require_company_permission(Permission.TRADE_WRITE))
    ],
    service: Annotated[ShipmentService, Depends(get_shipment_service)],
    database: Annotated[Database, Depends(get_database)],
    settings: Annotated[Settings, Depends(app_settings)],
) -> ShipmentResponse | JSONResponse:
    meta = write_meta(context, request)
    data = CostData(
        cost_type=payload.cost_type,
        stage=payload.stage,
        amount=payload.amount,
        currency=payload.currency,
        reference=payload.reference,
        notes=payload.notes,
    )
    with idempotent_call(database, settings, context, request, payload) as call:
        if call.replay is not None:
            return replay_response(call.replay)
        record = service.record_cost(
            call.session, meta=meta, shipment_id=shipment_id, data=data
        )
        body = shipment_response(record)
        call.complete(status_code=200, body=body.model_dump(mode="json"))
    response.headers["Cache-Control"] = "no-store"
    return body


@router.post(
    "/shipments/{shipment_id}/references",
    response_model=ShipmentResponse,
    summary="Record a booking, container or transport reference",
    description=(
        "The provenance must be MANUAL or DOCUMENT_EVIDENCE: no external carrier "
        "verification exists in this stage."
    ),
)
def add_shipment_reference(
    shipment_id: UUID,
    payload: ShipmentReferenceRequest,
    request: Request,
    response: Response,
    context: Annotated[
        SessionContext, Depends(require_company_permission(Permission.TRADE_WRITE))
    ],
    service: Annotated[ShipmentService, Depends(get_shipment_service)],
    database: Annotated[Database, Depends(get_database)],
    settings: Annotated[Settings, Depends(app_settings)],
) -> ShipmentResponse | JSONResponse:
    meta = write_meta(context, request)
    data = ReferenceData(
        reference_type=payload.reference_type,
        reference_value=payload.reference_value,
        provenance=payload.provenance,
    )
    with idempotent_call(database, settings, context, request, payload) as call:
        if call.replay is not None:
            return replay_response(call.replay)
        record = service.add_reference(
            call.session, meta=meta, shipment_id=shipment_id, data=data
        )
        body = shipment_response(record)
        call.complete(status_code=200, body=body.model_dump(mode="json"))
    response.headers["Cache-Control"] = "no-store"
    return body

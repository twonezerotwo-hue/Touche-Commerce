"""Pricing scenario endpoints: deterministic landed cost with stored inputs.

A scenario is created from one supplier quote and a list of sourced cost
components. The calculated results are persisted, not recomputed on read, so a
price agreed today does not silently change when a freight invoice arrives. A
recalculation is an explicit ``PUT`` guarded by ``If-Match``.
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
    pricing_scenario_list_response,
    pricing_scenario_response,
)
from app.api.v1.schemas.errors import ErrorEnvelope
from app.api.v1.schemas.sourcing import (
    PricingScenarioListResponse,
    PricingScenarioRequest,
    PricingScenarioResponse,
    ScenarioStatusValue,
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
from app.services.pricing import (
    CostComponentInput,
    PricingScenarioService,
    ScenarioCreateData,
    ScenarioFilters,
)

router = APIRouter(tags=["pricing-scenarios"])


def get_pricing_service(
    database: Annotated[Database, Depends(get_database)],
) -> PricingScenarioService:
    return PricingScenarioService(database)


def _scenario_data(payload: PricingScenarioRequest) -> ScenarioCreateData:
    return ScenarioCreateData(
        supplier_quote_id=payload.supplier_quote_id,
        target_currency=payload.target_currency.strip().upper(),
        sales_incoterm=payload.sales_incoterm,
        sales_named_place=payload.sales_named_place,
        margin_pct=payload.margin_pct,
        markup_pct=payload.markup_pct,
        fx_rate_snapshot_id=payload.fx_rate_snapshot_id,
        components=tuple(
            CostComponentInput(
                cost_type=item.cost_type,
                amount=item.amount,
                currency=item.currency.strip().upper(),
                basis=item.basis,
                source_reference=item.source_reference,
                verification_status=item.verification_status,
                fx_rate_snapshot_id=item.fx_rate_snapshot_id,
                product_id=item.product_id,
                notes=item.notes,
            )
            for item in payload.components
        ),
    )


@router.get(
    "/pricing-scenarios",
    response_model=PricingScenarioListResponse,
    summary="List pricing scenarios",
    description=(
        "Cursor-paginated, newest first. The summary carries landed total, sales "
        "total and gross margin so a comparison table needs no extra call."
    ),
    responses={
        200: {"description": "A page of scenarios."},
        422: {"model": ErrorEnvelope, "description": "Invalid cursor, limit or filter."},
    },
)
def list_pricing_scenarios(
    response: Response,
    context: Annotated[
        SessionContext, Depends(require_company_permission(Permission.COMPANY_VIEW))
    ],
    service: Annotated[PricingScenarioService, Depends(get_pricing_service)],
    settings: Annotated[Settings, Depends(app_settings)],
    scenario_status: Annotated[ScenarioStatusValue | None, Query(alias="status")] = None,
    deal_id: Annotated[UUID | None, Query()] = None,
    supplier_quote_id: Annotated[UUID | None, Query()] = None,
    limit: Annotated[int | None, Query(ge=1)] = None,
    cursor: Annotated[str | None, Query(max_length=512)] = None,
) -> PricingScenarioListResponse:
    response.headers["Cache-Control"] = "no-store"
    response.headers["Vary"] = "Cookie"
    page = service.list(
        company_id=active_company_id(context),
        filters=ScenarioFilters(
            status=scenario_status,
            deal_id=deal_id,
            supplier_quote_id=supplier_quote_id,
        ),
        limit=resolve_limit(limit, settings),
        cursor=cursor,
    )
    return pricing_scenario_list_response(page)


@router.post(
    "/pricing-scenarios",
    response_model=PricingScenarioResponse,
    status_code=status.HTTP_201_CREATED,
    summary="Price a supplier quote (landed cost + selling price)",
    description=(
        "Converts the quote into the target currency using an explicit FX snapshot, "
        "allocates every cost component (ORDER pro-rata by purchase value, LINE to "
        "its product) and derives selling prices from exactly one of margin or "
        "markup. The inputs and the rounded results are stored together."
    ),
    responses={
        201: {"description": "Calculated and stored."},
        400: {
            "model": ErrorEnvelope,
            "description": "Missing FX snapshot, unpriced line or invalid component.",
        },
        404: {"model": ErrorEnvelope, "description": "Unknown supplier quote."},
        409: {"model": ErrorEnvelope, "description": "Quote withdrawn or superseded."},
        422: {"model": ErrorEnvelope, "description": "Invalid payload."},
    },
)
def create_pricing_scenario(
    payload: PricingScenarioRequest,
    request: Request,
    response: Response,
    context: Annotated[
        SessionContext, Depends(require_company_permission(Permission.TRADE_WRITE))
    ],
    service: Annotated[PricingScenarioService, Depends(get_pricing_service)],
    database: Annotated[Database, Depends(get_database)],
    settings: Annotated[Settings, Depends(app_settings)],
) -> PricingScenarioResponse | JSONResponse:
    meta = write_meta(context, request)
    with idempotent_call(database, settings, context, request, payload) as call:
        if call.replay is not None:
            return replay_response(call.replay)
        record = service.create(call.session, meta=meta, data=_scenario_data(payload))
        body = pricing_scenario_response(record)
        call.complete(status_code=201, body=body.model_dump(mode="json"))
    response.headers["ETag"] = etag_for(record.version)
    response.headers["Cache-Control"] = "no-store"
    return body


@router.get(
    "/pricing-scenarios/{scenario_id}",
    response_model=PricingScenarioResponse,
    summary="Read one scenario with inputs, results and components",
    responses={404: {"model": ErrorEnvelope, "description": "Unknown scenario."}},
)
def get_pricing_scenario(
    scenario_id: UUID,
    response: Response,
    context: Annotated[
        SessionContext, Depends(require_company_permission(Permission.COMPANY_VIEW))
    ],
    service: Annotated[PricingScenarioService, Depends(get_pricing_service)],
) -> PricingScenarioResponse:
    record = service.get(
        company_id=active_company_id(context), scenario_id=scenario_id
    )
    response.headers["ETag"] = etag_for(record.version)
    response.headers["Cache-Control"] = "no-store"
    response.headers["Vary"] = "Cookie"
    return pricing_scenario_response(record)


@router.put(
    "/pricing-scenarios/{scenario_id}",
    response_model=PricingScenarioResponse,
    summary="Recalculate a scenario with new inputs (If-Match required)",
    description=(
        "Replaces the cost components and reruns the engine for the same supplier "
        "quote. A scenario is bound to its quote: repointing it is a 400, not a "
        "silent rewrite of history."
    ),
    responses={
        200: {"description": "Recalculated; the new ETag is returned."},
        400: {"model": ErrorEnvelope, "description": "Wrong quote, FX or component."},
        404: {"model": ErrorEnvelope, "description": "Unknown scenario."},
        409: {"model": ErrorEnvelope, "description": "Version conflict."},
        428: {"model": ErrorEnvelope, "description": "If-Match header missing."},
    },
)
def recalculate_pricing_scenario(
    scenario_id: UUID,
    payload: PricingScenarioRequest,
    request: Request,
    response: Response,
    context: Annotated[
        SessionContext, Depends(require_company_permission(Permission.TRADE_WRITE))
    ],
    service: Annotated[PricingScenarioService, Depends(get_pricing_service)],
    database: Annotated[Database, Depends(get_database)],
    settings: Annotated[Settings, Depends(app_settings)],
) -> PricingScenarioResponse | JSONResponse:
    expected_version = require_if_match(request.headers.get("If-Match"))
    meta = write_meta(context, request)
    with idempotent_call(database, settings, context, request, payload) as call:
        if call.replay is not None:
            return replay_response(call.replay)
        record = service.recalculate(
            call.session,
            meta=meta,
            scenario_id=scenario_id,
            expected_version=expected_version,
            data=_scenario_data(payload),
        )
        body = pricing_scenario_response(record)
        call.complete(status_code=200, body=body.model_dump(mode="json"))
    response.headers["ETag"] = etag_for(record.version)
    response.headers["Cache-Control"] = "no-store"
    return body


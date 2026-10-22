"""Product catalogue endpoints — list, create, read, update."""

from __future__ import annotations

from typing import Annotated
from uuid import UUID

from fastapi import APIRouter, Depends, Query, Request, Response, status
from fastapi.responses import JSONResponse

from app.api.deps import app_settings, get_database
from app.api.security import active_company_id, require_company_permission
from app.api.v1.etag import etag_for, require_if_match
from app.api.v1.presenters_trade import product_list_response, product_response
from app.api.v1.schemas.errors import ErrorEnvelope
from app.api.v1.schemas.trade import (
    ProductCreateRequest,
    ProductListResponse,
    ProductResponse,
    ProductUpdateRequest,
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
from app.services.catalog import ProductFilters, ProductService

router = APIRouter(tags=["products"])


def get_product_service(database: Annotated[Database, Depends(get_database)]) -> ProductService:
    return ProductService(database)


@router.get(
    "/products",
    response_model=ProductListResponse,
    summary="List products",
    description="Cursor-paginated catalogue, newest first; search matches SKU and name.",
    responses={
        200: {"description": "A page of products."},
        422: {"model": ErrorEnvelope, "description": "Invalid cursor, limit or filter."},
    },
)
def list_products(
    response: Response,
    context: Annotated[
        SessionContext, Depends(require_company_permission(Permission.COMPANY_VIEW))
    ],
    service: Annotated[ProductService, Depends(get_product_service)],
    settings: Annotated[Settings, Depends(app_settings)],
    search: Annotated[str | None, Query(max_length=160)] = None,
    product_status: Annotated[RecordStatusValue | None, Query(alias="status")] = None,
    limit: Annotated[int | None, Query(ge=1)] = None,
    cursor: Annotated[str | None, Query(max_length=512)] = None,
) -> ProductListResponse:
    response.headers["Cache-Control"] = "no-store"
    response.headers["Vary"] = "Cookie"
    page = service.list(
        company_id=active_company_id(context),
        filters=ProductFilters(search=search, status=product_status),
        limit=resolve_limit(limit, settings),
        cursor=cursor,
    )
    return product_list_response(page)


@router.post(
    "/products",
    response_model=ProductResponse,
    status_code=status.HTTP_201_CREATED,
    summary="Create a product",
    responses={
        201: {"description": "Created."},
        403: {"model": ErrorEnvelope, "description": "Missing trade.write."},
        409: {"model": ErrorEnvelope, "description": "Duplicate SKU or key conflict."},
        422: {"model": ErrorEnvelope, "description": "Invalid payload."},
    },
)
def create_product(
    payload: ProductCreateRequest,
    request: Request,
    response: Response,
    context: Annotated[
        SessionContext, Depends(require_company_permission(Permission.TRADE_WRITE))
    ],
    service: Annotated[ProductService, Depends(get_product_service)],
    database: Annotated[Database, Depends(get_database)],
    settings: Annotated[Settings, Depends(app_settings)],
) -> ProductResponse | JSONResponse:
    meta = write_meta(context, request)
    with idempotent_call(database, settings, context, request, payload) as call:
        if call.replay is not None:
            return replay_response(call.replay)
        record = service.create(call.session, meta=meta, data=payload.model_dump())
        body = product_response(record)
        call.complete(status_code=201, body=body.model_dump(mode="json"))
    response.headers["ETag"] = etag_for(record.version)
    response.headers["Cache-Control"] = "no-store"
    return body


@router.get(
    "/products/{product_id}",
    response_model=ProductResponse,
    summary="Read one product",
    responses={404: {"model": ErrorEnvelope, "description": "Unknown product."}},
)
def get_product(
    product_id: UUID,
    response: Response,
    context: Annotated[
        SessionContext, Depends(require_company_permission(Permission.COMPANY_VIEW))
    ],
    service: Annotated[ProductService, Depends(get_product_service)],
) -> ProductResponse:
    record = service.get(company_id=active_company_id(context), product_id=product_id)
    response.headers["ETag"] = etag_for(record.version)
    response.headers["Cache-Control"] = "no-store"
    response.headers["Vary"] = "Cookie"
    return product_response(record)


@router.patch(
    "/products/{product_id}",
    response_model=ProductResponse,
    summary="Update a product (If-Match required)",
    responses={
        200: {"description": "Updated; the new ETag is returned."},
        409: {"model": ErrorEnvelope, "description": "Version or key conflict."},
        428: {"model": ErrorEnvelope, "description": "If-Match header missing."},
    },
)
def update_product(
    product_id: UUID,
    payload: ProductUpdateRequest,
    request: Request,
    response: Response,
    context: Annotated[
        SessionContext, Depends(require_company_permission(Permission.TRADE_WRITE))
    ],
    service: Annotated[ProductService, Depends(get_product_service)],
    database: Annotated[Database, Depends(get_database)],
    settings: Annotated[Settings, Depends(app_settings)],
) -> ProductResponse | JSONResponse:
    expected_version = require_if_match(request.headers.get("If-Match"))
    meta = write_meta(context, request)
    with idempotent_call(database, settings, context, request, payload) as call:
        if call.replay is not None:
            return replay_response(call.replay)
        record = service.update(
            call.session,
            meta=meta,
            product_id=product_id,
            expected_version=expected_version,
            changes=payload.model_dump(exclude_unset=True),
        )
        body = product_response(record)
        call.complete(status_code=200, body=body.model_dump(mode="json"))
    response.headers["ETag"] = etag_for(record.version)
    response.headers["Cache-Control"] = "no-store"
    return body



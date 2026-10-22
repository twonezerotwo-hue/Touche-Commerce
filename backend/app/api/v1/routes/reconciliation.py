"""Stage 5D versioned reconciliation routes.

Read endpoints require only company.view. Creating a run or linking evidence
requires trade.write; confirming/disputing a review and resolving a discrepancy
require the distinct ``finance.reconcile`` permission. No route writes to
Finance or to an accounting table.
"""

from __future__ import annotations

from datetime import date
from typing import Annotated
from uuid import UUID

from fastapi import APIRouter, Depends, Query, Request, Response, status
from fastapi.responses import JSONResponse

from app.api.deps import app_settings, get_database
from app.api.security import active_company_id, require_company_permission
from app.api.v1.etag import etag_for, require_if_match
from app.api.v1.presenters_reconciliation import (
    discrepancy_list_response,
    discrepancy_response,
    evidence_list_response,
    order_finance_response,
    run_list_response,
    run_response,
)
from app.api.v1.schemas.errors import ErrorEnvelope
from app.api.v1.schemas.reconciliation import (
    DiscrepancyListResponse,
    DiscrepancyResolveRequest,
    DiscrepancyResponse,
    EvidenceLinkListResponse,
    EvidenceLinkRequest,
    OrderFinanceResponse,
    ReconciliationListResponse,
    ReconciliationRunCreateRequest,
    ReconciliationRunResponse,
    ReconciliationStatusValue,
    ReviewRequest,
)
from app.api.v1.trade_helpers import (
    idempotent_call,
    replay_response,
    resolve_limit,
    write_meta,
)
from app.core.config import Settings
from app.db.engine import Database
from app.db.models import FinanceCompanyMapping
from app.db.tenant import apply_actor_context, apply_company_context
from app.integrations.finance.connector import FinanceConnector
from app.security.permissions import Permission
from app.services.auth import SessionContext
from app.services.finance_mapping import load_mapping, snapshot
from app.services.reconciliation import (
    DiscrepancyFilters,
    ReconciliationService,
    RunFilters,
    read_finance_snapshot,
)
from app.services.reconciliation_calculations import canonical_currency

router = APIRouter(tags=["finance-reconciliation"])


def get_reconciliation_service(
    database: Annotated[Database, Depends(get_database)],
) -> ReconciliationService:
    return ReconciliationService(database)


def _mapping_row(database: Database, context: SessionContext) -> FinanceCompanyMapping | None:
    company_id = active_company_id(context)
    with database.transaction() as session:
        apply_company_context(session, company_id)
        apply_actor_context(session, context.user.user_id)
        return load_mapping(session, company_id)


def _no_store(response: Response) -> None:
    response.headers["Cache-Control"] = "no-store"
    response.headers["Vary"] = "Cookie"


@router.get(
    "/finance/reconciliation",
    response_model=ReconciliationListResponse,
    summary="List evidence reconciliation runs for the active company",
    description=(
        "Lists tenant-scoped runs only. There is no cross-currency total: "
        "status counts are counts, and each run keeps its own currency."
    ),
    responses={422: {"model": ErrorEnvelope, "description": "Invalid filter."}},
)
def list_reconciliation_runs(
    response: Response,
    context: Annotated[
        SessionContext, Depends(require_company_permission(Permission.COMPANY_VIEW))
    ],
    service: Annotated[ReconciliationService, Depends(get_reconciliation_service)],
    settings: Annotated[Settings, Depends(app_settings)],
    currency: Annotated[str | None, Query(max_length=3, pattern=r"^[A-Za-z]{2,3}$")] = None,
    order_id: Annotated[UUID | None, Query()] = None,
    run_status: Annotated[ReconciliationStatusValue | None, Query(alias="status")] = None,
    limit: Annotated[int | None, Query(ge=1)] = None,
    offset: Annotated[int, Query(ge=0, le=1_000_000)] = 0,
) -> ReconciliationListResponse:
    company_id = active_company_id(context)
    resolved_limit = resolve_limit(limit, settings)
    resolved_currency = canonical_currency(currency) if currency else None
    page = service.list_runs(
        company_id=company_id,
        filters=RunFilters(
            sales_order_id=order_id,
            currency=resolved_currency,
            status=run_status,
        ),
        limit=resolved_limit,
        offset=offset,
    )
    status_counts, open_count, blocking_count = service.run_counts(
        company_id=company_id, currency=resolved_currency
    )
    _no_store(response)
    return run_list_response(
        page,
        limit=resolved_limit,
        offset=offset,
        currency=resolved_currency,
        status_counts=status_counts,
        open_discrepancy_count=open_count,
        blocking_discrepancy_count=blocking_count,
    )


@router.post(
    "/finance/reconciliation/runs",
    response_model=ReconciliationRunResponse,
    status_code=status.HTTP_201_CREATED,
    summary="Create an evidence reconciliation snapshot for one sales order",
    description=(
        "Reads Finance's supported summary and aging endpoints, records stable "
        "source ids and deterministic discrepancies. It never posts a journal, "
        "invoice or payment and never attributes a company-wide balance to an order."
    ),
    responses={
        403: {"model": ErrorEnvelope, "description": "trade.write or company context missing."},
        409: {"model": ErrorEnvelope, "description": "Mapping or currency is not usable."},
        502: {"model": ErrorEnvelope, "description": "Finance authentication/protocol failure."},
        503: {"model": ErrorEnvelope, "description": "Finance unavailable or disabled."},
    },
)
def create_reconciliation_run(
    payload: ReconciliationRunCreateRequest,
    request: Request,
    response: Response,
    context: Annotated[SessionContext, Depends(require_company_permission(Permission.TRADE_WRITE))],
    service: Annotated[ReconciliationService, Depends(get_reconciliation_service)],
    database: Annotated[Database, Depends(get_database)],
    settings: Annotated[Settings, Depends(app_settings)],
) -> ReconciliationRunResponse | JSONResponse:
    company_id = active_company_id(context)
    meta = write_meta(context, request)
    with idempotent_call(database, settings, context, request, payload, required=True) as call:
        if call.replay is not None:
            return replay_response(call.replay)
        mapping = load_mapping(call.session, company_id)
        finance = read_finance_snapshot(
            FinanceConnector(settings),
            snapshot(mapping),
            requested_currency=payload.currency,
        )
        record = service.create_run(
            call.session,
            meta=meta,
            sales_order_id=payload.sales_order_id,
            requested_currency=payload.currency,
            as_of=payload.as_of or date.today(),
            mapping=mapping,
            finance=finance,
        )
        body = run_response(record)
        call.complete(status_code=201, body=body.model_dump(mode="json"))
    response.headers["ETag"] = etag_for(record.version)
    _no_store(response)
    return body


@router.get(
    "/finance/reconciliation/runs/{run_id}",
    response_model=ReconciliationRunResponse,
    summary="Read one reconciliation run with evidence, discrepancies and reviews",
    responses={404: {"model": ErrorEnvelope, "description": "Unknown run or another tenant."}},
)
def get_reconciliation_run(
    run_id: UUID,
    response: Response,
    context: Annotated[
        SessionContext, Depends(require_company_permission(Permission.COMPANY_VIEW))
    ],
    service: Annotated[ReconciliationService, Depends(get_reconciliation_service)],
) -> ReconciliationRunResponse:
    record = service.get_run(company_id=active_company_id(context), run_id=run_id)
    response.headers["ETag"] = etag_for(record.version)
    _no_store(response)
    return run_response(record)


@router.get(
    "/finance/evidence-links",
    response_model=EvidenceLinkListResponse,
    summary="List explicit evidence links for a run",
)
def list_evidence_links(
    response: Response,
    context: Annotated[
        SessionContext, Depends(require_company_permission(Permission.COMPANY_VIEW))
    ],
    service: Annotated[ReconciliationService, Depends(get_reconciliation_service)],
    settings: Annotated[Settings, Depends(app_settings)],
    run_id: Annotated[UUID, Query()],
    limit: Annotated[int | None, Query(ge=1)] = None,
    offset: Annotated[int, Query(ge=0, le=1_000_000)] = 0,
) -> EvidenceLinkListResponse:
    resolved_limit = resolve_limit(limit, settings)
    page = service.list_evidence(
        company_id=active_company_id(context),
        run_id=run_id,
        limit=resolved_limit,
        offset=offset,
    )
    _no_store(response)
    return evidence_list_response(page, limit=resolved_limit, offset=offset)


@router.post(
    "/finance/evidence-links",
    response_model=ReconciliationRunResponse,
    status_code=status.HTTP_201_CREATED,
    summary="Explicitly link one Commerce source to one Finance source id",
    description=(
        "Only transaction-level Finance aging ids are linkable. The amount is "
        "taken from the Finance snapshot, never from the request. A duplicate "
        "claim of the same source id in one run is rejected."
    ),
    responses={
        403: {"model": ErrorEnvelope, "description": "trade.write missing."},
        409: {"model": ErrorEnvelope, "description": "Invalid, duplicate or mismatched evidence."},
        428: {"model": ErrorEnvelope, "description": "If-Match header missing."},
    },
)
def create_evidence_link(
    payload: EvidenceLinkRequest,
    request: Request,
    response: Response,
    context: Annotated[SessionContext, Depends(require_company_permission(Permission.TRADE_WRITE))],
    service: Annotated[ReconciliationService, Depends(get_reconciliation_service)],
    database: Annotated[Database, Depends(get_database)],
    settings: Annotated[Settings, Depends(app_settings)],
) -> ReconciliationRunResponse | JSONResponse:
    expected_version = require_if_match(request.headers.get("If-Match"))
    meta = write_meta(context, request)
    with idempotent_call(database, settings, context, request, payload, required=True) as call:
        if call.replay is not None:
            return replay_response(call.replay)
        record = service.add_evidence(
            call.session,
            meta=meta,
            run_id=payload.run_id,
            expected_version=expected_version,
            source_entity_type=payload.source_entity_type,
            source_entity_id=payload.source_entity_id,
            finance_source_reference_id=payload.finance_source_reference_id,
            notes=payload.notes,
        )
        body = run_response(record)
        call.complete(status_code=201, body=body.model_dump(mode="json"))
    response.headers["ETag"] = etag_for(record.version)
    _no_store(response)
    return body


@router.post(
    "/finance/reviews",
    response_model=ReconciliationRunResponse,
    status_code=status.HTTP_201_CREATED,
    summary="Record an authorised financial review decision",
    description=(
        "Requires the distinct finance.reconcile permission. The run creator "
        "cannot review their own run. CONFIRM is the only path to VERIFIED and "
        "requires linked sales-order evidence, MATCHED_EVIDENCE and no open "
        "blocking discrepancies."
    ),
    responses={
        403: {"model": ErrorEnvelope, "description": "finance.reconcile missing or self-review."},
        409: {"model": ErrorEnvelope, "description": "Not verifiable in the current state."},
        428: {"model": ErrorEnvelope, "description": "If-Match header missing."},
    },
)
def create_review(
    payload: ReviewRequest,
    request: Request,
    response: Response,
    context: Annotated[
        SessionContext, Depends(require_company_permission(Permission.FINANCE_RECONCILE))
    ],
    service: Annotated[ReconciliationService, Depends(get_reconciliation_service)],
    database: Annotated[Database, Depends(get_database)],
    settings: Annotated[Settings, Depends(app_settings)],
) -> ReconciliationRunResponse | JSONResponse:
    expected_version = require_if_match(request.headers.get("If-Match"))
    meta = write_meta(context, request)
    with idempotent_call(database, settings, context, request, payload, required=True) as call:
        if call.replay is not None:
            return replay_response(call.replay)
        record = service.review(
            call.session,
            meta=meta,
            run_id=payload.run_id,
            expected_version=expected_version,
            decision=payload.decision,
            notes=payload.notes,
        )
        body = run_response(record)
        call.complete(status_code=201, body=body.model_dump(mode="json"))
    response.headers["ETag"] = etag_for(record.version)
    _no_store(response)
    return body


@router.get(
    "/finance/discrepancies",
    response_model=DiscrepancyListResponse,
    summary="List deterministic reconciliation discrepancies",
)
def list_discrepancies(
    response: Response,
    context: Annotated[
        SessionContext, Depends(require_company_permission(Permission.COMPANY_VIEW))
    ],
    service: Annotated[ReconciliationService, Depends(get_reconciliation_service)],
    settings: Annotated[Settings, Depends(app_settings)],
    run_id: Annotated[UUID | None, Query()] = None,
    code: Annotated[str | None, Query(max_length=32)] = None,
    severity: Annotated[str | None, Query(max_length=16)] = None,
    discrepancy_status: Annotated[str | None, Query(alias="status", max_length=16)] = None,
    currency: Annotated[str | None, Query(max_length=3, pattern=r"^[A-Za-z]{2,3}$")] = None,
    limit: Annotated[int | None, Query(ge=1)] = None,
    offset: Annotated[int, Query(ge=0, le=1_000_000)] = 0,
) -> DiscrepancyListResponse:
    resolved_limit = resolve_limit(limit, settings)
    page = service.list_discrepancies(
        company_id=active_company_id(context),
        filters=DiscrepancyFilters(
            run_id=run_id,
            code=code,
            severity=severity,
            status=discrepancy_status,
            currency=canonical_currency(currency) if currency else None,
        ),
        limit=resolved_limit,
        offset=offset,
    )
    _no_store(response)
    return discrepancy_list_response(page, limit=resolved_limit, offset=offset)


@router.get(
    "/finance/discrepancies/{discrepancy_id}",
    response_model=DiscrepancyResponse,
    summary="Read one discrepancy inside the active company",
    responses={404: {"model": ErrorEnvelope, "description": "Unknown discrepancy."}},
)
def get_discrepancy(
    discrepancy_id: UUID,
    response: Response,
    context: Annotated[
        SessionContext, Depends(require_company_permission(Permission.COMPANY_VIEW))
    ],
    service: Annotated[ReconciliationService, Depends(get_reconciliation_service)],
    settings: Annotated[Settings, Depends(app_settings)],
) -> DiscrepancyResponse:
    record = service.get_discrepancy(
        company_id=active_company_id(context), discrepancy_id=discrepancy_id
    )
    response.headers["ETag"] = etag_for(record.version)
    _no_store(response)
    return discrepancy_response(record)


@router.post(
    "/finance/discrepancies/{discrepancy_id}/resolve",
    response_model=DiscrepancyResponse,
    summary="Resolve a discrepancy with reviewer notes",
    description=(
        "Requires finance.reconcile. Resolution changes the discrepancy record "
        "only; it never changes a Finance ledger, invoice or payment."
    ),
    responses={
        403: {"model": ErrorEnvelope, "description": "finance.reconcile missing."},
        409: {"model": ErrorEnvelope, "description": "Already resolved or stale version."},
        428: {"model": ErrorEnvelope, "description": "If-Match header missing."},
    },
)
def resolve_discrepancy(
    discrepancy_id: UUID,
    payload: DiscrepancyResolveRequest,
    request: Request,
    response: Response,
    context: Annotated[
        SessionContext, Depends(require_company_permission(Permission.FINANCE_RECONCILE))
    ],
    service: Annotated[ReconciliationService, Depends(get_reconciliation_service)],
    database: Annotated[Database, Depends(get_database)],
    settings: Annotated[Settings, Depends(app_settings)],
) -> DiscrepancyResponse | JSONResponse:
    expected_version = require_if_match(request.headers.get("If-Match"))
    meta = write_meta(context, request)
    with idempotent_call(database, settings, context, request, payload, required=True) as call:
        if call.replay is not None:
            return replay_response(call.replay)
        record = service.resolve_discrepancy(
            call.session,
            meta=meta,
            discrepancy_id=discrepancy_id,
            expected_version=expected_version,
            notes=payload.notes,
        )
        body = discrepancy_response(record)
        call.complete(status_code=200, body=body.model_dump(mode="json"))
    response.headers["ETag"] = etag_for(record.version)
    _no_store(response)
    return body


@router.get(
    "/finance/orders/{sales_order_id}",
    response_model=OrderFinanceResponse,
    summary="Order finance view with separated commercial facts and evidence gaps",
    description=(
        "Shows accepted order value, purchase commitments, estimated landed cost, "
        "recorded operational costs and supported margins. Unavailable accounting "
        "facts stay labelled unavailable."
    ),
    responses={404: {"model": ErrorEnvelope, "description": "Unknown sales order."}},
)
def get_order_finance(
    sales_order_id: UUID,
    response: Response,
    context: Annotated[
        SessionContext, Depends(require_company_permission(Permission.COMPANY_VIEW))
    ],
    service: Annotated[ReconciliationService, Depends(get_reconciliation_service)],
) -> OrderFinanceResponse:
    record = service.order_finance_view(
        company_id=active_company_id(context), sales_order_id=sales_order_id
    )
    _no_store(response)
    return order_finance_response(record)

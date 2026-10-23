"""Stage 5E read-only financial intelligence API.

Every route requires an authenticated session, an active company, membership and
``company.view`` (the established financial read permission). No route writes to
Finance, creates an accounting entry or exposes another company's data.
"""

from __future__ import annotations

import csv
import io
from datetime import UTC, date, datetime, timedelta
from typing import Annotated
from uuid import UUID

from fastapi import APIRouter, Depends, Query, Request, Response
from fastapi.responses import Response as FastAPIResponse

from app.api.deps import app_settings, get_database
from app.api.security import (
    active_company_id,
    client_ip,
    request_user_agent,
    require_company_permission,
)
from app.api.v1.presenters_intelligence import (
    cost_variance_response,
    coverage_response,
    detail_response,
    exception_list_response,
    order_list_response,
    summary_response,
)
from app.api.v1.schemas.errors import ErrorEnvelope
from app.api.v1.schemas.intelligence import (
    CostVarianceListResponse,
    CoverageResponse,
    FinancialExceptionListResponse,
    IntelligenceSummaryResponse,
    OrderIntelligenceDetailResponse,
    OrderIntelligenceListResponse,
)
from app.api.v1.trade_helpers import resolve_limit
from app.core.config import Settings
from app.core.context import get_request_id
from app.db.engine import Database
from app.db.models import AuditAction, AuditOutcome
from app.db.tenant import apply_actor_context, apply_company_context
from app.security.permissions import Permission
from app.services.audit import record_audit
from app.services.auth import SessionContext
from app.services.intelligence import (
    MAX_ANALYSIS_ORDERS,
    AnalyzedOrder,
    IntelligenceFilters,
    IntelligenceService,
)
from app.services.intelligence_calculations import CALCULATION_VERSION, money

router = APIRouter(tags=["finance-intelligence"])


def get_intelligence_service(
    database: Annotated[Database, Depends(get_database)],
) -> IntelligenceService:
    return IntelligenceService(database)


def _no_store(response: Response) -> None:
    response.headers["Cache-Control"] = "no-store"
    response.headers["Vary"] = "Cookie"


def intelligence_filters(
    from_date: Annotated[date | None, Query(alias="from")] = None,
    to_date: Annotated[date | None, Query(alias="to")] = None,
    currency: Annotated[
        str | None, Query(max_length=3, pattern=r"^[A-Za-z]{3}$")
    ] = None,
    fulfilment_model: Annotated[str | None, Query(max_length=24)] = None,
    order_status: Annotated[str | None, Query(max_length=16)] = None,
    customer_id: Annotated[UUID | None, Query()] = None,
    supplier_id: Annotated[UUID | None, Query()] = None,
    reconciliation_status: Annotated[str | None, Query(max_length=24)] = None,
    completeness: Annotated[str | None, Query(max_length=16)] = None,
) -> IntelligenceFilters:
    end = to_date or date.today()
    start = from_date or (end - timedelta(days=364))
    return IntelligenceFilters(
        from_date=start,
        to_date=end,
        currency=currency.upper() if currency else None,
        fulfilment_model=fulfilment_model,
        order_status=order_status,
        customer_id=customer_id,
        supplier_id=supplier_id,
        reconciliation_status=reconciliation_status,
        completeness=completeness,
    )


FiltersDependency = Annotated[IntelligenceFilters, Depends(intelligence_filters)]


@router.get(
    "/finance/intelligence/summary",
    response_model=IntelligenceSummaryResponse,
    summary="Operational financial intelligence summary",
    description=(
        "Real Commerce commitments, estimates and documented costs grouped by "
        "currency. No mixed-currency total, no Finance balance attribution and no "
        "statutory statement is produced."
    ),
    responses={422: {"model": ErrorEnvelope, "description": "Invalid filter."}},
)
def intelligence_summary(
    response: Response,
    context: Annotated[
        SessionContext, Depends(require_company_permission(Permission.COMPANY_VIEW))
    ],
    service: Annotated[IntelligenceService, Depends(get_intelligence_service)],
    filters: FiltersDependency,
) -> IntelligenceSummaryResponse:
    record = service.summary(company_id=active_company_id(context), filters=filters)
    _no_store(response)
    return summary_response(record)


@router.get(
    "/finance/intelligence/orders",
    response_model=OrderIntelligenceListResponse,
    summary="Filtered order profitability list",
    description=(
        "Stable descending order-date pagination. Every amount is in the order "
        "currency; incomplete cost coverage remains explicit."
    ),
    responses={422: {"model": ErrorEnvelope, "description": "Invalid filter."}},
)
def intelligence_orders(
    response: Response,
    context: Annotated[
        SessionContext, Depends(require_company_permission(Permission.COMPANY_VIEW))
    ],
    service: Annotated[IntelligenceService, Depends(get_intelligence_service)],
    settings: Annotated[Settings, Depends(app_settings)],
    filters: FiltersDependency,
    limit: Annotated[int | None, Query(ge=1)] = None,
    offset: Annotated[int, Query(ge=0, le=1_000_000)] = 0,
) -> OrderIntelligenceListResponse:
    page = service.orders(
        company_id=active_company_id(context),
        filters=filters,
        limit=resolve_limit(limit, settings),
        offset=offset,
    )
    data_dates = [
        item.facts.data_through
        for item in page.items
        if item.facts.data_through is not None
    ]
    _no_store(response)
    return order_list_response(
        page,
        as_of=filters.to_date,
        data_through=max(data_dates) if data_dates else None,
    )


@router.get(
    "/finance/intelligence/orders/{sales_order_id}",
    response_model=OrderIntelligenceDetailResponse,
    summary="Order profitability, evidence and reconciliation timeline",
    description=(
        "Drill-down over the original accepted sales quote, pricing scenario, "
        "purchase orders, shipment costs, FX snapshots and Stage 5D evidence."
    ),
    responses={404: {"model": ErrorEnvelope, "description": "Unknown order."}},
)
def intelligence_order_detail(
    sales_order_id: UUID,
    response: Response,
    context: Annotated[
        SessionContext, Depends(require_company_permission(Permission.COMPANY_VIEW))
    ],
    service: Annotated[IntelligenceService, Depends(get_intelligence_service)],
) -> OrderIntelligenceDetailResponse:
    record = service.order_detail(
        company_id=active_company_id(context), sales_order_id=sales_order_id
    )
    _no_store(response)
    return detail_response(record)


@router.get(
    "/finance/intelligence/cost-variance",
    response_model=CostVarianceListResponse,
    summary="Estimated versus documented cost variance",
    description=(
        "Returns only orders with a complete estimate and complete documented "
        "basis. Quoted costs and incomplete cases are not presented as variance."
    ),
)
def intelligence_cost_variance(
    response: Response,
    context: Annotated[
        SessionContext, Depends(require_company_permission(Permission.COMPANY_VIEW))
    ],
    service: Annotated[IntelligenceService, Depends(get_intelligence_service)],
    settings: Annotated[Settings, Depends(app_settings)],
    filters: FiltersDependency,
    limit: Annotated[int | None, Query(ge=1)] = None,
    offset: Annotated[int, Query(ge=0, le=1_000_000)] = 0,
) -> CostVarianceListResponse:
    page = service.cost_variance(
        company_id=active_company_id(context),
        filters=filters,
        limit=resolve_limit(limit, settings),
        offset=offset,
    )
    _no_store(response)
    return cost_variance_response(page, as_of=filters.to_date)


@router.get(
    "/finance/intelligence/coverage",
    response_model=CoverageResponse,
    summary="Financial evidence and reconciliation coverage",
)
def intelligence_coverage(
    response: Response,
    context: Annotated[
        SessionContext, Depends(require_company_permission(Permission.COMPANY_VIEW))
    ],
    service: Annotated[IntelligenceService, Depends(get_intelligence_service)],
    filters: FiltersDependency,
) -> CoverageResponse:
    record = service.coverage(
        company_id=active_company_id(context), filters=filters
    )
    _no_store(response)
    return coverage_response(record)


@router.get(
    "/finance/intelligence/exceptions",
    response_model=FinancialExceptionListResponse,
    summary="Enriched financial exception queue",
    description=(
        "Reuses Stage 5D discrepancies and adds the affected order, currency, "
        "source reference, reviewer and last update. Resolution remains the "
        "existing finance.reconcile action."
    ),
)
def intelligence_exceptions(
    response: Response,
    context: Annotated[
        SessionContext, Depends(require_company_permission(Permission.COMPANY_VIEW))
    ],
    service: Annotated[IntelligenceService, Depends(get_intelligence_service)],
    settings: Annotated[Settings, Depends(app_settings)],
    status: Annotated[str | None, Query(max_length=16)] = "OPEN",
    severity: Annotated[str | None, Query(max_length=16)] = None,
    code: Annotated[str | None, Query(max_length=40)] = None,
    currency: Annotated[
        str | None, Query(max_length=3, pattern=r"^[A-Za-z]{3}$")
    ] = None,
    order_id: Annotated[UUID | None, Query()] = None,
    from_date: Annotated[date | None, Query(alias="from")] = None,
    to_date: Annotated[date | None, Query(alias="to")] = None,
    limit: Annotated[int | None, Query(ge=1)] = None,
    offset: Annotated[int, Query(ge=0, le=1_000_000)] = 0,
) -> FinancialExceptionListResponse:
    page = service.exceptions(
        company_id=active_company_id(context),
        status=status,
        severity=severity,
        code=code,
        currency=currency.upper() if currency else None,
        order_id=order_id,
        from_date=from_date,
        to_date=to_date,
        limit=resolve_limit(limit, settings),
        offset=offset,
    )
    _no_store(response)
    return exception_list_response(page)


_EXPORT_NOTICE = (
    "Operational financial analytics only. Not a statutory financial statement, "
    "not accounting profit and not a ledger export."
)


def _csv_safe(value: object) -> str:
    """Escape spreadsheet formula injection without altering ordinary text."""

    if value is None:
        return ""
    text = str(value)
    if text.startswith(("=", "+", "-", "@", "\t", "\r")):
        return f"'{text}"
    return text


def _csv_money(value: object) -> str:
    if value is None:
        return ""
    return str(money(value))  # type: ignore[arg-type]


def _export_csv(
    items: tuple[AnalyzedOrder, ...], *, as_of: date, generated_at: str
) -> bytes:
    columns = (
        "record_type",
        "analysis_label",
        "analysis_notice",
        "calculation_version",
        "generated_at",
        "as_of",
        "data_through",
        "sales_order_id",
        "order_number",
        "customer_name",
        "order_status",
        "fulfilment_model",
        "currency",
        "sales_value",
        "estimated_purchase_cost",
        "estimated_operational_cost",
        "estimated_landed_cost",
        "estimated_vat_cashflow",
        "committed_purchase_cost",
        "quoted_operational_cost",
        "documented_operational_cost",
        "documented_total_cost",
        "estimated_gross_profit",
        "estimated_gross_margin_pct",
        "estimated_markup_pct",
        "committed_gross_profit",
        "committed_gross_margin_pct",
        "committed_markup_pct",
        "cost_variance",
        "cost_variance_pct",
        "estimate_status",
        "committed_status",
        "completeness",
        "missing_components",
        "reconciliation_status",
        "open_discrepancies",
        "blocking_discrepancies",
    )
    buffer = io.StringIO(newline="")
    writer = csv.writer(buffer, lineterminator="\r\n")
    writer.writerow(columns)
    for item in items:
        facts = item.facts
        result = item.result
        # Only text is escaped: a negative amount (a loss) is a number, and
        # prefixing it would turn it into text in a spreadsheet.
        writer.writerow(
            [
                "OPERATIONAL_ANALYSIS_ORDER",
                "TOUCHE COMMERCE operational financial analysis",
                _EXPORT_NOTICE,
                CALCULATION_VERSION,
                generated_at,
                as_of.isoformat(),
                facts.data_through.isoformat() if facts.data_through else "",
                str(facts.sales_order_id),
                _csv_safe(facts.order_number),
                _csv_safe(facts.customer_name),
                _csv_safe(facts.status),
                _csv_safe(facts.fulfilment_model),
                _csv_safe(result.currency),
                str(result.sales_value),
                _csv_money(result.estimated_purchase_cost),
                _csv_money(result.estimated_operational_cost),
                _csv_money(result.estimated_landed_cost),
                _csv_money(result.estimated_vat_cashflow),
                _csv_money(result.committed_purchase_cost),
                _csv_money(result.quoted_operational_cost),
                _csv_money(result.documented_operational_cost),
                _csv_money(result.documented_total_cost),
                _csv_money(result.estimated_gross_profit),
                _csv_money(result.estimated_gross_margin_pct),
                _csv_money(result.estimated_markup_pct),
                _csv_money(result.committed_gross_profit),
                _csv_money(result.committed_gross_margin_pct),
                _csv_money(result.committed_markup_pct),
                _csv_money(result.cost_variance),
                _csv_money(result.cost_variance_pct),
                result.estimate_status.value,
                result.committed_status.value,
                result.completeness.value,
                _csv_safe(";".join(result.missing_components)),
                _csv_safe(facts.reconciliation_status or "NONE"),
                facts.open_discrepancy_count,
                facts.blocking_discrepancy_count,
            ]
        )
    return buffer.getvalue().encode("utf-8")


@router.get(
    "/finance/intelligence/export",
    summary="Export operational financial analysis as CSV",
    description=(
        "Respects the same company scope and filters as the dashboard. Every row "
        "carries its currency, completeness and calculation version. The file is "
        "explicitly not a statutory statement and is protected against formula "
        "injection."
    ),
)
def intelligence_export(
    request: Request,
    context: Annotated[
        SessionContext, Depends(require_company_permission(Permission.COMPANY_VIEW))
    ],
    database: Annotated[Database, Depends(get_database)],
    service: Annotated[IntelligenceService, Depends(get_intelligence_service)],
    filters: FiltersDependency,
) -> FastAPIResponse:
    page = service.orders(
        company_id=active_company_id(context),
        filters=filters,
        limit=MAX_ANALYSIS_ORDERS,
        offset=0,
    )
    generated_at = datetime.now(tz=UTC).isoformat()
    content = _export_csv(page.items, as_of=filters.to_date, generated_at=generated_at)
    with database.transaction() as session:
        apply_company_context(session, active_company_id(context))
        apply_actor_context(session, context.user.user_id)
        record_audit(
            session,
            action=AuditAction.FINANCE_READ,
            outcome=AuditOutcome.SUCCESS,
            actor_id=context.user.user_id,
            company_id=active_company_id(context),
            request_id=get_request_id(),
            ip_address=client_ip(request),
            user_agent=request_user_agent(request),
            resource_type="operational_financial_analysis",
            details={
                "format": "CSV",
                "classification": "OPERATIONAL_ANALYSIS",
                "calculation_version": CALCULATION_VERSION,
                "row_count": len(page.items),
                "from": filters.from_date.isoformat(),
                "to": filters.to_date.isoformat(),
                "currency": filters.currency,
                "completeness": filters.completeness,
                "reconciliation_status": filters.reconciliation_status,
            },
        )
    filename = f"touche-operational-financial-analysis-{filters.to_date:%Y%m%d}.csv"
    return FastAPIResponse(
        content=content,
        media_type="text/csv; charset=utf-8",
        headers={
            "Content-Disposition": f'attachment; filename="{filename}"',
            "Cache-Control": "no-store",
            "Vary": "Cookie",
            "X-Content-Type-Options": "nosniff",
        },
    )

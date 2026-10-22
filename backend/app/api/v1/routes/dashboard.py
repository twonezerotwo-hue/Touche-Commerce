"""Command-center aggregates for the signed-in company."""

from __future__ import annotations

from typing import Annotated

from fastapi import APIRouter, Depends, Response

from app.api.deps import get_database
from app.api.security import active_company_id, require_company_permission
from app.api.v1.presenters_trade import dashboard_response
from app.api.v1.schemas.errors import ErrorEnvelope
from app.api.v1.schemas.trade import DashboardSummaryResponse
from app.db.engine import Database
from app.security.permissions import Permission
from app.services.auth import SessionContext
from app.services.trade import DealService

router = APIRouter(tags=["dashboard"])


@router.get(
    "/dashboard/summary",
    response_model=DashboardSummaryResponse,
    summary="Trade dashboard for the active company",
    description=(
        "Deal counts by status, open pipeline per currency, catalogue/CRM totals and "
        "the most recent deals and audit activity. All values come from the database "
        "in one transaction; nothing is inferred in the browser."
    ),
    responses={
        200: {"description": "Dashboard snapshot."},
        403: {"model": ErrorEnvelope, "description": "No active company or permission."},
    },
)
def dashboard_summary(
    response: Response,
    context: Annotated[
        SessionContext, Depends(require_company_permission(Permission.COMPANY_VIEW))
    ],
    database: Annotated[Database, Depends(get_database)],
) -> DashboardSummaryResponse:
    company_id = active_company_id(context)
    summary = DealService(database).dashboard(company_id=company_id)
    response.headers["Cache-Control"] = "no-store"
    response.headers["Vary"] = "Cookie"
    return dashboard_response(summary, company_id=company_id)


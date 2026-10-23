"""Finance integration status (Stage 5A, read-only).

This is the only HTTP surface that talks about TOUCHE FINANCE.  It requires an
authenticated Commerce session, calls Finance's public health endpoint at most
once per request, and exposes no business data.  There is deliberately no
endpoint that posts an invoice, payment or ledger entry.
"""

from __future__ import annotations

from typing import Annotated

from fastapi import APIRouter, Depends, Response

from app.api.deps import app_settings
from app.api.security import current_session, require_company_permission
from app.api.v1.schemas.errors import ErrorEnvelope
from app.api.v1.schemas.integrations import FinanceLinkStatusResponse
from app.core.config import Settings
from app.integrations.eyay import EyayMarketPreview, market_preview
from app.integrations.finance.service import FinanceIntegrationService
from app.security.permissions import Permission
from app.services.auth import SessionContext

router = APIRouter(tags=["integrations"])


@router.get(
    "/integrations/finance/status",
    response_model=FinanceLinkStatusResponse,
    summary="Read-only TOUCHE FINANCE link status",
    description=(
        "Probes the locally configured Finance `GET /api/health` endpoint and "
        "reports whether Commerce can reach it. It never calls a business "
        "endpoint, never sends Finance a session or identity header, and never "
        "creates an invoice, payment or ledger entry."
    ),
    responses={
        200: {"description": "The probe completed (including unreachable states)."},
        401: {"model": ErrorEnvelope, "description": "No authenticated Commerce session."},
    },
)
def finance_link_status(
    settings: Annotated[Settings, Depends(app_settings)],
    _context: Annotated[SessionContext, Depends(current_session)],
) -> FinanceLinkStatusResponse:
    health = FinanceIntegrationService(settings).status()
    return FinanceLinkStatusResponse(
        state=health.state,
        finance_status=health.finance_status,
        latency_ms=health.latency_ms,
        detail=health.detail,
        checked_at=health.checked_at,
    )


@router.get(
    "/integrations/eyay/market",
    response_model=EyayMarketPreview,
    summary="E-YAY read-only source market context (never executes orders)",
)
def eyay_market_context(
    response: Response,
    settings: Annotated[Settings, Depends(app_settings)],
    _context: Annotated[
        SessionContext,
        Depends(require_company_permission(Permission.COMPANY_VIEW)),
    ],
) -> EyayMarketPreview:
    response.headers["Cache-Control"] = "no-store"
    response.headers["Vary"] = "Cookie"
    return market_preview(
        enabled=settings.eyay_enabled,
        base_url=settings.eyay_base_url,
        timeout=settings.eyay_timeout_seconds,
        max_response_bytes=settings.eyay_max_response_bytes,
    )

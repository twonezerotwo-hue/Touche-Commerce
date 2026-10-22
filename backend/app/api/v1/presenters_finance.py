"""Finance result → API response mapping (no financial calculations here)."""

from __future__ import annotations

from typing import Any

from app.api.v1.schemas.finance import (
    FinanceAccountsResponse,
    FinanceAgingResponse,
    FinanceCapabilitiesResponse,
    FinanceMapping,
    FinanceStatusResponse,
    FinanceSummaryResponse,
)
from app.integrations.finance.connector import FinanceConnectionStatus, FinanceResult


def status_response(status: FinanceConnectionStatus) -> FinanceStatusResponse:
    mapping = None
    if status.mapping is not None:
        mapping = FinanceMapping(
            finance_company_id=status.mapping.finance_company_id,
            finance_company_name=status.mapping.finance_company_name,
            status=status.mapping.status,
            configured_at=status.mapping.configured_at,
            last_verified_at=status.mapping.last_verified_at,
        )
    return FinanceStatusResponse(
        state=status.state,
        detail=status.detail,
        checked_at=status.checked_at,
        latency_ms=status.latency_ms,
        mapping=mapping,
        finance_status=status.finance_status,
        available_currencies=list(status.available_currencies),
        data_through=status.data_through,
        finance_request_id=status.finance_request_id,
    )


def _with_meta(result: FinanceResult, data: dict[str, Any]) -> dict[str, Any]:
    return {
        **data,
        "finance_request_id": result.request_id,
        "fetched_at": result.fetched_at,
    }


def capabilities_response(result: FinanceResult) -> FinanceCapabilitiesResponse:
    return FinanceCapabilitiesResponse.model_validate(_with_meta(result, result.data))


def summary_response(result: FinanceResult) -> FinanceSummaryResponse:
    return FinanceSummaryResponse.model_validate(_with_meta(result, result.data))


def accounts_response(result: FinanceResult) -> FinanceAccountsResponse:
    return FinanceAccountsResponse.model_validate(_with_meta(result, result.data))


def aging_response(result: FinanceResult) -> FinanceAgingResponse:
    return FinanceAgingResponse.model_validate(_with_meta(result, result.data))

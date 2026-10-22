"""Authenticated, read-only Finance integration (Stage 5C).

Every endpoint resolves the Finance company from the *active Commerce company's*
explicit mapping. Callers cannot submit a Finance company id, credentials or URL.
The connector only performs GET requests through the verified Finance v1
contract; no invoice, payment or journal write path exists.
"""

from __future__ import annotations

from collections.abc import Callable
from datetime import date
from typing import Annotated, Literal

from fastapi import APIRouter, Depends, Query, Request, Response
from sqlalchemy.exc import SQLAlchemyError

from app.api.deps import app_settings, get_database
from app.api.security import (
    active_company_id,
    client_ip,
    request_user_agent,
    require_company_permission,
)
from app.api.v1.presenters_finance import (
    accounts_response,
    aging_response,
    capabilities_response,
    status_response,
    summary_response,
)
from app.api.v1.schemas.errors import ErrorEnvelope
from app.api.v1.schemas.finance import (
    FinanceAccountsResponse,
    FinanceAgingResponse,
    FinanceCapabilitiesResponse,
    FinanceStatusResponse,
    FinanceSummaryResponse,
)
from app.core.config import Settings
from app.core.context import get_request_id
from app.core.errors import ApiError, BadRequestError, FinanceAuditUnavailableError
from app.db.engine import Database
from app.db.models import AuditAction, AuditOutcome
from app.db.tenant import apply_actor_context, apply_company_context
from app.integrations.finance.connector import (
    FinanceConnector,
    FinanceMappingSnapshot,
    FinanceResult,
)
from app.security.permissions import Permission
from app.services.audit import record_audit
from app.services.auth import SessionContext
from app.services.finance_mapping import load_mapping, snapshot

router = APIRouter(tags=["finance"])

def _mapping_for(database: Database, context: SessionContext) -> FinanceMappingSnapshot | None:
    company_id = active_company_id(context)
    with database.transaction() as session:
        apply_company_context(session, company_id)
        apply_actor_context(session, context.user.user_id)
        return snapshot(load_mapping(session, company_id))


def _write_audit(
    database: Database,
    context: SessionContext,
    *,
    outcome: AuditOutcome,
    endpoint: str,
    mapping: FinanceMappingSnapshot | None,
    details: dict[str, object],
    ip_address: str | None,
    user_agent: str | None,
) -> None:
    company_id = active_company_id(context)
    audit_details: dict[str, object] = dict(details)
    if mapping is not None:
        audit_details.setdefault("finance_company_id", mapping.finance_company_id)
    with database.transaction() as session:
        apply_company_context(session, company_id)
        apply_actor_context(session, context.user.user_id)
        record_audit(
            session,
            action=AuditAction.FINANCE_READ,
            outcome=outcome,
            actor_id=context.user.user_id,
            company_id=company_id,
            request_id=get_request_id(),
            ip_address=ip_address,
            user_agent=user_agent,
            resource_type="finance_ledger",
            resource_id=mapping.finance_company_id if mapping else None,
            details={"endpoint": endpoint, **audit_details},
        )


def _audit_success(
    database: Database,
    context: SessionContext,
    *,
    endpoint: str,
    mapping: FinanceMappingSnapshot | None,
    details: dict[str, object],
    request: Request,
) -> None:
    try:
        _write_audit(
            database,
            context,
            outcome=AuditOutcome.SUCCESS,
            endpoint=endpoint,
            mapping=mapping,
            details=details,
            ip_address=client_ip(request),
            user_agent=request_user_agent(request),
        )
    except SQLAlchemyError as exc:
        raise FinanceAuditUnavailableError() from exc


def _audit_failure(
    database: Database,
    context: SessionContext,
    *,
    endpoint: str,
    mapping: FinanceMappingSnapshot | None,
    error: ApiError,
    request: Request,
) -> None:
    outcome = AuditOutcome.DENIED if error.status_code in {401, 403, 409} else AuditOutcome.FAILURE
    details: dict[str, object] = {"commerce_code": str(error.code)}
    raw_details = error.details if isinstance(error.details, dict) else {}
    finance_code = raw_details.get("finance_code")
    if isinstance(finance_code, str):
        details["finance_code"] = finance_code[:64]
    try:
        _write_audit(
            database,
            context,
            outcome=outcome,
            endpoint=endpoint,
            mapping=mapping,
            details=details,
            ip_address=client_ip(request),
            user_agent=request_user_agent(request),
        )
    except Exception:
        return


def _no_store(response: Response) -> None:
    response.headers["Cache-Control"] = "no-store"
    response.headers["Vary"] = "Cookie"


def _run_data_read(
    *,
    request: Request,
    context: SessionContext,
    database: Database,
    settings: Settings,
    endpoint: str,
    operation: str,
    call: Callable[
        [FinanceConnector, FinanceMappingSnapshot | None], FinanceResult
    ],
    extra_details: dict[str, object] | None = None,
) -> FinanceResult:
    mapping = _mapping_for(database, context)
    try:
        result = call(FinanceConnector(settings), mapping)
    except ApiError as exc:
        _audit_failure(
            database,
            context,
            endpoint=endpoint,
            mapping=mapping,
            error=exc,
            request=request,
        )
        raise
    _audit_success(
        database,
        context,
        endpoint=endpoint,
        mapping=mapping,
        details={"operation": operation, **dict(extra_details or {})},
        request=request,
    )
    return result


@router.get(
    "/finance/status",
    response_model=FinanceStatusResponse,
    summary="Read-only Finance integration status for the active company",
    description=(
        "Resolves the active Commerce company's explicit Finance mapping, verifies "
        "it against Finance capabilities and the authorized company list, and "
        "reports NOT_CONFIGURED / CONNECTED / DEGRADED / UNAVAILABLE / AUTH_ERROR. "
        "No credentials are returned."
    ),
    responses={
        401: {"model": ErrorEnvelope, "description": "No authenticated Commerce session."},
        403: {"model": ErrorEnvelope, "description": "No active membership or company.view."},
    },
)
def get_finance_status(
    request: Request,
    response: Response,
    context: Annotated[
        SessionContext, Depends(require_company_permission(Permission.COMPANY_VIEW))
    ],
    database: Annotated[Database, Depends(get_database)],
    settings: Annotated[Settings, Depends(app_settings)],
) -> FinanceStatusResponse:
    mapping = _mapping_for(database, context)
    try:
        status = FinanceConnector(settings).status(mapping)
    except ApiError as exc:
        _audit_failure(
            database,
            context,
            endpoint="/finance/status",
            mapping=mapping,
            error=exc,
            request=request,
        )
        raise
    _audit_success(
        database,
        context,
        endpoint="/finance/status",
        mapping=mapping,
        details={"operation": "status", "state": str(status.state)},
        request=request,
    )
    _no_store(response)
    return status_response(status)


@router.get(
    "/finance/capabilities",
    response_model=FinanceCapabilitiesResponse,
    summary="Verified Finance capabilities for the mapped company",
    description=(
        "Returns only the mapped Finance company's capabilities. The Finance key's "
        "other authorized company ids are deliberately not exposed."
    ),
    responses={
        409: {"model": ErrorEnvelope, "description": "Mapping missing, disabled or rejected."},
        502: {"model": ErrorEnvelope, "description": "Finance authentication/protocol failure."},
        503: {
            "model": ErrorEnvelope,
            "description": "Finance unavailable or integration disabled.",
        },
    },
)
def get_finance_capabilities(
    request: Request,
    response: Response,
    context: Annotated[
        SessionContext, Depends(require_company_permission(Permission.COMPANY_VIEW))
    ],
    database: Annotated[Database, Depends(get_database)],
    settings: Annotated[Settings, Depends(app_settings)],
) -> FinanceCapabilitiesResponse:
    result = _run_data_read(
        request=request,
        context=context,
        database=database,
        settings=settings,
        endpoint="/finance/capabilities",
        operation="capabilities",
        call=lambda connector, mapping: connector.capabilities(mapping),
    )
    _no_store(response)
    return capabilities_response(result)


@router.get(
    "/finance/summary",
    response_model=FinanceSummaryResponse,
    summary="Finance ledger summary for the mapped company and one currency",
    description=(
        "Balances come from Finance's existing engine. A multi-currency company "
        "requires an explicit currency; amounts are never converted or aggregated."
    ),
    responses={
        409: {"model": ErrorEnvelope, "description": "Mapping or explicit currency required."},
        502: {"model": ErrorEnvelope, "description": "Finance authentication/protocol failure."},
        503: {
            "model": ErrorEnvelope,
            "description": "Finance unavailable or integration disabled.",
        },
    },
)
def get_finance_summary(
    request: Request,
    response: Response,
    context: Annotated[
        SessionContext, Depends(require_company_permission(Permission.COMPANY_VIEW))
    ],
    database: Annotated[Database, Depends(get_database)],
    settings: Annotated[Settings, Depends(app_settings)],
    currency: Annotated[
        str | None, Query(max_length=3, pattern=r"^[A-Za-z]{2,3}$")
    ] = None,
) -> FinanceSummaryResponse:
    result = _run_data_read(
        request=request,
        context=context,
        database=database,
        settings=settings,
        endpoint="/finance/summary",
        operation="summary",
        call=lambda connector, mapping: connector.summary(mapping, currency=currency),
        extra_details={"currency": currency.upper() if currency else None},
    )
    _no_store(response)
    return summary_response(result)




@router.get(
    "/finance/accounts",
    response_model=FinanceAccountsResponse,
    summary="Finance account balances for the mapped company",
    description=(
        "Account-level debit, credit and balance for an explicit date range and "
        "currency. Amounts and Finance's debit-minus-credit sign are preserved."
    ),
    responses={
        400: {"model": ErrorEnvelope, "description": "Invalid currency or date range."},
        409: {"model": ErrorEnvelope, "description": "Mapping or explicit currency required."},
        502: {"model": ErrorEnvelope, "description": "Finance authentication/protocol failure."},
        503: {
            "model": ErrorEnvelope,
            "description": "Finance unavailable or integration disabled.",
        },
    },
)
def get_finance_accounts(
    request: Request,
    response: Response,
    context: Annotated[
        SessionContext, Depends(require_company_permission(Permission.COMPANY_VIEW))
    ],
    database: Annotated[Database, Depends(get_database)],
    settings: Annotated[Settings, Depends(app_settings)],
    currency: Annotated[
        str | None, Query(max_length=3, pattern=r"^[A-Za-z]{2,3}$")
    ] = None,
    from_date: Annotated[date | None, Query(alias="from")] = None,
    to_date: Annotated[date | None, Query(alias="to")] = None,
    as_of: Annotated[date | None, Query()] = None,
    limit: Annotated[int | None, Query(ge=1, le=200)] = None,
    offset: Annotated[int, Query(ge=0, le=1_000_000)] = 0,
) -> FinanceAccountsResponse:
    effective_to = to_date or as_of
    if to_date is not None and as_of is not None and to_date != as_of:
        raise BadRequestError("Use either 'to' or 'as_of', not two different dates.")
    if from_date is not None and effective_to is not None and from_date > effective_to:
        raise BadRequestError("'from' must not be later than 'to'/'as_of'.")
    result = _run_data_read(
        request=request,
        context=context,
        database=database,
        settings=settings,
        endpoint="/finance/accounts",
        operation="accounts",
        call=lambda connector, mapping: connector.accounts(
            mapping,
            currency=currency,
            from_date=from_date.isoformat() if from_date else None,
            to_date=effective_to.isoformat() if effective_to else None,
            limit=limit,
            offset=offset,
        ),
        extra_details={
            "currency": currency.upper() if currency else None,
            "from": from_date.isoformat() if from_date else None,
            "to": effective_to.isoformat() if effective_to else None,
            "offset": offset,
        },
    )
    _no_store(response)
    return accounts_response(result)


@router.get(
    "/finance/aging",
    response_model=FinanceAgingResponse,
    summary="Finance receivable or payable FIFO aging",
    description=(
        "FIFO aging with Finance's documented buckets and open fis_id source items. "
        "Counterparty names are free text and are not treated as stable master keys."
    ),
    responses={
        400: {"model": ErrorEnvelope, "description": "Invalid type, currency or date."},
        409: {"model": ErrorEnvelope, "description": "Mapping or explicit currency required."},
        502: {"model": ErrorEnvelope, "description": "Finance authentication/protocol failure."},
        503: {
            "model": ErrorEnvelope,
            "description": "Finance unavailable or integration disabled.",
        },
    },
)
def get_finance_aging(
    request: Request,
    response: Response,
    context: Annotated[
        SessionContext, Depends(require_company_permission(Permission.COMPANY_VIEW))
    ],
    database: Annotated[Database, Depends(get_database)],
    settings: Annotated[Settings, Depends(app_settings)],
    kind: Annotated[Literal["receivable", "payable"], Query(alias="type")],
    currency: Annotated[
        str | None, Query(max_length=3, pattern=r"^[A-Za-z]{2,3}$")
    ] = None,
    as_of: Annotated[date | None, Query()] = None,
    limit: Annotated[int | None, Query(ge=1, le=200)] = None,
    offset: Annotated[int, Query(ge=0, le=1_000_000)] = 0,
) -> FinanceAgingResponse:
    result = _run_data_read(
        request=request,
        context=context,
        database=database,
        settings=settings,
        endpoint="/finance/aging",
        operation="aging",
        call=lambda connector, mapping: connector.aging(
            mapping,
            kind=kind,
            currency=currency,
            as_of=as_of.isoformat() if as_of else None,
            limit=limit,
            offset=offset,
        ),
        extra_details={
            "type": kind,
            "currency": currency.upper() if currency else None,
            "as_of": as_of.isoformat() if as_of else None,
            "offset": offset,
        },
    )
    _no_store(response)
    return aging_response(result)

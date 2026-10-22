"""Authenticated, read-only Stage 5C Finance connector.

The connector owns no accounting logic. It verifies the explicit company mapping
against Finance's own capability/company lists, chooses exactly one currency, and
passes Finance's source amounts through unchanged. Every failure is translated to
a Commerce error that preserves the original Finance category in
``details.finance_code`` without exposing credentials.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import UTC, datetime
from enum import StrEnum
from time import perf_counter
from typing import Any, Protocol

from app.core.config import Settings
from app.core.errors import (
    ApiError,
    FinanceAuditUnavailableError,
    FinanceAuthError,
    FinanceCompanyDeniedError,
    FinanceCurrencyRequiredError,
    FinanceIntegrationDisabledError,
    FinanceInvalidCurrencyError,
    FinanceMappingDisabledError,
    FinanceMappingUnverifiedError,
    FinanceNotConfiguredError,
    FinanceProtocolError,
    FinanceUnavailableError,
)
from app.integrations.finance.client import FinanceClientError, FinanceIntegrationClient
from app.integrations.finance.contracts import FinanceApiResponse


class FinanceConnectionState(StrEnum):
    """UI/API states for the read-only Finance link."""

    NOT_CONFIGURED = "not_configured"
    DISABLED = "disabled"
    CONNECTED = "connected"
    DEGRADED = "degraded"
    UNAVAILABLE = "unavailable"
    AUTH_ERROR = "auth_error"


@dataclass(frozen=True, slots=True)
class FinanceMappingSnapshot:
    """Detached mapping values; secrets are never part of this object."""

    finance_company_id: str
    finance_company_name: str | None
    status: str
    configured_at: datetime | None
    last_verified_at: datetime | None


@dataclass(frozen=True, slots=True)
class FinanceConnectionStatus:
    state: FinanceConnectionState
    detail: str
    checked_at: datetime
    latency_ms: float
    mapping: FinanceMappingSnapshot | None
    finance_status: str | None = None
    available_currencies: tuple[str, ...] = ()
    data_through: str | None = None
    finance_request_id: str | None = None


@dataclass(frozen=True, slots=True)
class FinanceResult:
    data: dict[str, Any]
    request_id: str | None = None
    fetched_at: datetime = field(default_factory=lambda: datetime.now(tz=UTC))


class FinanceReadClient(Protocol):
    """The subset of client calls used by the connector (easy to fake in tests)."""

    def health(self) -> FinanceApiResponse: ...

    def capabilities(self) -> FinanceApiResponse: ...

    def companies(self) -> FinanceApiResponse: ...

    def summary(self, company_id: str, *, currency: str | None = None) -> FinanceApiResponse: ...

    def accounts(
        self,
        company_id: str,
        *,
        currency: str | None = None,
        from_date: str | None = None,
        to_date: str | None = None,
        limit: int | None = None,
        offset: int | None = None,
    ) -> FinanceApiResponse: ...

    def aging(
        self,
        company_id: str,
        *,
        kind: str,
        currency: str | None = None,
        as_of: str | None = None,
        limit: int | None = None,
        offset: int | None = None,
    ) -> FinanceApiResponse: ...


class FinanceConnector:
    """Read-only service facade for one explicitly mapped Finance company."""

    def __init__(
        self,
        settings: Settings,
        *,
        client: FinanceReadClient | None = None,
    ) -> None:
        self._settings = settings
        self._client_override = client

    # --- Connection status -------------------------------------------------
    def status(self, mapping: FinanceMappingSnapshot | None) -> FinanceConnectionStatus:
        checked_at = datetime.now(tz=UTC)
        started = perf_counter()
        if mapping is None:
            return self._status(
                FinanceConnectionState.NOT_CONFIGURED,
                "No Finance company mapping is configured for this Commerce company.",
                checked_at,
                started,
                mapping,
            )
        if not self._settings.finance_integration_enabled:
            return self._status(
                FinanceConnectionState.DISABLED,
                "Finance integration is disabled by configuration.",
                checked_at,
                started,
                mapping,
            )
        if mapping.status == "disabled":
            return self._status(
                FinanceConnectionState.DISABLED,
                "The Finance company mapping is disabled.",
                checked_at,
                started,
                mapping,
            )
        if mapping.status != "verified":
            return self._status(
                FinanceConnectionState.DEGRADED,
                "The Finance company mapping exists but is not verified.",
                checked_at,
                started,
                mapping,
            )

        try:
            client = self._client()
            health_response = client.health()
            health = health_response.data
            capabilities = client.capabilities().data
            company = self._validated_company(
                mapping.finance_company_id, capabilities, client.companies().data
            )
        except FinanceClientError as exc:
            state = (
                FinanceConnectionState.AUTH_ERROR
                if self._is_auth_failure(exc.category)
                else FinanceConnectionState.UNAVAILABLE
            )
            return self._status(state, exc.category, checked_at, started, mapping)
        except ApiError as exc:
            return self._status(
                FinanceConnectionState.AUTH_ERROR,
                str(exc.code),
                checked_at,
                started,
                mapping,
            )

        finance_status = str(health.get("status") or "")
        state = (
            FinanceConnectionState.CONNECTED
            if finance_status == "ok"
            else FinanceConnectionState.DEGRADED
        )
        return self._status(
            state,
            (
                "Finance reports a consistent ledger."
                if state is FinanceConnectionState.CONNECTED
                else "Finance reports degraded recovery or ledger consistency."
            ),
            checked_at,
            started,
            mapping,
            finance_status=finance_status or None,
            available_currencies=_currencies(company),
            data_through=_optional_str(company.get("data_through")),
            finance_request_id=health_response.request_id,
        )

    # --- Read operations ---------------------------------------------------
    def capabilities(self, mapping: FinanceMappingSnapshot | None) -> FinanceResult:
        _client, company, capabilities, capabilities_meta = self._resolve(mapping)
        return FinanceResult(
            data={
                "finance_company_id": str(company.get("id") or ""),
                "company_name": str(company.get("name") or ""),
                "contract_version": str(capabilities.get("contract_version") or "1"),
                "scopes": list(capabilities.get("scopes") or []),
                "max_page": int(capabilities.get("max_page") or 200),
                "endpoints": list(capabilities.get("endpoints") or []),
                "currency_support": dict(capabilities.get("currency_support") or {}),
                "unsupported": list(capabilities.get("unsupported") or []),
                "limitations": list(capabilities.get("limitations") or []),
                "available_currencies": _currencies(company),
                "data_through": _optional_str(company.get("data_through")),
                "source": "finance_ledger",
            },
            request_id=capabilities_meta.request_id,
            fetched_at=_parse_timestamp(capabilities_meta.generated_at),
        )


    def summary(
        self,
        mapping: FinanceMappingSnapshot | None,
        *,
        currency: str | None = None,
    ) -> FinanceResult:
        client, company, _capabilities, _meta = self._resolve(mapping)
        selected = self._select_currency(company, currency)
        response = client.summary(
            mapping.finance_company_id if mapping is not None else "",
            currency=selected,
        )
        return FinanceResult(
            data=dict(response.data),
            request_id=response.request_id,
            fetched_at=_parse_timestamp(response.generated_at),
        )

    def accounts(
        self,
        mapping: FinanceMappingSnapshot | None,
        *,
        currency: str | None = None,
        from_date: str | None = None,
        to_date: str | None = None,
        limit: int | None = None,
        offset: int | None = None,
    ) -> FinanceResult:
        client, company, _capabilities, _meta = self._resolve(mapping)
        selected = self._select_currency(company, currency)
        response = client.accounts(
            mapping.finance_company_id if mapping is not None else "",
            currency=selected,
            from_date=from_date,
            to_date=to_date,
            limit=limit,
            offset=offset,
        )
        data = dict(response.data)
        if "from" in data:
            data["from_date"] = data.pop("from")
        return FinanceResult(
            data=data,
            request_id=response.request_id,
            fetched_at=_parse_timestamp(response.generated_at),
        )

    def aging(
        self,
        mapping: FinanceMappingSnapshot | None,
        *,
        kind: str,
        currency: str | None = None,
        as_of: str | None = None,
        limit: int | None = None,
        offset: int | None = None,
    ) -> FinanceResult:
        client, company, _capabilities, _meta = self._resolve(mapping)
        selected = self._select_currency(company, currency)
        response = client.aging(
            mapping.finance_company_id if mapping is not None else "",
            kind=kind,
            currency=selected,
            as_of=as_of,
            limit=limit,
            offset=offset,
        )
        return FinanceResult(
            data=dict(response.data),
            request_id=response.request_id,
            fetched_at=_parse_timestamp(response.generated_at),
        )

    def inspect_company(self, finance_company_id: str) -> tuple[dict[str, Any], dict[str, Any]]:
        """Verify one explicit Finance company for CLI configuration."""
        client = self._client()
        try:
            capabilities = client.capabilities().data
            company = self._validated_company(
                finance_company_id, capabilities, client.companies().data
            )
        except FinanceClientError as exc:
            raise _translate(exc) from exc
        return company, capabilities


    # --- Internals ---------------------------------------------------------
    def _client(self) -> FinanceReadClient:
        if not self._settings.finance_integration_enabled:
            raise FinanceIntegrationDisabledError()
        if self._client_override is not None:
            return self._client_override
        key_id = (
            self._settings.finance_integration_key_id.get_secret_value()
            if self._settings.finance_integration_key_id
            else ""
        )
        secret = (
            self._settings.finance_integration_secret.get_secret_value()
            if self._settings.finance_integration_secret
            else ""
        )
        if not key_id or not secret:
            raise FinanceAuthError(
                "Finance service credentials are not configured.",
                details={"finance_code": "MISSING_CREDENTIALS"},
            )
        return FinanceIntegrationClient(
            base_url=self._settings.finance_integration_base_url,
            key_id=key_id,
            secret=secret,
            timeout_seconds=self._settings.finance_integration_timeout_seconds,
            max_response_bytes=self._settings.finance_integration_max_response_bytes,
        )

    def _resolve(
        self, mapping: FinanceMappingSnapshot | None
    ) -> tuple[FinanceReadClient, dict[str, Any], dict[str, Any], FinanceApiResponse]:
        if mapping is None:
            raise FinanceNotConfiguredError()
        if mapping.status == "disabled":
            raise FinanceMappingDisabledError()
        if mapping.status != "verified":
            raise FinanceMappingUnverifiedError(details={"mapping_status": mapping.status})
        client = self._client()
        try:
            capabilities_response = client.capabilities()
            companies_response = client.companies()
        except FinanceClientError as exc:
            raise _translate(exc) from exc
        capabilities = capabilities_response.data
        company = self._validated_company(
            mapping.finance_company_id, capabilities, companies_response.data
        )
        return client, company, capabilities, capabilities_response

    @staticmethod
    def _validated_company(
        finance_company_id: str,
        capabilities: dict[str, Any],
        companies_payload: dict[str, Any],
    ) -> dict[str, Any]:
        if capabilities.get("read_only") is not True:
            raise FinanceProtocolError(
                "Finance did not declare the integration read-only.",
                details={"finance_code": "READ_ONLY_CONTRACT_REQUIRED"},
            )
        scopes = capabilities.get("scopes")
        if not isinstance(scopes, list) or "finance.read" not in scopes:
            raise FinanceAuthError(
                "The Finance service key does not carry finance.read.",
                details={"finance_code": "SCOPE_DENIED"},
            )
        authorized = capabilities.get("company_ids")
        if not isinstance(authorized, list) or finance_company_id not in authorized:
            raise FinanceCompanyDeniedError(
                "The mapped Finance company is not listed for this service key.",
                details={"finance_code": "COMPANY_DENIED"},
            )
        companies = companies_payload.get("companies")
        if not isinstance(companies, list):
            raise FinanceProtocolError(
                "Finance returned an invalid company list.",
                details={"finance_code": "INVALID_RESPONSE"},
            )
        for company in companies:
            if isinstance(company, dict) and str(company.get("id")) == finance_company_id:
                if company.get("active") is not True:
                    raise FinanceCompanyDeniedError(
                        "The mapped Finance company is not active.",
                        details={"finance_code": "COMPANY_INACTIVE"},
                    )
                return company
        raise FinanceCompanyDeniedError(
            "The mapped Finance company was not returned by Finance.",
            details={"finance_code": "COMPANY_DENIED"},
        )


    @staticmethod
    def _select_currency(company: dict[str, Any], requested: str | None) -> str | None:
        available = _currencies(company)
        selected = (requested or "").strip().upper()
        if selected:
            if available and selected not in available:
                raise FinanceInvalidCurrencyError(
                    details={
                        "finance_code": "INVALID_CURRENCY",
                        "available_currencies": list(available),
                    }
                )
            return selected
        if len(available) > 1:
            raise FinanceCurrencyRequiredError(
                details={
                    "finance_code": "CURRENCY_REQUIRED",
                    "available_currencies": list(available),
                }
            )
        return available[0] if available else None

    @staticmethod
    def _is_auth_failure(category: str) -> bool:
        return category in {
            "MISSING_CREDENTIALS",
            "INVALID_CREDENTIALS",
            "SCOPE_DENIED",
            "COMPANY_DENIED",
            "COMPANY_INACTIVE",
            "CONFIGURATION_INVALID",
        }

    @staticmethod
    def _status(
        state: FinanceConnectionState,
        detail: str,
        checked_at: datetime,
        started: float,
        mapping: FinanceMappingSnapshot | None,
        *,
        finance_status: str | None = None,
        available_currencies: tuple[str, ...] = (),
        data_through: str | None = None,
        finance_request_id: str | None = None,
    ) -> FinanceConnectionStatus:
        return FinanceConnectionStatus(
            state=state,
            detail=detail,
            checked_at=checked_at,
            latency_ms=round((perf_counter() - started) * 1000, 2),
            mapping=mapping,
            finance_status=finance_status,
            available_currencies=available_currencies,
            data_through=data_through,
            finance_request_id=finance_request_id,
        )



def _translate(exc: FinanceClientError) -> ApiError:
    details: dict[str, Any] = {"finance_code": exc.category}
    if exc.request_id:
        details["finance_request_id"] = exc.request_id
    if exc.status_code is not None:
        details["finance_http_status"] = exc.status_code
    available = exc.details.get("available_currencies")
    if isinstance(available, list):
        details["available_currencies"] = available
    if exc.category in {
        "MISSING_CREDENTIALS",
        "INVALID_CREDENTIALS",
        "SCOPE_DENIED",
        "AUTH_UNAVAILABLE",
        "CONFIGURATION_INVALID",
    }:
        return FinanceAuthError(details=details)
    if exc.category in {"COMPANY_DENIED", "COMPANY_NOT_FOUND", "COMPANY_INACTIVE"}:
        return FinanceCompanyDeniedError(details=details)
    if exc.category == "CURRENCY_REQUIRED":
        return FinanceCurrencyRequiredError(details=details)
    if exc.category == "INVALID_CURRENCY":
        return FinanceInvalidCurrencyError(details=details)
    if exc.category == "INTEGRATION_DISABLED":
        return FinanceIntegrationDisabledError(details=details)
    if exc.category == "AUDIT_UNAVAILABLE":
        return FinanceAuditUnavailableError(details=details)
    if exc.category in {"TIMEOUT", "UNREACHABLE", "LEDGER_UNAVAILABLE"}:
        return FinanceUnavailableError(details=details)
    return FinanceProtocolError(details=details)


def _currencies(company: dict[str, Any]) -> tuple[str, ...]:
    values = company.get("currencies")
    if not isinstance(values, list):
        return ()
    return tuple(str(value).upper() for value in values if str(value).strip())


def _optional_str(value: Any) -> str | None:
    return str(value) if value not in (None, "") else None


def _parse_timestamp(value: str | None) -> datetime:
    if value:
        try:
            return datetime.fromisoformat(value.replace("Z", "+00:00"))
        except ValueError:
            pass
    return datetime.now(tz=UTC)

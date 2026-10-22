"""Unit tests for the Stage 5C Finance client and connector contract.

No database, no Finance code and no live Finance process is used here. A local
stub server proves the authenticated HTTP shape; a fake client proves mapping,
currency and error semantics without network timing.
"""

from __future__ import annotations

import threading
import time
from collections.abc import Iterator
from dataclasses import dataclass
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from typing import Any, ClassVar

import pytest
from pydantic import SecretStr

from app.core.config import Settings
from app.core.errors import (
    FinanceAuthError,
    FinanceCompanyDeniedError,
    FinanceCurrencyRequiredError,
    FinanceInvalidCurrencyError,
    FinanceMappingDisabledError,
    FinanceMappingUnverifiedError,
    FinanceProtocolError,
    FinanceUnavailableError,
)
from app.integrations.finance.client import FinanceClientError, FinanceIntegrationClient
from app.integrations.finance.connector import (
    FinanceConnectionState,
    FinanceConnector,
    FinanceMappingSnapshot,
)
from app.integrations.finance.contracts import FinanceApiResponse


def _settings(**overrides: object) -> Settings:
    values: dict[str, object] = {
        "environment": "test",
        "database_url": None,
        "database_migration_url": None,
        "_env_file": None,
        "finance_integration_enabled": True,
        "finance_integration_base_url": "http://127.0.0.1:8765",
        "finance_integration_key_id": SecretStr("key_0123456789abcdef"),
        "finance_integration_secret": SecretStr("s" * 43),
        "finance_integration_timeout_seconds": 0.5,
    }
    values.update(overrides)
    return Settings(**values)  # type: ignore[arg-type]


def _capabilities(company_ids: list[str] | None = None) -> dict[str, Any]:
    return {
        "contract_version": "1",
        "enabled": True,
        "read_only": True,
        "scopes": ["finance.read"],
        "company_ids": company_ids or ["gursar_mimarlik"],
        "max_page": 200,
        "endpoints": ["GET /api/integration/v1/health"],
        "currency_support": {
            "mode": "per_request",
            "available": ["EUR", "TL", "USD"],
            "aggregation": False,
            "conversion": False,
        },
        "limitations": ["counterparties are free text"],
        "unsupported": ["journal writes", "invoice posting", "payment initiation"],
    }


def _company(
    company_id: str = "gursar_mimarlik",
    *,
    currencies: list[str] | None = None,
    active: bool = True,
) -> dict[str, Any]:
    resolved = currencies or ["TL"]
    return {
        "id": company_id,
        "name": "GÃ¼rsar MimarlÄ±k",
        "holding_id": "touche_holding",
        "active": active,
        "currency": resolved[0] if len(resolved) == 1 else None,
        "currencies": resolved,
        "multi_currency": len(resolved) > 1,
        "data_through": "2026-10-20",
    }


def _money(amount: str) -> dict[str, Any]:
    return {"amount": amount, "amount_kurus": round(float(amount) * 100)}


def _summary(currency: str = "TL") -> dict[str, Any]:
    return {
        "company_id": "gursar_mimarlik",
        "name": "GÃ¼rsar MimarlÄ±k",
        "holding_id": "touche_holding",
        "active": True,
        "as_of": "2026-10-20",
        "data_through": "2026-10-20",
        "currency": currency,
        "currencies": [currency],
        "source": "finance_ledger",
        "ledger": {
            "document_count": 2,
            "line_count": 2,
            "first_date": "2026-10-01",
            "last_date": "2026-10-20",
        },
        "balances": {
            "cash": _money("100.00"),
            "receivables": _money("200.00"),
            "payables": _money("300.00"),
            "revenue": _money("400.00"),
            "cost": _money("50.00"),
            "gross_profit": _money("350.00"),
        },
    }


class FakeClient:
    def __init__(
        self,
        *,
        capabilities: dict[str, Any] | None = None,
        companies: list[dict[str, Any]] | None = None,
        summary: dict[str, Any] | None = None,
        error: Exception | None = None,
    ) -> None:
        self._capabilities = capabilities or _capabilities()
        self._companies = companies or [_company()]
        self._summary = summary or _summary()
        self._error = error
        self.calls: list[tuple[str, dict[str, Any]]] = []

    def _check(self) -> None:
        if self._error is not None:
            raise self._error

    def _response(self, data: dict[str, Any]) -> FinanceApiResponse:
        return FinanceApiResponse(
            data=data,
            request_id="fin-req-1",
            generated_at="2026-10-22T12:00:00+00:00",
        )

    def health(self) -> FinanceApiResponse:
        self.calls.append(("health", {}))
        self._check()
        return self._response({"status": "ok", "data_through": "2026-10-20"})

    def capabilities(self) -> FinanceApiResponse:
        self.calls.append(("capabilities", {}))
        self._check()
        return self._response(self._capabilities)

    def companies(self) -> FinanceApiResponse:
        self.calls.append(("companies", {}))
        self._check()
        return self._response(
            {
                "companies": self._companies,
                "page": {
                    "limit": 50,
                    "offset": 0,
                    "total": len(self._companies),
                    "next_offset": None,
                },
            }
        )

    def summary(self, company_id: str, *, currency: str | None = None) -> FinanceApiResponse:
        self.calls.append(("summary", {"company_id": company_id, "currency": currency}))
        self._check()
        return self._response({**self._summary, "currency": currency or "TL"})

    def accounts(
        self,
        company_id: str,
        *,
        currency: str | None = None,
        from_date: str | None = None,
        to_date: str | None = None,
        limit: int | None = None,
        offset: int | None = None,
    ) -> FinanceApiResponse:
        self.calls.append(
            (
                "accounts",
                {
                    "company_id": company_id,
                    "currency": currency,
                    "from": from_date,
                    "to": to_date,
                    "limit": limit,
                    "offset": offset,
                },
            )
        )
        self._check()
        return self._response(
            {
                "company_id": company_id,
                "from": from_date or "2000-01-01",
                "as_of": to_date or "2026-10-20",
                "currency": currency,
                "accounts": [
                    {
                        "account_code": "120",
                        "name": "AlÄ±cÄ±lar",
                        "type": "VARLIK",
                        "debit": _money("10.00"),
                        "credit": _money("2.00"),
                        "balance": _money("8.00"),
                    }
                ],
                "page": {
                    "limit": limit or 50,
                    "offset": offset or 0,
                    "total": 1,
                    "next_offset": None,
                },
                "source": "finance_ledger",
            }
        )


    def aging(
        self,
        company_id: str,
        *,
        kind: str,
        currency: str | None = None,
        as_of: str | None = None,
        limit: int | None = None,
        offset: int | None = None,
    ) -> FinanceApiResponse:
        self.calls.append(
            (
                "aging",
                {
                    "company_id": company_id,
                    "type": kind,
                    "currency": currency,
                    "as_of": as_of,
                    "limit": limit,
                    "offset": offset,
                },
            )
        )
        self._check()
        return self._response(
            {
                "company_id": company_id,
                "type": kind,
                "account": "120" if kind == "receivable" else "320",
                "as_of": as_of or "2026-10-20",
                "currency": currency,
                "summary": {
                    "total": _money("10.00"),
                    "overdue": _money("0.00"),
                    "overdue_ratio": 0.0,
                },
                "items": [],
                "page": {
                    "limit": limit or 50,
                    "offset": offset or 0,
                    "total": 0,
                    "next_offset": None,
                },
                "source": "finance_ledger",
            }
        )


@pytest.fixture()
def mapping() -> FinanceMappingSnapshot:
    return FinanceMappingSnapshot(
        finance_company_id="gursar_mimarlik",
        finance_company_name="GÃ¼rsar MimarlÄ±k",
        status="verified",
        configured_at=None,
        last_verified_at=None,
    )


def test_status_not_configured_without_mapping() -> None:
    result = FinanceConnector(_settings(), client=FakeClient()).status(None)
    assert result.state is FinanceConnectionState.NOT_CONFIGURED


def test_status_disabled_never_calls_finance(mapping: FinanceMappingSnapshot) -> None:
    client = FakeClient(error=AssertionError("must not be called"))
    result = FinanceConnector(
        _settings(finance_integration_enabled=False), client=client
    ).status(mapping)
    assert result.state is FinanceConnectionState.DISABLED
    assert client.calls == []


def test_status_connected_returns_mapping_and_currency(
    mapping: FinanceMappingSnapshot,
) -> None:
    client = FakeClient(companies=[_company(currencies=["EUR", "TL", "USD"])])
    result = FinanceConnector(_settings(), client=client).status(mapping)
    assert result.state is FinanceConnectionState.CONNECTED
    assert result.available_currencies == ("EUR", "TL", "USD")
    assert result.data_through == "2026-10-20"
    assert result.finance_request_id == "fin-req-1"


def test_status_auth_failure_is_explicit(mapping: FinanceMappingSnapshot) -> None:
    client = FakeClient(
        error=FinanceClientError("INVALID_CREDENTIALS", "nope", status_code=401)
    )
    result = FinanceConnector(_settings(), client=client).status(mapping)
    assert result.state is FinanceConnectionState.AUTH_ERROR


def test_unverified_mapping_is_rejected(mapping: FinanceMappingSnapshot) -> None:
    pending = FinanceMappingSnapshot(
        finance_company_id=mapping.finance_company_id,
        finance_company_name=mapping.finance_company_name,
        status="pending",
        configured_at=None,
        last_verified_at=None,
    )
    with pytest.raises(FinanceMappingUnverifiedError):
        FinanceConnector(_settings(), client=FakeClient()).summary(pending, currency="TL")


def test_disabled_mapping_is_rejected(mapping: FinanceMappingSnapshot) -> None:
    disabled = FinanceMappingSnapshot(
        finance_company_id=mapping.finance_company_id,
        finance_company_name=mapping.finance_company_name,
        status="disabled",
        configured_at=None,
        last_verified_at=None,
    )
    with pytest.raises(FinanceMappingDisabledError):
        FinanceConnector(_settings(), client=FakeClient()).summary(disabled, currency="TL")


def test_company_not_authorized_by_key_is_rejected(mapping: FinanceMappingSnapshot) -> None:
    client = FakeClient(capabilities=_capabilities(["touche_enerji"]))
    with pytest.raises(FinanceCompanyDeniedError):
        FinanceConnector(_settings(), client=client).summary(mapping, currency="TL")



def test_multi_currency_requires_an_explicit_currency(mapping: FinanceMappingSnapshot) -> None:
    client = FakeClient(companies=[_company(currencies=["EUR", "TL", "USD"])])
    with pytest.raises(FinanceCurrencyRequiredError) as exc:
        FinanceConnector(_settings(), client=client).summary(mapping)
    details = exc.value.details
    assert isinstance(details, dict)
    assert details["available_currencies"] == ["EUR", "TL", "USD"]


def test_unknown_currency_is_rejected(mapping: FinanceMappingSnapshot) -> None:
    client = FakeClient(companies=[_company(currencies=["TL", "USD"])])
    with pytest.raises(FinanceInvalidCurrencyError):
        FinanceConnector(_settings(), client=client).summary(mapping, currency="EUR")


def test_single_currency_is_selected_without_aggregation(mapping: FinanceMappingSnapshot) -> None:
    client = FakeClient(companies=[_company(currencies=["TL"])])
    result = FinanceConnector(_settings(), client=client).summary(mapping)
    assert result.data["currency"] == "TL"
    assert client.calls[-1] == ("summary", {"company_id": "gursar_mimarlik", "currency": "TL"})


def test_accounts_pagination_is_forwarded(mapping: FinanceMappingSnapshot) -> None:
    client = FakeClient(companies=[_company(currencies=["TL"])])
    result = FinanceConnector(_settings(), client=client).accounts(
        mapping,
        from_date="2026-01-01",
        to_date="2026-02-28",
        limit=1,
        offset=2,
    )
    assert result.data["from_date"] == "2026-01-01"
    assert client.calls[-1] == (
        "accounts",
        {
            "company_id": "gursar_mimarlik",
            "currency": "TL",
            "from": "2026-01-01",
            "to": "2026-02-28",
            "limit": 1,
            "offset": 2,
        },
    )


def test_aging_passes_receivable_and_payable(mapping: FinanceMappingSnapshot) -> None:
    client = FakeClient(companies=[_company(currencies=["TL"])])
    connector = FinanceConnector(_settings(), client=client)
    receivable = connector.aging(mapping, kind="receivable", as_of="2026-10-20")
    payable = connector.aging(mapping, kind="payable", currency="TL")
    assert receivable.data["account"] == "120"
    assert payable.data["account"] == "320"
    aging_calls = [call for call in client.calls if call[0] == "aging"]
    assert aging_calls[-2][1]["type"] == "receivable"
    assert aging_calls[-1][1]["type"] == "payable"


def test_finance_category_is_preserved_as_commerce_details(
    mapping: FinanceMappingSnapshot,
) -> None:
    auth = FakeClient(
        error=FinanceClientError("INVALID_CREDENTIALS", "nope", status_code=401)
    )
    with pytest.raises(FinanceAuthError) as auth_exc:
        FinanceConnector(_settings(), client=auth).summary(mapping, currency="TL")
    auth_details = auth_exc.value.details
    assert isinstance(auth_details, dict)
    assert auth_details["finance_code"] == "INVALID_CREDENTIALS"
    down = FakeClient(
        error=FinanceClientError("LEDGER_UNAVAILABLE", "down", status_code=503)
    )
    with pytest.raises(FinanceUnavailableError) as down_exc:
        FinanceConnector(_settings(), client=down).summary(mapping, currency="TL")
    down_details = down_exc.value.details
    assert isinstance(down_details, dict)
    assert down_details["finance_code"] == "LEDGER_UNAVAILABLE"


def test_unsupported_contract_is_protocol_error(mapping: FinanceMappingSnapshot) -> None:
    capabilities = _capabilities()
    capabilities["read_only"] = False
    with pytest.raises(FinanceProtocolError):
        FinanceConnector(
            _settings(), client=FakeClient(capabilities=capabilities)
        ).summary(mapping, currency="TL")



class _StubHandler(BaseHTTPRequestHandler):
    server_version = "ToucheFinans/1.0"
    response_status: ClassVar[int] = 200
    response_body: ClassVar[bytes] = (
        b'{"data":{},"meta":{"contract_version":"1","read_only":true}}'
    )
    captured: ClassVar[list[tuple[str, dict[str, str]]]] = []

    def do_GET(self) -> None:
        type(self).captured.append(
            (self.path, {key.lower(): value for key, value in self.headers.items()})
        )
        self.send_response(type(self).response_status)
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(type(self).response_body)))
        self.end_headers()
        self.wfile.write(type(self).response_body)

    def log_message(self, format: str, *args: object) -> None:
        return


class _QuietServer(ThreadingHTTPServer):
    def handle_error(self, request: object, client_address: object) -> None:
        return


@dataclass(frozen=True)
class _Stub:
    server: ThreadingHTTPServer

    @property
    def base_url(self) -> str:
        host = str(self.server.server_address[0])
        port = int(self.server.server_address[1])
        return f"http://{host}:{port}"


@pytest.fixture()
def stub() -> Iterator[_Stub]:
    _StubHandler.server_version = "ToucheFinans/1.0"
    _StubHandler.response_status = 200
    _StubHandler.response_body = (
        b'{"data":{},"meta":{"contract_version":"1","read_only":true}}'
    )
    _StubHandler.captured = []
    server = _QuietServer(("127.0.0.1", 0), _StubHandler)
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    try:
        yield _Stub(server=server)
    finally:
        server.shutdown()
        server.server_close()


def test_http_client_sends_service_headers_and_bounded_path(stub: _Stub) -> None:
    client = FinanceIntegrationClient(stub.base_url, "key_0123456789abcdef", "s" * 43)
    client.capabilities()
    assert _StubHandler.captured
    path, headers = _StubHandler.captured[-1]
    assert path == "/api/integration/v1/capabilities"
    assert headers["x-touche-integration-key"] == "key_0123456789abcdef"
    assert headers["x-touche-integration-secret"] == "s" * 43
    assert "cookie" not in headers
    assert "tailscale-user-login" not in headers


def test_http_client_preserves_finance_error_category(stub: _Stub) -> None:
    _StubHandler.response_status = 403
    _StubHandler.response_body = (
        b'{"error":{"code":"COMPANY_DENIED","message":"no","request_id":"r1"}}'
    )
    client = FinanceIntegrationClient(stub.base_url, "key_0123456789abcdef", "s" * 43)
    with pytest.raises(FinanceClientError) as exc:
        client.summary("gursar_mimarlik")
    assert exc.value.category == "COMPANY_DENIED"
    assert exc.value.status_code == 403
    assert "s" * 43 not in str(exc.value)


def test_http_client_rejects_wrong_server_and_bad_contract(stub: _Stub) -> None:
    _StubHandler.server_version = "OtherServer/1.0"
    client = FinanceIntegrationClient(stub.base_url, "key_0123456789abcdef", "s" * 43)
    with pytest.raises(FinanceClientError) as exc:
        client.health()
    assert exc.value.category == "INVALID_SERVER"
    _StubHandler.server_version = "ToucheFinans/1.0"
    _StubHandler.response_body = b'{"data":{},"meta":{"contract_version":"2","read_only":true}}'
    with pytest.raises(FinanceClientError) as exc2:
        client.health()
    assert exc2.value.category == "UNSUPPORTED_CONTRACT"


def test_client_rejects_arbitrary_company_ids_without_network(stub: _Stub) -> None:
    client = FinanceIntegrationClient(stub.base_url, "key_0123456789abcdef", "s" * 43)
    with pytest.raises(ValueError):
        client.summary("../other")


def test_timeout_is_reported_without_secret(stub: _Stub) -> None:
    class SlowHandler(_StubHandler):
        def do_GET(self) -> None:
            time.sleep(0.25)
            super().do_GET()

    server = _QuietServer(("127.0.0.1", 0), SlowHandler)
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    try:
        base = f"http://127.0.0.1:{server.server_address[1]}"
        client = FinanceIntegrationClient(
            base, "key_0123456789abcdef", "s" * 43, timeout_seconds=0.05
        )
        with pytest.raises(FinanceClientError) as exc:
            client.health()
        assert exc.value.category == "TIMEOUT"
        assert "s" * 43 not in str(exc.value)
    finally:
        server.shutdown()
        server.server_close()


def test_connector_modules_do_not_open_finance_sqlite() -> None:
    from pathlib import Path

    import app.integrations.finance.client as client_module
    import app.integrations.finance.connector as connector_module

    for module in (client_module, connector_module):
        assert module.__file__ is not None
        source = Path(module.__file__).read_text(encoding="utf-8")
        assert "sqlite3" not in source
        assert "finans.db" not in source

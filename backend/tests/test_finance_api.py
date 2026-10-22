"""Stage 5C authenticated Finance API integration tests.

These use the isolated PostgreSQL test database and a local Finance-shaped stub.
They verify real Commerce sessions, active-company membership, RLS mapping,
currency selection, error translation and read-only route shape. They do not
claim to be a live Finance connection.
"""

from __future__ import annotations

import json
import threading
from collections.abc import Callable, Iterator
from dataclasses import dataclass
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from typing import Any, ClassVar
from uuid import UUID

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient
from pydantic import SecretStr
from sqlalchemy import select, text

from app.core.config import Settings
from app.db.engine import Database
from app.db.models import AuditAction, FinanceCompanyMapping
from app.db.tenant import apply_company_context
from app.services.finance_mapping import set_verified_mapping
from tests.conftest import IdentityWorld
from tests.support import csrf_from, csrf_headers, login

pytestmark = pytest.mark.integration

API = "/api/v1"
FINANCE = f"{API}/finance"


def _money(amount: str) -> dict[str, Any]:
    return {"amount": amount, "amount_kurus": round(float(amount) * 100)}


def _meta(data: dict[str, Any]) -> bytes:
    payload = {
        "data": data,
        "meta": {
            "request_id": "fin-req-api-1",
            "contract_version": "1",
            "generated_at": "2026-10-22T12:00:00+00:00",
            "source": "finance_ledger",
            "read_only": True,
        },
    }
    return json.dumps(payload).encode("utf-8")


def _companies() -> list[dict[str, Any]]:
    return [
        {
            "id": "gursar_mimarlik",
            "name": "GÃ¼rsar MimarlÄ±k",
            "holding_id": "touche_holding",
            "active": True,
            "currency": None,
            "currencies": ["EUR", "TL", "USD"],
            "multi_currency": True,
            "data_through": "2026-10-20",
        },
        {
            "id": "touche_enerji",
            "name": "Touche Enerji",
            "holding_id": "touche_holding",
            "active": True,
            "currency": "TL",
            "currencies": ["TL"],
            "multi_currency": False,
            "data_through": "2026-09-30",
        },
    ]


class FinanceStubHandler(BaseHTTPRequestHandler):
    server_version = "ToucheFinans/1.0"
    overrides: ClassVar[dict[str, tuple[int, bytes]]] = {}
    captured: ClassVar[list[tuple[str, dict[str, str]]]] = []

    def do_GET(self) -> None:
        type(self).captured.append(
            (self.path, {key.lower(): value for key, value in self.headers.items()})
        )
        path = self.path.split("?", 1)[0]
        override = type(self).overrides.get(path)
        status, body = override if override else (200, self._default(path, self.path))
        self.send_response(status)
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    @staticmethod
    def _default(path: str, full_path: str) -> bytes:
        if path == "/api/integration/v1/health":
            return _meta(
                {
                    "status": "ok",
                    "enabled": True,
                    "read_only": True,
                    "contract_version": "1",
                    "ledger_readable": True,
                    "data_through": "2026-10-20",
                    "pending_recovery": 0,
                    "needs_review": 0,
                    "audit_repair_required": 0,
                    "counts": {
                        "faaliyetler": 2,
                        "hesaplar": 22,
                        "fisler": 24,
                        "fis_satirlari": 48,
                    },
                    "source": "finance_ledger",
                }
            )
        if path == "/api/integration/v1/capabilities":
            return _meta(
                {
                    "contract_version": "1",
                    "enabled": True,
                    "read_only": True,
                    "scopes": ["finance.read"],
                    "company_ids": ["gursar_mimarlik"],
                    "max_page": 200,
                    "endpoints": ["GET /api/integration/v1/health"],
                    "currency_support": {
                        "mode": "per_request",
                        "available": ["EUR", "TL", "USD"],
                        "aggregation": False,
                        "conversion": False,
                    },
                    "limitations": ["counterparties are free text"],
                    "unsupported": ["journal writes", "invoice posting"],
                }
            )
        if path == "/api/integration/v1/companies":
            return _meta(
                {
                    "companies": _companies(),
                    "page": {"limit": 50, "offset": 0, "total": 2, "next_offset": None},
                    "source": "finance_ledger",
                }
            )
        if path.endswith("/summary"):
            return _meta(
                {
                    "company_id": "gursar_mimarlik",
                    "name": "GÃ¼rsar MimarlÄ±k",
                    "holding_id": "touche_holding",
                    "active": True,
                    "as_of": "2026-10-20",
                    "data_through": "2026-10-20",
                    "currency": "TL",
                    "currencies": ["EUR", "TL", "USD"],
                    "source": "finance_ledger",
                    "ledger": {
                        "document_count": 24,
                        "line_count": 48,
                        "first_date": "2026-09-01",
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
            )
        if path.endswith("/accounts"):
            return _meta(
                {
                    "company_id": "gursar_mimarlik",
                    "from": "2026-01-01",
                    "as_of": "2026-02-28",
                    "currency": "TL",
                    "accounts": [
                        {
                            "account_code": "120",
                            "name": "AlÄ±cÄ±lar",
                            "type": "VARLIK",
                            "debit": _money("100.00"),
                            "credit": _money("40.00"),
                            "balance": _money("60.00"),
                        }
                    ],
                    "page": {
                        "limit": 1,
                        "offset": 1,
                        "total": 1,
                        "next_offset": None,
                    },
                    "source": "finance_ledger",
                }
            )
        if path.endswith("/aging"):
            kind = "payable" if "type=payable" in full_path else "receivable"
            return _meta(
                {
                    "company_id": "gursar_mimarlik",
                    "type": kind,
                    "account": "320" if kind == "payable" else "120",
                    "as_of": "2026-10-20",
                    "currency": "TL",
                    "summary": {
                        "total": _money("600.00"),
                        "overdue": _money("600.00"),
                        "overdue_ratio": 100.0,
                    },
                    "items": [
                        {
                            "counterparty": "Customer A",
                            "counterparty_key_type": "ledger.cari",
                            "buckets": {
                                "not_due": _money("0.00"),
                                "days_1_30": _money("0.00"),
                                "days_31_60": _money("600.00"),
                                "days_61_90": _money("0.00"),
                                "days_over_90": _money("0.00"),
                            },
                            "total": _money("600.00"),
                            "advance": _money("0.00"),
                            "overdue": True,
                            "overdue_amount": _money("600.00"),
                            "open_items": [
                                {
                                    "source_id": "JRN-TEST-001",
                                    "source": "ledger.fisler",
                                    "due_date": "2026-01-31",
                                    "remaining": _money("600.00"),
                                }
                            ],
                        }
                    ],
                    "page": {
                        "limit": 50,
                        "offset": 0,
                        "total": 1,
                        "next_offset": None,
                    },
                    "source": "finance_ledger",
                }
            )
        return _meta({})




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
def finance_stub() -> Iterator[_Stub]:
    FinanceStubHandler.overrides = {}
    FinanceStubHandler.captured = []
    server = _QuietServer(("127.0.0.1", 0), FinanceStubHandler)
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    try:
        yield _Stub(server=server)
    finally:
        server.shutdown()
        server.server_close()


@pytest.fixture()
def finance_app(
    identity_app: FastAPI, test_settings: Settings, finance_stub: _Stub
) -> Iterator[FastAPI]:
    original = identity_app.state.settings
    identity_app.state.settings = test_settings.model_copy(
        update={
            "finance_integration_enabled": True,
            "finance_integration_base_url": finance_stub.base_url,
            "finance_integration_key_id": SecretStr("key_0123456789abcdef"),
            "finance_integration_secret": SecretStr("s" * 43),
            "finance_integration_timeout_seconds": 0.5,
        }
    )
    try:
        yield identity_app
    finally:
        identity_app.state.settings = original


@pytest.fixture()
def mapping_a(
    identity_world: IdentityWorld, migration_database: Database
) -> FinanceCompanyMapping:
    with migration_database.transaction() as session:
        return set_verified_mapping(
            session,
            company_id=identity_world.company_a,
            finance_company_id="gursar_mimarlik",
            finance_company_name="GÃ¼rsar MimarlÄ±k",
            configured_by=identity_world.user_a,
            verification_details={"currencies": ["EUR", "TL", "USD"]},
        )


def sign_in(
    client_factory: Callable[..., TestClient],
    *,
    email: str,
    company_id: UUID | None = None,
) -> tuple[TestClient, str]:
    client = client_factory()
    response = login(client, email)
    assert response.status_code == 200, response.text
    csrf = csrf_from(response)
    if response.json()["session"]["company"] is None:
        assert company_id is not None
        switched = client.post(
            f"{API}/session/company",
            json={"company_id": str(company_id)},
            headers=csrf_headers(csrf),
        )
        assert switched.status_code == 200, switched.text
        csrf = csrf_from(switched)
    return client, csrf


def _error(response: Any) -> str:
    return str(response.json()["error"]["code"])


def _details(response: Any) -> dict[str, Any]:
    details = response.json()["error"]["details"]
    return details if isinstance(details, dict) else {}



def test_status_is_connected_only_after_explicit_mapping(
    finance_app: FastAPI,
    client_factory: Callable[..., TestClient],
    identity_world: IdentityWorld,
    mapping_a: FinanceCompanyMapping,
) -> None:
    client, _csrf = sign_in(
        client_factory, email=identity_world.email_a, company_id=identity_world.company_a
    )
    response = client.get(f"{FINANCE}/status")
    assert response.status_code == 200, response.text
    body = response.json()
    assert body["state"] == "connected"
    assert body["mapping"]["finance_company_id"] == "gursar_mimarlik"
    assert body["available_currencies"] == ["EUR", "TL", "USD"]
    assert body["data_through"] == "2026-10-20"
    assert body["scope"] == "finance_read"
    assert body["read_only"] is True
    assert body["accounting_writes_enabled"] is False
    assert "s" * 43 not in response.text
    assert "key_0123456789abcdef" not in response.text


def test_no_mapping_is_not_configured_and_data_is_refused(
    finance_app: FastAPI,
    client_factory: Callable[..., TestClient],
    identity_world: IdentityWorld,
) -> None:
    client, _csrf = sign_in(
        client_factory, email=identity_world.email_a, company_id=identity_world.company_a
    )
    status = client.get(f"{FINANCE}/status")
    assert status.status_code == 200
    assert status.json()["state"] == "not_configured"
    summary = client.get(f"{FINANCE}/summary?currency=TL")
    assert summary.status_code == 409, summary.text
    assert _error(summary) == "FINANCE_NOT_CONFIGURED"


def test_disabled_connector_does_not_call_finance(
    finance_app: FastAPI,
    client_factory: Callable[..., TestClient],
    identity_world: IdentityWorld,
    mapping_a: FinanceCompanyMapping,
) -> None:
    finance_app.state.settings = finance_app.state.settings.model_copy(
        update={"finance_integration_enabled": False}
    )
    client, _csrf = sign_in(
        client_factory, email=identity_world.email_a, company_id=identity_world.company_a
    )
    response = client.get(f"{FINANCE}/status")
    assert response.status_code == 200
    assert response.json()["state"] == "disabled"
    assert FinanceStubHandler.captured == []


def test_missing_credentials_are_auth_error_not_a_crash(
    finance_app: FastAPI,
    client_factory: Callable[..., TestClient],
    identity_world: IdentityWorld,
    mapping_a: FinanceCompanyMapping,
) -> None:
    finance_app.state.settings = finance_app.state.settings.model_copy(
        update={"finance_integration_key_id": None, "finance_integration_secret": None}
    )
    client, _csrf = sign_in(
        client_factory, email=identity_world.email_a, company_id=identity_world.company_a
    )
    status = client.get(f"{FINANCE}/status")
    assert status.status_code == 200
    assert status.json()["state"] == "auth_error"
    summary = client.get(f"{FINANCE}/summary?currency=TL")
    assert summary.status_code == 502
    assert _error(summary) == "FINANCE_AUTH_ERROR"
    assert _details(summary)["finance_code"] == "MISSING_CREDENTIALS"


def test_finance_auth_error_preserves_category(
    finance_app: FastAPI,
    client_factory: Callable[..., TestClient],
    identity_world: IdentityWorld,
    mapping_a: FinanceCompanyMapping,
) -> None:
    FinanceStubHandler.overrides["/api/integration/v1/capabilities"] = (
        401,
        b'{"error":{"code":"INVALID_CREDENTIALS","message":"bad key","request_id":"fin-r"}}',
    )
    client, _csrf = sign_in(
        client_factory, email=identity_world.email_a, company_id=identity_world.company_a
    )
    status = client.get(f"{FINANCE}/status")
    assert status.status_code == 200
    assert status.json()["state"] == "auth_error"
    summary = client.get(f"{FINANCE}/summary?currency=TL")
    assert summary.status_code == 502
    assert _error(summary) == "FINANCE_AUTH_ERROR"
    assert _details(summary)["finance_code"] == "INVALID_CREDENTIALS"
    assert _details(summary)["finance_request_id"] == "fin-r"



def test_capabilities_hide_other_finance_company_ids(
    finance_app: FastAPI,
    client_factory: Callable[..., TestClient],
    identity_world: IdentityWorld,
    mapping_a: FinanceCompanyMapping,
) -> None:
    client, _csrf = sign_in(
        client_factory, email=identity_world.email_a, company_id=identity_world.company_a
    )
    response = client.get(f"{FINANCE}/capabilities")
    assert response.status_code == 200, response.text
    body = response.json()
    assert body["finance_company_id"] == "gursar_mimarlik"
    assert body["scopes"] == ["finance.read"]
    assert body["currency_support"]["aggregation"] is False
    assert "company_ids" not in body
    assert "touche_enerji" not in response.text


def test_summary_requires_currency_for_multi_currency_company(
    finance_app: FastAPI,
    client_factory: Callable[..., TestClient],
    identity_world: IdentityWorld,
    mapping_a: FinanceCompanyMapping,
) -> None:
    client, _csrf = sign_in(
        client_factory, email=identity_world.email_a, company_id=identity_world.company_a
    )
    response = client.get(f"{FINANCE}/summary")
    assert response.status_code == 409
    assert _error(response) == "FINANCE_CURRENCY_REQUIRED"
    assert _details(response)["available_currencies"] == ["EUR", "TL", "USD"]


def test_summary_explicit_currency_preserves_finance_amounts(
    finance_app: FastAPI,
    client_factory: Callable[..., TestClient],
    identity_world: IdentityWorld,
    mapping_a: FinanceCompanyMapping,
) -> None:
    client, _csrf = sign_in(
        client_factory, email=identity_world.email_a, company_id=identity_world.company_a
    )
    response = client.get(f"{FINANCE}/summary?currency=TL")
    assert response.status_code == 200, response.text
    body = response.json()
    assert body["currency"] == "TL"
    assert body["balances"]["cash"] == {"amount": "100.00", "amount_kurus": 10000}
    assert body["balances"]["gross_profit"]["amount"] == "350.00"
    assert body["data_through"] == "2026-10-20"
    assert body["finance_request_id"] == "fin-req-api-1"


def test_invalid_currency_is_not_converted(
    finance_app: FastAPI,
    client_factory: Callable[..., TestClient],
    identity_world: IdentityWorld,
    mapping_a: FinanceCompanyMapping,
) -> None:
    client, _csrf = sign_in(
        client_factory, email=identity_world.email_a, company_id=identity_world.company_a
    )
    response = client.get(f"{FINANCE}/summary?currency=GBP")
    assert response.status_code == 400
    assert _error(response) == "FINANCE_INVALID_CURRENCY"


def test_accounts_date_range_and_pagination(
    finance_app: FastAPI,
    client_factory: Callable[..., TestClient],
    identity_world: IdentityWorld,
    mapping_a: FinanceCompanyMapping,
) -> None:
    client, _csrf = sign_in(
        client_factory, email=identity_world.email_a, company_id=identity_world.company_a
    )
    response = client.get(
        f"{FINANCE}/accounts?currency=TL&from=2026-01-01&to=2026-02-28&limit=1&offset=1"
    )
    assert response.status_code == 200, response.text
    body = response.json()
    assert body["from_date"] == "2026-01-01"
    assert body["as_of"] == "2026-02-28"
    assert body["page"] == {"limit": 1, "offset": 1, "total": 1, "next_offset": None}
    assert body["accounts"][0]["account_code"] == "120"
    assert body["accounts"][0]["balance"]["amount"] == "60.00"


def test_accounts_reject_reversed_dates_without_calling_finance(
    finance_app: FastAPI,
    client_factory: Callable[..., TestClient],
    identity_world: IdentityWorld,
    mapping_a: FinanceCompanyMapping,
) -> None:
    client, _csrf = sign_in(
        client_factory, email=identity_world.email_a, company_id=identity_world.company_a
    )
    before = len(FinanceStubHandler.captured)
    response = client.get(f"{FINANCE}/accounts?currency=TL&from=2026-03-01&to=2026-02-01")
    assert response.status_code == 400
    assert _error(response) == "BAD_REQUEST"
    assert len(FinanceStubHandler.captured) == before


def test_receivable_and_payable_aging(
    finance_app: FastAPI,
    client_factory: Callable[..., TestClient],
    identity_world: IdentityWorld,
    mapping_a: FinanceCompanyMapping,
) -> None:
    client, _csrf = sign_in(
        client_factory, email=identity_world.email_a, company_id=identity_world.company_a
    )
    for kind, account in (("receivable", "120"), ("payable", "320")):
        response = client.get(f"{FINANCE}/aging?type={kind}&currency=TL")
        assert response.status_code == 200, response.text
        body = response.json()
        assert body["type"] == kind
        assert body["account"] == account
        assert body["items"][0]["open_items"][0]["source_id"] == "JRN-TEST-001"
        assert body["items"][0]["counterparty_key_type"] == "ledger.cari"



def test_mapping_to_unauthorized_finance_company_is_rejected(
    finance_app: FastAPI,
    client_factory: Callable[..., TestClient],
    identity_world: IdentityWorld,
    migration_database: Database,
) -> None:
    with migration_database.transaction() as session:
        set_verified_mapping(
            session,
            company_id=identity_world.company_a,
            finance_company_id="touche_enerji",
            finance_company_name="Touche Enerji",
            configured_by=identity_world.user_a,
            verification_details={},
        )
    client, _csrf = sign_in(
        client_factory, email=identity_world.email_a, company_id=identity_world.company_a
    )
    response = client.get(f"{FINANCE}/summary?currency=TL")
    assert response.status_code == 409
    assert _error(response) == "FINANCE_COMPANY_DENIED"
    assert _details(response)["finance_code"] == "COMPANY_DENIED"


def test_other_tenant_cannot_read_the_mapped_company(
    finance_app: FastAPI,
    client_factory: Callable[..., TestClient],
    identity_world: IdentityWorld,
    mapping_a: FinanceCompanyMapping,
) -> None:
    client, _csrf = sign_in(client_factory, email=identity_world.email_b)
    status = client.get(f"{FINANCE}/status")
    assert status.status_code == 200
    assert status.json()["state"] == "not_configured"
    assert status.json()["mapping"] is None
    summary = client.get(f"{FINANCE}/summary?currency=TL")
    assert summary.status_code == 409
    assert _error(summary) == "FINANCE_NOT_CONFIGURED"
    assert "gursar_mimarlik" not in summary.text


def test_mapping_table_is_rls_protected_and_runtime_read_only(
    finance_app: FastAPI,
    identity_world: IdentityWorld,
    mapping_a: FinanceCompanyMapping,
) -> None:
    database: Database = finance_app.state.database
    with database.transaction() as session:
        apply_company_context(session, identity_world.company_b)
        other = session.execute(select(FinanceCompanyMapping)).scalars().all()
    assert other == []
    with database.transaction() as session:
        apply_company_context(session, identity_world.company_a)
        allowed = session.execute(select(FinanceCompanyMapping)).scalars().all()
        assert [row.finance_company_id for row in allowed] == ["gursar_mimarlik"]


def test_audit_records_the_read_without_credentials(
    finance_app: FastAPI,
    client_factory: Callable[..., TestClient],
    identity_world: IdentityWorld,
    mapping_a: FinanceCompanyMapping,
    migration_database: Database,
) -> None:
    client, _csrf = sign_in(
        client_factory, email=identity_world.email_a, company_id=identity_world.company_a
    )
    assert client.get(f"{FINANCE}/summary?currency=TL").status_code == 200
    with migration_database.session() as session:
        row = session.execute(
            text(
                "SELECT action, details::text FROM touche.audit_record "
                "WHERE action = :action ORDER BY occurred_at DESC"
            ),
            {"action": AuditAction.FINANCE_READ.value},
        ).first()
    assert row is not None
    assert row[0] == AuditAction.FINANCE_READ.value
    details = str(row[1])
    assert "gursar_mimarlik" in details
    assert "s" * 43 not in details
    assert "key_0123456789abcdef" not in details


def test_finance_routes_are_get_only_and_never_advertise_credentials(
    finance_app: FastAPI,
) -> None:
    spec = finance_app.openapi()
    finance_paths = {
        path: item for path, item in spec["paths"].items() if path.startswith("/api/v1/finance")
    }
    assert finance_paths
    for item in finance_paths.values():
        assert set(item) == {"get"}
    rendered = json.dumps(spec)
    assert "finance_integration_secret" not in rendered
    assert "X-Touche-Integration-Secret" not in rendered


def test_status_404_for_unauthenticated(
    client: TestClient,
) -> None:
    response = client.get(f"{FINANCE}/status")
    assert response.status_code == 401
    assert _error(response) == "UNAUTHORIZED"


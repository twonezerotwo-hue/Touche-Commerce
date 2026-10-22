"""Stage 5A Finance connector tests.

Everything here is local: a stub HTTP server stands in for Finance, so the suite
never imports Finance code, never touches its SQLite database and never starts
its recovery routine.
"""

from __future__ import annotations

import socket
import threading
import time
from collections.abc import Iterator
from dataclasses import dataclass
from datetime import UTC, datetime
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from typing import ClassVar

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient
from pydantic import ValidationError

from app.api.security import current_session
from app.core.config import Settings
from app.integrations.finance.client import (
    FinanceEndpointError,
    FinanceHealthClient,
    parse_loopback_base_url,
)
from app.integrations.finance.contracts import FinanceHealth, FinanceLinkState
from app.integrations.finance.service import FinanceIntegrationService


def _settings(**overrides: object) -> Settings:
    values: dict[str, object] = {
        "environment": "test",
        "database_url": None,
        "database_migration_url": None,
        "_env_file": None,
    }
    values.update(overrides)
    return Settings(**values)  # type: ignore[arg-type]


class _StubHandler(BaseHTTPRequestHandler):
    server_version = "ToucheFinans/1.0"
    content_type: ClassVar[str] = "application/json"
    status_code: ClassVar[int] = 200
    body: ClassVar[bytes] = b'{"durum":"ok","yerel":true}'
    delay_seconds: ClassVar[float] = 0.0
    requests: ClassVar[list[tuple[str, dict[str, str]]]] = []

    def do_GET(self) -> None:
        type(self).requests.append(
            (self.path, {key.lower(): value for key, value in self.headers.items()})
        )
        if type(self).delay_seconds:
            time.sleep(type(self).delay_seconds)
        self.send_response(type(self).status_code)
        self.send_header("Content-Type", type(self).content_type)
        self.send_header("Content-Length", str(len(type(self).body)))
        self.end_headers()
        self.wfile.write(type(self).body)

    def log_message(self, format: str, *args: object) -> None:
        return


class _QuietServer(ThreadingHTTPServer):
    """A test server that does not print broken-pipe tracebacks.

    Timeout and oversized-response tests intentionally close the client socket
    early; the handler's later write is expected to fail.
    """

    def handle_error(self, request: object, client_address: object) -> None:
        return


@dataclass(frozen=True, slots=True)
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
    _StubHandler.content_type = "application/json"
    _StubHandler.status_code = 200
    _StubHandler.body = b'{"durum":"ok","yerel":true}'
    _StubHandler.delay_seconds = 0.0
    _StubHandler.requests = []
    server = _QuietServer(("127.0.0.1", 0), _StubHandler)
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    try:
        yield _Stub(server=server)
    finally:
        server.shutdown()
        server.server_close()
        thread.join(timeout=2)


def test_loopback_url_accepts_ipv4_and_ipv6() -> None:
    assert parse_loopback_base_url("http://127.0.0.1:8765") == ("127.0.0.1", 8765)
    assert parse_loopback_base_url("http://[::1]:8765/") == ("::1", 8765)


@pytest.mark.parametrize(
    "url",
    [
        "https://127.0.0.1:8765",
        "http://localhost:8765",
        "http://example.com:8765",
        "http://user:secret@127.0.0.1:8765",
        "http://127.0.0.1:8765/api",
        "http://127.0.0.1:8765?probe=1",
        "http://127.0.0.1:8765#fragment",
        "http://127.0.0.1:99999",
    ],
)
def test_non_loopback_or_ambiguous_urls_are_rejected(url: str) -> None:
    with pytest.raises(FinanceEndpointError):
        parse_loopback_base_url(url)


def test_config_default_is_disabled_and_loopback_only() -> None:
    settings = _settings()

    assert settings.finance_integration_enabled is False
    assert settings.finance_integration_base_url == "http://127.0.0.1:8765"
    assert settings.finance_integration_timeout_seconds == 2.0


@pytest.mark.parametrize(
    "url",
    [
        "https://127.0.0.1:8765",
        "http://finance.example:8765",
        "http://user:secret@127.0.0.1:8765",
        "http://127.0.0.1:8765/api",
        "http://127.0.0.1:8765?probe=1",
    ],
)
def test_config_rejects_unsafe_finance_urls(url: str) -> None:
    with pytest.raises(ValidationError, match="finance_integration_base_url"):
        _settings(finance_integration_base_url=url)


def test_healthy_probe_uses_only_the_public_health_path(stub: _Stub) -> None:
    result = FinanceHealthClient(stub.base_url, timeout_seconds=1).probe()

    assert result.state is FinanceLinkState.HEALTHY
    assert result.finance_status == "ok"
    assert result.reports_local_admin_session is True
    assert result.latency_ms >= 0
    path, headers = _StubHandler.requests[0]
    assert path == "/api/health"
    assert "cookie" not in headers
    assert "authorization" not in headers
    assert "tailscale-user-login" not in headers
    assert headers["user-agent"].startswith("touche-commerce-finance-link/")


def test_non_finance_server_identity_is_incompatible(stub: _Stub) -> None:
    _StubHandler.server_version = "ExampleServer/1.0"

    result = FinanceHealthClient(stub.base_url, timeout_seconds=1).probe()

    assert result.state is FinanceLinkState.INCOMPATIBLE
    assert "TOUCHE FINANCE" in result.detail


def test_non_json_content_type_is_incompatible(stub: _Stub) -> None:
    _StubHandler.content_type = "text/html"

    result = FinanceHealthClient(stub.base_url, timeout_seconds=1).probe()

    assert result.state is FinanceLinkState.INCOMPATIBLE
    assert "JSON" in result.detail


def test_degraded_finance_is_reported_as_degraded(stub: _Stub) -> None:
    _StubHandler.body = b'{"durum":"degraded","yerel":false}'

    result = FinanceHealthClient(stub.base_url, timeout_seconds=1).probe()

    assert result.state is FinanceLinkState.DEGRADED
    assert result.finance_status == "degraded"
    assert result.reports_local_admin_session is False


@pytest.mark.parametrize(
    ("status_code", "body", "expected"),
    [
        (200, b"not-json", FinanceLinkState.INCOMPATIBLE),
        (200, b"[]", FinanceLinkState.INCOMPATIBLE),
        (200, b'{"durum":"maintenance"}', FinanceLinkState.INCOMPATIBLE),
        (200, b'{"durum":"ok","yerel":"yes"}', FinanceLinkState.INCOMPATIBLE),
        (302, b"", FinanceLinkState.INCOMPATIBLE),
        (500, b'{"durum":"ok"}', FinanceLinkState.INCOMPATIBLE),
    ],
)
def test_protocol_mismatches_are_incompatible(
    stub: _Stub,
    status_code: int,
    body: bytes,
    expected: FinanceLinkState,
) -> None:
    _StubHandler.status_code = status_code
    _StubHandler.body = body

    result = FinanceHealthClient(stub.base_url, timeout_seconds=1).probe()

    assert result.state is expected
    assert result.finance_status is None


def test_oversized_health_response_is_incompatible(stub: _Stub) -> None:
    _StubHandler.body = b'{"durum":"ok","padding":"' + b"x" * 9000 + b'"}'

    result = FinanceHealthClient(stub.base_url, timeout_seconds=1).probe()

    assert result.state is FinanceLinkState.INCOMPATIBLE
    assert "size" in result.detail


def test_connection_refused_is_unreachable() -> None:
    with socket.socket() as probe_socket:
        probe_socket.bind(("127.0.0.1", 0))
        port = probe_socket.getsockname()[1]

    result = FinanceHealthClient(f"http://127.0.0.1:{port}", timeout_seconds=0.3).probe()

    assert result.state is FinanceLinkState.UNREACHABLE


def test_timeout_is_unreachable(stub: _Stub) -> None:
    _StubHandler.delay_seconds = 0.5

    result = FinanceHealthClient(stub.base_url, timeout_seconds=0.1).probe()

    assert result.state is FinanceLinkState.UNREACHABLE
    assert "timed out" in result.detail


class _ExplodingProbe:
    def probe(self) -> FinanceHealth:
        raise AssertionError("a disabled integration must not perform network I/O")


def test_disabled_service_never_calls_the_probe() -> None:
    result = FinanceIntegrationService(_settings(), probe=_ExplodingProbe()).status()

    assert result.state is FinanceLinkState.DISABLED
    assert result.latency_ms == 0.0


def test_enabled_service_returns_the_probe_result() -> None:
    expected = FinanceHealth(
        state=FinanceLinkState.HEALTHY,
        finance_status="ok",
        latency_ms=1.5,
        detail="stub",
        checked_at=datetime.now(tz=UTC),
    )

    class _FixedProbe:
        def probe(self) -> FinanceHealth:
            return expected

    service = FinanceIntegrationService(
        _settings(finance_integration_enabled=True),
        probe=_FixedProbe(),
    )

    assert service.status() == expected



def test_status_endpoint_requires_a_commerce_session(client: TestClient) -> None:
    response = client.get("/api/v1/integrations/finance/status")

    assert response.status_code == 401
    assert "error" in response.json()


def test_status_endpoint_reports_disabled_by_default(
    app: FastAPI, client: TestClient
) -> None:
    app.dependency_overrides[current_session] = lambda: object()
    try:
        response = client.get("/api/v1/integrations/finance/status")
    finally:
        app.dependency_overrides.clear()

    assert response.status_code == 200
    body = response.json()
    assert body["state"] == "disabled"
    assert body["scope"] == "health_only"
    assert body["accounting_writes_enabled"] is False
    assert body["finance_status"] is None


def test_status_endpoint_uses_the_configured_loopback_probe(
    app: FastAPI,
    client: TestClient,
    stub: _Stub,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    app.dependency_overrides[current_session] = lambda: object()
    monkeypatch.setattr(
        app.state,
        "settings",
        _settings(
            finance_integration_enabled=True,
            finance_integration_base_url=stub.base_url,
            finance_integration_timeout_seconds=1.0,
        ),
    )
    try:
        response = client.get("/api/v1/integrations/finance/status")
    finally:
        app.dependency_overrides.clear()

    assert response.status_code == 200
    body = response.json()
    assert body["state"] == "healthy"
    assert body["finance_status"] == "ok"
    assert body["scope"] == "health_only"
    assert body["accounting_writes_enabled"] is False
    assert body["latency_ms"] >= 0


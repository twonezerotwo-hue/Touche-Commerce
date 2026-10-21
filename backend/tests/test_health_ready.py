"""Readiness endpoint tests: success, failure and dependency isolation."""

from __future__ import annotations

import json

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

from app.core.config import Settings
from app.db.health import DatabaseReadiness
from app.main import create_app


def test_ready_returns_200_when_database_is_reachable(
    app: FastAPI, client: TestClient, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setattr(
        app.state.database,
        "check_readiness",
        lambda: DatabaseReadiness(
            ok=True, latency_ms=4.12, server_version="17.6", role="touche_app"
        ),
    )

    response = client.get("/api/v1/health/ready")

    assert response.status_code == 200
    body = response.json()
    assert body["status"] == "ready"
    assert body["service"] == "touche-commerce-api"
    assert body["environment"] == "test"
    assert len(body["checks"]) == 1
    check = body["checks"][0]
    assert check["name"] == "database"
    assert check["status"] == "ok"
    assert check["latency_ms"] == 4.12
    assert check["error_code"] is None
    assert "PostgreSQL 17.6" in check["detail"]
    assert "touche_app" in check["detail"]


def test_ready_returns_503_envelope_when_database_is_unreachable(client: TestClient) -> None:
    """The configured test DSN points at a closed port on purpose."""

    response = client.get("/api/v1/health/ready")

    assert response.status_code == 503
    body = response.json()
    assert body["error"]["code"] == "NOT_READY"
    assert body["error"]["request_id"] == response.headers["X-Request-ID"]
    assert body["error"]["details"]["status"] == "not_ready"
    check = body["error"]["details"]["checks"][0]
    assert check["name"] == "database"
    assert check["status"] == "error"
    assert check["error_code"] == "DATABASE_UNAVAILABLE"

    # A readiness failure must never leak credentials or the DSN.
    serialised = json.dumps(body)
    assert "unused_password" not in serialised
    assert "postgresql+psycopg" not in serialised
    assert response.headers["cache-control"] == "no-store"


def test_ready_reports_missing_database_configuration() -> None:
    settings = Settings(environment="test", database_url=None, _env_file=None)
    application = create_app(settings)
    with TestClient(application, raise_server_exceptions=False) as client:
        response = client.get("/api/v1/health/ready")

    assert response.status_code == 503
    check = response.json()["error"]["details"]["checks"][0]
    assert check["error_code"] == "DATABASE_NOT_CONFIGURED"


@pytest.mark.integration
def test_ready_against_live_postgresql(live_settings: Settings) -> None:
    """Executes the real readiness query against the configured PostgreSQL."""
    application = create_app(live_settings)

    with TestClient(application, raise_server_exceptions=False) as client:
        response = client.get("/api/v1/health/ready")

    assert response.status_code == 200, response.text
    body = response.json()
    assert body["status"] == "ready"
    check = body["checks"][0]
    assert check["status"] == "ok"
    assert check["detail"].startswith("PostgreSQL 17")
    assert "touche_app" in check["detail"]
    assert check["latency_ms"] > 0

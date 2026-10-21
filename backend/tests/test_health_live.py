"""Liveness endpoint tests.

Liveness must prove "the process serves HTTP" and must never depend on
PostgreSQL — otherwise a database outage would get healthy pods restarted.
"""

from __future__ import annotations

import json
import re
from datetime import datetime, timedelta

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

EXPECTED_FIELDS = {"status", "service", "version", "environment", "checked_at"}


def test_live_returns_200_and_identity(client: TestClient) -> None:
    response = client.get("/api/v1/health/live")

    assert response.status_code == 200
    body = response.json()
    assert set(body) == EXPECTED_FIELDS
    assert body["status"] == "ok"
    assert body["service"] == "touche-commerce-api"
    assert body["version"] == "0.1.0"
    assert body["environment"] == "test"
    checked_at = datetime.fromisoformat(body["checked_at"])
    assert checked_at.utcoffset() == timedelta(0)


def test_live_returns_json_content_type(client: TestClient) -> None:
    response = client.get("/api/v1/health/live")
    assert response.headers["content-type"].startswith("application/json")


def test_live_does_not_touch_the_database(
    app: FastAPI, client: TestClient, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Fail loudly if liveness ever starts calling the readiness probe."""

    def explode() -> None:
        raise AssertionError("liveness must not touch PostgreSQL")

    monkeypatch.setattr(app.state.database, "check_readiness", explode)

    response = client.get("/api/v1/health/live")

    assert response.status_code == 200


def test_live_sets_a_request_id_header(client: TestClient) -> None:
    response = client.get("/api/v1/health/live")
    request_id = response.headers.get("X-Request-ID")
    assert request_id is not None
    assert re.fullmatch(r"[0-9a-f]{32}", request_id)


def test_service_descriptor_points_at_health_endpoints(client: TestClient) -> None:
    response = client.get("/")
    assert response.status_code == 200
    body = response.json()
    assert body["liveness"] == "/api/v1/health/live"
    assert body["readiness"] == "/api/v1/health/ready"
    assert json.dumps(body)  # serialisable, no secret objects leaked

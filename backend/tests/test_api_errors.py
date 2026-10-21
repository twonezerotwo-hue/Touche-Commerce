"""API error contract tests.

These tests pin the public error envelope: clients and the generated TypeScript
types depend on it (docs/API_CONTRACTS.md).
"""

from __future__ import annotations

import json
import re

from fastapi import Query
from fastapi.testclient import TestClient

from app.core.config import Settings
from app.main import create_app


def _assert_envelope(payload: dict[str, object]) -> dict[str, object]:
    error = payload["error"]
    assert isinstance(error, dict)
    assert set(error) >= {"code", "message", "request_id", "timestamp", "details"}
    assert isinstance(error["code"], str) and error["code"]
    assert isinstance(error["message"], str) and error["message"]
    return error


def test_unknown_route_returns_not_found_envelope(client: TestClient) -> None:
    response = client.get("/api/v1/definitely-not-a-route")

    assert response.status_code == 404
    error = _assert_envelope(response.json())
    assert error["code"] == "NOT_FOUND"
    assert error["request_id"] == response.headers["X-Request-ID"]
    assert response.headers["cache-control"] == "no-store"
    assert response.headers["x-content-type-options"] == "nosniff"


def test_method_not_allowed_returns_envelope(client: TestClient) -> None:
    response = client.post("/api/v1/health/live")

    assert response.status_code == 405
    error = _assert_envelope(response.json())
    assert error["code"] == "METHOD_NOT_ALLOWED"


def test_validation_error_returns_field_level_details(settings: Settings) -> None:
    application = create_app(settings)

    @application.get("/api/v1/_test/validation")
    def validated(limit: int = Query(default=10, ge=1, le=100)) -> dict[str, int]:
        return {"limit": limit}

    with TestClient(application, raise_server_exceptions=False) as client:
        accepted = client.get("/api/v1/_test/validation?limit=5")
        rejected = client.get("/api/v1/_test/validation?limit=500")

    assert accepted.status_code == 200
    assert accepted.json() == {"limit": 5}

    assert rejected.status_code == 422
    error = _assert_envelope(rejected.json())
    assert error["code"] == "VALIDATION_ERROR"
    details = error["details"]
    assert isinstance(details, list) and details
    assert details[0]["field"] == "query.limit"
    assert details[0]["type"] == "less_than_equal"


def test_unhandled_exception_returns_opaque_500(settings: Settings) -> None:
    application = create_app(settings)

    @application.get("/api/v1/_test/boom")
    def boom() -> None:
        raise RuntimeError("database password=hunter2 leaked in an exception")

    with TestClient(application, raise_server_exceptions=False) as client:
        response = client.get("/api/v1/_test/boom")

    assert response.status_code == 500
    error = _assert_envelope(response.json())
    assert error["code"] == "INTERNAL_ERROR"
    serialised = json.dumps(response.json())
    assert "hunter2" not in serialised
    assert "RuntimeError" not in serialised


def test_request_id_is_echoed_when_safe(client: TestClient) -> None:
    request_id = "abcd1234-request-0001"
    response = client.get("/api/v1/health/live", headers={"X-Request-ID": request_id})

    assert response.headers["X-Request-ID"] == request_id


def test_unsafe_request_id_is_replaced(client: TestClient) -> None:
    response = client.get("/api/v1/health/live", headers={"X-Request-ID": "bad id!\n"})

    returned = response.headers["X-Request-ID"]
    assert returned != "bad id!\n"
    assert re.fullmatch(r"[0-9a-f]{32}", returned)


def test_cors_preflight_for_local_frontend(client: TestClient) -> None:
    response = client.options(
        "/api/v1/health/live",
        headers={
            "Origin": "http://localhost:3000",
            "Access-Control-Request-Method": "GET",
            "Access-Control-Request-Headers": "X-Request-ID",
        },
    )

    assert response.status_code == 200
    assert response.headers["access-control-allow-origin"] == "http://localhost:3000"
    assert response.headers["access-control-allow-credentials"] == "true"


def test_cors_headers_present_on_health_response(client: TestClient) -> None:
    response = client.get("/api/v1/health/live", headers={"Origin": "http://localhost:3000"})

    assert response.status_code == 200
    assert response.headers["access-control-allow-origin"] == "http://localhost:3000"
    assert "X-Request-ID" in response.headers["access-control-expose-headers"]

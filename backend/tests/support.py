"""Test support helpers shared by the identity test modules."""

from __future__ import annotations

from typing import Any

from fastapi.testclient import TestClient

ORIGIN = "http://localhost:3000"
TEST_PASSWORD = "Correct-Horse-Battery-9"
PASSWORD_HASH_MARKER = "password_hash"
SESSION_TOKEN_MARKER = "token"


def login(client: TestClient, email: str, password: str = TEST_PASSWORD) -> Any:
    """POST /auth/login with the trusted Origin header."""
    return client.post("/api/v1/auth/login", json={"email": email, "password": password})


def csrf_headers(csrf_token: str) -> dict[str, str]:
    return {"X-CSRF-Token": csrf_token}


def csrf_from(response: Any) -> str:
    payload = response.json()
    return str(payload["session"]["csrf_token"])


def cookie_value(client: TestClient, name: str = "touche_session") -> str:
    """Read the raw session cookie value from the client jar."""
    value = client.cookies.get(name)
    assert value is not None, f"cookie {name} was not set"
    return str(value)

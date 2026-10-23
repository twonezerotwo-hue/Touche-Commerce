"""Stage 7C2: opt-outs are append-only, admin-only and always block messaging."""

from __future__ import annotations

from collections.abc import Callable
from uuid import uuid4

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import text

from app.ai.director import AIRuntime
from app.db.engine import Database
from app.security.permissions import Permission, Role, permissions_for
from tests.conftest import IdentityWorld
from tests.support import csrf_headers
from tests.test_ai_api import ask, install_ai
from tests.test_operations_api import OrderWorld, sign_in
from tests.test_reconciliation_api import approver, trader, world

pytestmark = pytest.mark.integration

_IMPORTED_FIXTURES = (world, trader, approver, install_ai)
BASE = "/api/v1/communications"


@pytest.fixture()
def admin_session(
    identity_world: IdentityWorld,
    migration_database: Database,
    client_factory: Callable[..., TestClient],
) -> tuple[TestClient, str]:
    """Grant the existing company-B viewer the admin role in disposable test DB."""
    with migration_database.transaction() as session:
        session.execute(
            text("UPDATE touche.membership SET role='admin' WHERE id=:membership_id"),
            {"membership_id": identity_world.membership_b_viewer},
        )
    return sign_in(
        client_factory, email=identity_world.email_a,
        company_id=identity_world.company_b,
    )


def _payload(world: OrderWorld) -> dict[str, str]:
    return {
        "counterparty_id": world.supplier["id"],
        "channel": "EMAIL",
        "reason": "CONTACT_REQUEST",
    }


def _headers(csrf: str, *, key: str | None = None) -> dict[str, str]:
    return {**csrf_headers(csrf), "Idempotency-Key": key or uuid4().hex}


def test_separate_admin_only_suppression_capability() -> None:
    assert Permission.COMMUNICATIONS_SUPPRESS in permissions_for(Role.ADMIN)
    for role in (Role.VIEWER, Role.TRADER, Role.APPROVER):
        assert Permission.COMMUNICATIONS_SUPPRESS not in permissions_for(role)
    for role in Role:
        assert Permission.COMMUNICATIONS_SEND not in permissions_for(role)


def test_unauthorized_and_missing_headers_never_record_opt_out(
    world: OrderWorld,
    admin_session: tuple[TestClient, str],
) -> None:
    admin_client, csrf = admin_session
    denied = world.client.post(
        f"{BASE}/suppressions", json=_payload(world),
        headers=_headers(world.csrf),
    )
    assert denied.status_code == 403
    assert world.client.get(f"{BASE}/suppressions").status_code == 403
    assert admin_client.post(
        f"{BASE}/suppressions", json=_payload(world),
        headers={"Idempotency-Key": uuid4().hex},
    ).status_code == 403
    missing_key = admin_client.post(
        f"{BASE}/suppressions", json=_payload(world), headers=csrf_headers(csrf)
    )
    assert missing_key.status_code == 400
    assert admin_client.get(f"{BASE}/suppressions").json()["items"] == []


def test_suppression_is_idempotent_immutable_and_logged_without_contact_details(
    world: OrderWorld,
    admin_session: tuple[TestClient, str],
    migration_database: Database,
    install_ai: Callable[..., AIRuntime],
) -> None:
    admin_client, csrf = admin_session
    payload = _payload(world)
    key = uuid4().hex
    first = admin_client.post(
        f"{BASE}/suppressions", json=payload, headers=_headers(csrf, key=key)
    )
    assert first.status_code == 201, first.text
    assert first.json()["grants_consent"] is False
    assert first.json()["effect"] == "BLOCKED"
    assert "@" not in first.text
    assert "example.com" not in first.text

    replay = admin_client.post(
        f"{BASE}/suppressions", json=payload, headers=_headers(csrf, key=key)
    )
    assert replay.status_code == 201, replay.text
    assert replay.headers.get("Idempotent-Replay") == "true"
    assert replay.json() == first.json()

    repeated = admin_client.post(
        f"{BASE}/suppressions",
        json={**payload, "reason": "COMPLIANCE_REVIEW"},
        headers=_headers(csrf),
    )
    assert repeated.status_code == 200, repeated.text
    assert repeated.json() == first.json()  # first suppression reason is immutable

    list_response = admin_client.get(f"{BASE}/suppressions?limit=1")
    assert list_response.status_code == 200, list_response.text
    assert list_response.json()["items"] == [first.json()]
    assert admin_client.delete(
        f"{BASE}/suppressions/{first.json()['id']}", headers=_headers(csrf)
    ).status_code in {404, 405}

    with migration_database.transaction() as session:
        rows = session.execute(
            text(
                "SELECT details FROM touche.audit_record "
                "WHERE action='communications.suppression.recorded' "
                "AND resource_id=:resource_id"
            ),
            {"resource_id": first.json()["id"]},
        ).scalars().all()
    assert len(rows) == 1
    assert rows[0]["channel"] == "EMAIL"
    assert "@" not in str(rows[0])

    install_ai()
    run = ask(world.client, world.csrf, "Draft a follow-up email to suppliers")
    draft = next(p for p in run["proposals"] if p["kind"] == "DRAFT")
    preflight = world.client.post(
        f"{BASE}/preflight",
        json={
            "draft_id": draft["id"],
            "draft_version": draft["version"],
            "counterparty_id": world.supplier["id"],
            "channel": "EMAIL",
            "recipient": "vendor@example.com",
        },
        headers=csrf_headers(world.csrf),
    )
    assert preflight.status_code == 200, preflight.text
    assert "RECIPIENT_SUPPRESSED" in preflight.json()["blockers"]
    assert preflight.json()["sendable"] is False
    assert "vendor@example.com" not in preflight.text


def test_cross_company_suppression_fails_closed(
    world: OrderWorld,
    admin_session: tuple[TestClient, str],
    identity_world: IdentityWorld,
    migration_database: Database,
) -> None:
    client, csrf = admin_session
    with migration_database.transaction() as session:
        other = session.execute(
            text(
                "SELECT id FROM touche.counterparty "
                "WHERE company_id=:other_company LIMIT 1"
            ),
            {"other_company": identity_world.company_a},
        ).scalar_one_or_none()
    # Test even a well-formed but unknown CRM ID does not leak a company.
    response = client.post(
        f"{BASE}/suppressions",
        json={**_payload(world), "counterparty_id": str(other or uuid4())},
        headers=_headers(csrf),
    )
    assert response.status_code == 404
    assert client.get(f"{BASE}/suppressions").json()["items"] == []

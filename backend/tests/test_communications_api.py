"""Stage 7A API tests: company-scoped draft discovery never sends messages."""

from __future__ import annotations

from collections.abc import Callable
from typing import Any
from uuid import uuid4

import pytest

from app.ai.director import AIRuntime
from app.security.permissions import Permission, Role, permissions_for
from tests.support import csrf_headers
from tests.test_ai_api import ask, install_ai
from tests.test_operations_api import OrderWorld
from tests.test_reconciliation_api import approver, trader, world

pytestmark = pytest.mark.integration

_IMPORTED_FIXTURES = (world, install_ai, approver, trader)
API = "/api/v1/communications"


def test_no_role_receives_outbound_send_permission() -> None:
    for role in Role:
        assert Permission.COMMUNICATIONS_SEND not in permissions_for(role)


def test_status_is_draft_only_and_has_no_live_channel(world: OrderWorld) -> None:
    result = world.client.get(f"{API}/status")
    assert result.status_code == 200, result.text
    assert result.headers["Cache-Control"] == "no-store"
    body = result.json()
    assert body["mode"] == "DRAFT_ONLY"
    assert body["external_sending_enabled"] is False
    assert body["send_permission"] == "communications.send"
    assert body["can_review_drafts"] is True
    assert {row["channel"] for row in body["channels"]} == {
        "EMAIL", "WHATSAPP_BUSINESS"
    }
    assert all(row["can_send"] is False for row in body["channels"])
    assert all(row["state"] == "NOT_CONFIGURED" for row in body["channels"])


def test_read_only_drafts_and_no_send_endpoint(
    world: OrderWorld, install_ai: Callable[..., AIRuntime]
) -> None:
    install_ai()
    before = world.client.get(f"{API}/drafts")
    assert before.status_code == 200
    assert before.json()["items"] == []

    run = ask(world.client, world.csrf, "Draft a follow-up email to suppliers about my deal quotes")
    assert run["status"] == "COMPLETED"
    listed = world.client.get(f"{API}/drafts?limit=5")
    assert listed.status_code == 200, listed.text
    assert listed.headers["Cache-Control"] == "no-store"
    body: dict[str, Any] = listed.json()
    assert body["source"] == "AI_OFFICE"
    assert body["items"]
    assert all(item["sent"] is False for item in body["items"])
    assert all(item["source_href"] == "/ai" for item in body["items"])
    assert all(item["body"] and item["title"] for item in body["items"])

    # No write route is registered, even if a browser tries to call it.
    sending = world.client.post(f"{API}/send", json={})
    assert sending.status_code in {404, 405}


def test_limit_cannot_be_unbounded(world: OrderWorld) -> None:
    response = world.client.get(f"{API}/drafts?limit=10000")
    assert response.status_code == 422


def test_send_preflight_cannot_dispatch_or_echo_recipient(
    world: OrderWorld, install_ai: Callable[..., AIRuntime]
) -> None:
    install_ai()
    run = ask(world.client, world.csrf, "Draft a follow-up email to suppliers about my deal quotes")
    draft = next(p for p in run["proposals"] if p["kind"] == "DRAFT")
    recipient = "supplier@example.com"
    request = {
        "draft_id": draft["id"],
        "draft_version": draft["version"],
        "channel": "EMAIL",
        "recipient": recipient,
    }
    reply = world.client.post(f"{API}/preflight", json=request, headers=csrf_headers(world.csrf))
    assert reply.status_code == 200, reply.text
    body = reply.json()
    assert body["sendable"] is False
    assert body["external_sending_enabled"] is False
    assert body["recipient_echoed"] is False
    assert "DRAFT_NOT_APPROVED" in body["blockers"]
    assert "CHANNEL_NOT_CONFIGURED" in body["blockers"]
    assert "SEND_PERMISSION_UNAVAILABLE" in body["blockers"]
    assert recipient not in reply.text
    assert "send" not in body


def test_send_preflight_validates_version_and_recipient(
    world: OrderWorld, install_ai: Callable[..., AIRuntime]
) -> None:
    install_ai()
    run = ask(world.client, world.csrf, "Draft a follow-up email to suppliers about my deal quotes")
    draft = next(p for p in run["proposals"] if p["kind"] == "DRAFT")
    reply = world.client.post(
        f"{API}/preflight",
        json={
            "draft_id": draft["id"],
            "draft_version": draft["version"] + 1,
            "channel": "WHATSAPP_BUSINESS",
            "recipient": "NOT-A-PHONE",
        },
        headers=csrf_headers(world.csrf),
    )
    assert reply.status_code == 200, reply.text
    blockers = reply.json()["blockers"]
    assert "DRAFT_VERSION_MISMATCH" in blockers
    assert "RECIPIENT_INVALID" in blockers
    assert "CHANNEL_NOT_CONFIGURED" in blockers
    assert reply.json()["sendable"] is False


def test_send_preflight_requires_csrf_and_trade_permission(
    world: OrderWorld, approver: tuple, install_ai: Callable[..., AIRuntime]
) -> None:
    install_ai()
    run = ask(world.client, world.csrf, "Draft a follow-up email to suppliers about my deal quotes")
    draft = next(p for p in run["proposals"] if p["kind"] == "DRAFT")
    request = {
        "draft_id": draft["id"],
        "draft_version": draft["version"],
        "channel": "EMAIL",
        "recipient": "supplier@example.com",
    }
    no_csrf = world.client.post(f"{API}/preflight", json=request)
    assert no_csrf.status_code == 403

    viewer, viewer_csrf = approver
    forbidden = viewer.post(
        f"{API}/preflight", json=request, headers=csrf_headers(viewer_csrf)
    )
    assert forbidden.status_code == 403


def _create_crm_contact(world: OrderWorld, *, email: str | None = None,
                        phone: str | None = None) -> dict[str, Any]:
    fields: dict[str, Any] = {
        "name": f"Source {uuid4().hex[:10]}",
        "type": "supplier",
        "country": "GB",
    }
    if email is not None:
        fields["email"] = email
    if phone is not None:
        fields["phone"] = phone
    res = world.client.post(
        "/api/v1/counterparties",
        json=fields,
        headers={
            **csrf_headers(world.csrf),
            "Idempotency-Key": uuid4().hex,
        },
    )
    assert res.status_code == 201, res.text
    return dict(res.json())


def test_preflight_never_conflates_crm_with_consent(
    world: OrderWorld, install_ai: Callable[..., AIRuntime]
) -> None:
    install_ai()
    run = ask(world.client, world.csrf, "Draft an email to a supplier")
    draft = next(p for p in run["proposals"] if p["kind"] == "DRAFT")
    address = "purchasing@example.com"
    contact = _create_crm_contact(world, email=address)
    request = {
        "draft_id": draft["id"],
        "draft_version": draft["version"],
        "counterparty_id": contact["id"],
        "channel": "EMAIL",
        "recipient": address,
    }
    matched = world.client.post(
        f"{API}/preflight", json=request, headers=csrf_headers(world.csrf)
    )
    assert matched.status_code == 200, matched.text
    blockers = matched.json()["blockers"]
    assert "CRM_RECIPIENT_MISMATCH" not in blockers
    assert "CONSENT_UNDOCUMENTED" in blockers
    assert matched.json()["sendable"] is False
    assert address not in matched.text

    unknown = world.client.post(
        f"{API}/preflight",
        json={**request, "counterparty_id": str(uuid4())},
        headers=csrf_headers(world.csrf),
    )
    assert unknown.status_code == 200, unknown.text
    assert "CRM_RECIPIENT_MISMATCH" in unknown.json()["blockers"]

    unrelated = world.client.post(
        f"{API}/preflight",
        json={**request, "recipient": "other@example.com"},
        headers=csrf_headers(world.csrf),
    )
    assert unrelated.status_code == 200, unrelated.text
    assert "CRM_RECIPIENT_MISMATCH" in unrelated.json()["blockers"]
    assert "CONSENT_UNDOCUMENTED" in unrelated.json()["blockers"]


def test_preflight_requires_crm_match_for_whatsapp(
    world: OrderWorld, install_ai: Callable[..., AIRuntime]
) -> None:
    install_ai()
    run = ask(world.client, world.csrf, "Draft a supplier message")
    draft = next(p for p in run["proposals"] if p["kind"] == "DRAFT")
    phone = "+36201234567"
    contact = _create_crm_contact(world, phone=phone)
    request = {
        "draft_id": draft["id"],
        "draft_version": draft["version"],
        "counterparty_id": contact["id"],
        "channel": "WHATSAPP_BUSINESS",
        "recipient": phone,
    }
    matched = world.client.post(
        f"{API}/preflight", json=request, headers=csrf_headers(world.csrf)
    )
    assert matched.status_code == 200, matched.text
    assert "CRM_RECIPIENT_MISMATCH" not in matched.json()["blockers"]
    assert "CONSENT_UNDOCUMENTED" in matched.json()["blockers"]
    assert matched.json()["external_sending_enabled"] is False

    missing = world.client.post(
        f"{API}/preflight",
        json={**request, "counterparty_id": None},
        headers=csrf_headers(world.csrf),
    )
    assert missing.status_code == 200, missing.text
    assert "CRM_RECIPIENT_MISMATCH" in missing.json()["blockers"]


def test_preflight_never_treats_archived_crm_contact_as_current(
    world: OrderWorld, install_ai: Callable[..., AIRuntime]
) -> None:
    install_ai()
    run = ask(world.client, world.csrf, "Draft a supplier message")
    draft = next(p for p in run["proposals"] if p["kind"] == "DRAFT")
    address = "archive@example.com"
    contact = _create_crm_contact(world, email=address)
    patch = world.client.patch(
        f"/api/v1/counterparties/{contact['id']}",
        json={"status": "archived"},
        headers={
            **csrf_headers(world.csrf),
            "If-Match": f"\"v{contact['version']}\"",
            "Idempotency-Key": uuid4().hex,
        },
    )
    assert patch.status_code == 200, patch.text
    result = world.client.post(
        f"{API}/preflight",
        json={
            "draft_id": draft["id"],
            "draft_version": draft["version"],
            "counterparty_id": contact["id"],
            "channel": "EMAIL",
            "recipient": address,
        },
        headers=csrf_headers(world.csrf),
    )
    assert result.status_code == 200, result.text
    assert "CRM_RECIPIENT_MISMATCH" in result.json()["blockers"]
    assert result.json()["sendable"] is False


def test_provider_requirements_fail_closed_and_never_expose_secrets(
    world: OrderWorld,
) -> None:
    result = world.client.get(f"{API}/provider-requirements")
    assert result.status_code == 200, result.text
    assert result.headers["Cache-Control"] == "no-store"
    body = result.json()
    assert body["readiness"] == "BLOCKED"
    assert body["live_provider_verified"] is False
    assert body["human_send_approval_available"] is False
    assert body["sending_enabled"] is False
    assert {x["channel"] for x in body["providers"]} == {
        "EMAIL", "WHATSAPP_BUSINESS"
    }
    assert all(p["transport_enabled"] is False for p in body["providers"])
    assert all(p["requires_verified_consent"] is True for p in body["providers"])
    assert "secret" not in result.text.lower()
    assert "access_token" not in result.text.lower()
    assert world.client.post(f"{API}/provider-requirements", json={}).status_code == 405

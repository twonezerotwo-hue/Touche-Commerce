"""Stage 1B trade API integration tests (live PostgreSQL, real runtime role).

Coverage focuses on what the contract promises and what would silently break a
tenant or a deal if it regressed: authorization, RLS, the state machine,
idempotent replay, optimistic concurrency and auditability.
"""

from __future__ import annotations

from collections.abc import Callable, Iterator
from decimal import Decimal
from typing import Any
from uuid import UUID, uuid4

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import text
from sqlalchemy.exc import DBAPIError, IntegrityError

from app.core.config import Settings
from app.db.engine import Database
from tests.conftest import IdentityWorld
from tests.support import csrf_from, csrf_headers, login

pytestmark = pytest.mark.integration

API = "/api/v1"
COUNTERPARTIES = f"{API}/counterparties"
PRODUCTS = f"{API}/products"
DEALS = f"{API}/deals"
DASHBOARD = f"{API}/dashboard/summary"


def error_code(response: Any) -> str:
    return str(response.json()["error"]["code"])


def sign_in(
    client_factory: Callable[..., TestClient],
    *,
    email: str,
    company_id: UUID | None = None,
) -> tuple[TestClient, str]:
    """Log in and, when the user has several memberships, select the company."""
    client = client_factory()
    response = login(client, email)
    assert response.status_code == 200, response.text
    csrf = csrf_from(response)
    if response.json()["session"]["company"] is None:
        assert company_id is not None, "the test must name a company for multi-member users"
        switched = client.post(
            f"{API}/session/company",
            json={"company_id": str(company_id)},
            headers=csrf_headers(csrf),
        )
        assert switched.status_code == 200, switched.text
        csrf = csrf_from(switched)
    return client, csrf


@pytest.fixture()
def trader(
    identity_world: IdentityWorld, client_factory: Callable[..., TestClient]
) -> tuple[TestClient, str]:
    """Bilal: trader in company B (single membership, auto-selected)."""
    return sign_in(client_factory, email=identity_world.email_b)


@pytest.fixture()
def viewer(
    identity_world: IdentityWorld, client_factory: Callable[..., TestClient]
) -> tuple[TestClient, str]:
    """Amina acting in company B, where she is only a viewer."""
    return sign_in(
        client_factory, email=identity_world.email_a, company_id=identity_world.company_b
    )


@pytest.fixture()
def admin(
    identity_world: IdentityWorld, client_factory: Callable[..., TestClient]
) -> tuple[TestClient, str]:
    """Amina acting in company A, where she is administrator (no trade.write)."""
    return sign_in(
        client_factory, email=identity_world.email_a, company_id=identity_world.company_a
    )


def idempotency_headers(key: str | None = None) -> dict[str, str]:
    return {"Idempotency-Key": key or uuid4().hex}


def create_counterparty(
    client: TestClient, csrf: str, *, name: str = "Acme Metals", **overrides: Any
) -> dict[str, Any]:
    payload = {
        "name": name,
        "type": "buyer",
        "country": "GB",
        "contact_name": "Jane Doe",
        "email": "jane@acme.example",
        **overrides,
    }
    response = client.post(
        COUNTERPARTIES,
        json=payload,
        headers={**csrf_headers(csrf), **idempotency_headers()},
    )
    assert response.status_code == 201, response.text
    return dict(response.json())


def create_product(
    client: TestClient, csrf: str, *, sku: str = "ALU-INGOT", **overrides: Any
) -> dict[str, Any]:
    payload = {
        "sku": sku,
        "name": "Aluminium ingot 99.7%",
        "unit": "mt",
        "currency": "USD",
        "unit_price": "2450.0000",
        **overrides,
    }
    response = client.post(
        PRODUCTS,
        json=payload,
        headers={**csrf_headers(csrf), **idempotency_headers()},
    )
    assert response.status_code == 201, response.text
    return dict(response.json())


def create_deal(
    client: TestClient,
    csrf: str,
    *,
    counterparty_id: str,
    product_id: str,
    **overrides: Any,
) -> dict[str, Any]:
    payload: dict[str, Any] = {
        "title": "50 MT aluminium ingots",
        "counterparty_id": counterparty_id,
        "currency": "USD",
        "expected_close_date": "2026-11-30",
        "notes": "FOB Rotterdam",
        "items": [
            {
                "product_id": product_id,
                "quantity": "50.000",
                "unit_price": "2450.0000",
            }
        ],
        **overrides,
    }
    response = client.post(
        DEALS,
        json=payload,
        headers={**csrf_headers(csrf), **idempotency_headers()},
    )
    assert response.status_code == 201, response.text
    return dict(response.json())


def transition(
    client: TestClient,
    csrf: str,
    deal_id: str,
    to: str,
    *,
    reason: str | None = None,
    key: str | None = None,
    extra_headers: dict[str, str] | None = None,
) -> Any:
    body: dict[str, Any] = {"to": to}
    if reason is not None:
        body["reason"] = reason
    headers = {
        **csrf_headers(csrf),
        **idempotency_headers(key),
        **(extra_headers or {}),
    }
    return client.post(f"{DEALS}/{deal_id}/transitions", json=body, headers=headers)



class TestCounterparties:
    def test_create_returns_etag_and_normalised_fields(
        self, identity_world: IdentityWorld, trader: tuple[TestClient, str]
    ) -> None:
        client, csrf = trader
        response = client.post(
            COUNTERPARTIES,
            json={
                "name": "  Acme   Metals ",
                "type": "supplier",
                "country": "gb",
                "email": "SALES@Acme.Example",
            },
            headers={**csrf_headers(csrf), **idempotency_headers()},
        )

        assert response.status_code == 201, response.text
        payload = response.json()
        assert payload["name"] == "Acme Metals"
        assert payload["country"] == "GB"
        assert payload["email"] == "sales@acme.example"
        assert payload["version"] == 1
        assert payload["status"] == "active"
        assert payload["company_id"] == str(identity_world.company_b)
        assert response.headers["ETag"] == '"v1"'

    def test_duplicate_name_is_a_conflict(self, trader: tuple[TestClient, str]) -> None:
        client, csrf = trader
        create_counterparty(client, csrf)
        response = client.post(
            COUNTERPARTIES,
            json={"name": "Acme Metals"},
            headers={**csrf_headers(csrf), **idempotency_headers()},
        )
        assert response.status_code == 409
        assert error_code(response) == "CONFLICT"

    def test_list_paginates_with_cursor_and_stable_order(
        self, trader: tuple[TestClient, str]
    ) -> None:
        client, csrf = trader
        for name in ("Alpha", "Beta", "Gamma"):
            create_counterparty(client, csrf, name=name)

        first = client.get(COUNTERPARTIES, params={"limit": 2})
        assert first.status_code == 200
        first_body = first.json()
        assert len(first_body["items"]) == 2
        assert first_body["has_more"] is True
        assert first_body["next_cursor"]

        second = client.get(
            COUNTERPARTIES, params={"limit": 2, "cursor": first_body["next_cursor"]}
        )
        second_body = second.json()
        assert len(second_body["items"]) == 1
        assert second_body["has_more"] is False
        assert second_body["next_cursor"] is None
        assert {item["name"] for item in first_body["items"]} & {
            item["name"] for item in second_body["items"]
        } == set()

    def test_cursor_from_another_filter_set_is_rejected(
        self, trader: tuple[TestClient, str]
    ) -> None:
        client, csrf = trader
        for name in ("Alpha", "Beta"):
            create_counterparty(client, csrf, name=name)
        page = client.get(COUNTERPARTIES, params={"limit": 1}).json()
        response = client.get(
            COUNTERPARTIES,
            params={"limit": 1, "cursor": page["next_cursor"], "status": "archived"},
        )
        assert response.status_code == 422
        assert error_code(response) == "VALIDATION_ERROR"

    def test_invalid_limit_is_rejected(self, trader: tuple[TestClient, str]) -> None:
        client, _csrf = trader
        assert client.get(COUNTERPARTIES, params={"limit": 101}).status_code == 422
        assert client.get(COUNTERPARTIES, params={"limit": 0}).status_code == 422

    def test_admin_and_viewer_cannot_write(
        self,
        admin: tuple[TestClient, str],
        viewer: tuple[TestClient, str],
    ) -> None:
        for client, csrf in (admin, viewer):
            response = client.post(
                COUNTERPARTIES,
                json={"name": f"Forbidden {uuid4().hex[:6]}"},
                headers={**csrf_headers(csrf), **idempotency_headers()},
            )
            assert response.status_code == 403, response.text
            assert error_code(response) == "FORBIDDEN"

    def test_other_company_rows_are_invisible(
        self,
        trader: tuple[TestClient, str],
        admin: tuple[TestClient, str],
    ) -> None:
        client, csrf = trader
        record = create_counterparty(client, csrf, name="Meridian Buyer")

        other_client, _other_csrf = admin
        listing = other_client.get(COUNTERPARTIES)
        assert listing.status_code == 200
        assert listing.json()["items"] == []

        direct = other_client.get(f"{COUNTERPARTIES}/{record['id']}")
        assert direct.status_code == 404


class TestProducts:
    def test_patch_requires_if_match_and_bumps_the_version(
        self, trader: tuple[TestClient, str]
    ) -> None:
        client, csrf = trader
        product = create_product(client, csrf)

        missing = client.patch(
            f"{PRODUCTS}/{product['id']}",
            json={"name": "Aluminium ingot 99.9%"},
            headers={**csrf_headers(csrf), **idempotency_headers()},
        )
        assert missing.status_code == 428
        assert error_code(missing) == "PRECONDITION_REQUIRED"

        updated = client.patch(
            f"{PRODUCTS}/{product['id']}",
            json={"name": "Aluminium ingot 99.9%", "unit_price": "2510.5000"},
            headers={
                **csrf_headers(csrf),
                **idempotency_headers(),
                "If-Match": '"v1"',
            },
        )
        assert updated.status_code == 200, updated.text
        assert updated.json()["version"] == 2
        assert updated.headers["ETag"] == '"v2"'
        assert Decimal(updated.json()["unit_price"]) == Decimal("2510.5000")

        stale = client.patch(
            f"{PRODUCTS}/{product['id']}",
            json={"name": "Stale write"},
            headers={
                **csrf_headers(csrf),
                **idempotency_headers(),
                "If-Match": '"v1"',
            },
        )
        assert stale.status_code == 409
        assert error_code(stale) == "VERSION_CONFLICT"
        assert stale.headers["ETag"] == '"v2"'

    def test_duplicate_sku_is_a_conflict(self, trader: tuple[TestClient, str]) -> None:
        client, csrf = trader
        create_product(client, csrf, sku="COPPER")
        response = client.post(
            PRODUCTS,
            json={
                "sku": "copper",
                "name": "Copper cathode",
                "unit": "mt",
                "currency": "USD",
                "unit_price": "9000.0000",
            },
            headers={**csrf_headers(csrf), **idempotency_headers()},
        )
        assert response.status_code == 409

    def test_unit_price_must_be_non_negative(
        self, trader: tuple[TestClient, str]
    ) -> None:
        client, csrf = trader
        response = client.post(
            PRODUCTS,
            json={
                "sku": "NEGATIVE",
                "name": "Invalid",
                "unit": "kg",
                "currency": "USD",
                "unit_price": "-1",
            },
            headers={**csrf_headers(csrf), **idempotency_headers()},
        )
        assert response.status_code == 422
        assert error_code(response) == "VALIDATION_ERROR"



class TestDeals:
    def test_create_records_initial_history_and_total_value(
        self, trader: tuple[TestClient, str]
    ) -> None:
        client, csrf = trader
        counterparty = create_counterparty(client, csrf)
        product = create_product(client, csrf)

        response = client.post(
            DEALS,
            json={
                "title": "50 MT aluminium ingots",
                "counterparty_id": counterparty["id"],
                "currency": "usd",
                "items": [
                    {
                        "product_id": product["id"],
                        "quantity": "50.000",
                        "unit_price": "2450.0000",
                    }
                ],
            },
            headers={**csrf_headers(csrf), **idempotency_headers()},
        )

        assert response.status_code == 201, response.text
        body = response.json()
        assert body["status"] == "DRAFT"
        assert body["currency"] == "USD"
        assert body["reference"].startswith("T-")
        assert body["counterparty_name"] == "Acme Metals"
        assert Decimal(body["total_value"]) == Decimal("122500.00")
        assert Decimal(body["items"][0]["line_total"]) == Decimal("122500.00")
        assert len(body["transitions"]) == 1
        assert body["transitions"][0]["from_status"] is None
        assert body["transitions"][0]["to_status"] == "DRAFT"
        assert body["allowed_transitions"] == ["OPEN", "CANCELLED"]
        assert response.headers["ETag"] == '"v1"'

    def test_patch_cannot_set_status(self, trader: tuple[TestClient, str]) -> None:
        client, csrf = trader
        counterparty = create_counterparty(client, csrf)
        product = create_product(client, csrf)
        deal = create_deal(
            client, csrf, counterparty_id=counterparty["id"], product_id=product["id"]
        )

        response = client.patch(
            f"{DEALS}/{deal['id']}",
            json={"status": "WON"},
            headers={
                **csrf_headers(csrf),
                **idempotency_headers(),
                "If-Match": '"v1"',
            },
        )
        assert response.status_code == 422
        assert error_code(response) == "VALIDATION_ERROR"
        assert client.get(f"{DEALS}/{deal['id']}").json()["status"] == "DRAFT"

    def test_patch_updates_header_with_if_match(
        self, trader: tuple[TestClient, str]
    ) -> None:
        client, csrf = trader
        counterparty = create_counterparty(client, csrf)
        product = create_product(client, csrf)
        deal = create_deal(
            client, csrf, counterparty_id=counterparty["id"], product_id=product["id"]
        )

        without_header = client.patch(
            f"{DEALS}/{deal['id']}",
            json={"title": "Renamed"},
            headers={**csrf_headers(csrf), **idempotency_headers()},
        )
        assert without_header.status_code == 428

        updated = client.patch(
            f"{DEALS}/{deal['id']}",
            json={"title": "  Renamed   deal ", "notes": "  "},
            headers={
                **csrf_headers(csrf),
                **idempotency_headers(),
                "If-Match": '"v1"',
            },
        )
        assert updated.status_code == 200, updated.text
        assert updated.json()["title"] == "Renamed deal"
        assert updated.json()["notes"] is None
        assert updated.json()["version"] == 2



    def test_foreign_counterparty_is_rejected_without_leaking_existence(
        self,
        identity_world: IdentityWorld,
        migration_database: Database,
        trader: tuple[TestClient, str],
        client_factory: Callable[..., TestClient],
    ) -> None:
        client, csrf = trader
        counterparty = create_counterparty(client, csrf, name="Only In B")
        product = create_product(client, csrf, sku="B-ONLY")

        # Bilal also becomes a trader in company A, so he may attempt a deal there.
        from app.security.permissions import Role
        from app.services import admin

        with migration_database.transaction() as session:
            admin.grant_membership(
                session,
                user_id=identity_world.user_b,
                company_id=identity_world.company_a,
                role=Role.TRADER,
            )

        company_a_client, company_a_csrf = sign_in(
            client_factory,
            email=identity_world.email_b,
            company_id=identity_world.company_a,
        )
        response = company_a_client.post(
            DEALS,
            json={
                "title": "Cross tenant attempt",
                "counterparty_id": counterparty["id"],
                "currency": "USD",
                "items": [
                    {
                        "product_id": product["id"],
                        "quantity": "1.000",
                        "unit_price": "10.0000",
                    }
                ],
            },
            headers={**csrf_headers(company_a_csrf), **idempotency_headers()},
        )
        assert response.status_code == 400
        assert error_code(response) == "BAD_REQUEST"
        assert company_a_client.get(DEALS).json()["items"] == []

    def test_list_filters_and_totals(self, trader: tuple[TestClient, str]) -> None:
        client, csrf = trader
        counterparty = create_counterparty(client, csrf)
        product = create_product(client, csrf)
        first = create_deal(
            client, csrf, counterparty_id=counterparty["id"], product_id=product["id"]
        )
        second_product = create_product(client, csrf, sku="SECOND")
        create_deal(
            client,
            csrf,
            counterparty_id=counterparty["id"],
            product_id=second_product["id"],
            title="Second deal",
        )

        listing = client.get(DEALS, params={"status": "DRAFT", "limit": 10})
        assert listing.status_code == 200
        body = listing.json()
        assert body["has_more"] is False
        assert first["id"] in {item["id"] for item in body["items"]}
        assert all(Decimal(item["total_value"]) > 0 for item in body["items"])

        by_counterparty = client.get(DEALS, params={"counterparty_id": counterparty["id"]})
        assert len(by_counterparty.json()["items"]) == 2

        no_match = client.get(DEALS, params={"search": "nothing-matches"})
        assert no_match.json()["items"] == []

    def test_dashboard_reflects_created_data(
        self, trader: tuple[TestClient, str]
    ) -> None:
        client, csrf = trader
        counterparty = create_counterparty(client, csrf)
        product = create_product(client, csrf)
        create_deal(
            client, csrf, counterparty_id=counterparty["id"], product_id=product["id"]
        )

        response = client.get(DASHBOARD)
        assert response.status_code == 200, response.text
        body = response.json()
        assert body["deals_total"] == 1
        assert body["counterparties_total"] == 1
        assert body["products_total"] == 1
        draft = next(item for item in body["status_counts"] if item["status"] == "DRAFT")
        assert draft["deal_count"] == 1
        assert Decimal(draft["total_value"]) == Decimal("122500.00")
        assert body["pipeline"] == [
            {"currency": "USD", "deal_count": 1, "total_value": "122500.00"}
        ]
        assert body["recent_deals"][0]["status"] == "DRAFT"
        assert any(entry["action"] == "deal.created" for entry in body["recent_activity"])



class TestTransitions:
    def _deal(self, client: TestClient, csrf: str) -> dict[str, Any]:
        counterparty = create_counterparty(client, csrf)
        product = create_product(client, csrf)
        return create_deal(
            client, csrf, counterparty_id=counterparty["id"], product_id=product["id"]
        )

    def test_idempotency_key_is_required(
        self, trader: tuple[TestClient, str]
    ) -> None:
        client, csrf = trader
        deal = self._deal(client, csrf)
        response = client.post(
            f"{DEALS}/{deal['id']}/transitions",
            json={"to": "OPEN"},
            headers=csrf_headers(csrf),
        )
        assert response.status_code == 400
        assert error_code(response) == "IDEMPOTENCY_KEY_REQUIRED"
        assert client.get(f"{DEALS}/{deal['id']}").json()["status"] == "DRAFT"

    def test_draft_to_open_appends_history(
        self, trader: tuple[TestClient, str]
    ) -> None:
        client, csrf = trader
        deal = self._deal(client, csrf)

        response = transition(client, csrf, deal["id"], "OPEN")
        assert response.status_code == 200, response.text
        body = response.json()
        assert body["status"] == "OPEN"
        assert body["version"] == 2
        assert [entry["to_status"] for entry in body["transitions"]] == ["DRAFT", "OPEN"]
        assert body["allowed_transitions"] == ["NEGOTIATION", "LOST", "CANCELLED"]
        assert response.headers["ETag"] == '"v2"'

    def test_won_is_disabled(
        self, trader: tuple[TestClient, str]
    ) -> None:
        client, csrf = trader
        deal = self._deal(client, csrf)
        transition(client, csrf, deal["id"], "OPEN")

        response = transition(client, csrf, deal["id"], "WON")
        assert response.status_code == 409
        assert error_code(response) == "TRANSITION_DISABLED"
        detail = client.get(f"{DEALS}/{deal['id']}").json()
        assert detail["status"] == "OPEN"
        assert len(detail["transitions"]) == 2

    def test_lost_requires_a_reason(self, trader: tuple[TestClient, str]) -> None:
        client, csrf = trader
        deal = self._deal(client, csrf)
        transition(client, csrf, deal["id"], "OPEN")

        response = transition(client, csrf, deal["id"], "LOST")
        assert response.status_code == 422
        assert error_code(response) == "REASON_REQUIRED"
        assert response.json()["error"]["details"][0]["field"] == "reason"

    def test_lost_closes_the_deal_and_blocks_further_edges(
        self, trader: tuple[TestClient, str]
    ) -> None:
        client, csrf = trader
        deal = self._deal(client, csrf)
        transition(client, csrf, deal["id"], "OPEN")

        lost = transition(client, csrf, deal["id"], "LOST", reason=" buyer   withdrew ")
        assert lost.status_code == 200, lost.text
        body = lost.json()
        assert body["status"] == "LOST"
        assert body["closed_at"] is not None
        assert body["transitions"][-1]["reason"] == "buyer withdrew"
        assert body["allowed_transitions"] == []

        again = transition(client, csrf, deal["id"], "CANCELLED", reason="late cancel")
        assert again.status_code == 409
        assert error_code(again) == "INVALID_TRANSITION"

    def test_invalid_edge_lists_allowed_targets(
        self, trader: tuple[TestClient, str]
    ) -> None:
        client, csrf = trader
        deal = self._deal(client, csrf)

        response = transition(client, csrf, deal["id"], "LOST", reason="too early")
        assert response.status_code == 409
        assert error_code(response) == "INVALID_TRANSITION"
        assert response.json()["error"]["details"]["allowed"] == ["OPEN", "CANCELLED"]

    def test_closed_deal_cannot_be_edited(
        self, trader: tuple[TestClient, str]
    ) -> None:
        client, csrf = trader
        deal = self._deal(client, csrf)
        transition(client, csrf, deal["id"], "OPEN")
        closed = transition(client, csrf, deal["id"], "LOST", reason="no budget")
        etag = closed.headers["ETag"]

        response = client.patch(
            f"{DEALS}/{deal['id']}",
            json={"title": "Should fail"},
            headers={**csrf_headers(csrf), **idempotency_headers(), "If-Match": etag},
        )
        assert response.status_code == 409
        assert error_code(response) == "CONFLICT"

    def test_stale_if_match_is_a_version_conflict(
        self, trader: tuple[TestClient, str]
    ) -> None:
        client, csrf = trader
        deal = self._deal(client, csrf)
        transition(client, csrf, deal["id"], "OPEN")

        response = transition(
            client, csrf, deal["id"], "NEGOTIATION", extra_headers={"If-Match": '"v1"'}
        )
        assert response.status_code == 409
        assert error_code(response) == "VERSION_CONFLICT"
        assert response.headers["ETag"] == '"v2"'



class TestIdempotency:
    def test_replay_returns_the_stored_response_without_a_second_effect(
        self, trader: tuple[TestClient, str]
    ) -> None:
        client, csrf = trader
        counterparty = create_counterparty(client, csrf)
        product = create_product(client, csrf)
        deal = create_deal(
            client, csrf, counterparty_id=counterparty["id"], product_id=product["id"]
        )
        key = uuid4().hex

        first = transition(client, csrf, deal["id"], "OPEN", key=key)
        assert first.status_code == 200
        replay = transition(client, csrf, deal["id"], "OPEN", key=key)

        assert replay.status_code == 200
        assert replay.headers["Idempotent-Replay"] == "true"
        assert replay.json() == first.json()
        detail = client.get(f"{DEALS}/{deal['id']}").json()
        assert [entry["to_status"] for entry in detail["transitions"]] == ["DRAFT", "OPEN"]
        assert detail["version"] == 2

    def test_same_key_with_a_different_body_conflicts(
        self, trader: tuple[TestClient, str]
    ) -> None:
        client, csrf = trader
        counterparty = create_counterparty(client, csrf)
        product = create_product(client, csrf)
        deal = create_deal(
            client, csrf, counterparty_id=counterparty["id"], product_id=product["id"]
        )
        key = uuid4().hex

        assert transition(client, csrf, deal["id"], "OPEN", key=key).status_code == 200
        conflicting = transition(client, csrf, deal["id"], "CANCELLED", reason="changed", key=key)
        assert conflicting.status_code == 409
        assert error_code(conflicting) == "IDEMPOTENCY_CONFLICT"

    def test_same_key_on_another_endpoint_is_a_different_operation(
        self, trader: tuple[TestClient, str]
    ) -> None:
        client, csrf = trader
        key = uuid4().hex
        first = client.post(
            COUNTERPARTIES,
            json={"name": "Idem One"},
            headers={**csrf_headers(csrf), **idempotency_headers(key)},
        )
        second = client.post(
            PRODUCTS,
            json={
                "sku": "IDEM-TWO",
                "name": "Idem Two",
                "unit": "kg",
                "currency": "USD",
                "unit_price": "1.0000",
            },
            headers={**csrf_headers(csrf), **idempotency_headers(key)},
        )
        assert first.status_code == 201
        assert second.status_code == 201

    def test_completed_record_is_stored_once_per_company_actor_endpoint(
        self, trader: tuple[TestClient, str], migration_database: Database
    ) -> None:
        client, csrf = trader
        key = uuid4().hex
        create_response = client.post(
            COUNTERPARTIES,
            json={"name": "Audited Idempotency"},
            headers={**csrf_headers(csrf), **idempotency_headers(key)},
        )
        assert create_response.status_code == 201

        with migration_database.transaction() as session:
            rows = (
                session.execute(
                    text(
                        "SELECT status, response_status, response_body, endpoint "
                        "FROM touche.idempotency_record WHERE key = :key"
                    ),
                    {"key": key},
                )
                .mappings()
                .all()
            )
        assert len(rows) == 1
        assert rows[0]["status"] == "completed"
        assert rows[0]["response_status"] == 201
        assert rows[0]["endpoint"] == "POST /api/v1/counterparties"
        assert rows[0]["response_body"]["name"] == "Audited Idempotency"


class TestAudit:
    def test_trade_actions_are_audited_with_request_ids(
        self,
        identity_world: IdentityWorld,
        trader: tuple[TestClient, str],
        migration_database: Database,
    ) -> None:
        client, csrf = trader
        counterparty = create_counterparty(client, csrf)
        product = create_product(client, csrf)
        deal = create_deal(
            client, csrf, counterparty_id=counterparty["id"], product_id=product["id"]
        )
        transition(client, csrf, deal["id"], "OPEN")

        with migration_database.transaction() as session:
            rows = (
                session.execute(
                    text(
                        "SELECT action, outcome, actor_id, request_id, details "
                        "FROM touche.audit_record WHERE company_id = :company "
                        "ORDER BY occurred_at"
                    ),
                    {"company": identity_world.company_b},
                )
                .mappings()
                .all()
            )

        actions = [
            str(row["action"])
            for row in rows
            if str(row["action"]).startswith(("counterparty.", "product.", "deal."))
        ]
        trade_rows = [
            row
            for row in rows
            if str(row["action"]).startswith(("counterparty.", "product.", "deal."))
        ]
        assert actions == [
            "counterparty.created",
            "product.created",
            "deal.created",
            "deal.transitioned",
        ]
        assert all(row["outcome"] == "success" for row in trade_rows)
        assert all(row["request_id"] for row in trade_rows)
        assert all(str(row["actor_id"]) == str(identity_world.user_b) for row in trade_rows)
        transition_details = trade_rows[-1]["details"]
        assert transition_details["from"] == "DRAFT"
        assert transition_details["to"] == "OPEN"



@pytest.fixture(scope="session")
def runtime_database(test_settings: Settings) -> Iterator[Database]:
    """Application-role handle (NOBYPASSRLS) against the isolated test database."""
    database = Database(test_settings)
    yield database
    database.dispose()


class TestTenantIsolation:
    def test_rls_hides_trade_rows_from_other_companies(
        self,
        identity_world: IdentityWorld,
        trader: tuple[TestClient, str],
        runtime_database: Database,
    ) -> None:
        client, csrf = trader
        counterparty = create_counterparty(client, csrf, name="Isolated Buyer")
        product = create_product(client, csrf, sku="ISO-1")
        deal = create_deal(
            client, csrf, counterparty_id=counterparty["id"], product_id=product["id"]
        )

        with runtime_database.session() as session:
            session.execute(
                text("SELECT set_config('touche.company_id', :value, true)"),
                {"value": str(identity_world.company_b)},
            )
            assert session.execute(
                text("SELECT count(*) FROM touche.counterparty")
            ).scalar_one() == 1
            assert session.execute(text("SELECT count(*) FROM touche.deal")).scalar_one() == 1
            assert session.execute(
                text("SELECT count(*) FROM touche.deal_transition")
            ).scalar_one() == 1

        with runtime_database.session() as session:
            session.execute(
                text("SELECT set_config('touche.company_id', :value, true)"),
                {"value": str(identity_world.company_a)},
            )
            assert session.execute(
                text("SELECT count(*) FROM touche.counterparty")
            ).scalar_one() == 0
            assert session.execute(text("SELECT count(*) FROM touche.deal")).scalar_one() == 0
            assert session.execute(
                text("SELECT count(*) FROM touche.deal_item")
            ).scalar_one() == 0
            assert session.execute(
                text("SELECT id FROM touche.deal WHERE id = :id"), {"id": deal["id"]}
            ).first() is None

    def test_missing_tenant_context_fails_closed(
        self, runtime_database: Database
    ) -> None:
        with runtime_database.session() as session:
            assert session.execute(
                text("SELECT count(*) FROM touche.deal")
            ).scalar_one() == 0
            assert session.execute(
                text("SELECT count(*) FROM touche.counterparty")
            ).scalar_one() == 0

    def test_composite_fk_blocks_cross_tenant_deal(
        self,
        identity_world: IdentityWorld,
        trader: tuple[TestClient, str],
        migration_database: Database,
    ) -> None:
        client, csrf = trader
        counterparty = create_counterparty(client, csrf, name="B Counterparty")

        insert = text(
            "INSERT INTO touche.deal "
            "(company_id, reference, title, status, counterparty_id, currency, "
            " version, created_by) "
            "VALUES (:company, :reference, 'Cross tenant', 'DRAFT', :counterparty, "
            "'USD', 1, :user)"
        )
        with pytest.raises(IntegrityError), migration_database.transaction() as session:
            session.execute(
                insert,
                {
                    "company": identity_world.company_a,
                    "reference": "X-TENANT",
                    "counterparty": counterparty["id"],
                    "user": identity_world.user_a,
                },
            )

    def test_deal_history_is_append_only_for_the_runtime_role(
        self,
        trader: tuple[TestClient, str],
        runtime_database: Database,
        identity_world: IdentityWorld,
    ) -> None:
        client, csrf = trader
        counterparty = create_counterparty(client, csrf, name="Append Only")
        product = create_product(client, csrf, sku="APPEND-1")
        create_deal(
            client, csrf, counterparty_id=counterparty["id"], product_id=product["id"]
        )

        with (
            pytest.raises(DBAPIError) as excinfo,
            runtime_database.transaction() as session,
        ):
            session.execute(
                text("SELECT set_config('touche.company_id', :value, true)"),
                {"value": str(identity_world.company_b)},
            )
            session.execute(text("UPDATE touche.deal_transition SET reason = 'tampered'"))
        message = str(excinfo.value).lower()
        assert "permission denied" in message or "insufficient_privilege" in message

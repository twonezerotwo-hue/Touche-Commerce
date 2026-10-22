"""Stage 3 sourcing API integration tests (live PostgreSQL, real runtime role).

These tests exercise the promises that matter commercially: one RFQ per supplier,
``PREPARED`` is not ``SENT``, a quote is bound to the request it answers, FX is
never guessed, allocations never lose a cent, approval needs a second person with
``finance.approve``, and another company can never read any of it.
"""

from __future__ import annotations

from collections.abc import Callable
from datetime import UTC, datetime, timedelta
from decimal import Decimal
from typing import Any
from uuid import UUID, uuid4

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import text

from app.db.engine import Database
from app.security.permissions import Role
from app.services import admin
from tests.conftest import IdentityWorld
from tests.support import csrf_from, csrf_headers, login

pytestmark = pytest.mark.integration

API = "/api/v1"
COUNTERPARTIES = f"{API}/counterparties"
PRODUCTS = f"{API}/products"
DEALS = f"{API}/deals"
RFQS = f"{API}/rfqs"
SUPPLIER_QUOTES = f"{API}/supplier-quotes"
FX_RATES = f"{API}/fx-rates"
SCENARIOS = f"{API}/pricing-scenarios"
SALES_QUOTES = f"{API}/sales-quotes"

FUTURE = (datetime.now(tz=UTC) + timedelta(days=30)).date()


def error_code(response: Any) -> str:
    return str(response.json()["error"]["code"])


def idempotency_headers(key: str | None = None) -> dict[str, str]:
    return {"Idempotency-Key": key or uuid4().hex}


def etag(version: int) -> str:
    return f'"v{version}"'


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
    """Bilal: trader in company B."""
    return sign_in(client_factory, email=identity_world.email_b)


@pytest.fixture()
def approver(
    identity_world: IdentityWorld,
    migration_database: Database,
    client_factory: Callable[..., TestClient],
) -> tuple[TestClient, str]:
    """Amina, re-granted as approver in company B (finance.approve, no trade.write)."""
    with migration_database.transaction() as session:
        admin.grant_membership(
            session,
            user_id=identity_world.user_a,
            company_id=identity_world.company_b,
            role=Role.APPROVER,
        )
    return sign_in(
        client_factory,
        email=identity_world.email_a,
        company_id=identity_world.company_b,
    )


def create_counterparty(
    client: TestClient,
    csrf: str,
    *,
    name: str = "Acme Metals",
    type_: str = "supplier",
) -> dict[str, Any]:
    response = client.post(
        COUNTERPARTIES,
        json={"name": name, "type": type_, "country": "GB"},
        headers={**csrf_headers(csrf), **idempotency_headers()},
    )
    assert response.status_code == 201, response.text
    return dict(response.json())


def create_product(
    client: TestClient, csrf: str, *, sku: str = "ALM-KERNEL", unit_price: str = "2.0000"
) -> dict[str, Any]:
    response = client.post(
        PRODUCTS,
        json={
            "sku": sku,
            "name": f"Product {sku}",
            "unit": "kg",
            "currency": "USD",
            "unit_price": unit_price,
        },
        headers={**csrf_headers(csrf), **idempotency_headers()},
    )
    assert response.status_code == 201, response.text
    return dict(response.json())


def create_deal(
    client: TestClient, csrf: str, *, counterparty_id: str, product_id: str
) -> dict[str, Any]:
    response = client.post(
        DEALS,
        json={
            "title": "Almond shipment",
            "counterparty_id": counterparty_id,
            "currency": "USD",
            "items": [
                {
                    "product_id": product_id,
                    "quantity": "100.000",
                    "unit_price": "2.0000",
                }
            ],
        },
        headers={**csrf_headers(csrf), **idempotency_headers()},
    )
    assert response.status_code == 201, response.text
    return dict(response.json())


def create_rfqs(
    client: TestClient,
    csrf: str,
    *,
    deal_id: str,
    supplier_ids: list[str],
    product_ids: list[str],
    unit_price: str = "2.0000",
) -> list[dict[str, Any]]:
    response = client.post(
        RFQS,
        json={
            "deal_id": deal_id,
            "supplier_ids": supplier_ids,
            "requested_currency": "USD",
            "delivery_location": "Rotterdam, NL",
            "response_due_date": str(FUTURE),
            "items": [
                {
                    "product_id": product_id,
                    "description": "Almond kernels, 25 kg bags",
                    "quantity": "100.000",
                    "unit": "kg",
                }
                for product_id in product_ids
            ],
        },
        headers={**csrf_headers(csrf), **idempotency_headers()},
    )
    assert response.status_code == 201, response.text
    return list(response.json()["items"])


def transition_rfq(
    client: TestClient,
    csrf: str,
    rfq_id: str,
    to: str,
    *,
    channel: str | None = None,
    evidence: str | None = None,
    reason: str | None = None,
    key: str | None = None,
    headers: dict[str, str] | None = None,
) -> Any:
    body: dict[str, Any] = {"to": to}
    if channel is not None:
        body["channel"] = channel
    if evidence is not None:
        body["evidence"] = evidence
    if reason is not None:
        body["reason"] = reason
    return client.post(
        f"{RFQS}/{rfq_id}/transitions",
        json=body,
        headers={
            **csrf_headers(csrf),
            **idempotency_headers(key),
            **(headers or {}),
        },
    )


def send_rfq(client: TestClient, csrf: str, rfq: dict[str, Any]) -> dict[str, Any]:
    """Prepare and dispatch an RFQ, returning the SENT representation."""
    prepared = transition_rfq(client, csrf, rfq["id"], "PREPARED")
    assert prepared.status_code == 200, prepared.text
    sent = transition_rfq(
        client,
        csrf,
        rfq["id"],
        "SENT",
        channel="email",
        evidence="message-id:<rfq-1@touche.example>",
    )
    assert sent.status_code == 200, sent.text
    return dict(sent.json())


def quote_payload(
    items: list[dict[str, Any]], *, currency: str = "USD", **overrides: Any
) -> dict[str, Any]:
    return {
        "currency": currency,
        "incoterm": "CIF",
        "named_delivery_place": "Rotterdam, NL",
        "payment_terms": "30 days net",
        "lead_time_days": 21,
        "valid_until": str(FUTURE),
        "source_reference": "email: supplier quote 2026-10-22",
        "items": items,
        **overrides,
    }


def record_quote(
    client: TestClient,
    csrf: str,
    *,
    rfq_id: str,
    items: list[dict[str, Any]],
    currency: str = "USD",
    **overrides: Any,
) -> Any:
    return client.post(
        f"{RFQS}/{rfq_id}/quotes",
        json=quote_payload(items, currency=currency, **overrides),
        headers={**csrf_headers(csrf), **idempotency_headers()},
    )


def revise_quote(
    client: TestClient,
    csrf: str,
    *,
    quote: dict[str, Any],
    items: list[dict[str, Any]],
    reason: str = "Supplier corrected the freight",
    **overrides: Any,
) -> Any:
    return client.post(
        f"{SUPPLIER_QUOTES}/{quote['id']}/revisions",
        json=quote_payload(items, reason=reason, **overrides),
        headers={
            **csrf_headers(csrf),
            **idempotency_headers(),
            "If-Match": etag(int(quote["version"])),
        },
    )


def scenario_payload(
    quote_id: str,
    *,
    target_currency: str = "USD",
    margin_pct: str = "20",
    markup_pct: str = "0",
    fx_rate_snapshot_id: str | None = None,
    components: list[dict[str, Any]] | None = None,
) -> dict[str, Any]:
    return {
        "supplier_quote_id": quote_id,
        "target_currency": target_currency,
        "margin_pct": margin_pct,
        "markup_pct": markup_pct,
        "fx_rate_snapshot_id": fx_rate_snapshot_id,
        "components": components or [],
    }


def create_scenario(client: TestClient, csrf: str, payload: dict[str, Any]) -> Any:
    return client.post(
        SCENARIOS,
        json=payload,
        headers={**csrf_headers(csrf), **idempotency_headers()},
    )


class SourcingWorld:
    """One company, one buyer, two suppliers, two products, a sent RFQ and a quote."""

    def __init__(self, **values: Any) -> None:
        self.__dict__.update(values)


@pytest.fixture()
def world(trader: tuple[TestClient, str], identity_world: IdentityWorld) -> SourcingWorld:
    client, csrf = trader
    supplier_one = create_counterparty(client, csrf, name="Supplier One")
    supplier_two = create_counterparty(client, csrf, name="Supplier Two")
    buyer = create_counterparty(client, csrf, name="Buyer Ltd", type_="buyer")
    first = create_product(client, csrf, sku="ALM-KERNEL")
    second = create_product(client, csrf, sku="CASHEW-W320", unit_price="3.0000")
    deal = create_deal(client, csrf, counterparty_id=buyer["id"], product_id=first["id"])
    rfqs = create_rfqs(
        client,
        csrf,
        deal_id=deal["id"],
        supplier_ids=[supplier_one["id"]],
        product_ids=[first["id"], second["id"]],
    )
    rfq = send_rfq(client, csrf, rfqs[0])
    quote_response = record_quote(
        client,
        csrf,
        rfq_id=rfq["id"],
        items=[
            {"product_id": first["id"], "quantity": "100.000", "unit_price": "1.6000"},
            {"product_id": second["id"], "quantity": "50.000", "unit_price": "2.4000"},
        ],
    )
    assert quote_response.status_code == 201, quote_response.text
    return SourcingWorld(
        client=client,
        csrf=csrf,
        company_id=identity_world.company_b,
        supplier_one=supplier_one,
        supplier_two=supplier_two,
        buyer=buyer,
        first=first,
        second=second,
        deal=deal,
        rfq=rfq,
        quote=dict(quote_response.json()),
    )


class TestRfqCreation:
    def test_one_rfq_per_supplier_in_one_transaction(
        self, trader: tuple[TestClient, str], identity_world: IdentityWorld
    ) -> None:
        client, csrf = trader
        supplier_one = create_counterparty(client, csrf, name="Supplier One")
        supplier_two = create_counterparty(client, csrf, name="Supplier Two")
        buyer = create_counterparty(client, csrf, name="Buyer Ltd", type_="buyer")
        product = create_product(client, csrf)
        deal = create_deal(client, csrf, counterparty_id=buyer["id"], product_id=product["id"])

        rfqs = create_rfqs(
            client,
            csrf,
            deal_id=deal["id"],
            supplier_ids=[supplier_one["id"], supplier_two["id"]],
            product_ids=[product["id"]],
        )

        assert len(rfqs) == 2
        assert {item["supplier_counterparty_id"] for item in rfqs} == {
            supplier_one["id"],
            supplier_two["id"],
        }
        assert len({item["reference_number"] for item in rfqs}) == 2
        assert all(item["status"] == "DRAFT" for item in rfqs)
        assert all(item["revision"] == 1 for item in rfqs)
        assert all(item["company_id"] == str(identity_world.company_b) for item in rfqs)
        listing = client.get(RFQS, params={"deal_id": deal["id"]})
        assert listing.status_code == 200
        assert {item["id"] for item in listing.json()["items"]} == {item["id"] for item in rfqs}
        assert all(item["quote_count"] == 0 for item in listing.json()["items"])

    def test_buyer_cannot_receive_an_rfq(self, trader: tuple[TestClient, str]) -> None:
        client, csrf = trader
        buyer = create_counterparty(client, csrf, name="Only Buys", type_="buyer")
        product = create_product(client, csrf)
        deal = create_deal(client, csrf, counterparty_id=buyer["id"], product_id=product["id"])

        response = client.post(
            RFQS,
            json={
                "deal_id": deal["id"],
                "supplier_ids": [buyer["id"]],
                "requested_currency": "USD",
                "delivery_location": "Rotterdam, NL",
                "items": [
                    {
                        "product_id": product["id"],
                        "description": "Almond kernels",
                        "quantity": "10.000",
                        "unit": "kg",
                    }
                ],
            },
            headers={**csrf_headers(csrf), **idempotency_headers()},
        )

        assert response.status_code == 400, response.text
        assert error_code(response) == "BAD_REQUEST"

    def test_duplicate_supplier_is_a_validation_error(self, trader: tuple[TestClient, str]) -> None:
        client, csrf = trader
        supplier = create_counterparty(client, csrf)
        buyer = create_counterparty(client, csrf, name="Buyer Ltd", type_="buyer")
        product = create_product(client, csrf)
        deal = create_deal(client, csrf, counterparty_id=buyer["id"], product_id=product["id"])

        response = client.post(
            RFQS,
            json={
                "deal_id": deal["id"],
                "supplier_ids": [supplier["id"], supplier["id"]],
                "requested_currency": "USD",
                "delivery_location": "Rotterdam, NL",
                "items": [
                    {
                        "product_id": product["id"],
                        "description": "Almond kernels",
                        "quantity": "10.000",
                        "unit": "kg",
                    }
                ],
            },
            headers={**csrf_headers(csrf), **idempotency_headers()},
        )

        assert response.status_code == 422, response.text
        assert error_code(response) == "VALIDATION_ERROR"


class TestRfqLifecycle:
    def test_prepared_is_explicitly_not_sent(self, trader: tuple[TestClient, str]) -> None:
        client, csrf = trader
        supplier = create_counterparty(client, csrf)
        buyer = create_counterparty(client, csrf, name="Buyer Ltd", type_="buyer")
        product = create_product(client, csrf)
        deal = create_deal(client, csrf, counterparty_id=buyer["id"], product_id=product["id"])
        rfq = create_rfqs(
            client,
            csrf,
            deal_id=deal["id"],
            supplier_ids=[supplier["id"]],
            product_ids=[product["id"]],
        )[0]

        skipped = transition_rfq(
            client, csrf, rfq["id"], "SENT", channel="email", evidence="proof-123"
        )
        assert skipped.status_code == 409, skipped.text
        assert error_code(skipped) == "INVALID_TRANSITION"
        assert "PREPARED" in skipped.json()["error"]["details"]["allowed_transitions"]

        prepared = transition_rfq(client, csrf, rfq["id"], "PREPARED")
        assert prepared.status_code == 200, prepared.text
        prepared_body = prepared.json()
        assert prepared_body["status"] == "PREPARED"
        assert prepared_body["sent_at"] is None
        assert [item["revision"] for item in prepared_body["revisions"]] == [1]

        snapshot = client.get(f"{RFQS}/{rfq['id']}/revisions/1")
        assert snapshot.status_code == 200, snapshot.text
        assert snapshot.json()["snapshot"]["items"][0]["product_id"] == product["id"]

        without_evidence = transition_rfq(client, csrf, rfq["id"], "SENT", channel="email")
        assert without_evidence.status_code == 400, without_evidence.text
        assert error_code(without_evidence) == "BAD_REQUEST"

        sent = transition_rfq(
            client, csrf, rfq["id"], "SENT", channel="email", evidence="proof-123"
        )
        assert sent.status_code == 200, sent.text
        assert sent.json()["status"] == "SENT"
        assert sent.json()["sent_at"] is not None
        assert sent.json()["sent_channel"] == "email"
        assert sent.headers["ETag"] == etag(int(sent.json()["version"]))

    def test_transition_requires_and_replays_an_idempotency_key(self, world: SourcingWorld) -> None:
        client, csrf = world.client, world.csrf
        created = create_rfqs(
            client,
            csrf,
            deal_id=world.deal["id"],
            supplier_ids=[world.supplier_two["id"]],
            product_ids=[world.first["id"]],
        )[0]

        missing = client.post(
            f"{RFQS}/{created['id']}/transitions",
            json={"to": "PREPARED"},
            headers=csrf_headers(csrf),
        )
        assert missing.status_code == 400, missing.text
        assert error_code(missing) == "IDEMPOTENCY_KEY_REQUIRED"

        key = uuid4().hex
        first = transition_rfq(client, csrf, created["id"], "PREPARED", key=key)
        second = transition_rfq(client, csrf, created["id"], "PREPARED", key=key)
        assert first.status_code == 200, first.text
        assert second.status_code == 200, second.text
        assert second.headers.get("Idempotent-Replay") == "true"
        assert first.json() == second.json()

    def test_editing_a_prepared_rfq_opens_the_next_revision(self, world: SourcingWorld) -> None:
        client, csrf = world.client, world.csrf
        created = create_rfqs(
            client,
            csrf,
            deal_id=world.deal["id"],
            supplier_ids=[world.supplier_two["id"]],
            product_ids=[world.first["id"]],
        )[0]
        prepared = transition_rfq(client, csrf, created["id"], "PREPARED")
        assert prepared.status_code == 200, prepared.text
        version = int(prepared.json()["version"])

        missing_if_match = client.patch(
            f"{RFQS}/{created['id']}",
            json={"delivery_location": "Hamburg, DE"},
            headers={**csrf_headers(csrf), **idempotency_headers()},
        )
        assert missing_if_match.status_code == 428, missing_if_match.text
        assert error_code(missing_if_match) == "PRECONDITION_REQUIRED"

        edited = client.patch(
            f"{RFQS}/{created['id']}",
            json={"delivery_location": "Hamburg, DE"},
            headers={
                **csrf_headers(csrf),
                **idempotency_headers(),
                "If-Match": etag(version),
            },
        )
        assert edited.status_code == 200, edited.text
        edited_body = edited.json()
        assert edited_body["status"] == "DRAFT"
        assert edited_body["revision"] == 2
        assert edited_body["delivery_location"] == "Hamburg, DE"

        re_prepared = transition_rfq(client, csrf, created["id"], "PREPARED")
        assert re_prepared.status_code == 200, re_prepared.text
        assert [item["revision"] for item in re_prepared.json()["revisions"]] == [2, 1]

        original = client.get(f"{RFQS}/{created['id']}/revisions/1")
        assert original.status_code == 200
        assert original.json()["snapshot"]["delivery_location"] == "Rotterdam, NL"

    def test_a_sent_rfq_is_no_longer_editable(self, world: SourcingWorld) -> None:
        current = world.client.get(f"{RFQS}/{world.rfq['id']}")
        assert current.status_code == 200
        response = world.client.patch(
            f"{RFQS}/{world.rfq['id']}",
            json={"delivery_location": "Hamburg, DE"},
            headers={
                **csrf_headers(world.csrf),
                **idempotency_headers(),
                "If-Match": etag(int(current.json()["version"])),
            },
        )

        assert response.status_code == 409, response.text
        assert error_code(response) == "CONFLICT"


class TestSupplierQuotes:
    def test_quote_requires_a_sent_rfq(self, world: SourcingWorld) -> None:
        client, csrf = world.client, world.csrf
        created = create_rfqs(
            client,
            csrf,
            deal_id=world.deal["id"],
            supplier_ids=[world.supplier_two["id"]],
            product_ids=[world.first["id"]],
        )[0]

        response = record_quote(
            client,
            csrf,
            rfq_id=created["id"],
            items=[{"product_id": world.first["id"], "quantity": "10.000", "unit_price": "1.50"}],
        )

        assert response.status_code == 409, response.text
        assert error_code(response) == "CONFLICT"

    def test_quote_must_match_requested_products(self, world: SourcingWorld) -> None:
        client, csrf = world.client, world.csrf
        created = create_rfqs(
            client,
            csrf,
            deal_id=world.deal["id"],
            supplier_ids=[world.supplier_two["id"]],
            product_ids=[world.first["id"]],
        )[0]
        prepared = transition_rfq(client, csrf, created["id"], "PREPARED")
        assert prepared.status_code == 200, prepared.text
        sent = transition_rfq(
            client,
            csrf,
            created["id"],
            "SENT",
            channel="email",
            evidence="proof-456",
        )
        assert sent.status_code == 200, sent.text

        response = record_quote(
            client,
            csrf,
            rfq_id=created["id"],
            items=[{"product_id": world.second["id"], "quantity": "10.000", "unit_price": "2.00"}],
        )

        assert response.status_code == 400, response.text
        assert error_code(response) == "BAD_REQUEST"

    def test_revision_supersedes_and_blocks_pricing_the_old_quote(
        self, world: SourcingWorld
    ) -> None:
        client, csrf = world.client, world.csrf
        revised = revise_quote(
            client,
            csrf,
            quote=world.quote,
            items=[{"product_id": world.first["id"], "quantity": "100.000", "unit_price": "1.50"}],
        )
        assert revised.status_code == 201, revised.text
        revised_body = revised.json()
        assert revised_body["revision"] == 2
        assert revised_body["supersedes_quote_id"] == world.quote["id"]
        assert revised_body["total_value"] == "150.00"

        original = client.get(f"{SUPPLIER_QUOTES}/{world.quote['id']}")
        assert original.status_code == 200
        assert original.json()["superseded_by_quote_id"] == revised_body["id"]

        again = revise_quote(
            client,
            csrf,
            quote=world.quote,
            items=[{"product_id": world.first["id"], "quantity": "100.000", "unit_price": "1.40"}],
        )
        assert again.status_code == 409, again.text
        assert error_code(again) == "CONFLICT"

        stale = create_scenario(client, csrf, scenario_payload(world.quote["id"], margin_pct="10"))
        assert stale.status_code == 409, stale.text
        assert error_code(stale) == "CONFLICT"

    def test_withdrawn_quote_allows_a_replacement(self, world: SourcingWorld) -> None:
        client, csrf = world.client, world.csrf
        withdrawn = client.post(
            f"{SUPPLIER_QUOTES}/{world.quote['id']}/withdraw",
            json={"reason": "Supplier retracted the offer"},
            headers={
                **csrf_headers(csrf),
                **idempotency_headers(),
                "If-Match": etag(int(world.quote["version"])),
            },
        )
        assert withdrawn.status_code == 200, withdrawn.text
        assert withdrawn.json()["status"] == "WITHDRAWN"

        replacement = record_quote(
            client,
            csrf,
            rfq_id=world.rfq["id"],
            items=[{"product_id": world.first["id"], "quantity": "100.000", "unit_price": "1.55"}],
        )
        assert replacement.status_code == 201, replacement.text
        assert replacement.json()["revision"] == 1
        assert replacement.json()["status"] == "RECEIVED"


def freight_component(
    *,
    amount: str = "40.00",
    verification: str = "VERIFIED",
    basis: str = "ORDER",
    product_id: str | None = None,
    currency: str = "USD",
) -> dict[str, Any]:
    return {
        "cost_type": "FREIGHT",
        "amount": amount,
        "currency": currency,
        "basis": basis,
        "source_reference": "freight-invoice-2026-10",
        "verification_status": verification,
        "product_id": product_id,
    }


class TestPricingScenarios:
    def test_order_cost_is_allocated_and_margin_prices_the_lines(
        self, world: SourcingWorld
    ) -> None:
        client, csrf = world.client, world.csrf
        response = create_scenario(
            client,
            csrf,
            scenario_payload(
                world.quote["id"],
                margin_pct="20",
                components=[freight_component(amount="40.00")],
            ),
        )

        assert response.status_code == 201, response.text
        body = response.json()
        results = body["calculated_results"]
        assert body["status"] == "VERIFIED_INPUTS"
        assert results["totals"]["purchase_total"] == "280.00"
        assert results["totals"]["additional_cost_total"] == "40.00"
        assert results["totals"]["landed_total"] == "320.00"

        allocated = sum(
            (Decimal(line["allocated_cost"]) for line in results["lines"]), Decimal("0")
        )
        assert allocated == Decimal("40.00")
        for line in results["lines"]:
            expected = (Decimal(line["landed_unit_cost"]) / Decimal("0.8")).quantize(
                Decimal("0.0001")
            )
            assert Decimal(line["unit_sale_price"]) == expected
        assert Decimal(results["totals"]["gross_margin"]) == (
            Decimal(results["totals"]["sales_total"]) - Decimal("320.00")
        )
        assert body["components"][0]["amount"] == "40.00"
        assert response.headers["ETag"] == etag(1)

    def test_recalculation_requires_if_match_and_replaces_components(
        self, world: SourcingWorld
    ) -> None:
        client, csrf = world.client, world.csrf
        created = create_scenario(
            client,
            csrf,
            scenario_payload(
                world.quote["id"],
                margin_pct="20",
                components=[freight_component(amount="40.00")],
            ),
        )
        assert created.status_code == 201, created.text
        scenario = created.json()
        recalculation = scenario_payload(
            world.quote["id"],
            margin_pct="25",
            components=[freight_component(amount="60.00")],
        )

        without_if_match = client.put(
            f"{SCENARIOS}/{scenario['id']}",
            json=recalculation,
            headers={**csrf_headers(csrf), **idempotency_headers()},
        )
        assert without_if_match.status_code == 428, without_if_match.text

        stale = client.put(
            f"{SCENARIOS}/{scenario['id']}",
            json=recalculation,
            headers={
                **csrf_headers(csrf),
                **idempotency_headers(),
                "If-Match": etag(99),
            },
        )
        assert stale.status_code == 409, stale.text
        assert error_code(stale) == "VERSION_CONFLICT"

        updated = client.put(
            f"{SCENARIOS}/{scenario['id']}",
            json=recalculation,
            headers={
                **csrf_headers(csrf),
                **idempotency_headers(),
                "If-Match": etag(int(scenario["version"])),
            },
        )
        assert updated.status_code == 200, updated.text
        assert updated.json()["version"] == 2
        totals = updated.json()["calculated_results"]["totals"]
        assert totals["additional_cost_total"] == "60.00"
        assert len(updated.json()["components"]) == 1

    def test_estimated_component_marks_the_scenario_estimated(self, world: SourcingWorld) -> None:
        response = create_scenario(
            world.client,
            world.csrf,
            scenario_payload(
                world.quote["id"],
                margin_pct="10",
                components=[freight_component(verification="ESTIMATED")],
            ),
        )

        assert response.status_code == 201, response.text
        assert response.json()["status"] == "ESTIMATED"
        assert response.json()["completeness"]["estimated_component_count"] == 1

    def test_cross_currency_needs_a_matching_explicit_fx_snapshot(
        self, world: SourcingWorld
    ) -> None:
        client, csrf = world.client, world.csrf
        rfq = create_rfqs(
            client,
            csrf,
            deal_id=world.deal["id"],
            supplier_ids=[world.supplier_two["id"]],
            product_ids=[world.first["id"]],
        )[0]
        sent = send_rfq(client, csrf, rfq)
        recorded = record_quote(
            client,
            csrf,
            rfq_id=sent["id"],
            currency="EUR",
            items=[
                {
                    "product_id": world.first["id"],
                    "quantity": "100.000",
                    "unit_price": "1.6000",
                }
            ],
        )
        assert recorded.status_code == 201, recorded.text
        quote_id = recorded.json()["id"]

        missing = create_scenario(client, csrf, scenario_payload(quote_id, margin_pct="10"))
        assert missing.status_code == 400, missing.text
        assert error_code(missing) == "BAD_REQUEST"

        wrong_pair = client.post(
            FX_RATES,
            json={
                "base_currency": "USD",
                "quote_currency": "EUR",
                "rate": "0.9000000000",
                "effective_at": "2026-10-22T00:00:00Z",
                "source": "ECB reference rate 2026-10-22",
            },
            headers={**csrf_headers(csrf), **idempotency_headers()},
        )
        assert wrong_pair.status_code == 201, wrong_pair.text

        rejected = create_scenario(
            client,
            csrf,
            scenario_payload(
                quote_id,
                margin_pct="10",
                fx_rate_snapshot_id=wrong_pair.json()["id"],
            ),
        )
        assert rejected.status_code == 400, rejected.text
        assert error_code(rejected) == "BAD_REQUEST"

        correct_pair = client.post(
            FX_RATES,
            json={
                "base_currency": "EUR",
                "quote_currency": "USD",
                "rate": "1.1000000000",
                "effective_at": "2026-10-22T00:00:00Z",
                "source": "ECB reference rate 2026-10-22",
            },
            headers={**csrf_headers(csrf), **idempotency_headers()},
        )
        assert correct_pair.status_code == 201, correct_pair.text

        priced = create_scenario(
            client,
            csrf,
            scenario_payload(
                quote_id,
                margin_pct="10",
                fx_rate_snapshot_id=correct_pair.json()["id"],
            ),
        )
        assert priced.status_code == 201, priced.text
        assert priced.json()["calculated_results"]["totals"]["purchase_total"] == "176.00"
        assert priced.json()["quote_currency"] == "EUR"
        assert priced.json()["target_currency"] == "USD"

    def test_snapshot_currency_pair_must_be_distinct(self, world: SourcingWorld) -> None:
        response = world.client.post(
            FX_RATES,
            json={
                "base_currency": "USD",
                "quote_currency": "USD",
                "rate": "1.0000000000",
                "effective_at": "2026-10-22T00:00:00Z",
                "source": "manual",
            },
            headers={**csrf_headers(world.csrf), **idempotency_headers()},
        )

        assert response.status_code == 422, response.text
        assert error_code(response) == "VALIDATION_ERROR"


def create_sales_quote(
    client: TestClient,
    csrf: str,
    *,
    scenario_id: str,
    customer_id: str,
    valid_until: str | None = None,
) -> Any:
    return client.post(
        SALES_QUOTES,
        json={
            "scenario_id": scenario_id,
            "customer_id": customer_id,
            "valid_until": valid_until or str(FUTURE),
            "incoterm": "CIF",
            "named_delivery_place": "Rotterdam, NL",
            "payment_terms": "30 days net",
        },
        headers={**csrf_headers(csrf), **idempotency_headers()},
    )


def sales_action(
    client: TestClient,
    csrf: str,
    quote: dict[str, Any],
    action: str,
    *,
    payload: dict[str, Any] | None = None,
    if_match: str | None = None,
) -> Any:
    headers = {
        **csrf_headers(csrf),
        **idempotency_headers(),
        "If-Match": if_match or etag(int(quote["version"])),
    }
    return client.post(
        f"{SALES_QUOTES}/{quote['id']}/{action}",
        json=payload,
        headers=headers,
    )


def verified_scenario(world: SourcingWorld, *, verification: str = "VERIFIED") -> dict[str, Any]:
    response = create_scenario(
        world.client,
        world.csrf,
        scenario_payload(
            world.quote["id"],
            margin_pct="20",
            components=[freight_component(verification=verification)],
        ),
    )
    assert response.status_code == 201, response.text
    return dict(response.json())


class TestSalesQuotes:
    def test_submission_requires_verified_scenario_inputs(self, world: SourcingWorld) -> None:
        client, csrf = world.client, world.csrf
        estimated = verified_scenario(world, verification="ESTIMATED")

        drafted = create_sales_quote(
            client, csrf, scenario_id=estimated["id"], customer_id=world.buyer["id"]
        )
        assert drafted.status_code == 201, drafted.text
        body = drafted.json()
        assert body["status"] == "DRAFT"
        assert body["scenario_status"] == "ESTIMATED"
        assert body["can_submit"] is False
        assert body["allowed_transitions"] == ["PENDING_APPROVAL", "WITHDRAWN"]

        blocked = sales_action(client, csrf, body, "submit")
        assert blocked.status_code == 409, blocked.text
        assert error_code(blocked) == "CONFLICT"

    def test_approval_needs_finance_permission_and_a_second_person(
        self, world: SourcingWorld, approver: tuple[TestClient, str], identity_world: IdentityWorld
    ) -> None:
        client, csrf = world.client, world.csrf
        scenario = verified_scenario(world)
        drafted = create_sales_quote(
            client, csrf, scenario_id=scenario["id"], customer_id=world.buyer["id"]
        )
        assert drafted.status_code == 201, drafted.text
        submitted = sales_action(client, csrf, drafted.json(), "submit")
        assert submitted.status_code == 200, submitted.text
        assert submitted.json()["status"] == "PENDING_APPROVAL"
        assert submitted.json()["submitted_by"] == str(identity_world.user_b)

        by_trader = sales_action(client, csrf, submitted.json(), "approve")
        assert by_trader.status_code == 403, by_trader.text
        assert error_code(by_trader) == "FORBIDDEN"

        approver_client, approver_csrf = approver
        approved = sales_action(approver_client, approver_csrf, submitted.json(), "approve")
        assert approved.status_code == 200, approved.text
        approved_body = approved.json()
        assert approved_body["status"] == "APPROVED"
        assert approved_body["approved_by"] == str(identity_world.user_a)
        assert approved_body["approved_at"] is not None
        assert approved_body["allowed_transitions"] == []

        again = sales_action(approver_client, approver_csrf, approved_body, "approve")
        assert again.status_code == 409, again.text
        assert error_code(again) == "INVALID_TRANSITION"

    def test_rejection_requires_a_reason_and_is_terminal(
        self, world: SourcingWorld, approver: tuple[TestClient, str]
    ) -> None:
        client, csrf = world.client, world.csrf
        approver_client, approver_csrf = approver
        scenario = verified_scenario(world)
        drafted = create_sales_quote(
            client, csrf, scenario_id=scenario["id"], customer_id=world.buyer["id"]
        )
        assert drafted.status_code == 201, drafted.text
        submitted = sales_action(client, csrf, drafted.json(), "submit")
        assert submitted.status_code == 200, submitted.text

        blank = sales_action(
            approver_client,
            approver_csrf,
            submitted.json(),
            "reject",
            payload={"reason": "   "},
        )
        assert blank.status_code == 422, blank.text
        assert error_code(blank) == "REASON_REQUIRED"

        rejected = sales_action(
            approver_client,
            approver_csrf,
            submitted.json(),
            "reject",
            payload={"reason": "Margin below the desk minimum"},
        )
        assert rejected.status_code == 200, rejected.text
        assert rejected.json()["status"] == "REJECTED"
        assert rejected.json()["rejection_reason"] == "Margin below the desk minimum"
        assert rejected.json()["allowed_transitions"] == []

        resubmitted = sales_action(client, csrf, rejected.json(), "submit")
        assert resubmitted.status_code == 409, resubmitted.text
        assert error_code(resubmitted) == "INVALID_TRANSITION"

    def test_revision_of_an_approved_quote_keeps_the_original(
        self, world: SourcingWorld, approver: tuple[TestClient, str]
    ) -> None:
        client, csrf = world.client, world.csrf
        approver_client, approver_csrf = approver
        scenario = verified_scenario(world)
        drafted = create_sales_quote(
            client, csrf, scenario_id=scenario["id"], customer_id=world.buyer["id"]
        )
        assert drafted.status_code == 201, drafted.text
        submitted = sales_action(client, csrf, drafted.json(), "submit")
        assert submitted.status_code == 200, submitted.text
        approved = sales_action(approver_client, approver_csrf, submitted.json(), "approve")
        assert approved.status_code == 200, approved.text

        revised = sales_action(
            client,
            csrf,
            approved.json(),
            "revisions",
            payload={"valid_until": str(FUTURE), "reason": "Customer asked for 60 days"},
        )
        assert revised.status_code == 201, revised.text
        revised_body = revised.json()
        assert revised_body["revision"] == 2
        assert revised_body["status"] == "DRAFT"
        assert revised_body["supersedes_sales_quote_id"] == approved.json()["id"]

        original = client.get(f"{SALES_QUOTES}/{approved.json()['id']}")
        assert original.status_code == 200
        assert original.json()["status"] == "APPROVED"
        assert original.json()["superseded_by_sales_quote_id"] == revised_body["id"]

        again = sales_action(
            client,
            csrf,
            approved.json(),
            "revisions",
            payload={"valid_until": str(FUTURE)},
        )
        assert again.status_code == 409, again.text
        assert error_code(again) == "CONFLICT"

    def test_approved_quote_cannot_be_withdrawn(
        self, world: SourcingWorld, approver: tuple[TestClient, str]
    ) -> None:
        client, csrf = world.client, world.csrf
        approver_client, approver_csrf = approver
        scenario = verified_scenario(world)
        drafted = create_sales_quote(
            client, csrf, scenario_id=scenario["id"], customer_id=world.buyer["id"]
        )
        submitted = sales_action(client, csrf, drafted.json(), "submit")
        approved = sales_action(approver_client, approver_csrf, submitted.json(), "approve")
        assert approved.status_code == 200, approved.text

        withdrawn = sales_action(client, csrf, approved.json(), "withdraw", payload={})
        assert withdrawn.status_code == 409, withdrawn.text
        assert error_code(withdrawn) == "INVALID_TRANSITION"


class TestTenantIsolationAndAudit:
    def test_another_company_cannot_read_sourcing_records(
        self,
        world: SourcingWorld,
        client_factory: Callable[..., TestClient],
        identity_world: IdentityWorld,
    ) -> None:
        outsider, _ = sign_in(
            client_factory,
            email=identity_world.email_a,
            company_id=identity_world.company_a,
        )

        rfq = outsider.get(f"{RFQS}/{world.rfq['id']}")
        assert rfq.status_code == 404, rfq.text
        assert error_code(rfq) == "NOT_FOUND"

        quote = outsider.get(f"{SUPPLIER_QUOTES}/{world.quote['id']}")
        assert quote.status_code == 404, quote.text

        listing = outsider.get(RFQS)
        assert listing.status_code == 200
        assert listing.json()["items"] == []

        listing_quotes = outsider.get(SUPPLIER_QUOTES)
        assert listing_quotes.status_code == 200
        assert listing_quotes.json()["items"] == []

    def test_workflow_actions_are_audited(
        self, world: SourcingWorld, migration_database: Database
    ) -> None:
        scenario = verified_scenario(world)
        drafted = create_sales_quote(
            world.client,
            world.csrf,
            scenario_id=scenario["id"],
            customer_id=world.buyer["id"],
        )
        assert drafted.status_code == 201, drafted.text

        with migration_database.transaction() as session:
            actions = set(
                session.execute(
                    text(
                        "SELECT DISTINCT action FROM touche.audit_record "
                        "WHERE company_id = :company_id"
                    ),
                    {"company_id": str(world.company_id)},
                ).scalars()
            )

        assert {
            "rfq.created",
            "rfq.prepared",
            "rfq.sent",
            "supplier_quote.recorded",
            "pricing_scenario.created",
            "sales_quote.created",
        } <= actions

    def test_negative_quantity_is_a_validation_error(self, world: SourcingWorld) -> None:
        response = record_quote(
            world.client,
            world.csrf,
            rfq_id=world.rfq["id"],
            items=[
                {
                    "product_id": world.first["id"],
                    "quantity": "-1.000",
                    "unit_price": "1.0000",
                }
            ],
        )

        assert response.status_code == 422, response.text
        assert error_code(response) == "VALIDATION_ERROR"

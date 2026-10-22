"""Stage 4 operations integration tests (live PostgreSQL, real runtime role).

The promises under test are commercial, not cosmetic:

* a deal becomes ``WON`` only through the order-conversion service, in one
  transaction, and only with documented customer acceptance of the exact
  approved revision;
* the order keeps the accepted commercial facts even after the catalogue or the
  quote changes;
* procurement is optional, evidenced and never silently "sent";
* a partial shipment never fulfils a whole order, and quantities cannot exceed
  what was ordered;
* documents are stored privately, hashed, versioned and readable only inside
  their own company and linked entity;
* a different company sees nothing, and a role without ``trade.write`` cannot
  create orders.
"""

from __future__ import annotations

import hashlib
import re
import shutil
import tempfile
from collections.abc import Callable, Iterator
from concurrent.futures import ThreadPoolExecutor
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
from decimal import Decimal
from pathlib import Path
from typing import Any
from uuid import uuid4

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient
from sqlalchemy import select, text

from app.core.config import Settings
from app.db.engine import Database
from app.db.models import AuditAction, AuditRecord, TradeDocument
from app.main import create_app
from app.security.permissions import Role
from app.services import admin
from tests.conftest import IdentityWorld
from tests.support import ORIGIN, csrf_from, csrf_headers, login
from tests.test_sourcing_api import (
    create_counterparty,
    create_deal,
    create_product,
    create_rfqs,
    create_sales_quote,
    create_scenario,
    error_code,
    etag,
    freight_component,
    record_quote,
    sales_action,
    scenario_payload,
    send_rfq,
)

pytestmark = pytest.mark.integration

API = "/api/v1"
DEALS = f"{API}/deals"
ORDERS = f"{API}/sales-orders"
PURCHASE_ORDERS = f"{API}/purchase-orders"
SHIPMENTS = f"{API}/shipments"
DOCUMENTS = f"{API}/documents"
OPERATIONS = f"{API}/operations/summary"

FUTURE = (datetime.now(tz=UTC) + timedelta(days=30)).date()
PDF_BYTES = b"%PDF-1.7\n1 0 obj\n<< /Type /Catalog >>\nendobj\ntrailer\n%%EOF\n"


def reason_of(response: Any) -> Any:
    details = response.json()["error"].get("details")
    return details.get("reason") if isinstance(details, dict) else details


def sign_in(
    client_factory: Callable[..., TestClient],
    *,
    email: str,
    company_id: Any | None = None,
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


def act(
    client: TestClient,
    csrf: str,
    path: str,
    payload: Any,
    *,
    if_match: str | None = None,
    key: str | None = None,
) -> Any:
    headers = {**csrf_headers(csrf), "Idempotency-Key": key or uuid4().hex}
    if if_match is not None:
        headers["If-Match"] = if_match
    return client.post(f"{API}{path}", json=payload, headers=headers)


@dataclass
class OrderWorld:
    """One approved quote for one deal, ready for acceptance and conversion."""

    client: TestClient
    csrf: str
    approver_client: TestClient
    approver_csrf: str
    buyer: dict[str, Any]
    supplier: dict[str, Any]
    product: dict[str, Any]
    deal: dict[str, Any]
    supplier_quote: dict[str, Any]
    quote: dict[str, Any]


@pytest.fixture(scope="session")
def document_storage_root() -> Iterator[Path]:
    """Private storage for this module, never the developer's real document root.

    ``tmp_path_factory`` is unusable on this workstation (the shared pytest temp
    directory is ACL-restricted), so the fixture creates its own directory under
    the backend's ignored ``var`` folder and removes it afterwards.
    """
    root = Path(tempfile.mkdtemp(prefix="stage4-documents-", dir=_var_root()))
    yield root
    shutil.rmtree(root, ignore_errors=True)


def _var_root() -> Path:
    root = Path(__file__).resolve().parents[1] / "var"
    root.mkdir(parents=True, exist_ok=True)
    return root


@pytest.fixture(scope="session")
def identity_app(test_settings: Settings, document_storage_root: Path) -> FastAPI:
    """App on the isolated database with documents redirected to a temp directory."""
    configured = test_settings.model_copy(
        update={"document_storage_path": document_storage_root}
    )
    return create_app(configured)


@pytest.fixture()
def client_factory(identity_app: FastAPI) -> Iterator[Callable[..., TestClient]]:
    clients: list[TestClient] = []

    def make(
        *, origin: str | None = ORIGIN, headers: dict[str, str] | None = None
    ) -> TestClient:
        default_headers = {"User-Agent": "pytest-touche", **(headers or {})}
        if origin is not None:
            default_headers["Origin"] = origin
        client = TestClient(identity_app, headers=default_headers, raise_server_exceptions=False)
        client.__enter__()
        clients.append(client)
        return client

    yield make
    for created in clients:
        created.__exit__(None, None, None)


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
    """Amina, approver in company B (finance.approve, no trade.write)."""
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


@pytest.fixture()
def world(
    trader: tuple[TestClient, str],
    approver: tuple[TestClient, str],
) -> OrderWorld:
    """Build an approved sales quote through the real Stage 3 endpoints."""
    client, csrf = trader
    approver_client, approver_csrf = approver
    supplier = create_counterparty(client, csrf, name="Supplier One")
    buyer = create_counterparty(client, csrf, name="Buyer Ltd", type_="buyer")
    product = create_product(client, csrf, sku="ALM-KERNEL")
    deal = create_deal(
        client, csrf, counterparty_id=buyer["id"], product_id=product["id"]
    )
    opened = act(
        client,
        csrf,
        f"/deals/{deal['id']}/transitions",
        {"to": "OPEN"},
        if_match=etag(int(deal["version"])),
    )
    assert opened.status_code == 200, opened.text
    deal = dict(opened.json())
    rfqs = create_rfqs(
        client,
        csrf,
        deal_id=deal["id"],
        supplier_ids=[supplier["id"]],
        product_ids=[product["id"]],
    )
    rfq = send_rfq(client, csrf, rfqs[0])
    supplier_quote = record_quote(
        client,
        csrf,
        rfq_id=rfq["id"],
        items=[{"product_id": product["id"], "quantity": "100.000", "unit_price": "1.6000"}],
    )
    assert supplier_quote.status_code == 201, supplier_quote.text
    supplier_quote_body = dict(supplier_quote.json())

    scenario = create_scenario(
        client,
        csrf,
        scenario_payload(
            supplier_quote_body["id"],
            margin_pct="20",
            components=[freight_component()],
        ),
    )
    assert scenario.status_code == 201, scenario.text

    drafted = create_sales_quote(
        client, csrf, scenario_id=scenario.json()["id"], customer_id=buyer["id"]
    )
    assert drafted.status_code == 201, drafted.text
    submitted = sales_action(client, csrf, drafted.json(), "submit")
    assert submitted.status_code == 200, submitted.text
    approved = sales_action(approver_client, approver_csrf, submitted.json(), "approve")
    assert approved.status_code == 200, approved.text
    return OrderWorld(
        client=client,
        csrf=csrf,
        approver_client=approver_client,
        approver_csrf=approver_csrf,
        buyer=buyer,
        supplier=supplier,
        product=product,
        deal=deal,
        supplier_quote=supplier_quote_body,
        quote=dict(approved.json()),
    )


def record_acceptance(
    world: OrderWorld,
    *,
    accepted_at: datetime | None = None,
    channel: str = "SIGNED_QUOTE",
    reference: str = "Customer PO ACME-4471",
) -> Any:
    return act(
        world.client,
        world.csrf,
        f"/deals/{world.deal['id']}/customer-acceptance",
        {
            "channel": channel,
            "accepted_at": (accepted_at or datetime.now(tz=UTC)).isoformat(),
            "accepted_by_name": "Dana Buyer",
            "evidence_reference": reference,
        },
    )


def convert(
    world: OrderWorld,
    *,
    acceptance_id: Any | None = None,
    key: str | None = None,
    model: str = "PURCHASE_RESALE",
    expected_total: str | None = None,
    notes: str | None = None,
) -> Any:
    payload: dict[str, Any] = {
        "sales_quote_id": world.quote["id"],
        "fulfilment_model": model,
    }
    if acceptance_id is not None:
        payload["acceptance_evidence_id"] = str(acceptance_id)
    if expected_total is not None:
        payload["expected_total"] = expected_total
    if notes is not None:
        payload["notes"] = notes
    return act(world.client, world.csrf, f"/deals/{world.deal['id']}/sales-order", payload, key=key)


def won(
    world: OrderWorld, *, model: str = "PURCHASE_RESALE"
) -> tuple[dict[str, Any], dict[str, Any]]:
    acceptance = record_acceptance(world)
    assert acceptance.status_code == 201, acceptance.text
    response = convert(world, acceptance_id=acceptance.json()["id"], model=model)
    assert response.status_code == 201, response.text
    return dict(response.json()), dict(acceptance.json())


def order_transition(
    world: OrderWorld, order: dict[str, Any], target: str, *, reason: str | None = None
) -> Any:
    payload: dict[str, Any] = {"target": target}
    if reason is not None:
        payload["reason"] = reason
    return act(
        world.client,
        world.csrf,
        f"/sales-orders/{order['id']}/transitions",
        payload,
        if_match=etag(int(order["version"])),
    )


def create_purchase_order(world: OrderWorld, order: dict[str, Any], **overrides: Any) -> Any:
    payload: dict[str, Any] = {
        "sales_order_id": order["id"],
        "supplier_id": world.supplier["id"],
        "supplier_quote_id": world.supplier_quote["id"],
        "incoterm": "CIF",
        "named_delivery_place": "Rotterdam, NL",
        "payment_terms": "30 days net",
        "expected_dispatch_date": str(FUTURE),
        "items": [
            {
                "product_id": world.product["id"],
                "quantity": "100.000",
                "unit": "kg",
                "unit_cost": "1.6000",
            }
        ],
    }
    payload.update(overrides)
    return act(world.client, world.csrf, "/purchase-orders", payload)


def po_transition(
    client: TestClient,
    csrf: str,
    purchase_order: dict[str, Any],
    target: str,
    **fields: Any,
) -> Any:
    return act(
        client,
        csrf,
        f"/purchase-orders/{purchase_order['id']}/transitions",
        {"target": target, **fields},
        if_match=etag(int(purchase_order["version"])),
    )


def plan_shipment(
    world: OrderWorld,
    order: dict[str, Any],
    *,
    quantity: str = "40.000",
    **overrides: Any,
) -> Any:
    payload: dict[str, Any] = {
        "sales_order_id": order["id"],
        "transport_mode": "SEA",
        "origin": "Jebel Ali, AE",
        "destination": "Rotterdam, NL",
        "carrier": "Maersk",
        "forwarder": "Kuehne+Nagel",
        "planned_dispatch_at": (datetime.now(tz=UTC) + timedelta(days=3)).isoformat(),
        "estimated_arrival_at": (datetime.now(tz=UTC) + timedelta(days=21)).isoformat(),
        "items": [{"sales_order_item_id": order["items"][0]["id"], "quantity": quantity}],
    }
    payload.update(overrides)
    return act(world.client, world.csrf, "/shipments", payload)


def ship_transition(
    world: OrderWorld, shipment: dict[str, Any], target: str, **fields: Any
) -> Any:
    return act(
        world.client,
        world.csrf,
        f"/shipments/{shipment['id']}/transitions",
        {"target": target, **fields},
        if_match=etag(int(shipment["version"])),
    )


def deliver(
    world: OrderWorld,
    shipment: dict[str, Any],
    *,
    evidence: str = "POD-2026-101",
) -> dict[str, Any]:
    """Walk a planned shipment through the real, evidence-checked milestones."""
    booked = ship_transition(world, shipment, "BOOKED")
    assert booked.status_code == 200, booked.text
    dispatched = ship_transition(
        world,
        booked.json(),
        "DISPATCHED",
        tracking_reference="MSKU1234567",
        tracking_source="MANUAL",
    )
    assert dispatched.status_code == 200, dispatched.text
    in_transit = ship_transition(world, dispatched.json(), "IN_TRANSIT")
    assert in_transit.status_code == 200, in_transit.text
    arrived = ship_transition(world, in_transit.json(), "ARRIVED")
    assert arrived.status_code == 200, arrived.text
    delivered = ship_transition(
        world, arrived.json(), "DELIVERED", delivery_evidence_reference=evidence
    )
    assert delivered.status_code == 200, delivered.text
    return dict(delivered.json())


def upload_document(
    world: OrderWorld,
    *,
    content: bytes = PDF_BYTES,
    filename: str = "pod.pdf",
    mime_type: str = "application/pdf",
    document_type: str = "DELIVERY_CONFIRMATION",
    linked_entity_type: str = "SALES_ORDER",
    linked_entity_id: Any,
    title: str = "Proof of delivery",
    supersedes_document_id: Any | None = None,
    key: str | None = None,
) -> Any:
    data: dict[str, str] = {
        "document_type": document_type,
        "linked_entity_type": linked_entity_type,
        "linked_entity_id": str(linked_entity_id),
        "title": title,
    }
    if supersedes_document_id is not None:
        data["supersedes_document_id"] = str(supersedes_document_id)
    return world.client.post(
        DOCUMENTS,
        data=data,
        files={"file": (filename, content, mime_type)},
        headers={**csrf_headers(world.csrf), "Idempotency-Key": key or uuid4().hex},
    )


class TestOrderConversionGate:
    """An internally approved quote is not a customer order."""

    def test_conversion_without_customer_acceptance_is_refused(self, world: OrderWorld) -> None:
        response = convert(world)
        # The schema itself refuses to describe an order that carries no
        # acceptance at all; there is no payload that means "skip the gate".
        assert response.status_code == 422, response.text
        assert error_code(response) == "VALIDATION_ERROR"
        assert "acceptance" in response.json()["error"]["details"][0]["message"].lower()

        deal = world.client.get(f"{DEALS}/{world.deal['id']}")
        assert deal.status_code == 200
        assert deal.json()["status"] != "WON"
        listing = world.client.get(ORDERS, params={"deal_id": world.deal["id"]})
        assert listing.status_code == 200
        assert listing.json()["items"] == []

    def test_unknown_acceptance_evidence_is_refused(self, world: OrderWorld) -> None:
        response = convert(world, acceptance_id=uuid4())
        assert response.status_code == 400, response.text
        assert error_code(response) == "BAD_REQUEST"
        assert reason_of(response) == "ACCEPTANCE_NOT_FOUND"

    def test_acceptance_cannot_predate_the_internal_approval(self, world: OrderWorld) -> None:
        response = record_acceptance(
            world, accepted_at=datetime.now(tz=UTC) - timedelta(days=1)
        )
        assert response.status_code == 400, response.text
        assert response.json()["error"]["details"][0]["field"] == "accepted_at"

    def test_internal_approval_alone_creates_no_order(self, world: OrderWorld) -> None:
        assert world.quote["status"] == "APPROVED"
        listing = world.client.get(ORDERS)
        assert listing.status_code == 200
        assert listing.json()["items"] == []
        acceptances = world.client.get(f"{DEALS}/{world.deal['id']}/customer-acceptance")
        assert acceptances.json()["items"] == []
        # A recorded acceptance with no evidence reference is not offered by the
        # schema at all, so an internal approval can never be mistaken for one.
        refused = act(
            world.client,
            world.csrf,
            f"/deals/{world.deal['id']}/customer-acceptance",
            {
                "channel": "EMAIL",
                "accepted_at": datetime.now(tz=UTC).isoformat(),
                "accepted_by_name": "Dana Buyer",
                "evidence_reference": "  ",
            },
        )
        assert refused.status_code == 422, refused.text
        assert error_code(refused) == "VALIDATION_ERROR"


class TestOrderConversion:
    def test_conversion_creates_order_and_wins_deal_atomically(self, world: OrderWorld) -> None:
        order, acceptance = won(world)

        assert order["status"] == "CONFIRMED"
        assert order["sales_quote_revision"] == 1
        assert order["acceptance_evidence_id"] == acceptance["id"]
        assert order["currency"] == "USD"
        assert order["incoterm"] == "CIF"
        assert order["named_delivery_place"] == "Rotterdam, NL"
        assert order["payment_terms_snapshot"] == "30 days net"
        assert order["fulfilment_model"] == "PURCHASE_RESALE"
        assert order["allowed_transitions"] == ["IN_FULFILLMENT", "CANCELLED"]

        quote_item = world.quote["items"][0]
        line = order["items"][0]
        assert Decimal(str(line["quantity"])) == Decimal("100.000")
        assert line["unit"] == "kg"
        assert Decimal(str(line["unit_price"])) == Decimal(str(quote_item["unit_price"]))
        assert Decimal(str(order["order_total"])) == Decimal(str(line["line_total"]))

        snapshot = order["accepted_terms"]
        assert snapshot["sales_quote_id"] == world.quote["id"]
        assert snapshot["revision"] == 1
        assert snapshot["acceptance_evidence_id"] == acceptance["id"]
        assert snapshot["acceptance_channel"] == "SIGNED_QUOTE"
        assert snapshot["items"][0]["unit_price"] == str(quote_item["unit_price"])

        deal = world.client.get(f"{DEALS}/{world.deal['id']}")
        assert deal.status_code == 200
        assert deal.json()["status"] == "WON"
        listing = world.client.get(ORDERS, params={"deal_id": world.deal["id"]})
        assert [item["id"] for item in listing.json()["items"]] == [order["id"]]

    def test_same_key_replays_the_original_order(self, world: OrderWorld) -> None:
        acceptance = record_acceptance(world)
        assert acceptance.status_code == 201, acceptance.text
        key = "convert-replay-key"
        first = convert(world, acceptance_id=acceptance.json()["id"], key=key)
        assert first.status_code == 201, first.text

        second = convert(world, acceptance_id=acceptance.json()["id"], key=key)
        assert second.status_code == 201, second.text
        assert second.headers.get("Idempotent-Replay") == "true"
        assert second.json() == first.json()

    def test_same_key_with_a_changed_payload_conflicts(self, world: OrderWorld) -> None:
        acceptance = record_acceptance(world)
        key = "convert-changed-payload"
        first = convert(world, acceptance_id=acceptance.json()["id"], key=key)
        assert first.status_code == 201, first.text

        changed = convert(
            world,
            acceptance_id=acceptance.json()["id"],
            key=key,
            notes="A different request body",
        )
        assert changed.status_code == 409, changed.text
        assert error_code(changed) == "IDEMPOTENCY_CONFLICT"


    def test_a_second_conversion_key_after_won_is_refused(self, world: OrderWorld) -> None:
        order, acceptance = won(world)
        response = convert(world, acceptance_id=acceptance["id"], key="another-key")
        assert response.status_code == 409, response.text
        assert error_code(response) == "ALREADY_WON"

        listing = world.client.get(ORDERS, params={"deal_id": world.deal["id"]})
        assert [item["id"] for item in listing.json()["items"]] == [order["id"]]

    def test_concurrent_conversions_create_exactly_one_order(
        self,
        world: OrderWorld,
        identity_world: IdentityWorld,
        client_factory: Callable[..., TestClient],
    ) -> None:
        acceptance = record_acceptance(world)
        assert acceptance.status_code == 201, acceptance.text
        other_client, other_csrf = sign_in(client_factory, email=identity_world.email_b)
        payload = {
            "sales_quote_id": world.quote["id"],
            "acceptance_evidence_id": acceptance.json()["id"],
        }

        def attempt(client: TestClient, csrf: str, key: str) -> Any:
            return act(
                client,
                csrf,
                f"/deals/{world.deal['id']}/sales-order",
                payload,
                key=key,
            )

        with ThreadPoolExecutor(max_workers=2) as pool:
            futures = [
                pool.submit(attempt, world.client, world.csrf, "concurrent-one"),
                pool.submit(attempt, other_client, other_csrf, "concurrent-two"),
            ]
            statuses = sorted(future.result().status_code for future in futures)

        assert statuses == [201, 409]
        listing = world.client.get(ORDERS, params={"deal_id": world.deal["id"]})
        assert len(listing.json()["items"]) == 1

    def test_won_is_unreachable_outside_the_conversion_service(self, world: OrderWorld) -> None:
        direct = act(
            world.client,
            world.csrf,
            f"/deals/{world.deal['id']}/transitions",
            {"to": "WON"},
            if_match=etag(int(world.deal["version"])),
        )
        assert direct.status_code == 409, direct.text
        assert error_code(direct) == "TRANSITION_DISABLED"

        won(world)
        current = world.client.get(f"{DEALS}/{world.deal['id']}").json()
        again = act(
            world.client,
            world.csrf,
            f"/deals/{world.deal['id']}/transitions",
            {"to": "LOST", "reason": "No longer relevant"},
            if_match=etag(int(current["version"])),
        )
        assert again.status_code == 409, again.text
        assert error_code(again) == "ALREADY_WON"


    def test_terms_stay_frozen_after_quote_revision_and_catalogue_change(
        self, world: OrderWorld, migration_database: Database
    ) -> None:
        order, _ = won(world)
        revised = sales_action(
            world.client,
            world.csrf,
            world.quote,
            "revisions",
            payload={"valid_until": str(FUTURE), "reason": "Customer asked for a later date"},
        )
        assert revised.status_code == 201, revised.text
        assert revised.json()["revision"] == 2

        with migration_database.transaction() as session:
            session.execute(
                text("UPDATE touche.product SET unit_price = 99.0000 WHERE id = :id"),
                {"id": world.product["id"]},
            )

        refreshed = world.client.get(f"{ORDERS}/{order['id']}")
        assert refreshed.status_code == 200, refreshed.text
        body = refreshed.json()
        assert body["sales_quote_revision"] == 1
        assert body["items"][0]["unit_price"] == order["items"][0]["unit_price"]
        assert body["order_total"] == order["order_total"]
        assert body["accepted_terms"] == order["accepted_terms"]


class TestOrderLifecycle:
    def test_cancellation_requires_a_reason_and_preserves_the_snapshot(
        self, world: OrderWorld
    ) -> None:
        order, _ = won(world)
        refused = order_transition(world, order, "CANCELLED")
        assert refused.status_code == 422, refused.text
        assert error_code(refused) == "REASON_REQUIRED"

        cancelled = order_transition(
            world, order, "CANCELLED", reason="Customer withdrew the order"
        )
        assert cancelled.status_code == 200, cancelled.text
        body = cancelled.json()
        assert body["status"] == "CANCELLED"
        assert body["cancellation_reason"] == "Customer withdrew the order"
        assert body["cancelled_at"] is not None
        assert body["accepted_terms"] == order["accepted_terms"]

        revived = order_transition(world, body, "CONFIRMED")
        assert revived.status_code == 409, revived.text
        assert error_code(revived) == "INVALID_TRANSITION"

    def test_amendment_is_recorded_without_rewriting_the_accepted_terms(
        self, world: OrderWorld
    ) -> None:
        order, _ = won(world)
        amended = act(
            world.client,
            world.csrf,
            f"/sales-orders/{order['id']}/amendments",
            {"reason": "Customer asked for 60 days", "payment_terms": "60 days net"},
            if_match=etag(int(order["version"])),
        )
        assert amended.status_code == 200, amended.text
        body = amended.json()
        assert body["payment_terms_snapshot"] == "60 days net"
        assert body["accepted_terms"]["payment_terms"] == "30 days net"
        assert len(body["amendments"]) == 1
        assert body["amendments"][0]["changes"]["payment_terms"] == {
            "from": "30 days net",
            "to": "60 days net",
        }

        derived = order_transition(world, body, "FULFILLED")
        assert derived.status_code == 409, derived.text
        assert error_code(derived) == "INVALID_TRANSITION"

    def test_brokerage_order_does_not_carry_procurement(self, world: OrderWorld) -> None:
        order, _ = won(world, model="BROKERAGE")
        assert order["fulfilment_model"] == "BROKERAGE"
        response = create_purchase_order(world, order)
        assert response.status_code == 409, response.text
        assert reason_of(response) == "PROCUREMENT_NOT_APPLICABLE"


class TestProcurement:
    def test_purchase_order_requires_approval_and_dispatch_evidence(
        self, world: OrderWorld
    ) -> None:
        order, _ = won(world)
        created = create_purchase_order(world, order)
        assert created.status_code == 201, created.text
        purchase_order = created.json()
        assert purchase_order["status"] == "DRAFT"
        assert purchase_order["allowed_transitions"] == ["APPROVED", "CANCELLED"]
        assert purchase_order["supplier_quote_id"] == world.supplier_quote["id"]
        assert Decimal(str(purchase_order["total_cost"])) == Decimal("160.00")
        assert purchase_order["dispatched_at"] is None

        by_trader = po_transition(world.client, world.csrf, purchase_order, "APPROVED")
        assert by_trader.status_code == 403, by_trader.text
        assert error_code(by_trader) == "FORBIDDEN"

        approved = po_transition(
            world.approver_client, world.approver_csrf, purchase_order, "APPROVED"
        )
        assert approved.status_code == 200, approved.text
        assert approved.json()["status"] == "APPROVED"
        assert approved.json()["approved_by"] is not None

        missing = po_transition(world.client, world.csrf, approved.json(), "RECORDED_SENT")
        assert missing.status_code == 400, missing.text
        fields = {item["field"] for item in missing.json()["error"]["details"]}
        assert fields == {"dispatch_channel", "dispatch_reference"}

        sent = po_transition(
            world.client,
            world.csrf,
            approved.json(),
            "RECORDED_SENT",
            dispatch_channel="EMAIL",
            dispatch_reference="SMTP-msg-4471",
        )
        assert sent.status_code == 200, sent.text
        assert sent.json()["status"] == "RECORDED_SENT"
        assert sent.json()["dispatch_channel"] == "EMAIL"
        assert sent.json()["dispatched_at"] is not None

        unconfirmed = po_transition(
            world.client, world.csrf, sent.json(), "SUPPLIER_CONFIRMED"
        )
        assert unconfirmed.status_code == 400, unconfirmed.text

        confirmed = po_transition(
            world.client,
            world.csrf,
            sent.json(),
            "SUPPLIER_CONFIRMED",
            supplier_confirmation_reference="SUP-ACK-9931",
            evidence_reference="email: supplier acknowledgement",
        )
        assert confirmed.status_code == 200, confirmed.text
        assert confirmed.json()["supplier_confirmed_at"] is not None
        assert (
            confirmed.json()["supplier_confirmation_reference"] == "SUP-ACK-9931"
        )

    def test_purchase_orders_are_tenant_scoped(
        self,
        world: OrderWorld,
        identity_world: IdentityWorld,
        client_factory: Callable[..., TestClient],
    ) -> None:
        order, _ = won(world)
        purchase_order = create_purchase_order(world, order).json()
        outsider, _ = sign_in(
            client_factory,
            email=identity_world.email_a,
            company_id=identity_world.company_a,
        )
        assert outsider.get(f"{PURCHASE_ORDERS}/{purchase_order['id']}").status_code == 404
        assert outsider.get(PURCHASE_ORDERS).json()["items"] == []
        assert outsider.get(f"{ORDERS}/{order['id']}").status_code == 404


class TestShipments:
    def test_partial_shipment_never_fulfils_the_whole_order(self, world: OrderWorld) -> None:
        order, _ = won(world)
        planned = plan_shipment(world, order, quantity="40.000")
        assert planned.status_code == 201, planned.text
        shipment = planned.json()
        assert shipment["status"] == "PLANNED"
        assert Decimal(str(shipment["items"][0]["quantity"])) == Decimal("40.000")
        assert shipment["items"][0]["delivered_quantity"] == "0"

        delivered = deliver(world, shipment)
        assert delivered["status"] == "DELIVERED"
        assert delivered["actual_dispatch_at"] is not None
        assert delivered["actual_arrival_at"] is not None
        assert delivered["delivered_at"] is not None
        assert delivered["delivery_evidence_reference"] == "POD-2026-101"
        assert [event["event_type"] for event in delivered["events"]] == [
            "PLANNED",
            "BOOKED",
            "DISPATCHED",
            "IN_TRANSIT",
            "ARRIVED",
            "DELIVERED",
        ]

        fulfilment = world.client.get(f"{ORDERS}/{order['id']}/fulfilment")
        assert fulfilment.status_code == 200, fulfilment.text
        line = fulfilment.json()["lines"][0]
        assert Decimal(str(line["ordered"])) == Decimal("100.000")
        assert Decimal(str(line["delivered"])) == Decimal("40.000")
        assert Decimal(str(line["remaining"])) == Decimal("60.000")
        assert fulfilment.json()["fully_delivered"] is False

        refreshed = world.client.get(f"{ORDERS}/{order['id']}").json()
        assert refreshed["status"] == "IN_FULFILLMENT"

    def test_over_allocation_is_refused_and_full_delivery_fulfils(
        self, world: OrderWorld
    ) -> None:
        order, _ = won(world)
        first = plan_shipment(world, order, quantity="40.000")
        assert first.status_code == 201, first.text

        over = plan_shipment(world, order, quantity="61.000")
        assert over.status_code == 400, over.text
        assert over.json()["error"]["details"]["remaining"] == "60.000"

        remaining = plan_shipment(world, order, quantity="60.000")
        assert remaining.status_code == 201, remaining.text

        deliver(world, first.json(), evidence="POD-A")
        assert (
            world.client.get(f"{ORDERS}/{order['id']}").json()["status"]
            == "IN_FULFILLMENT"
        )

        deliver(world, remaining.json(), evidence="POD-B")
        fulfilment = world.client.get(f"{ORDERS}/{order['id']}/fulfilment").json()
        assert fulfilment["fully_delivered"] is True
        assert fulfilment["delivered_any"] is True
        assert Decimal(str(fulfilment["completion_ratio"])) == Decimal("1")
        assert world.client.get(f"{ORDERS}/{order['id']}").json()["status"] == "FULFILLED"

    def test_movement_requires_evidence_and_valid_transitions(
        self, world: OrderWorld
    ) -> None:
        order, _ = won(world)
        shipment = plan_shipment(world, order).json()

        jumped = ship_transition(
            world, shipment, "DELIVERED", delivery_evidence_reference="POD-1"
        )
        assert jumped.status_code == 409, jumped.text
        assert error_code(jumped) == "INVALID_TRANSITION"

        booked = ship_transition(world, shipment, "BOOKED")
        assert booked.status_code == 200, booked.text

        no_tracking = ship_transition(world, booked.json(), "DISPATCHED")
        assert no_tracking.status_code == 400, no_tracking.text
        assert no_tracking.json()["error"]["details"][0]["field"] == "tracking_reference"

        dispatched = ship_transition(
            world, booked.json(), "DISPATCHED", tracking_reference="MSKU7654321"
        )
        assert dispatched.status_code == 200, dispatched.text
        in_transit = ship_transition(world, dispatched.json(), "IN_TRANSIT")
        assert in_transit.status_code == 200, in_transit.text
        arrived = ship_transition(world, in_transit.json(), "ARRIVED")
        assert arrived.status_code == 200, arrived.text

        no_evidence = ship_transition(world, arrived.json(), "DELIVERED")
        assert no_evidence.status_code == 400, no_evidence.text
        assert (
            no_evidence.json()["error"]["details"][0]["field"]
            == "delivery_evidence_reference"
        )
        assert (
            world.client.get(f"{ORDERS}/{order['id']}").json()["status"]
            == "IN_FULFILLMENT"
        )


    def test_cancelling_a_shipment_releases_its_allocation(self, world: OrderWorld) -> None:
        order, _ = won(world)
        shipment = plan_shipment(world, order, quantity="100.000")
        assert shipment.status_code == 201, shipment.text
        allocated = world.client.get(f"{ORDERS}/{order['id']}/fulfilment").json()
        assert Decimal(str(allocated["lines"][0]["allocated"])) == Decimal("100.000")

        cancelled = ship_transition(
            world, shipment.json(), "CANCELLED", reason="Booking cancelled by carrier"
        )
        assert cancelled.status_code == 200, cancelled.text
        assert cancelled.json()["status"] == "CANCELLED"
        assert cancelled.json()["cancellation_reason"] == "Booking cancelled by carrier"

        released = world.client.get(f"{ORDERS}/{order['id']}/fulfilment").json()
        assert Decimal(str(released["lines"][0]["allocated"])) == Decimal("0.000")
        replanned = plan_shipment(world, order, quantity="100.000")
        assert replanned.status_code == 201, replanned.text

    def test_cost_provenance_references_and_documented_delay(self, world: OrderWorld) -> None:
        order, _ = won(world)
        rejected = plan_shipment(
            world,
            order,
            items=[
                {
                    "sales_order_item_id": order["items"][0]["id"],
                    "quantity": "10.000",
                    "unit": "mt",
                }
            ],
        )
        assert rejected.status_code == 422, rejected.text
        assert error_code(rejected) == "VALIDATION_ERROR"

        past = (datetime.now(tz=UTC) - timedelta(days=4)).isoformat()
        planned = plan_shipment(world, order, estimated_arrival_at=past)
        assert planned.status_code == 201, planned.text
        shipment = planned.json()
        assert shipment["is_delayed"] is True

        quoted = act(
            world.client,
            world.csrf,
            f"/shipments/{shipment['id']}/costs",
            {
                "cost_type": "FREIGHT",
                "stage": "QUOTED",
                "amount": "480.00",
                "currency": "USD",
                "reference": "freight-quote-4471",
            },
        )
        assert quoted.status_code in (200, 201), quoted.text
        incurred = act(
            world.client,
            world.csrf,
            f"/shipments/{shipment['id']}/costs",
            {
                "cost_type": "FREIGHT",
                "stage": "INCURRED",
                "amount": "512.50",
                "currency": "USD",
                "reference": "freight-invoice-9902",
            },
        )
        assert incurred.status_code in (200, 201), incurred.text

        reference = act(
            world.client,
            world.csrf,
            f"/shipments/{shipment['id']}/references",
            {
                "reference_type": "CONTAINER",
                "reference_value": "MSKU1234567",
                "provenance": "DOCUMENT_EVIDENCE",
            },
        )
        assert reference.status_code in (200, 201), reference.text

        refreshed = world.client.get(f"{SHIPMENTS}/{shipment['id']}").json()
        assert [cost["stage"] for cost in refreshed["costs"]] == ["QUOTED", "INCURRED"]
        assert refreshed["references"][0]["provenance"] == "DOCUMENT_EVIDENCE"
        assert Decimal(str(refreshed["costs"][1]["amount"])) == Decimal("512.50")


class TestDocuments:
    def test_upload_download_versions_and_archive(self, world: OrderWorld) -> None:
        order, _ = won(world)
        first = upload_document(world, linked_entity_id=order["id"])
        assert first.status_code == 201, first.text
        document = first.json()
        assert document["version"] == 1
        assert document["sha256"] == hashlib.sha256(PDF_BYTES).hexdigest()
        assert document["size_bytes"] == len(PDF_BYTES)
        assert document["verification_status"] == "UNVERIFIED"
        assert document["download_path"] == f"/documents/{document['id']}/download"

        download = world.client.get(f"{DOCUMENTS}/{document['id']}/download")
        assert download.status_code == 200, download.text
        assert download.content == PDF_BYTES
        assert download.headers["content-type"] == "application/pdf"
        assert "attachment" in download.headers["content-disposition"]
        assert download.headers["x-document-sha256"] == document["sha256"]
        assert download.headers["x-content-type-options"] == "nosniff"

        revision = PDF_BYTES + b"\n% revision 2\n"
        second = upload_document(
            world,
            linked_entity_id=order["id"],
            supersedes_document_id=document["id"],
            content=revision,
            title="Proof of delivery v2",
        )
        assert second.status_code == 201, second.text
        latest = second.json()
        assert latest["version"] == 2
        assert latest["supersedes_document_id"] == document["id"]
        assert latest["sha256"] == hashlib.sha256(revision).hexdigest()

        archived_first = world.client.get(f"{DOCUMENTS}/{document['id']}")
        assert archived_first.json()["status"] == "ARCHIVED"
        history = world.client.get(f"{DOCUMENTS}/{latest['id']}/history")
        assert history.status_code == 200
        assert [item["version"] for item in history.json()["items"]] == [1, 2]

        archived = act(
            world.client,
            world.csrf,
            f"/documents/{latest['id']}/archive",
            {"reason": "Superseded by a corrected copy"},
        )
        assert archived.status_code == 200, archived.text
        assert archived.json()["status"] == "ARCHIVED"

        refused = world.client.get(f"{DOCUMENTS}/{latest['id']}/download")
        assert refused.status_code == 409, refused.text
        assert reason_of(refused) == "DOCUMENT_ARCHIVED"


    def test_upload_rejects_types_size_and_foreign_entities(
        self,
        world: OrderWorld,
        identity_world: IdentityWorld,
        client_factory: Callable[..., TestClient],
        identity_app: FastAPI,
    ) -> None:
        order, _ = won(world)
        unsupported = upload_document(
            world,
            linked_entity_id=order["id"],
            filename="payload.html",
            mime_type="text/html",
            content=b"<html><script>alert(1)</script></html>",
        )
        assert unsupported.status_code == 400, unsupported.text
        assert (
            unsupported.json()["error"]["details"]["reason"]
            == "UNSUPPORTED_CONTENT_TYPE"
        )

        foreign_link = upload_document(world, linked_entity_id=uuid4())
        assert foreign_link.status_code == 404, foreign_link.text

        outsider_client, _ = sign_in(
            client_factory,
            email=identity_world.email_a,
            company_id=identity_world.company_a,
        )
        assert outsider_client.get(DOCUMENTS).json()["items"] == []

        settings = identity_app.state.settings
        original = settings.document_max_bytes
        settings.document_max_bytes = 1024
        try:
            oversized = upload_document(
                world, linked_entity_id=order["id"], content=PDF_BYTES + b"0" * 2048
            )
            assert oversized.status_code == 413, oversized.text
            assert error_code(oversized) == "PAYLOAD_TOO_LARGE"
        finally:
            settings.document_max_bytes = original

    def test_storage_keys_are_server_generated_and_corruption_is_refused(
        self,
        world: OrderWorld,
        migration_database: Database,
        document_storage_root: Path,
    ) -> None:
        order, _ = won(world)
        uploaded = upload_document(
            world, linked_entity_id=order["id"], filename="../../etc/passwd.pdf"
        )
        assert uploaded.status_code == 201, uploaded.text
        document = uploaded.json()
        assert document["original_filename"] == "passwd.pdf"

        with migration_database.transaction() as session:
            storage_key = session.execute(
                select(TradeDocument.storage_key).where(
                    TradeDocument.id == document["id"]
                )
            ).scalar_one()
        assert re.fullmatch(
            r"[0-9a-f-]{36}/[0-9a-f-]{36}/v1-[0-9a-f]{16}\.pdf", storage_key
        )
        assert ".." not in storage_key

        download = world.client.get(f"{DOCUMENTS}/{document['id']}/download")
        disposition = download.headers["content-disposition"]
        assert "attachment" in disposition
        assert ".." not in disposition
        assert "etc/passwd" not in disposition

        stored = document_storage_root / storage_key
        assert stored.is_file()
        stored.write_bytes(b"tampered content")
        corrupted = world.client.get(f"{DOCUMENTS}/{document['id']}/download")
        assert corrupted.status_code == 409, corrupted.text
        assert reason_of(corrupted) == "DOCUMENT_CHECKSUM_MISMATCH"

    def test_draft_previews_are_labelled_and_not_legal_documents(
        self, world: OrderWorld
    ) -> None:
        order, _ = won(world)
        preview = world.client.get(
            f"{ORDERS}/{order['id']}/documents/preview",
            params={"kind": "commercial_invoice"},
        )
        assert preview.status_code == 200, preview.text
        body = preview.json()
        assert body["header"]["is_draft"] is True
        assert "not a legally issued" in body["header"]["legal_notice"]
        assert body["header"]["document_number"] == f"DRAFT-{order['order_number']}"
        assert body["lines"][0]["sku"] == order["items"][0]["sku"]
        assert Decimal(body["lines"][0]["quantity"]) == Decimal("100.000")

        shipment = plan_shipment(world, order, quantity="40.000")
        assert shipment.status_code == 201, shipment.text
        packing = world.client.get(
            f"{ORDERS}/{order['id']}/documents/preview",
            params={"kind": "packing_list", "shipment_id": shipment.json()["id"]},
        )
        assert packing.status_code == 200, packing.text
        assert packing.json()["header"]["document_label"] == "Packing list (draft)"
        assert Decimal(packing.json()["lines"][0]["shipment_quantity"]) == Decimal(
            "40.000"
        )


class TestOperationsAndIsolation:
    def test_operations_summary_reflects_real_rows(self, world: OrderWorld) -> None:
        order, _ = won(world)
        shipment = plan_shipment(world, order, quantity="10.000")
        assert shipment.status_code == 201, shipment.text
        uploaded = upload_document(world, linked_entity_id=order["id"])
        assert uploaded.status_code == 201, uploaded.text

        summary = world.client.get(OPERATIONS)
        assert summary.status_code == 200, summary.text
        body = summary.json()
        assert body["orders_total"] == 1
        assert body["orders_confirmed"] == 1
        assert body["orders_in_fulfillment"] == 0
        assert body["purchase_orders_total"] == 0
        assert body["active_shipments"] == 1
        assert body["documents_total"] == 1
        assert body["delivered_shipments"] == 0
        assert body["delivered_shipments_without_evidence"] == 0

        assert len(body["order_value_by_currency"]) == 1
        entry = body["order_value_by_currency"][0]
        assert entry["currency"] == "USD"
        assert entry["order_count"] == 1
        assert Decimal(str(entry["total_value"])) == Decimal(str(order["order_total"]))

    def test_other_companies_see_no_operational_records(
        self,
        world: OrderWorld,
        identity_world: IdentityWorld,
        client_factory: Callable[..., TestClient],
    ) -> None:
        order, _ = won(world)
        shipment = plan_shipment(world, order)
        assert shipment.status_code == 201, shipment.text
        document = upload_document(world, linked_entity_id=order["id"])
        assert document.status_code == 201, document.text

        outsider, _ = sign_in(
            client_factory,
            email=identity_world.email_a,
            company_id=identity_world.company_a,
        )
        assert outsider.get(f"{ORDERS}/{order['id']}").status_code == 404
        assert outsider.get(f"{SHIPMENTS}/{shipment.json()['id']}").status_code == 404
        assert outsider.get(f"{DOCUMENTS}/{document.json()['id']}").status_code == 404
        assert (
            outsider.get(f"{DOCUMENTS}/{document.json()['id']}/download").status_code
            == 404
        )
        for path in (ORDERS, PURCHASE_ORDERS, SHIPMENTS, DOCUMENTS):
            listing = outsider.get(path)
            assert listing.status_code == 200
            assert listing.json()["items"] == []

    def test_role_without_trade_write_cannot_convert(self, world: OrderWorld) -> None:
        response = act(
            world.approver_client,
            world.approver_csrf,
            f"/deals/{world.deal['id']}/sales-order",
            {"sales_quote_id": world.quote["id"]},
        )
        assert response.status_code == 403, response.text
        assert error_code(response) == "FORBIDDEN"

    def test_audit_records_the_irreversible_actions(
        self, world: OrderWorld, migration_database: Database
    ) -> None:
        order, acceptance = won(world)
        document = upload_document(world, linked_entity_id=order["id"])
        assert document.status_code == 201, document.text
        document_id = document.json()["id"]
        assert world.client.get(f"{DOCUMENTS}/{document_id}/download").status_code == 200

        with migration_database.transaction() as session:
            rows = (
                session.execute(
                    select(AuditRecord)
                    .where(
                        AuditRecord.resource_id.in_(
                            [
                                order["id"],
                                world.deal["id"],
                                document_id,
                                acceptance["id"],
                            ]
                        )
                    )
                    .order_by(AuditRecord.occurred_at)
                )
                .scalars()
                .all()
            )
        actions = {AuditAction(row.action) for row in rows}
        assert AuditAction.SALES_ORDER_CREATED in actions
        assert AuditAction.DEAL_WON in actions
        assert AuditAction.CUSTOMER_ACCEPTANCE_RECORDED in actions
        assert AuditAction.DOCUMENT_UPLOADED in actions
        assert AuditAction.DOCUMENT_DOWNLOADED in actions
        for row in rows:
            assert row.actor_id is not None
            assert row.occurred_at is not None
        assert any(row.resource_id == acceptance["id"] for row in rows)












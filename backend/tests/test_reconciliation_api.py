"""Stage 5D authenticated reconciliation integration tests.

A local Finance-shaped HTTP server is used. It is not the live Finance
application. The tests use real Commerce sessions, the isolated PostgreSQL test
database, real Stage 3/4 order records and the runtime database role.
"""

from __future__ import annotations

import json
import threading
from collections.abc import Callable, Iterator
from dataclasses import dataclass
from datetime import UTC, datetime
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from typing import Any, ClassVar
from uuid import uuid4

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient
from pydantic import SecretStr
from sqlalchemy import select, text

from app.core.config import Settings
from app.db.engine import Database
from app.db.models import (
    AuditAction,
    AuditRecord,
    FinanceCompanyMapping,
)
from app.security.permissions import Permission, Role, has_permission
from app.services import admin
from app.services.finance_mapping import set_verified_mapping
from tests.conftest import IdentityWorld
from tests.test_finance_api import sign_in
from tests.test_operations_api import (
    OrderWorld,
    act,
    create_purchase_order,
    plan_shipment,
    po_transition,
    won,
)
from tests.test_sourcing_api import (
    create_counterparty,
    create_deal,
    create_product,
    create_rfqs,
    create_sales_quote,
    create_scenario,
    freight_component,
    record_quote,
    sales_action,
    scenario_payload,
    send_rfq,
)
from tests.test_sourcing_api import (
    etag as sourcing_etag,
)

pytestmark = pytest.mark.integration


@pytest.fixture()
def trader(
    identity_world: IdentityWorld, client_factory: Callable[..., TestClient]
) -> tuple[TestClient, str]:
    return sign_in(client_factory, email=identity_world.email_b)


@pytest.fixture()
def approver(
    identity_world: IdentityWorld,
    migration_database: Database,
    client_factory: Callable[..., TestClient],
) -> tuple[TestClient, str]:
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
    deal = create_deal(client, csrf, counterparty_id=buyer["id"], product_id=product["id"])
    opened = act(
        client,
        csrf,
        f"/deals/{deal['id']}/transitions",
        {"to": "OPEN"},
        if_match=sourcing_etag(int(deal["version"])),
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
        items=[
            {
                "product_id": product["id"],
                "quantity": "100.000",
                "unit_price": "1.6000",
            }
        ],
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


API = "/api/v1"
RECONCILIATION = f"{API}/finance/reconciliation"
RUNS = f"{RECONCILIATION}/runs"
EVIDENCE = f"{API}/finance/evidence-links"
REVIEWS = f"{API}/finance/reviews"
DISCREPANCIES = f"{API}/finance/discrepancies"


def _money(amount: str) -> dict[str, Any]:
    return {"amount": amount, "amount_kurus": round(float(amount) * 100)}


def _envelope(data: dict[str, Any], request_id: str) -> bytes:
    return json.dumps(
        {
            "data": data,
            "meta": {
                "request_id": request_id,
                "contract_version": "1",
                "generated_at": datetime.now(tz=UTC).isoformat(),
                "source": "finance_ledger",
                "read_only": True,
            },
        }
    ).encode("utf-8")


@dataclass
class FinanceStub:
    server: ThreadingHTTPServer
    receivable_amount: str = "240.00"
    payable_amount: str = "100.00"

    @property
    def base_url(self) -> str:
        host = str(self.server.server_address[0])
        port = int(self.server.server_address[1])
        return f"http://{host}:{port}"


class ReconciliationFinanceHandler(BaseHTTPRequestHandler):
    server_version = "ToucheFinans/1.0"
    stub: ClassVar[FinanceStub]
    calls: ClassVar[list[tuple[str, str]]] = []

    def log_message(self, format: str, *args: object) -> None:
        return

    def do_GET(self) -> None:
        type(self).calls.append(("GET", self.path))
        path = self.path.split("?", 1)[0]
        if path == "/api/integration/v1/health":
            payload = _envelope({"status": "ok", "read_only": True, "mode": "ro"}, "fin-health")
        elif path == "/api/integration/v1/capabilities":
            payload = _envelope(
                {
                    "contract_version": "1",
                    "enabled": True,
                    "read_only": True,
                    "scopes": ["finance.read"],
                    "company_ids": ["gursar_mimarlik"],
                    "max_page": 200,
                    "endpoints": ["GET /api/integration/v1/health"],
                    "currency_support": {
                        "mode": "per_request",
                        "available": ["USD"],
                        "aggregation": False,
                        "conversion": False,
                    },
                    "limitations": ["counterparties are free text"],
                    "unsupported": ["journal writes", "invoice posting"],
                },
                "fin-caps",
            )
        elif path == "/api/integration/v1/companies":
            payload = _envelope(
                {
                    "companies": [
                        {
                            "id": "gursar_mimarlik",
                            "name": "Gursar Mimarlik",
                            "holding_id": "touche_holding",
                            "active": True,
                            "currency": "USD",
                            "currencies": ["USD"],
                            "multi_currency": False,
                            "data_through": datetime.now(tz=UTC).date().isoformat(),
                        }
                    ],
                    "page": {
                        "limit": 50,
                        "offset": 0,
                        "total": 1,
                        "next_offset": None,
                    },
                    "source": "finance_ledger",
                },
                "fin-companies",
            )
        elif path.endswith("/summary"):
            payload = _envelope(
                {
                    "company_id": "gursar_mimarlik",
                    "name": "Gursar Mimarlik",
                    "holding_id": "touche_holding",
                    "active": True,
                    "as_of": datetime.now(tz=UTC).date().isoformat(),
                    "data_through": datetime.now(tz=UTC).date().isoformat(),
                    "currency": "USD",
                    "currencies": ["USD"],
                    "source": "finance_ledger",
                    "ledger": {
                        "document_count": 2,
                        "line_count": 4,
                        "first_date": "2026-01-01",
                        "last_date": datetime.now(tz=UTC).date().isoformat(),
                    },
                    "balances": {
                        "cash": _money("10.00"),
                        "receivables": _money(type(self).stub.receivable_amount),
                        "payables": _money(type(self).stub.payable_amount),
                        "revenue": _money("240.00"),
                        "cost": _money("100.00"),
                        "gross_profit": _money("140.00"),
                    },
                },
                "fin-summary",
            )
        elif path.endswith("/aging"):
            kind = "payable" if "type=payable" in self.path else "receivable"
            amount = (
                type(self).stub.payable_amount
                if kind == "payable"
                else type(self).stub.receivable_amount
            )
            source_id = "FIN-AP-1" if kind == "payable" else "FIN-AR-1"
            payload = _envelope(
                {
                    "company_id": "gursar_mimarlik",
                    "type": kind,
                    "account": "320" if kind == "payable" else "120",
                    "as_of": datetime.now(tz=UTC).date().isoformat(),
                    "currency": "USD",
                    "summary": {
                        "total": _money(amount),
                        "overdue": _money("0.00"),
                        "overdue_ratio": 0.0,
                    },
                    "items": [
                        {
                            "counterparty": (
                                "Buyer Ltd" if kind == "receivable" else "Supplier One"
                            ),
                            "counterparty_key_type": "ledger.cari",
                            "buckets": {
                                "not_due": _money(amount),
                                "days_1_30": _money("0.00"),
                                "days_31_60": _money("0.00"),
                                "days_61_90": _money("0.00"),
                                "days_over_90": _money("0.00"),
                            },
                            "total": _money(amount),
                            "advance": _money("0.00"),
                            "overdue": False,
                            "overdue_amount": _money("0.00"),
                            "open_items": [
                                {
                                    "source_id": source_id,
                                    "source": "ledger.fisler",
                                    "due_date": "2026-12-31",
                                    "remaining": _money(amount),
                                }
                            ],
                        }
                    ],
                    "page": {
                        "limit": 200,
                        "offset": 0,
                        "total": 1,
                        "next_offset": None,
                    },
                    "source": "finance_ledger",
                },
                f"fin-aging-{kind}",
            )
        else:
            self.send_response(404)
            self.send_header("Content-Type", "application/json")
            self.end_headers()
            self.wfile.write(b'{"error":{"code":"NOT_FOUND","message":"missing"}}')
            return
        self.send_response(200)
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(payload)))
        self.end_headers()
        self.wfile.write(payload)

    def do_POST(self) -> None:
        type(self).calls.append(("POST", self.path))
        self.send_response(405)
        self.send_header("Content-Type", "application/json")
        self.end_headers()
        self.wfile.write(b'{"error":{"code":"READ_ONLY","message":"read only"}}')


class _QuietServer(ThreadingHTTPServer):
    def handle_error(self, request: object, client_address: object) -> None:
        return


@pytest.fixture()
def finance_stub() -> Iterator[FinanceStub]:
    ReconciliationFinanceHandler.calls = []
    server = _QuietServer(("127.0.0.1", 0), ReconciliationFinanceHandler)
    stub = FinanceStub(server=server)
    ReconciliationFinanceHandler.stub = stub
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    try:
        yield stub
    finally:
        server.shutdown()
        server.server_close()


@pytest.fixture()
def reconciliation_app(
    identity_app: FastAPI, test_settings: Settings, finance_stub: FinanceStub
) -> Iterator[FastAPI]:
    original = identity_app.state.settings
    identity_app.state.settings = test_settings.model_copy(
        update={
            "finance_integration_enabled": True,
            "finance_integration_base_url": finance_stub.base_url,
            "finance_integration_key_id": SecretStr("key_0123456789abcdef"),
            "finance_integration_secret": SecretStr("s" * 43),
            "finance_integration_timeout_seconds": 1.0,
        }
    )
    try:
        yield identity_app
    finally:
        identity_app.state.settings = original


@pytest.fixture()
def mapping_b(identity_world: IdentityWorld, migration_database: Database) -> FinanceCompanyMapping:
    with migration_database.transaction() as session:
        return set_verified_mapping(
            session,
            company_id=identity_world.company_b,
            finance_company_id="gursar_mimarlik",
            finance_company_name="Gursar Mimarlik",
            configured_by=identity_world.user_a,
            verification_details={"currencies": ["USD"]},
        )


def etag(version: int) -> str:
    return f'"v{version}"'


def run_body(order: dict[str, Any], *, currency: str | None = "USD") -> dict[str, Any]:
    payload: dict[str, Any] = {
        "sales_order_id": order["id"],
        "as_of": datetime.now(tz=UTC).date().isoformat(),
    }
    if currency is not None:
        payload["currency"] = currency
    return payload


def create_run(
    world: OrderWorld,
    order: dict[str, Any],
    *,
    currency: str | None = "USD",
    key: str | None = None,
) -> Any:
    return act(
        world.client,
        world.csrf,
        "/finance/reconciliation/runs",
        run_body(order, currency=currency),
        key=key or uuid4().hex,
    )


def prepare_complete_order(
    world: OrderWorld,
    approver_pair: tuple[TestClient, str],
) -> tuple[dict[str, Any], dict[str, Any], dict[str, Any]]:
    """Create accepted order, committed PO and one costed active shipment."""

    order, _ = won(world)
    purchase_order = create_purchase_order(world, order)
    assert purchase_order.status_code == 201, purchase_order.text
    po = dict(purchase_order.json())
    approver_client, approver_csrf = approver_pair
    approved = po_transition(approver_client, approver_csrf, po, "APPROVED")
    assert approved.status_code == 200, approved.text
    po = dict(approved.json())

    shipment = plan_shipment(world, order, quantity="10.000")
    assert shipment.status_code == 201, shipment.text
    shipment_body = dict(shipment.json())
    costed = act(
        world.client,
        world.csrf,
        f"/shipments/{shipment_body['id']}/costs",
        {
            "cost_type": "FREIGHT",
            "stage": "INCURRED",
            "amount": "20.00",
            "currency": "USD",
            "reference": "stage5d-freight-1",
        },
    )
    assert costed.status_code in (200, 201), costed.text
    return order, po, dict(costed.json())


def source_reference(run: dict[str, Any], source_type: str) -> dict[str, Any]:
    return next(item for item in run["source_references"] if item["source_type"] == source_type)


def evidence_body(
    run: dict[str, Any],
    order: dict[str, Any],
    *,
    source_type: str = "AGING_RECEIVABLE",
) -> dict[str, Any]:
    reference = source_reference(run, source_type)
    return {
        "run_id": run["id"],
        "source_entity_type": "SALES_ORDER",
        "source_entity_id": order["id"],
        "finance_source_reference_id": reference["id"],
        "notes": "Customer PO and Finance open item reviewed together.",
    }


def test_run_requires_verified_mapping(world: OrderWorld, reconciliation_app: FastAPI) -> None:
    order, _ = won(world)
    response = create_run(world, order)
    assert response.status_code == 409, response.text
    assert response.json()["error"]["code"] == "FINANCE_NOT_CONFIGURED"


def test_run_requires_explicit_currency(
    world: OrderWorld, reconciliation_app: FastAPI, mapping_b: FinanceCompanyMapping
) -> None:
    order, _ = won(world)
    response = create_run(world, order, currency=None)
    assert response.status_code == 409, response.text
    assert response.json()["error"]["code"] == "FINANCE_CURRENCY_REQUIRED"


def test_complete_run_records_separated_metrics_and_source_ids(
    world: OrderWorld,
    reconciliation_app: FastAPI,
    mapping_b: FinanceCompanyMapping,
    finance_stub: FinanceStub,
) -> None:
    order, _, _ = prepare_complete_order(world, (world.approver_client, world.approver_csrf))
    finance_stub.receivable_amount = str(order["order_total"])
    response = create_run(world, order)
    assert response.status_code == 201, response.text
    run = response.json()

    assert run["status"] == "UNMATCHED"
    assert run["read_only"] is True
    assert run["accounting_writes_enabled"] is False
    assert run["metrics"]["accepted_sales_order_value"] == str(order["order_total"])
    assert run["metrics"]["purchase_commitments_total"] is not None
    assert run["metrics"]["estimated_landed_cost"] is not None
    assert run["metrics"]["recorded_operational_costs"] == "20.00"
    assert run["metrics"]["document_supported_margin"] is None
    assert run["classifications"]["actual_profit"] == "UNAVAILABLE"
    assert run["classifications"]["commitment_based_margin"] == "COMMITTED"
    reference = source_reference(run, "AGING_RECEIVABLE")
    assert reference["source_reference"] == "FIN-AR-1"
    assert reference["is_transaction_level"] is True
    assert reference["payload"]["counterparty_label"] == "Buyer Ltd"
    assert any(item["code"] == "MISSING_FINANCE_REFERENCE" for item in run["discrepancies"])
    assert all(method == "GET" for method, _path in ReconciliationFinanceHandler.calls)
    assert "s" * 43 not in response.text


def test_evidence_link_review_and_audit_flow(
    world: OrderWorld,
    reconciliation_app: FastAPI,
    mapping_b: FinanceCompanyMapping,
    finance_stub: FinanceStub,
    migration_database: Database,
) -> None:
    order, _, _ = prepare_complete_order(world, (world.approver_client, world.approver_csrf))
    finance_stub.receivable_amount = str(order["order_total"])
    created = create_run(world, order)
    assert created.status_code == 201, created.text
    run = created.json()
    body = evidence_body(run, order)

    linked = act(
        world.client,
        world.csrf,
        "/finance/evidence-links",
        body,
        if_match=etag(run["version"]),
    )
    assert linked.status_code == 201, linked.text
    linked_run = linked.json()
    assert linked_run["status"] == "MATCHED_EVIDENCE"
    assert linked_run["evidence_count"] == 1
    assert linked_run["evidence_links"][0]["verification_status"] == "UNVERIFIED"
    missing_reference = next(
        item for item in linked_run["discrepancies"] if item["code"] == "MISSING_FINANCE_REFERENCE"
    )
    assert missing_reference["status"] == "RESOLVED"

    reviewed = act(
        world.approver_client,
        world.approver_csrf,
        "/finance/reviews",
        {
            "run_id": linked_run["id"],
            "decision": "CONFIRM",
            "notes": "Matched source id and exact amount checked.",
        },
        if_match=etag(linked_run["version"]),
    )
    assert reviewed.status_code == 201, reviewed.text
    verified = reviewed.json()
    assert verified["status"] == "VERIFIED"
    assert verified["evidence_links"][0]["verification_status"] == "VERIFIED"
    assert verified["reviews"][-1]["decision"] == "CONFIRM"

    with migration_database.transaction() as session:
        rows = (
            session.execute(
                select(AuditRecord).where(
                    AuditRecord.resource_id.in_([run["id"], linked_run["evidence_links"][0]["id"]])
                )
            )
            .scalars()
            .all()
        )
    actions = {AuditAction(row.action) for row in rows}
    assert AuditAction.FINANCE_RECONCILIATION_RUN_CREATED in actions
    assert AuditAction.FINANCE_EVIDENCE_LINKED in actions
    assert AuditAction.FINANCE_RECONCILIATION_REVIEWED in actions
    assert "s" * 43 not in json.dumps([row.details for row in rows], default=str)


def test_duplicate_evidence_and_summary_reference_are_refused(
    world: OrderWorld,
    reconciliation_app: FastAPI,
    mapping_b: FinanceCompanyMapping,
    finance_stub: FinanceStub,
) -> None:
    order, _, _ = prepare_complete_order(world, (world.approver_client, world.approver_csrf))
    finance_stub.receivable_amount = str(order["order_total"])
    run = create_run(world, order).json()

    first = act(
        world.client,
        world.csrf,
        "/finance/evidence-links",
        evidence_body(run, order),
        if_match=etag(run["version"]),
    )
    assert first.status_code == 201, first.text
    first_run = first.json()
    duplicate = act(
        world.client,
        world.csrf,
        "/finance/evidence-links",
        evidence_body(first_run, order),
        if_match=etag(first_run["version"]),
    )
    assert duplicate.status_code == 409, duplicate.text
    assert duplicate.json()["error"]["code"] == "RECONCILIATION_EVIDENCE_DUPLICATE"

    summary = source_reference(first_run, "SUMMARY")
    not_matchable = act(
        world.client,
        world.csrf,
        "/finance/evidence-links",
        {
            "run_id": first_run["id"],
            "source_entity_type": "SALES_ORDER",
            "source_entity_id": order["id"],
            "finance_source_reference_id": summary["id"],
        },
        if_match=etag(first_run["version"]),
    )
    assert not_matchable.status_code == 409, not_matchable.text
    assert not_matchable.json()["error"]["code"] == "RECONCILIATION_SOURCE_NOT_MATCHABLE"

    payable = source_reference(first_run, "AGING_PAYABLE")
    invalid_entity = act(
        world.client,
        world.csrf,
        "/finance/evidence-links",
        {
            "run_id": first_run["id"],
            "source_entity_type": "PURCHASE_ORDER",
            "source_entity_id": str(uuid4()),
            "finance_source_reference_id": payable["id"],
        },
        if_match=etag(first_run["version"]),
    )
    assert invalid_entity.status_code == 409, invalid_entity.text
    assert invalid_entity.json()["error"]["code"] == "RECONCILIATION_EVIDENCE_INVALID"


def test_read_surfaces_expose_real_runs_discrepancies_and_order_view(
    world: OrderWorld,
    reconciliation_app: FastAPI,
    mapping_b: FinanceCompanyMapping,
    finance_stub: FinanceStub,
) -> None:
    order, _, _ = prepare_complete_order(world, (world.approver_client, world.approver_csrf))
    finance_stub.receivable_amount = str(order["order_total"])
    run = create_run(world, order).json()

    detail = world.client.get(f"{RUNS}/{run['id']}")
    assert detail.status_code == 200, detail.text
    assert detail.headers["ETag"] == etag(run["version"])
    assert detail.json()["finance_snapshot"]["currency"] == "USD"

    listing = world.client.get(f"{RECONCILIATION}?currency=USD")
    assert listing.status_code == 200, listing.text
    assert listing.json()["total"] == 1
    assert listing.json()["status_counts"]["UNMATCHED"] == 1
    assert listing.json()["open_discrepancy_count"] >= 1

    order_view = world.client.get(f"{API}/finance/orders/{order['id']}")
    assert order_view.status_code == 200, order_view.text
    body = order_view.json()
    assert body["order"]["sales_order_id"] == order["id"]
    assert body["metrics"]["accepted_sales_order_value"] == str(order["order_total"])
    assert body["latest_run_id"] == run["id"]
    assert body["latest_run_status"] == "UNMATCHED"
    assert body["classifications"]["actual_profit"] == "UNAVAILABLE"
    assert any(gap["code"] == "MISSING_FINANCE_REFERENCE" for gap in body["missing_evidence"])

    discrepancies = world.client.get(f"{DISCREPANCIES}?run_id={run['id']}")
    assert discrepancies.status_code == 200, discrepancies.text
    assert discrepancies.json()["total"] >= 1
    discrepancy_id = discrepancies.json()["items"][0]["id"]
    assert world.client.get(f"{DISCREPANCIES}/{discrepancy_id}").status_code == 200

    evidence_list = world.client.get(f"{EVIDENCE}?run_id={run['id']}")
    assert evidence_list.status_code == 200
    assert evidence_list.json()["total"] == 0


def test_amount_mismatch_blocks_verification_and_can_be_resolved(
    world: OrderWorld,
    reconciliation_app: FastAPI,
    mapping_b: FinanceCompanyMapping,
    finance_stub: FinanceStub,
) -> None:
    order, _, _ = prepare_complete_order(world, (world.approver_client, world.approver_csrf))
    finance_stub.receivable_amount = "999.00"
    run = create_run(world, order).json()
    linked = act(
        world.client,
        world.csrf,
        "/finance/evidence-links",
        evidence_body(run, order),
        if_match=etag(run["version"]),
    )
    assert linked.status_code == 201, linked.text
    linked_run = linked.json()
    assert linked_run["status"] == "POTENTIAL_MATCH"
    mismatch = next(
        item for item in linked_run["discrepancies"] if item["code"] == "AMOUNT_MISMATCH"
    )
    assert mismatch["severity"] == "BLOCKING"

    refused = act(
        world.approver_client,
        world.approver_csrf,
        "/finance/reviews",
        {
            "run_id": linked_run["id"],
            "decision": "CONFIRM",
            "notes": "Attempt before resolving the blocking difference.",
        },
        if_match=etag(linked_run["version"]),
    )
    assert refused.status_code == 409, refused.text
    assert refused.json()["error"]["code"] == "RECONCILIATION_NOT_VERIFIABLE"

    resolved = act(
        world.approver_client,
        world.approver_csrf,
        f"/finance/discrepancies/{mismatch['id']}/resolve",
        {"notes": "Difference investigated; separate credit document requested."},
        if_match=etag(mismatch["version"]),
    )
    assert resolved.status_code == 200, resolved.text
    assert resolved.json()["status"] == "RESOLVED"
    assert resolved.json()["resolution_notes"]


def test_review_requires_permission_and_linked_evidence(
    world: OrderWorld,
    reconciliation_app: FastAPI,
    mapping_b: FinanceCompanyMapping,
    finance_stub: FinanceStub,
    identity_world: IdentityWorld,
    client_factory: Callable[..., TestClient],
) -> None:
    order, _, _ = prepare_complete_order(world, (world.approver_client, world.approver_csrf))
    finance_stub.receivable_amount = str(order["order_total"])
    run = create_run(world, order).json()

    unauthorized = act(
        world.client,
        world.csrf,
        "/finance/reviews",
        {
            "run_id": run["id"],
            "decision": "CONFIRM",
            "notes": "Trader must not review financial evidence.",
        },
        if_match=etag(run["version"]),
    )
    assert unauthorized.status_code == 403, unauthorized.text

    no_evidence = act(
        world.approver_client,
        world.approver_csrf,
        "/finance/reviews",
        {
            "run_id": run["id"],
            "decision": "CONFIRM",
            "notes": "No evidence has been linked for this order.",
        },
        if_match=etag(run["version"]),
    )
    assert no_evidence.status_code == 409, no_evidence.text
    assert no_evidence.json()["error"]["code"] == "RECONCILIATION_NOT_VERIFIABLE"

    admin_client, admin_csrf = sign_in(
        client_factory,
        email=identity_world.email_a,
        company_id=identity_world.company_a,
    )
    admin_review = act(
        admin_client,
        admin_csrf,
        "/finance/reviews",
        {
            "run_id": str(uuid4()),
            "decision": "CONFIRM",
            "notes": "Admin must not inherit financial review authority.",
        },
        if_match=etag(1),
    )
    assert admin_review.status_code == 403, admin_review.text
    assert not has_permission(Role.ADMIN, Permission.FINANCE_RECONCILE)


def test_cross_tenant_run_is_invisible(
    world: OrderWorld,
    reconciliation_app: FastAPI,
    mapping_b: FinanceCompanyMapping,
    finance_stub: FinanceStub,
    identity_world: IdentityWorld,
    client_factory: Callable[..., TestClient],
) -> None:
    order, _, _ = prepare_complete_order(world, (world.approver_client, world.approver_csrf))
    finance_stub.receivable_amount = str(order["order_total"])
    run = create_run(world, order).json()

    outsider, _ = sign_in(
        client_factory,
        email=identity_world.email_a,
        company_id=identity_world.company_a,
    )
    assert outsider.get(f"{RUNS}/{run['id']}").status_code == 404
    listing = outsider.get(f"{RECONCILIATION}?currency=USD")
    assert listing.status_code == 200
    assert listing.json()["items"] == []
    assert listing.json()["total"] == 0


def test_idempotency_replay_and_conflict(
    world: OrderWorld,
    reconciliation_app: FastAPI,
    mapping_b: FinanceCompanyMapping,
    finance_stub: FinanceStub,
) -> None:
    order, _, _ = prepare_complete_order(world, (world.approver_client, world.approver_csrf))
    finance_stub.receivable_amount = str(order["order_total"])
    key = uuid4().hex
    first = create_run(world, order, key=key)
    assert first.status_code == 201, first.text
    replay = create_run(world, order, key=key)
    assert replay.status_code == 201, replay.text
    assert replay.headers.get("Idempotent-Replay") == "true"
    assert replay.json()["id"] == first.json()["id"]

    conflict = act(
        world.client,
        world.csrf,
        "/finance/reconciliation/runs",
        run_body(order, currency="EUR"),
        key=key,
    )
    assert conflict.status_code == 409, conflict.text
    assert conflict.json()["error"]["code"] == "IDEMPOTENCY_CONFLICT"


def test_stale_run_version_is_rejected(
    world: OrderWorld,
    reconciliation_app: FastAPI,
    mapping_b: FinanceCompanyMapping,
    finance_stub: FinanceStub,
) -> None:
    order, _, _ = prepare_complete_order(world, (world.approver_client, world.approver_csrf))
    finance_stub.receivable_amount = str(order["order_total"])
    run = create_run(world, order).json()
    stale = act(
        world.client,
        world.csrf,
        "/finance/evidence-links",
        evidence_body(run, order),
        if_match=etag(run["version"] + 10),
    )
    assert stale.status_code == 409, stale.text
    assert stale.json()["error"]["code"] == "VERSION_CONFLICT"


def test_runtime_cannot_delete_reconciliation_or_policies_are_tenant_scoped(
    migration_database: Database,
) -> None:
    with migration_database.transaction() as session:
        for table in (
            "finance_reconciliation_run",
            "finance_source_reference",
            "finance_reconciliation_evidence",
            "finance_discrepancy",
            "finance_reconciliation_review",
        ):
            can_delete = session.execute(
                text("SELECT has_table_privilege('touche_app', :qualified, 'DELETE')"),
                {"qualified": f"touche.{table}"},
            ).scalar_one()
            assert can_delete is False
            policy_count = session.execute(
                text(
                    "SELECT count(*) FROM pg_policies "
                    "WHERE schemaname='touche' AND tablename=:table"
                ),
                {"table": table},
            ).scalar_one()
            assert policy_count > 0

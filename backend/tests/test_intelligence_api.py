"""Stage 5E financial intelligence API integration tests."""

from __future__ import annotations

from datetime import UTC, datetime, timedelta
from typing import Any

import pytest

from app.db.engine import Database
from app.db.models import AuditAction
from tests.conftest import IdentityWorld
from tests.test_finance_api import sign_in
from tests.test_operations_api import (
    ORDERS as SALES_ORDERS,
)
from tests.test_operations_api import (
    SHIPMENTS,
    OrderWorld,
    act,
    create_purchase_order,
    deliver,
    plan_shipment,
    po_transition,
    won,
)
from tests.test_reconciliation_api import (
    approver,
    create_run,
    finance_stub,
    mapping_b,
    reconciliation_app,
    trader,
    world,
)

pytestmark = pytest.mark.integration

API = "/api/v1"
SUMMARY = f"{API}/finance/intelligence/summary"
ORDERS = f"{API}/finance/intelligence/orders"
COVERAGE = f"{API}/finance/intelligence/coverage"
VARIANCE = f"{API}/finance/intelligence/cost-variance"
EXCEPTIONS = f"{API}/finance/intelligence/exceptions"
EXPORT = f"{API}/finance/intelligence/export"

# Imported fixtures are intentionally re-exported to pytest discovery.
_IMPORTED_FIXTURES = (
    approver,
    finance_stub,
    mapping_b,
    reconciliation_app,
    trader,
    world,
)


def _today() -> str:
    return datetime.now(tz=UTC).date().isoformat()


def _from(days: int = 30) -> str:
    return (datetime.now(tz=UTC).date() - timedelta(days=days)).isoformat()


def _params(**overrides: str) -> dict[str, str]:
    values = {"from": _from(), "to": _today()}
    values.update(overrides)
    return values


def prepare_order(world: OrderWorld) -> tuple[dict[str, Any], dict[str, Any]]:
    """Accepted order, approved PO, one fully delivered documented shipment."""

    order, _ = won(world)
    purchase_order = create_purchase_order(world, order)
    assert purchase_order.status_code == 201, purchase_order.text
    approved = po_transition(
        world.approver_client,
        world.approver_csrf,
        purchase_order.json(),
        "APPROVED",
    )
    assert approved.status_code == 200, approved.text
    planned = plan_shipment(world, order, quantity="100.000")
    assert planned.status_code == 201, planned.text
    shipment = planned.json()
    costed = act(
        world.client,
        world.csrf,
        f"/shipments/{shipment['id']}/costs",
        {
            "cost_type": "FREIGHT",
            "stage": "INCURRED",
            "amount": "20.00",
            "currency": "USD",
            "reference": "stage5e-freight-1",
        },
    )
    assert costed.status_code in (200, 201), costed.text
    refreshed = world.client.get(f"{SHIPMENTS}/{shipment['id']}")
    assert refreshed.status_code == 200, refreshed.text
    delivered = deliver(world, refreshed.json())
    assert delivered["status"] == "DELIVERED"
    order_body = world.client.get(f"{SALES_ORDERS}/{order['id']}")
    assert order_body.status_code == 200, order_body.text
    return dict(order_body.json()), dict(approved.json())


def metric(body: dict[str, Any], key: str) -> dict[str, Any]:
    return next(item for item in body["metrics"] if item["key"] == key)


def test_summary_orders_and_detail_use_real_commerce_facts(world: OrderWorld) -> None:
    order, purchase_order = prepare_order(world)

    summary = world.client.get(SUMMARY, params=_params())
    assert summary.status_code == 200, summary.text
    body = summary.json()
    assert body["calculation_version"] == "stage5e-1.0.0"
    assert body["read_only"] is True
    assert body["accounting_writes_enabled"] is False
    assert body["statutory_statements"] is False
    assert body["order_count"] == 1
    assert body["active_order_count"] == 1
    assert metric(body, "accepted_sales_order_value")["money"] == [
        {"currency": "USD", "amount": "250.00"}
    ]
    assert metric(body, "purchase_commitments")["money"] == [
        {"currency": "USD", "amount": "160.00"}
    ]
    assert metric(body, "estimated_gross_profit")["money"] == [
        {"currency": "USD", "amount": "50.00"}
    ]
    assert metric(body, "estimated_gross_margin")["percentages"] == [
        {"currency": "USD", "value": "20.00"}
    ]
    assert metric(body, "recorded_operational_costs")["money"] == [
        {"currency": "USD", "amount": "20.00"}
    ]
    assert metric(body, "reconciliation_coverage")["percentage"] == "0.00"
    assert metric(body, "open_discrepancies")["count"] == 0
    assert summary.headers["cache-control"] == "no-store"

    listing = world.client.get(ORDERS, params=_params())
    assert listing.status_code == 200, listing.text
    item = listing.json()["items"][0]
    assert item["order_number"] == order["order_number"]
    assert item["estimated_gross_profit"] == "50.00"
    assert item["committed_gross_profit"] == "70.00"
    assert item["documented_total_cost"] == "180.00"
    assert item["cost_variance"] == "-20.00"
    assert item["estimate_status"] == "COMPLETE"
    assert item["committed_status"] == "COMPLETE"
    assert item["completeness"] == "COMPLETE"

    detail = world.client.get(f"{ORDERS}/{order['id']}")
    assert detail.status_code == 200, detail.text
    detail_body = detail.json()
    assert detail_body["quote"]["quote_number"] == world.quote["quote_number"]
    assert detail_body["purchase_orders"][0]["po_number"] == purchase_order["po_number"]
    assert detail_body["purchase_orders"][0]["classification"] == "COMMITTED"
    assert detail_body["shipments"][0]["costs"][0]["classification"] == "DOCUMENTED"
    assert any(line["cost_type"] == "FREIGHT" for line in detail_body["cost_lines"])
    assert detail_body["limitations"]
    assert detail_body["read_only"] is True


def test_filters_pagination_and_currency_isolation(world: OrderWorld) -> None:
    prepare_order(world)

    other_currency = world.client.get(SUMMARY, params=_params(currency="EUR"))
    assert other_currency.status_code == 200, other_currency.text
    assert other_currency.json()["order_count"] == 0
    assert metric(other_currency.json(), "open_discrepancies")["available"] is True

    page = world.client.get(ORDERS, params={**_params(), "limit": "1", "offset": "1"})
    assert page.status_code == 200, page.text
    assert page.json()["total"] == 1
    assert page.json()["items"] == []

    invalid_range = world.client.get(
        ORDERS, params={"from": _today(), "to": _from()}
    )
    assert invalid_range.status_code == 400, invalid_range.text

    too_long = world.client.get(
        ORDERS, params={"from": "2024-01-01", "to": "2026-01-02"}
    )
    assert too_long.status_code == 400, too_long.text
    assert "731" in too_long.json()["error"]["message"]


def test_cross_tenant_cannot_read_order_or_totals(
    world: OrderWorld,
    identity_world: IdentityWorld,
    client_factory: Any,
) -> None:
    order, _ = prepare_order(world)
    outsider, _ = sign_in(
        client_factory,
        email=identity_world.email_a,
        company_id=identity_world.company_a,
    )

    assert outsider.get(f"{ORDERS}/{order['id']}").status_code == 404
    summary = outsider.get(SUMMARY, params=_params())
    assert summary.status_code == 200
    assert summary.json()["order_count"] == 0


def test_exceptions_reuse_stage5d_with_order_context(
    world: OrderWorld,
    reconciliation_app: Any,
    mapping_b: Any,
) -> None:
    order, _ = prepare_order(world)
    run = create_run(world, order)
    assert run.status_code == 201, run.text

    response = world.client.get(EXCEPTIONS)
    assert response.status_code == 200, response.text
    body = response.json()
    assert body["total"] > 0
    finding = body["items"][0]
    assert finding["order_number"] == order["order_number"]
    assert finding["currency"] == "USD"
    assert finding["sales_order_id"] == order["id"]
    assert "MISSING_FINANCE_REFERENCE" in {item["code"] for item in body["items"]}

    summary = world.client.get(SUMMARY, params=_params()).json()
    assert metric(summary, "open_discrepancies")["count"] == body["total"]


def test_export_is_operational_authorised_and_formula_safe(
    world: OrderWorld,
    identity_world: IdentityWorld,
    client_factory: Any,
    migration_database: Database,
) -> None:
    prepare_order(world)
    response = world.client.get(EXPORT, params=_params())
    assert response.status_code == 200, response.text
    assert response.headers["content-type"].startswith("text/csv")
    assert "attachment;" in response.headers["content-disposition"]
    text = response.content.decode("utf-8")
    assert "TOUCHE COMMERCE operational financial analysis" in text
    assert "stage5e-1.0.0" in text
    assert "Not a statutory financial statement" in text
    assert "OPERATIONAL_ANALYSIS_ORDER" in text

    outsider, _ = sign_in(
        client_factory,
        email=identity_world.email_a,
        company_id=identity_world.company_a,
    )
    empty = outsider.get(EXPORT, params=_params())
    assert empty.status_code == 200
    assert "SO-" not in empty.content.decode("utf-8")

    from sqlalchemy import select

    from app.db.models import AuditRecord

    with migration_database.transaction() as session:
        found = session.execute(
            select(AuditRecord).where(
                AuditRecord.action == AuditAction.FINANCE_READ.value,
                AuditRecord.resource_type == "operational_financial_analysis",
            )
        ).scalars()
        assert any(row.company_id == identity_world.company_b for row in found)

    from app.api.v1.routes.intelligence import _csv_safe

    assert _csv_safe("=2+2") == "'=2+2"
    assert _csv_safe("+SUM(A1)") == "'+SUM(A1)"
    assert _csv_safe("-5.00") == "'-5.00"
    assert _csv_safe("@cmd") == "'@cmd"
    assert _csv_safe("Buyer Ltd") == "Buyer Ltd"

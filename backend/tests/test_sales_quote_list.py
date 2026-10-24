# ruff: noqa: F811  (fixtures are imported by name and then used as parameters)
"""The sales-quote list tells the interface when each quote was approved.

The order-conversion form pre-fills the customer's acceptance time and the API refuses one that
predates the internal approval, so the list must carry that timestamp.
"""

from __future__ import annotations

from datetime import datetime

import pytest

from tests.test_operations_api import (  # noqa: F401 - fixtures are used by name
    OrderWorld,
    approver,
    client_factory,
    document_storage_root,
    identity_app,
    trader,
    world,
)

pytestmark = pytest.mark.integration


def test_the_list_carries_the_approval_time_of_an_approved_quote(world: OrderWorld) -> None:
    response = world.client.get("/api/v1/sales-quotes", params={"deal_id": world.deal["id"]})
    assert response.status_code == 200, response.text
    items = response.json()["items"]
    assert [item["status"] for item in items] == ["APPROVED"]
    approved_at = datetime.fromisoformat(items[0]["approved_at"].replace("Z", "+00:00"))
    created_at = datetime.fromisoformat(items[0]["created_at"].replace("Z", "+00:00"))
    assert approved_at >= created_at
    assert approved_at.tzinfo is not None


def test_a_quote_that_is_not_approved_has_no_approval_time(world: OrderWorld) -> None:
    detail = world.client.get(f"/api/v1/sales-quotes/{world.quote['id']}").json()
    assert detail["approved_at"] is not None  # sanity: the fixture quote is approved
    listing = world.client.get("/api/v1/sales-quotes").json()["items"]
    for item in listing:
        assert (item["approved_at"] is None) == (item["status"] != "APPROVED")

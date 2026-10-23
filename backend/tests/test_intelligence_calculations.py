"""Pure Stage 5E profitability tests: Decimal, bases, FX and completeness."""

from __future__ import annotations

import csv
import io
from datetime import UTC, date, datetime
from decimal import Decimal
from uuid import UUID, uuid4

from app.api.v1.routes.intelligence import _export_csv
from app.db.models import PurchaseOrderStatus, SalesOrderStatus, ShipmentStatus
from app.services.intelligence import AnalyzedOrder
from app.services.intelligence_calculations import (
    CompletenessStatus,
    FxFact,
    OrderFacts,
    PricingComponentFact,
    PricingScenarioFact,
    PurchaseOrderFact,
    ShipmentCostFact,
    ShipmentFact,
    analyse_order,
    money,
    sum_by_currency,
)

NOW = datetime(2026, 10, 23, 9, 0, tzinfo=UTC)
COMPANY_ID = UUID("11111111-1111-1111-1111-111111111111")


def fx(
    base: str = "EUR",
    quote: str = "USD",
    rate: str = "1.1000000000",
) -> FxFact:
    return FxFact(
        snapshot_id=uuid4(),
        base_currency=base,
        quote_currency=quote,
        rate=Decimal(rate),
        effective_at=NOW,
        source="ECB reference snapshot",
    )


def component(
    cost_type: str = "FREIGHT",
    amount: str = "20.00",
    *,
    currency: str = "USD",
    snapshot: FxFact | None = None,
    verification: str = "VERIFIED",
) -> PricingComponentFact:
    return PricingComponentFact(
        component_id=uuid4(),
        cost_type=cost_type,
        amount=Decimal(amount),
        currency=currency,
        basis="ORDER",
        verification_status=verification,
        source_reference=f"{cost_type.lower()}-invoice-1",
        fx=snapshot,
    )


def scenario(
    *,
    purchase: str = "100.00",
    components: tuple[PricingComponentFact, ...] | None = None,
    target: str = "USD",
    status: str = "VERIFIED_INPUTS",
    landed: str = "120.00",
) -> PricingScenarioFact:
    parts = (
        components if components is not None else (component("FREIGHT", "20.00"),)
    )
    return PricingScenarioFact(
        scenario_id=uuid4(),
        status=status,
        calculation_version="stage3-1.0.0",
        quote_currency=target,
        target_currency=target,
        purchase_total=Decimal(purchase),
        additional_cost_total=money(
            sum((part.amount for part in parts), Decimal("0"))
        ),
        landed_total=Decimal(landed),
        sales_total=Decimal("200.00"),
        fx_rate=Decimal("1"),
        components=parts,
    )


def po(
    total: str = "100.00",
    *,
    status: str = PurchaseOrderStatus.APPROVED.value,
    currency: str = "USD",
) -> PurchaseOrderFact:
    return PurchaseOrderFact(
        purchase_order_id=uuid4(),
        po_number=f"PO-{uuid4().hex[:8]}",
        status=status,
        currency=currency,
        total_cost=Decimal(total),
        supplier_id=uuid4(),
        supplier_name="Supplier One",
    )


def shipment_cost(
    amount: str = "25.00",
    *,
    stage: str = "INCURRED",
    cost_type: str = "FREIGHT",
    currency: str = "USD",
) -> ShipmentCostFact:
    return ShipmentCostFact(
        cost_id=uuid4(),
        cost_type=cost_type,
        stage=stage,
        currency=currency,
        amount=Decimal(amount),
        reference=f"{stage.lower()}-{uuid4().hex[:6]}",
    )


def shipment(
    *costs: ShipmentCostFact,
    status: str = ShipmentStatus.DELIVERED.value,
) -> ShipmentFact:
    return ShipmentFact(
        shipment_id=uuid4(),
        shipment_number=f"SHP-{uuid4().hex[:8]}",
        status=status,
        costs=tuple(costs),
    )


def order(**overrides: object) -> OrderFacts:
    values: dict[str, object] = {
        "sales_order_id": uuid4(),
        "order_number": "SO-2610-TEST",
        "customer_id": uuid4(),
        "customer_name": "Buyer Ltd",
        "status": SalesOrderStatus.FULFILLED.value,
        "fulfilment_model": "PURCHASE_RESALE",
        "currency": "USD",
        "order_total": Decimal("200.00"),
        "confirmed_at": NOW,
        "expected_delivery_date": None,
        "pricing": scenario(),
        "purchase_orders": (po(),),
        "shipments": (shipment(shipment_cost()),),
        "reconciliation_status": "VERIFIED",
        "open_discrepancy_count": 0,
        "blocking_discrepancy_count": 0,
    }
    values.update(overrides)
    return OrderFacts(**values)  # type: ignore[arg-type]


def test_estimated_profit_excludes_vat_cashflow() -> None:
    result = analyse_order(
        order(
            pricing=scenario(
                components=(
                    component("FREIGHT", "20.00"),
                    component("VAT_CASHFLOW", "10.00"),
                ),
                landed="130.00",
            ),
        )
    )

    assert result.estimated_purchase_cost == Decimal("100.00")
    assert result.estimated_operational_cost == Decimal("20.00")
    assert result.estimated_vat_cashflow == Decimal("10.00")
    assert result.estimated_landed_cost == Decimal("120.00")
    assert result.estimated_gross_profit == Decimal("80.00")
    assert result.estimated_gross_margin_pct == Decimal("40.00")
    assert result.estimated_markup_pct == Decimal("66.67")
    assert result.scenario_landed_total_including_vat == Decimal("130.00")


def test_committed_basis_uses_po_and_documented_cost_not_the_estimate() -> None:
    result = analyse_order(order())

    assert result.documented_total_cost == Decimal("125.00")
    assert result.committed_gross_profit == Decimal("75.00")
    assert result.committed_gross_margin_pct == Decimal("37.50")
    assert result.committed_markup_pct == Decimal("60.00")
    assert result.cost_variance == Decimal("5.00")
    assert result.cost_variance_pct == Decimal("4.17")
    assert result.estimated_gross_profit == Decimal("80.00")
    assert result.documented_total_cost != result.estimated_landed_cost


def test_quoted_costs_are_forecast_and_do_not_enter_documented_profit() -> None:
    result = analyse_order(
        order(shipments=(shipment(shipment_cost("30.00", stage="QUOTED")),))
    )

    assert result.quoted_operational_cost == Decimal("30.00")
    assert result.documented_operational_cost is None
    assert result.committed_gross_profit is None
    assert "DOCUMENTED_OPERATIONAL_COSTS" in result.missing_components
    assert result.committed_status is CompletenessStatus.PARTIAL


def test_partial_fulfilment_never_claims_full_documented_profit() -> None:
    result = analyse_order(order(status=SalesOrderStatus.IN_FULFILLMENT.value))

    assert result.estimated_gross_profit == Decimal("80.00")
    assert result.committed_gross_profit is None
    assert result.partial_fulfilment is True
    assert "PARTIAL_FULFILMENT" in result.missing_components
    assert result.committed_status is CompletenessStatus.PARTIAL


def test_multiple_purchase_orders_are_summed_only_in_one_currency() -> None:
    result = analyse_order(order(purchase_orders=(po("100.00"), po("50.00"))))

    assert result.committed_purchase_cost == Decimal("150.00")
    assert result.documented_total_cost == Decimal("175.00")
    assert result.committed_gross_profit == Decimal("25.00")


def test_purchase_currency_mismatch_makes_committed_basis_unavailable() -> None:
    result = analyse_order(
        order(purchase_orders=(po("100.00"), po("50.00", currency="EUR")))
    )

    assert result.purchase_currency_mismatch is True
    assert result.committed_purchase_cost is None
    assert result.committed_gross_profit is None
    assert "CURRENCY_MISMATCH_PURCHASE" in result.missing_components
    assert result.committed_status is CompletenessStatus.PARTIAL


def test_component_fx_snapshot_is_used_exactly_and_origin_is_retained() -> None:
    result = analyse_order(
        order(
            pricing=scenario(
                components=(
                    component("FREIGHT", "20.00", currency="EUR", snapshot=fx()),
                )
            )
        )
    )

    assert result.estimated_operational_cost == Decimal("22.00")
    assert result.estimated_landed_cost == Decimal("122.00")
    assert result.estimated_gross_profit == Decimal("78.00")
    line = result.cost_lines[0]
    assert line.original_currency == "EUR"
    assert line.original_amount == Decimal("20.00")
    assert line.converted_amount == Decimal("22.00")
    assert line.fx_rate == Decimal("1.1")


def test_missing_component_fx_makes_the_estimate_unavailable() -> None:
    result = analyse_order(
        order(
            pricing=scenario(
                components=(component("FREIGHT", "20.00", currency="EUR"),)
            )
        )
    )

    assert result.estimate_status is CompletenessStatus.UNAVAILABLE
    assert result.estimated_landed_cost is None
    assert result.estimated_gross_profit is None
    assert "ESTIMATE_FX_UNAVAILABLE" in result.missing_components


def test_zero_sales_and_zero_cost_never_divide_by_zero() -> None:
    result = analyse_order(
        order(
            order_total=Decimal("0"),
            pricing=scenario(purchase="0", components=(), landed="0"),
            purchase_orders=(),
            shipments=(shipment(shipment_cost("0.00")),),
        )
    )

    assert result.estimated_gross_profit == Decimal("0.00")
    assert result.estimated_gross_margin_pct is None
    assert result.estimated_markup_pct is None
    assert result.committed_gross_margin_pct is None
    assert result.committed_markup_pct is None


def test_negative_margin_is_reported_without_hiding_the_loss() -> None:
    result = analyse_order(
        order(
            order_total=Decimal("50.00"),
            pricing=scenario(purchase="100.00", components=(), landed="100.00"),
        )
    )

    assert result.estimated_gross_profit == Decimal("-50.00")
    assert result.estimated_gross_margin_pct == Decimal("-100.00")
    assert result.estimated_markup_pct == Decimal("-50.00")


def test_csv_export_keeps_a_loss_numeric_and_escapes_only_text() -> None:
    facts = order(
        order_total=Decimal("50.00"),
        customer_name='=HYPERLINK("http://example.invalid")',
        pricing=scenario(purchase="100.00", components=(), landed="100.00"),
    )
    content = _export_csv(
        (AnalyzedOrder(facts=facts, result=analyse_order(facts)),),
        as_of=date(2026, 10, 23),
        generated_at="2026-10-23T09:00:00+00:00",
    )

    (row,) = csv.DictReader(io.StringIO(content.decode("utf-8"), newline=""))

    assert row["estimated_gross_profit"] == "-50.00"
    assert row["estimated_gross_margin_pct"] == "-100.00"
    assert row["estimated_markup_pct"] == "-50.00"
    assert row["customer_name"] == "'=HYPERLINK(\"http://example.invalid\")"


def test_cancelled_order_has_no_current_profitability() -> None:
    result = analyse_order(order(status=SalesOrderStatus.CANCELLED.value))

    assert result.cancelled is True
    assert result.completeness is CompletenessStatus.UNAVAILABLE
    assert result.estimated_gross_profit is None
    assert result.committed_gross_profit is None
    assert "CANCELLED_ORDER" in result.missing_components


def test_draft_purchase_order_blocks_the_committed_basis() -> None:
    result = analyse_order(
        order(purchase_orders=(po(status=PurchaseOrderStatus.DRAFT.value),))
    )

    assert result.committed_purchase_cost is None
    assert result.committed_gross_profit is None
    assert "PURCHASE_COMMITMENT_INCOMPLETE" in result.missing_components
    assert result.committed_status is CompletenessStatus.PARTIAL


def test_cancelled_purchase_order_is_ignored() -> None:
    result = analyse_order(
        order(
            purchase_orders=(
                po("100.00"),
                po("999.00", status=PurchaseOrderStatus.CANCELLED.value),
            )
        )
    )

    assert result.committed_purchase_cost == Decimal("100.00")
    assert result.committed_gross_profit == Decimal("75.00")


def test_brokerage_needs_no_purchase_order_but_still_needs_costs() -> None:
    result = analyse_order(order(fulfilment_model="BROKERAGE", purchase_orders=()))

    assert result.committed_purchase_cost == Decimal("0.00")
    assert result.documented_total_cost == Decimal("25.00")
    assert result.committed_gross_profit == Decimal("175.00")


def test_missing_shipment_evidence_keeps_profit_unavailable() -> None:
    result = analyse_order(order(shipments=()))

    assert result.committed_gross_profit is None
    assert "SHIPMENT_COST_MISSING" in result.missing_components
    assert result.completeness is CompletenessStatus.PARTIAL


def test_reconciliation_status_does_not_change_profit_and_actual_profit_stays_unavailable() -> None:
    result = analyse_order(
        order(reconciliation_status="VERIFIED", open_discrepancy_count=0)
    )

    assert result.classifications["actual_profit"] == "UNAVAILABLE"
    assert result.classifications["finance_observed_profit"] == "UNAVAILABLE"
    assert result.classifications["estimated_gross_profit"] == "ESTIMATED"
    assert result.classifications["committed_gross_profit"] == "COMMITTED"


def test_currency_totals_are_never_mixed() -> None:
    totals = sum_by_currency(
        [("USD", Decimal("10.00")), ("EUR", Decimal("5.00")), ("USD", Decimal("2.50"))]
    )

    assert [(item.currency, item.amount) for item in totals] == [
        ("EUR", Decimal("5.00")),
        ("USD", Decimal("12.50")),
    ]

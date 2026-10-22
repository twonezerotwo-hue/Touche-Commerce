"""Pure Stage 5D calculation tests.

No database, HTTP or Finance process is used. The tests pin the distinctions the
domain depends on: estimated vs committed vs documented values, no mixed-currency
arithmetic, no invented actual profit, and no false discrepancy categories.
"""

from __future__ import annotations

from dataclasses import replace
from datetime import date
from decimal import Decimal
from uuid import uuid4

from app.services.reconciliation_calculations import (
    CommercialFacts,
    PricingEstimateFact,
    PurchaseCommitmentFact,
    ShipmentCostFact,
    ShipmentFact,
    analyse,
    build_metrics,
    canonical_currency,
)

TODAY = date(2026, 10, 22)


def estimate(
    *, landed: str = "160.00", currency: str = "USD", status: str = "VERIFIED_INPUTS"
) -> PricingEstimateFact:
    return PricingEstimateFact(
        scenario_id=uuid4(),
        status=status,
        calculation_version="stage3-1.0.0",
        target_currency=currency,
        landed_total=Decimal(landed),
        sales_total=Decimal("240.00"),
    )


def po(
    amount: str = "140.00", *, status: str = "APPROVED", currency: str = "USD"
) -> PurchaseCommitmentFact:
    return PurchaseCommitmentFact(
        purchase_order_id=uuid4(),
        po_number=f"PO-{uuid4().hex[:5]}",
        status=status,
        currency=currency,
        total_cost=Decimal(amount),
    )


def shipment(
    *,
    costs: tuple[tuple[str, str, str], ...] = (("20.00", "USD", "FREIGHT"),),
    status: str = "BOOKED",
) -> ShipmentFact:
    return ShipmentFact(
        shipment_id=uuid4(),
        shipment_number=f"SHP-{uuid4().hex[:5]}",
        status=status,
        costs=tuple(
            ShipmentCostFact(
                cost_id=uuid4(),
                cost_type=cost_type,
                stage="ACTUAL",
                currency=currency,
                amount=Decimal(amount),
                reference=f"REF-{uuid4().hex[:6]}",
            )
            for amount, currency, cost_type in costs
        ),
    )


def facts(
    *,
    order_total: str = "240.00",
    currency: str = "USD",
    model: str = "PURCHASE_RESALE",
    status: str = "CONFIRMED",
    purchase_orders: tuple[PurchaseCommitmentFact, ...] | None = None,
    shipments: tuple[ShipmentFact, ...] | None = None,
    pricing: PricingEstimateFact | None = None,
) -> CommercialFacts:
    return CommercialFacts(
        sales_order_id=uuid4(),
        order_number="SO-2610-ABC123",
        customer_name="Buyer Ltd",
        status=status,
        fulfilment_model=model,
        currency=currency,
        order_total=Decimal(order_total),
        confirmed_at="2026-10-01T10:00:00+00:00",
        expected_delivery_date=None,
        purchase_orders=purchase_orders if purchase_orders is not None else (po(),),
        shipments=shipments if shipments is not None else (shipment(),),
        pricing_estimate=pricing if pricing is not None else estimate(),
    )


def test_currency_alias_is_not_conversion() -> None:
    assert canonical_currency("TL") == "TRY"
    assert canonical_currency("try") == "TRY"
    assert canonical_currency("EUR") == "EUR"


def test_decimal_metrics_are_exact_and_commitment_margin_is_not_profit() -> None:
    metrics = build_metrics(facts())
    assert metrics.accepted_sales_order_value == Decimal("240.00")
    assert metrics.purchase_commitments_total == Decimal("140.00")
    assert metrics.estimated_landed_cost == Decimal("160.00")
    assert metrics.recorded_operational_costs == Decimal("20.00")
    assert metrics.estimate_vs_recorded_variance == Decimal("140.00")
    assert metrics.commitment_based_margin == Decimal("80.00")
    assert metrics.commitment_based_margin_pct == Decimal("33.33")
    assert metrics.document_supported_margin is None


def test_multiple_purchase_orders_are_summed_only_in_one_currency() -> None:
    metrics = build_metrics(facts(purchase_orders=(po("100.00"), po("40.00", status="RECEIVED"))))
    assert metrics.purchase_commitments_total == Decimal("140.00")
    assert metrics.purchase_commitment_count == 2


def test_mixed_currency_purchase_order_is_not_added() -> None:
    analysis = analyse(
        facts(purchase_orders=(po("100.00"), po("40.00", currency="EUR"))),
        as_of=TODAY,
        finance_data_through=TODAY,
    )
    assert analysis.metrics.purchase_commitments_total is None
    assert analysis.metrics.commitment_based_margin is None
    assert any(d.code.value == "CURRENCY_MISMATCH" for d in analysis.discrepancies)


def test_draft_purchase_order_is_not_a_commitment() -> None:
    metrics = build_metrics(facts(purchase_orders=(po("100.00", status="DRAFT"),)))
    assert metrics.purchase_commitments_total is None
    assert metrics.purchase_commitment_count == 0


def test_partial_shipments_with_missing_freight_leave_costs_unavailable() -> None:
    analysis = analyse(
        facts(
            shipments=(
                shipment(costs=(("20.00", "USD", "FREIGHT"),)),
                shipment(costs=()),
            )
        ),
        as_of=TODAY,
        finance_data_through=TODAY,
    )
    assert analysis.metrics.recorded_operational_costs is None
    assert analysis.metrics.commitment_based_margin is None
    assert any(d.code.value == "INCOMPLETE_COSTS" for d in analysis.discrepancies)
    assert analysis.status == "INCOMPLETE"


def test_brokerage_does_not_require_a_purchase_commitment() -> None:
    metrics = build_metrics(facts(model="BROKERAGE", purchase_orders=()))
    assert metrics.purchase_commitments_total == Decimal("0.00")
    assert metrics.purchase_commitment_count == 0
    assert metrics.commitment_based_margin == Decimal("220.00")


def test_missing_pricing_estimate_is_missing_evidence_not_zero() -> None:
    analysis = analyse(
        replace(facts(), pricing_estimate=None),
        as_of=TODAY,
        finance_data_through=TODAY,
    )
    assert analysis.metrics.estimated_landed_cost is None
    assert analysis.metrics.estimate_vs_recorded_variance is None
    assert analysis.status == "INCOMPLETE"
    assert any(d.code.value == "MISSING_EVIDENCE" for d in analysis.discrepancies)


def test_finance_staleness_is_explicit() -> None:
    analysis = analyse(
        facts(),
        as_of=TODAY,
        finance_data_through=date(2026, 10, 20),
    )
    stale = [d for d in analysis.discrepancies if d.code.value == "SOURCE_STALE"]
    assert len(stale) == 1
    assert stale[0].severity.value == "WARNING"


def test_no_order_level_finance_reference_is_unavailable_not_a_missing_invoice() -> None:
    analysis = analyse(facts(), as_of=TODAY, finance_data_through=TODAY)
    gap = next(d for d in analysis.discrepancies if d.code.value == "MISSING_FINANCE_REFERENCE")
    assert "not proof that a real invoice is missing" in gap.detail
    assert analysis.status == "UNMATCHED"


def test_classifications_never_claim_actual_profit_or_document_margin() -> None:
    analysis = analyse(facts(), as_of=TODAY, finance_data_through=TODAY)
    assert analysis.classifications["actual_profit"] == "UNAVAILABLE"
    assert analysis.classifications["document_supported_margin"] == "UNAVAILABLE"
    assert analysis.classifications["commitment_based_margin"] == "COMMITTED"
    assert analysis.classifications["estimated_landed_cost"] == "ESTIMATED"


def test_all_supported_inputs_reach_unmatched_but_never_auto_verified() -> None:
    analysis = analyse(facts(), as_of=TODAY, finance_data_through=TODAY)
    assert analysis.metrics.is_complete
    assert analysis.status == "UNMATCHED"

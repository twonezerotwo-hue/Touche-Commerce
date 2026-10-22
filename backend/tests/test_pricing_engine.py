"""Unit tests for the deterministic landed-cost engine (no database required).

The engine is where a pricing bug would be most expensive, so these tests pin the
rules that make a landed cost auditable: explicit FX, cent-exact allocation,
margin versus markup, and a status that tells the truth about the inputs.
"""

from __future__ import annotations

from decimal import Decimal
from uuid import UUID, uuid4

import pytest

from app.db.models import ScenarioStatus
from app.services.pricing_engine import (
    CALCULATION_VERSION,
    CostInput,
    FxInput,
    PricingInputError,
    QuoteLineInput,
    allocate,
    calculate,
    money,
    unit_price,
)

D = Decimal


def line(
    *,
    quantity: str = "10",
    unit_price: str = "1.60",
    product_id: UUID | None = None,
) -> QuoteLineInput:
    return QuoteLineInput(
        product_id=product_id or uuid4(),
        description="Almond kernels",
        unit="kg",
        quantity=D(quantity),
        unit_price=D(unit_price),
    )


def test_allocate_never_loses_a_cent() -> None:
    shares = allocate(D("10.00"), [D("1"), D("1"), D("1")])

    assert sum(shares) == D("10.00")
    assert shares == [D("3.34"), D("3.33"), D("3.33")]


def test_allocate_is_stable_for_identical_weights() -> None:
    first = allocate(D("0.05"), [D("2"), D("2"), D("2")])
    second = allocate(D("0.05"), [D("2"), D("2"), D("2")])

    assert first == second
    assert sum(first) == D("0.05")


def test_allocate_with_zero_weights_splits_evenly() -> None:
    shares = allocate(D("3.00"), [D("0"), D("0")])

    assert shares == [D("1.50"), D("1.50")]


def test_margin_and_markup_produce_different_prices() -> None:
    cost = {
        "lines": [line(quantity="1", unit_price="10.00")],
        "quote_currency": "USD",
        "target_currency": "USD",
        "fx": None,
        "components": [],
    }

    margin = calculate(**cost, margin_pct=D("20"))
    markup = calculate(**cost, markup_pct=D("20"))

    assert margin.lines[0].unit_sale_price == D("12.5000")
    assert markup.lines[0].unit_sale_price == D("12.0000")


def test_margin_and_markup_are_mutually_exclusive() -> None:
    with pytest.raises(PricingInputError, match="either margin_pct or markup_pct"):
        calculate(
            lines=[line()],
            quote_currency="USD",
            target_currency="USD",
            fx=None,
            components=[],
            margin_pct=D("10"),
            markup_pct=D("10"),
        )


def test_order_cost_is_allocated_pro_rata_by_purchase_value() -> None:
    cheap = line(quantity="10", unit_price="1.60")
    rich = line(quantity="10", unit_price="2.40")

    outcome = calculate(
        lines=[cheap, rich],
        quote_currency="USD",
        target_currency="USD",
        fx=None,
        components=[
            CostInput(
                cost_type="FREIGHT",
                amount=D("10.00"),
                currency="USD",
                basis="ORDER",
                verification_status="VERIFIED",
                source_reference="INV-1",
            )
        ],
        margin_pct=D("15"),
    )

    assert [item.allocated_cost for item in outcome.lines] == [D("4.00"), D("6.00")]
    assert outcome.purchase_total == D("40.00")
    assert outcome.additional_cost_total == D("10.00")
    assert outcome.landed_total == D("50.00")
    assert outcome.sales_total == D("58.82")
    assert outcome.gross_margin == D("8.82")


def test_line_cost_lands_on_its_own_product() -> None:
    first = line(quantity="10", unit_price="1.00")
    second = line(quantity="10", unit_price="3.00")

    outcome = calculate(
        lines=[first, second],
        quote_currency="USD",
        target_currency="USD",
        fx=None,
        components=[
            CostInput(
                cost_type="DOMESTIC_TRANSPORT",
                amount=D("5.00"),
                currency="USD",
                basis="LINE",
                verification_status="VERIFIED",
                source_reference="TRUCK-9",
                product_id=second.product_id,
            )
        ],
    )

    assert outcome.lines[0].allocated_cost == D("0.00")
    assert outcome.lines[1].allocated_cost == D("5.00")
    assert outcome.lines[1].landed_line_cost == D("35.00")


def test_line_cost_without_product_is_rejected() -> None:
    with pytest.raises(PricingInputError, match="must name the product"):
        calculate(
            lines=[line()],
            quote_currency="USD",
            target_currency="USD",
            fx=None,
            components=[
                CostInput(
                    cost_type="FREIGHT",
                    amount=D("1.00"),
                    currency="USD",
                    basis="LINE",
                    verification_status="VERIFIED",
                    source_reference="INV-1",
                )
            ],
        )


def test_line_cost_for_an_unquoted_product_is_rejected() -> None:
    with pytest.raises(PricingInputError, match="not quoted"):
        calculate(
            lines=[line()],
            quote_currency="USD",
            target_currency="USD",
            fx=None,
            components=[
                CostInput(
                    cost_type="FREIGHT",
                    amount=D("1.00"),
                    currency="USD",
                    basis="LINE",
                    verification_status="VERIFIED",
                    source_reference="INV-1",
                    product_id=uuid4(),
                )
            ],
        )


def test_cross_currency_requires_an_explicit_snapshot() -> None:
    with pytest.raises(PricingInputError, match="explicit FX rate snapshot"):
        calculate(
            lines=[line()],
            quote_currency="EUR",
            target_currency="USD",
            fx=None,
            components=[],
        )


def test_fx_snapshot_must_convert_the_right_pair() -> None:
    with pytest.raises(PricingInputError, match="must convert"):
        calculate(
            lines=[line()],
            quote_currency="EUR",
            target_currency="USD",
            fx=FxInput(
                base_currency="USD",
                quote_currency="EUR",
                rate=D("0.92"),
                snapshot_id=uuid4(),
            ),
            components=[],
        )


def test_fx_converts_line_costs_before_allocating() -> None:
    outcome = calculate(
        lines=[line(quantity="10", unit_price="2.00")],
        quote_currency="EUR",
        target_currency="USD",
        fx=FxInput(
            base_currency="EUR",
            quote_currency="USD",
            rate=D("1.1000000000"),
            snapshot_id=uuid4(),
        ),
        components=[],
    )

    assert outcome.lines[0].unit_cost == D("2.2000")
    assert outcome.lines[0].line_cost == D("22.00")
    assert outcome.purchase_total == D("22.00")


def test_estimated_component_marks_the_scenario_estimated() -> None:
    outcome = calculate(
        lines=[line()],
        quote_currency="USD",
        target_currency="USD",
        fx=None,
        components=[
            CostInput(
                cost_type="FREIGHT",
                amount=D("5.00"),
                currency="USD",
                basis="ORDER",
                verification_status="ESTIMATED",
                source_reference="QUOTE-1",
            )
        ],
    )

    assert outcome.status is ScenarioStatus.ESTIMATED
    assert outcome.completeness["estimated_component_count"] == 1
    assert outcome.completeness["calculation_version"] == CALCULATION_VERSION


def test_verified_inputs_are_reported_as_verified() -> None:
    outcome = calculate(
        lines=[line()],
        quote_currency="usd",
        target_currency="USD",
        fx=None,
        components=[
            CostInput(
                cost_type="FREIGHT",
                amount=D("5.00"),
                currency="USD",
                basis="ORDER",
                verification_status="VERIFIED",
                source_reference="INV-1",
            )
        ],
    )

    assert outcome.status is ScenarioStatus.VERIFIED_INPUTS
    assert outcome.quote_currency == "USD"
    assert outcome.completeness["issues"] == []


def test_zero_priced_line_is_incomplete() -> None:
    outcome = calculate(
        lines=[line(unit_price="0")],
        quote_currency="USD",
        target_currency="USD",
        fx=None,
        components=[],
    )

    assert outcome.status is ScenarioStatus.INCOMPLETE
    assert outcome.completeness["issues"]


def test_duplicate_products_are_rejected() -> None:
    product_id = uuid4()
    with pytest.raises(PricingInputError, match="only once"):
        calculate(
            lines=[
                line(product_id=product_id),
                line(product_id=product_id),
            ],
            quote_currency="USD",
            target_currency="USD",
            fx=None,
            components=[],
        )


def test_quantity_must_be_positive() -> None:
    with pytest.raises(PricingInputError, match="Quantity must be positive"):
        calculate(
            lines=[line(quantity="0")],
            quote_currency="USD",
            target_currency="USD",
            fx=None,
            components=[],
        )


def test_negative_unit_price_is_rejected() -> None:
    with pytest.raises(PricingInputError, match="cannot be negative"):
        calculate(
            lines=[line(unit_price="-1.00")],
            quote_currency="USD",
            target_currency="USD",
            fx=None,
            components=[],
        )


def test_percentages_outside_the_range_are_rejected() -> None:
    with pytest.raises(PricingInputError, match="below 100"):
        calculate(
            lines=[line()],
            quote_currency="USD",
            target_currency="USD",
            fx=None,
            components=[],
            margin_pct=D("100"),
        )


def test_unknown_cost_type_is_rejected() -> None:
    with pytest.raises(PricingInputError, match="Unknown cost type"):
        calculate(
            lines=[line()],
            quote_currency="USD",
            target_currency="USD",
            fx=None,
            components=[
                CostInput(
                    cost_type="MAGIC",
                    amount=D("1.00"),
                    currency="USD",
                    basis="ORDER",
                    verification_status="VERIFIED",
                    source_reference="INV-1",
                )
            ],
        )


def test_rounding_helpers_are_half_up() -> None:
    assert money(D("1.005")) == D("1.01")
    assert unit_price(D("2.35294")) == D("2.3529")

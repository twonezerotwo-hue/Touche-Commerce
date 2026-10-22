"""Deterministic landed-cost and selling-price engine (Stage 3).

The engine is a *pure* function of explicit inputs. It never calls a bank feed,
never guesses an exchange rate and never reads the clock: the same inputs always
produce the same results, which is what makes a landed-cost figure auditable.

Money rules (Decimal end to end):

* quantities and unit prices are kept as given (``Numeric`` in PostgreSQL);
* converted amounts, allocations and totals are rounded to cents
  (``ROUND_HALF_UP``) and per-unit figures to four decimals;
* ORDER-basis costs are allocated pro-rata by line purchase value using the
  largest-remainder method, so the allocated cents always add up to the cost
  component exactly instead of losing a cent per line;
* LINE-basis costs must name the product line they belong to.

Selling price is derived from the *landed* unit cost using exactly one of margin
or markup: ``price = cost / (1 - margin)`` or ``price = cost * (1 + markup)``.
Mixing both is rejected because the two produce different prices for the same
percentage and a silent choice would be a pricing bug.
"""

from __future__ import annotations

from collections.abc import Sequence
from dataclasses import dataclass
from decimal import ROUND_DOWN, ROUND_HALF_UP, Decimal
from uuid import UUID

from app.db.models.sourcing import (
    CostBasis,
    CostType,
    ScenarioStatus,
    VerificationStatus,
)

CALCULATION_VERSION = "stage3-1.0.0"
MONEY_QUANTUM = Decimal("0.01")
UNIT_QUANTUM = Decimal("0.0001")
ZERO = Decimal("0")


class PricingInputError(ValueError):
    """The inputs cannot produce a deterministic landed cost."""


@dataclass(frozen=True)
class QuoteLineInput:
    """One purchase line, in the supplier quote's currency."""

    product_id: UUID
    description: str
    unit: str
    quantity: Decimal
    unit_price: Decimal


@dataclass(frozen=True)
class FxInput:
    """An explicit, sourced conversion from the quote to the target currency."""

    base_currency: str
    quote_currency: str
    rate: Decimal
    snapshot_id: UUID


@dataclass(frozen=True)
class CostInput:
    """One additional cost, with its rate already resolved to the target currency.

    ``fx_rate`` is ``None`` when ``currency`` already equals the target currency;
    the service resolves the rate from an :class:`FxInput` snapshot before the
    engine runs, and stores the snapshot id with the component.
    """

    cost_type: str
    amount: Decimal
    currency: str
    basis: str
    verification_status: str
    source_reference: str
    product_id: UUID | None = None
    fx_rate: Decimal | None = None
    fx_snapshot_id: UUID | None = None
    notes: str | None = None


@dataclass(frozen=True)
class PricingLine:
    product_id: UUID
    description: str
    unit: str
    quantity: Decimal
    unit_cost: Decimal
    line_cost: Decimal
    allocated_cost: Decimal
    landed_line_cost: Decimal
    landed_unit_cost: Decimal
    margin_pct: Decimal
    markup_pct: Decimal
    unit_sale_price: Decimal
    line_sale_price: Decimal
    line_margin: Decimal


@dataclass(frozen=True)
class PricingOutcome:
    quote_currency: str
    target_currency: str
    fx_rate: Decimal
    fx_snapshot_id: UUID | None
    lines: tuple[PricingLine, ...]
    purchase_total: Decimal
    additional_cost_total: Decimal
    landed_total: Decimal
    sales_total: Decimal
    gross_margin: Decimal
    gross_margin_pct: Decimal
    markup_pct: Decimal
    margin_pct: Decimal
    status: ScenarioStatus
    completeness: dict[str, object]

    def as_inputs(self) -> dict[str, object]:
        """JSON-safe snapshot of every assumption used by the calculation."""
        return {
            "calculation_version": CALCULATION_VERSION,
            "quote_currency": self.quote_currency,
            "target_currency": self.target_currency,
            "fx_rate": str(self.fx_rate),
            "fx_snapshot_id": str(self.fx_snapshot_id) if self.fx_snapshot_id else None,
            "margin_pct": str(self.margin_pct),
            "markup_pct": str(self.markup_pct),
        }

    def as_results(self) -> dict[str, object]:
        """JSON-safe snapshot of the derived figures, rounded exactly as returned."""
        return {
            "calculation_version": CALCULATION_VERSION,
            "status": self.status.value,
            "totals": {
                "purchase_total": str(self.purchase_total),
                "additional_cost_total": str(self.additional_cost_total),
                "landed_total": str(self.landed_total),
                "sales_total": str(self.sales_total),
                "gross_margin": str(self.gross_margin),
                "gross_margin_pct": str(self.gross_margin_pct),
                "markup_pct": str(self.markup_pct),
            },
            "lines": [
                {
                    "product_id": str(line.product_id),
                    "description": line.description,
                    "unit": line.unit,
                    "quantity": str(line.quantity),
                    "unit_cost": str(line.unit_cost),
                    "line_cost": str(line.line_cost),
                    "allocated_cost": str(line.allocated_cost),
                    "landed_line_cost": str(line.landed_line_cost),
                    "landed_unit_cost": str(line.landed_unit_cost),
                    "unit_sale_price": str(line.unit_sale_price),
                    "line_sale_price": str(line.line_sale_price),
                    "line_margin": str(line.line_margin),
                }
                for line in self.lines
            ],
            "completeness": self.completeness,
        }


def money(value: Decimal) -> Decimal:
    """Round a monetary value to cents, half up (never banker's rounding)."""
    return Decimal(value).quantize(MONEY_QUANTUM, rounding=ROUND_HALF_UP)


def unit_price(value: Decimal) -> Decimal:
    """Round a per-unit price to four decimals."""
    return Decimal(value).quantize(UNIT_QUANTUM, rounding=ROUND_HALF_UP)


def allocate(total: Decimal, weights: list[Decimal]) -> list[Decimal]:
    """Allocate ``total`` pro-rata, returning cents that sum to ``total`` exactly.

    Fractional remainders are handed out in descending order (ties broken by
    position) so allocation is stable for identical inputs.
    """
    if not weights:
        return []
    target = money(total)
    if sum(weights, ZERO) <= ZERO:
        weights = [Decimal(1) for _ in weights]
    weight_sum = sum(weights, ZERO)
    raw = [target * weight / weight_sum for weight in weights]
    shares = [value.quantize(MONEY_QUANTUM, rounding=ROUND_DOWN) for value in raw]
    remainder = int(((target - sum(shares, ZERO)) / MONEY_QUANTUM).to_integral_value())
    order = sorted(range(len(raw)), key=lambda index: (-(raw[index] - shares[index]), index))
    for index in order[:remainder]:
        shares[index] += MONEY_QUANTUM
    return shares


def _currency(value: str, field: str) -> str:
    cleaned = value.strip().upper()
    if len(cleaned) != 3 or not cleaned.isalpha():
        raise PricingInputError(f"{field} must be a three-letter ISO-4217 code.")
    return cleaned


def _percent(value: Decimal, field: str) -> Decimal:
    if value < ZERO or value >= Decimal("100"):
        raise PricingInputError(f"{field} must be at least 0 and below 100.")
    return Decimal(value)


def _resolve_fx(
    *, quote_currency: str, target_currency: str, fx: FxInput | None
) -> tuple[Decimal, UUID | None]:
    if quote_currency == target_currency:
        return Decimal("1"), None
    if fx is None:
        raise PricingInputError(
            "An explicit FX rate snapshot is required to convert "
            f"{quote_currency} to {target_currency}; rates are never inferred."
        )
    if fx.base_currency != quote_currency or fx.quote_currency != target_currency:
        raise PricingInputError(
            "The FX snapshot must convert the supplier quote currency "
            f"({quote_currency}) into the target currency ({target_currency})."
        )
    if fx.rate <= ZERO:
        raise PricingInputError("The FX rate must be greater than zero.")
    return Decimal(fx.rate), fx.snapshot_id


def _component_rate(component: CostInput, target_currency: str) -> Decimal:
    if component.currency == target_currency:
        return Decimal("1")
    if component.fx_rate is None or component.fx_snapshot_id is None:
        raise PricingInputError(
            f"The {component.cost_type} component is in {component.currency}; an "
            f"explicit FX snapshot to {target_currency} is required."
        )
    if component.fx_rate <= ZERO:
        raise PricingInputError("A cost component FX rate must be greater than zero.")
    return Decimal(component.fx_rate)


def calculate(
    *,
    lines: Sequence[QuoteLineInput],
    quote_currency: str,
    target_currency: str,
    fx: FxInput | None,
    components: Sequence[CostInput],
    margin_pct: Decimal = ZERO,
    markup_pct: Decimal = ZERO,
) -> PricingOutcome:
    """Compute landed costs and selling prices for one supplier quote.

    Raises :class:`PricingInputError` instead of guessing: a missing FX snapshot,
    a LINE cost without a product, or both margin and markup are input errors.
    """
    source_currency = _currency(quote_currency, "quote_currency")
    resolved_target = _currency(target_currency, "target_currency")
    if not lines:
        raise PricingInputError("A pricing scenario needs at least one quoted line.")
    products = [line.product_id for line in lines]
    if len(set(products)) != len(products):
        raise PricingInputError("Each product may appear only once per supplier quote.")

    margin = _percent(margin_pct, "margin_pct")
    markup = _percent(markup_pct, "markup_pct")
    if margin > ZERO and markup > ZERO:
        raise PricingInputError("Use either margin_pct or markup_pct, never both.")

    rate, fx_snapshot_id = _resolve_fx(
        quote_currency=source_currency, target_currency=resolved_target, fx=fx
    )

    base_costs: list[Decimal] = []
    landed_costs: list[Decimal] = []
    for line in lines:
        if line.quantity <= ZERO:
            raise PricingInputError(f"Quantity must be positive for {line.description}.")
        if line.unit_price < ZERO:
            raise PricingInputError(f"Unit price cannot be negative for {line.description}.")
        base = money(unit_price(line.unit_price * rate) * line.quantity)
        base_costs.append(base)
        landed_costs.append(base)

    cost_types = {item.value for item in CostType}
    bases = {basis.value for basis in CostBasis}
    verified_statuses = {status.value for status in VerificationStatus}
    for component in components:
        if component.cost_type not in cost_types:
            raise PricingInputError(f"Unknown cost type: {component.cost_type}.")
        if component.basis not in bases:
            raise PricingInputError(f"Unknown cost basis: {component.basis}.")
        if component.verification_status not in verified_statuses:
            raise PricingInputError(
                f"Unknown verification status: {component.verification_status}."
            )
        if component.amount < ZERO:
            raise PricingInputError("A cost component cannot be negative.")
        converted = money(component.amount * _component_rate(component, resolved_target))
        if component.basis == CostBasis.LINE.value:
            if component.product_id is None:
                raise PricingInputError(
                    "A LINE-basis cost component must name the product it belongs to."
                )
            if component.product_id not in products:
                raise PricingInputError(
                    "A LINE-basis cost component references a product that is not quoted."
                )
            landed_costs[products.index(component.product_id)] += converted
        else:
            shares = allocate(converted, base_costs)
            landed_costs = [
                value + share for value, share in zip(landed_costs, shares, strict=True)
            ]

    additional_total = sum(landed_costs, ZERO) - sum(base_costs, ZERO)

    lines_out: list[PricingLine] = []
    for line, base, landed in zip(lines, base_costs, landed_costs, strict=True):
        landed_unit = unit_price(landed / line.quantity)
        if margin > ZERO:
            selling = unit_price(landed_unit / (Decimal("1") - margin / Decimal("100")))
        elif markup > ZERO:
            selling = unit_price(landed_unit * (Decimal("1") + markup / Decimal("100")))
        else:
            selling = landed_unit
        revenue = money(selling * line.quantity)
        lines_out.append(
            PricingLine(
                product_id=line.product_id,
                description=line.description,
                unit=line.unit,
                quantity=line.quantity,
                unit_cost=unit_price(line.unit_price * rate),
                line_cost=base,
                allocated_cost=money(landed - base),
                landed_line_cost=money(landed),
                landed_unit_cost=landed_unit,
                margin_pct=margin,
                markup_pct=markup,
                unit_sale_price=selling,
                line_sale_price=revenue,
                line_margin=money(revenue - landed),
            )
        )

    purchase_total = money(sum(base_costs, ZERO))
    landed_total = money(sum(landed_costs, ZERO))
    sales_total = money(sum((line.line_sale_price for line in lines_out), Decimal("0.00")))
    gross_margin = money(sales_total - landed_total)
    realised_margin = (
        unit_price(gross_margin / sales_total * Decimal("100")) if sales_total > ZERO else ZERO
    )
    realised_markup = (
        unit_price(gross_margin / landed_total * Decimal("100")) if landed_total > ZERO else ZERO
    )

    issues = [f"line_unpriced:{line.product_id}" for line in lines_out if line.line_cost == ZERO]
    estimated = sum(
        1
        for component in components
        if component.verification_status == VerificationStatus.ESTIMATED.value
    )
    completeness: dict[str, object] = {
        "calculation_version": CALCULATION_VERSION,
        "line_count": len(lines_out),
        "component_count": len(components),
        "verified_component_count": len(components) - estimated,
        "estimated_component_count": estimated,
        "fx_required": source_currency != resolved_target,
        "fx_snapshot_id": str(fx_snapshot_id) if fx_snapshot_id else None,
        "realised_margin_pct": str(realised_margin),
        "realised_markup_pct": str(realised_markup),
        "issues": issues,
    }
    status = (
        ScenarioStatus.INCOMPLETE
        if issues
        else ScenarioStatus.ESTIMATED
        if estimated
        else ScenarioStatus.VERIFIED_INPUTS
    )
    return PricingOutcome(
        quote_currency=source_currency,
        target_currency=resolved_target,
        fx_rate=rate,
        fx_snapshot_id=fx_snapshot_id,
        lines=tuple(lines_out),
        purchase_total=purchase_total,
        additional_cost_total=money(additional_total),
        landed_total=landed_total,
        sales_total=sales_total,
        gross_margin=gross_margin,
        gross_margin_pct=realised_margin,
        markup_pct=markup,
        margin_pct=margin,
        status=status,
        completeness=completeness,
    )


__all__ = [
    "CALCULATION_VERSION",
    "MONEY_QUANTUM",
    "CostInput",
    "FxInput",
    "PricingInputError",
    "PricingLine",
    "PricingOutcome",
    "QuoteLineInput",
    "allocate",
    "calculate",
    "money",
    "unit_price",
]

"""Pricing scenario service: landed cost, margin and the stored calculation.

The service is the seam between the database and the pure engine in
:mod:`app.services.pricing_engine`. It resolves *explicit* FX snapshots, turns
quote lines and cost components into engine inputs, persists both the inputs and
the results, and never derives a rate or a price on its own.

Storing the calculation rather than recomputing it on read matters: a quote
received today keeps today's landed cost even after tomorrow's freight invoice
arrives. Recalculating is an explicit, audited action that bumps ``version``.
"""

from __future__ import annotations

from collections.abc import Sequence
from dataclasses import dataclass
from datetime import UTC, datetime
from decimal import Decimal
from typing import Any
from uuid import UUID

from sqlalchemy import and_, delete, select, tuple_
from sqlalchemy.orm import Session

from app.core.errors import BadRequestError, NotFoundError, VersionConflictError
from app.db.engine import Database
from app.db.models import (
    AuditAction,
    AuditOutcome,
    Counterparty,
    Deal,
    FxRateSnapshot,
    Incoterm,
    PricingCostComponent,
    PricingScenario,
    Product,
    SupplierQuote,
    SupplierRfq,
    VerificationStatus,
)
from app.db.tenant import apply_company_context
from app.services.audit import record_audit
from app.services.fx import normalise_currency
from app.services.pagination import decode_cursor, encode_cursor
from app.services.pricing_engine import (
    CALCULATION_VERSION,
    CostInput,
    FxInput,
    PricingInputError,
    PricingOutcome,
    QuoteLineInput,
    calculate,
    money,
)
from app.services.supplier_quotes import QuoteRecord, SupplierQuoteService
from app.services.trade_meta import WriteMeta, clean_optional

_INCOTERMS = {term.value for term in Incoterm}
_VERIFICATION = {status.value for status in VerificationStatus}


@dataclass(frozen=True)
class CostComponentInput:
    cost_type: str
    amount: Decimal
    currency: str
    basis: str
    source_reference: str
    verification_status: str
    fx_rate_snapshot_id: UUID | None = None
    product_id: UUID | None = None
    notes: str | None = None


@dataclass(frozen=True)
class ScenarioCreateData:
    supplier_quote_id: UUID
    target_currency: str
    sales_incoterm: str | None
    sales_named_place: str | None
    margin_pct: Decimal
    markup_pct: Decimal
    fx_rate_snapshot_id: UUID | None
    components: tuple[CostComponentInput, ...]


@dataclass(frozen=True)
class ScenarioComponentRecord:
    id: UUID
    cost_type: str
    amount: Decimal
    currency: str
    basis: str
    source_reference: str
    verification_status: str
    fx_rate_snapshot_id: UUID | None
    product_id: UUID | None
    product_sku: str | None
    product_name: str | None
    notes: str | None


@dataclass(frozen=True)
class ScenarioRecord:
    id: UUID
    company_id: UUID
    deal_id: UUID
    deal_reference: str
    supplier_quote_id: UUID
    rfq_id: UUID
    rfq_reference: str
    supplier_counterparty_id: UUID
    supplier_name: str
    quote_currency: str
    quote_revision: int
    target_currency: str
    sales_incoterm: str | None
    sales_named_place: str | None
    status: str
    calculation_version: str
    pricing_inputs: dict[str, object]
    calculated_results: dict[str, object]
    completeness: dict[str, object]
    version: int
    created_by: UUID
    created_at: datetime
    updated_at: datetime
    components: tuple[ScenarioComponentRecord, ...]


@dataclass(frozen=True)
class ScenarioSummaryRecord:
    id: UUID
    company_id: UUID
    deal_id: UUID
    deal_reference: str
    supplier_quote_id: UUID
    rfq_reference: str
    supplier_name: str
    target_currency: str
    status: str
    landed_total: Decimal
    sales_total: Decimal
    gross_margin: Decimal
    gross_margin_pct: Decimal
    version: int
    created_at: datetime
    updated_at: datetime


@dataclass(frozen=True)
class ScenarioFilters:
    status: str | None = None
    deal_id: UUID | None = None
    supplier_quote_id: UUID | None = None

    def as_fingerprint(self) -> dict[str, str | None]:
        return {
            "status": self.status,
            "deal_id": str(self.deal_id) if self.deal_id else None,
            "supplier_quote_id": (str(self.supplier_quote_id) if self.supplier_quote_id else None),
        }


@dataclass(frozen=True)
class ScenarioPage:
    items: tuple[ScenarioSummaryRecord, ...]
    next_cursor: str | None


def _fx_snapshot(
    session: Session, *, company_id: UUID, snapshot_id: UUID, base: str, quote: str
) -> FxRateSnapshot:
    row = session.execute(
        select(FxRateSnapshot).where(
            FxRateSnapshot.id == snapshot_id,
            FxRateSnapshot.company_id == company_id,
        )
    ).scalar_one_or_none()
    if row is None:
        raise BadRequestError(
            "The FX rate snapshot does not exist in this company.",
            details=[
                {
                    "field": "fx_rate_snapshot_id",
                    "message": "Unknown FX snapshot for the active company.",
                    "type": "value_error",
                }
            ],
        )
    if (row.base_currency, row.quote_currency) != (base, quote):
        raise BadRequestError(
            "The FX snapshot converts the wrong currency pair.",
            details=[
                {
                    "field": "fx_rate_snapshot_id",
                    "message": (
                        f"Expected {base}/{quote}, got {row.base_currency}/{row.quote_currency}."
                    ),
                    "type": "value_error",
                }
            ],
        )
    return row


def _prepare(
    session: Session,
    *,
    company_id: UUID,
    quote: QuoteRecord,
    data: ScenarioCreateData,
) -> tuple[dict[str, object], PricingOutcome, list[dict[str, Any]]]:
    """Resolve FX, build engine inputs and run the deterministic calculation."""
    target = normalise_currency(data.target_currency, "target_currency")
    source = normalise_currency(quote.currency, "quote_currency")

    fx_input: FxInput | None
    if source == target:
        if data.fx_rate_snapshot_id is not None:
            raise BadRequestError(
                "No FX snapshot is needed when the quote is already in the target currency.",
                details=[
                    {
                        "field": "fx_rate_snapshot_id",
                        "message": "Remove the snapshot or change the target currency.",
                        "type": "value_error",
                    }
                ],
            )
        fx_input = None
    else:
        if data.fx_rate_snapshot_id is None:
            raise BadRequestError(
                "An explicit FX rate snapshot is required for this conversion.",
                details=[
                    {
                        "field": "fx_rate_snapshot_id",
                        "message": f"Record a sourced {source}/{target} rate first.",
                        "type": "value_error",
                    }
                ],
            )
        snapshot = _fx_snapshot(
            session,
            company_id=company_id,
            snapshot_id=data.fx_rate_snapshot_id,
            base=source,
            quote=target,
        )
        fx_input = FxInput(
            base_currency=snapshot.base_currency,
            quote_currency=snapshot.quote_currency,
            rate=Decimal(snapshot.rate),
            snapshot_id=snapshot.id,
        )

    if data.sales_incoterm is not None:
        incoterm = str(data.sales_incoterm).strip().upper()
        if incoterm not in _INCOTERMS:
            raise BadRequestError(
                "Unknown sales Incoterm; use an Incoterms 2020 code.",
                details=[
                    {
                        "field": "sales_incoterm",
                        "message": f"{incoterm} is not an Incoterms 2020 code.",
                        "type": "value_error",
                    }
                ],
            )
    if data.sales_named_place is not None:
        place = " ".join(data.sales_named_place.split())
        if not 2 <= len(place) <= 160:
            raise BadRequestError("The sales named place must be 2 to 160 characters.")

    components: list[CostInput] = []
    component_rows: list[dict[str, Any]] = []
    for component in data.components:
        currency = normalise_currency(component.currency, "components.currency")
        if component.verification_status not in _VERIFICATION:
            raise BadRequestError(f"Unknown verification status: {component.verification_status}.")
        rate: Decimal | None = None
        snapshot_id: UUID | None = None
        source_reference = " ".join(component.source_reference.split())
        if currency == target:
            if component.fx_rate_snapshot_id is not None:
                raise BadRequestError(
                    "A cost component already in the target currency needs no FX snapshot.",
                    details=[
                        {
                            "field": "components.fx_rate_snapshot_id",
                            "message": "Remove the snapshot for this component.",
                            "type": "value_error",
                        }
                    ],
                )
        else:
            if component.fx_rate_snapshot_id is None:
                raise BadRequestError(
                    "Every cost component in another currency needs an FX snapshot.",
                    details=[
                        {
                            "field": "components.fx_rate_snapshot_id",
                            "message": (
                                f"Record a sourced {currency}/{target} rate for the "
                                f"{component.cost_type} component."
                            ),
                            "type": "value_error",
                        }
                    ],
                )
            snapshot = _fx_snapshot(
                session,
                company_id=company_id,
                snapshot_id=component.fx_rate_snapshot_id,
                base=currency,
                quote=target,
            )
            rate = Decimal(snapshot.rate)
            snapshot_id = snapshot.id

        components.append(
            CostInput(
                cost_type=component.cost_type,
                amount=Decimal(component.amount),
                currency=currency,
                basis=component.basis,
                verification_status=component.verification_status,
                source_reference=source_reference,
                product_id=component.product_id,
                fx_rate=rate,
                fx_snapshot_id=snapshot_id,
                notes=clean_optional(component.notes),
            )
        )
        component_rows.append(
            {
                "cost_type": component.cost_type,
                "amount": money(Decimal(component.amount)),
                "currency": currency,
                "basis": component.basis,
                "source_reference": source_reference,
                "verification_status": component.verification_status,
                "fx_rate_snapshot_id": snapshot_id,
                "product_id": component.product_id,
                "notes": clean_optional(component.notes),
            }
        )

    try:
        outcome = calculate(
            lines=[
                QuoteLineInput(
                    product_id=item.product_id,
                    description=item.description,
                    unit=item.unit,
                    quantity=item.quantity,
                    unit_price=item.unit_price,
                )
                for item in quote.items
            ],
            quote_currency=source,
            target_currency=target,
            fx=fx_input,
            components=components,
            margin_pct=data.margin_pct,
            markup_pct=data.markup_pct,
        )
    except PricingInputError as exc:
        raise BadRequestError(
            str(exc), details=[{"message": str(exc), "type": "value_error"}]
        ) from exc

    inputs: dict[str, object] = {
        "calculation_version": CALCULATION_VERSION,
        "supplier_quote_id": str(quote.id),
        "supplier_quote_revision": quote.revision,
        "quote_currency": source,
        "target_currency": target,
        "margin_pct": str(data.margin_pct),
        "markup_pct": str(data.markup_pct),
        "fx_snapshot_id": str(fx_input.snapshot_id) if fx_input else None,
        "fx_rate": str(fx_input.rate) if fx_input else "1",
        "lines": [
            {
                "product_id": str(item.product_id),
                "description": item.description,
                "unit": item.unit,
                "quantity": str(item.quantity),
                "unit_price": str(item.unit_price),
            }
            for item in quote.items
        ],
        "components": [
            {
                key: (str(value) if isinstance(value, UUID | Decimal) else value)
                for key, value in row.items()
            }
            for row in component_rows
        ],
    }
    return inputs, outcome, component_rows


def _component_records(
    session: Session, *, company_id: UUID, scenario_id: UUID
) -> tuple[ScenarioComponentRecord, ...]:
    rows = session.execute(
        select(
            PricingCostComponent,
            Product.sku,
            Product.name,
        )
        .outerjoin(
            Product,
            and_(
                Product.id == PricingCostComponent.product_id,
                Product.company_id == PricingCostComponent.company_id,
            ),
        )
        .where(
            PricingCostComponent.scenario_id == scenario_id,
            PricingCostComponent.company_id == company_id,
        )
        .order_by(PricingCostComponent.created_at, PricingCostComponent.id)
    ).all()
    return tuple(
        ScenarioComponentRecord(
            id=component.id,
            cost_type=component.cost_type,
            amount=component.amount,
            currency=component.currency,
            basis=component.basis,
            source_reference=component.source_reference,
            verification_status=component.verification_status,
            fx_rate_snapshot_id=component.fx_rate_snapshot_id,
            product_id=component.product_id,
            product_sku=sku,
            product_name=name,
            notes=component.notes,
        )
        for component, sku, name in rows
    )


def _load(
    session: Session, *, company_id: UUID, scenario_id: UUID, include_children: bool = True
) -> ScenarioRecord:
    row = session.execute(
        select(
            PricingScenario,
            SupplierQuote.currency,
            SupplierQuote.revision,
            SupplierQuote.rfq_id,
            SupplierQuote.supplier_counterparty_id,
            SupplierRfq.reference_number,
            SupplierRfq.deal_id,
            Deal.reference,
            Counterparty.name,
        )
        .join(
            SupplierQuote,
            and_(
                SupplierQuote.id == PricingScenario.supplier_quote_id,
                SupplierQuote.company_id == PricingScenario.company_id,
            ),
        )
        .join(
            SupplierRfq,
            and_(
                SupplierRfq.id == SupplierQuote.rfq_id,
                SupplierRfq.company_id == SupplierQuote.company_id,
            ),
        )
        .join(
            Deal,
            and_(
                Deal.id == SupplierRfq.deal_id,
                Deal.company_id == SupplierRfq.company_id,
            ),
        )
        .join(
            Counterparty,
            and_(
                Counterparty.id == SupplierQuote.supplier_counterparty_id,
                Counterparty.company_id == SupplierQuote.company_id,
            ),
        )
        .where(
            PricingScenario.id == scenario_id,
            PricingScenario.company_id == company_id,
        )
    ).one_or_none()
    if row is None:
        raise NotFoundError("The pricing scenario does not exist.")
    (
        scenario,
        quote_currency,
        quote_revision,
        rfq_id,
        supplier_id,
        rfq_reference,
        deal_id,
        deal_reference,
        supplier_name,
    ) = row
    return ScenarioRecord(
        id=scenario.id,
        company_id=scenario.company_id,
        deal_id=deal_id,
        deal_reference=deal_reference,
        supplier_quote_id=scenario.supplier_quote_id,
        rfq_id=rfq_id,
        rfq_reference=rfq_reference,
        supplier_counterparty_id=supplier_id,
        supplier_name=supplier_name,
        quote_currency=quote_currency,
        quote_revision=quote_revision,
        target_currency=scenario.target_currency,
        sales_incoterm=scenario.sales_incoterm,
        sales_named_place=scenario.sales_named_place,
        status=scenario.status,
        calculation_version=scenario.calculation_version,
        pricing_inputs=dict(scenario.pricing_inputs),
        calculated_results=dict(scenario.calculated_results),
        completeness=dict(scenario.completeness),
        version=scenario.version,
        created_by=scenario.created_by,
        created_at=scenario.created_at,
        updated_at=scenario.updated_at,
        components=(
            _component_records(session, company_id=company_id, scenario_id=scenario.id)
            if include_children
            else ()
        ),
    )


def _totals(scenario: PricingScenario) -> dict[str, Decimal]:
    raw = scenario.calculated_results.get("totals")
    totals = raw if isinstance(raw, dict) else {}
    return {
        key: money(Decimal(str(totals.get(key, "0"))))
        for key in ("landed_total", "sales_total", "gross_margin", "gross_margin_pct")
    }


class PricingScenarioService:
    """Create, read and recalculate deterministically priced scenarios."""

    def __init__(self, database: Database) -> None:
        self._database = database
        self._quotes = SupplierQuoteService(database)

    # ------------------------------------------------------------------ reads
    def list(
        self,
        *,
        company_id: UUID,
        filters: ScenarioFilters,
        limit: int,
        cursor: str | None,
    ) -> ScenarioPage:
        fingerprint = filters.as_fingerprint()
        position = decode_cursor(cursor, filters=fingerprint) if cursor else None

        with self._database.transaction() as session:
            apply_company_context(session, company_id)
            statement = (
                select(
                    PricingScenario,
                    SupplierQuote.rfq_id,
                    SupplierRfq.reference_number,
                    SupplierRfq.deal_id,
                    Deal.reference,
                    Counterparty.name,
                )
                .join(
                    SupplierQuote,
                    and_(
                        SupplierQuote.id == PricingScenario.supplier_quote_id,
                        SupplierQuote.company_id == PricingScenario.company_id,
                    ),
                )
                .join(
                    SupplierRfq,
                    and_(
                        SupplierRfq.id == SupplierQuote.rfq_id,
                        SupplierRfq.company_id == SupplierQuote.company_id,
                    ),
                )
                .join(
                    Deal,
                    and_(
                        Deal.id == SupplierRfq.deal_id,
                        Deal.company_id == SupplierRfq.company_id,
                    ),
                )
                .join(
                    Counterparty,
                    and_(
                        Counterparty.id == SupplierQuote.supplier_counterparty_id,
                        Counterparty.company_id == SupplierQuote.company_id,
                    ),
                )
                .where(PricingScenario.company_id == company_id)
            )
            if filters.status:
                statement = statement.where(PricingScenario.status == filters.status)
            if filters.deal_id:
                statement = statement.where(SupplierRfq.deal_id == filters.deal_id)
            if filters.supplier_quote_id:
                statement = statement.where(
                    PricingScenario.supplier_quote_id == filters.supplier_quote_id
                )
            if position is not None:
                statement = statement.where(
                    tuple_(PricingScenario.created_at, PricingScenario.id)
                    < tuple_(position.created_at, position.row_id)
                )
            statement = statement.order_by(
                PricingScenario.created_at.desc(), PricingScenario.id.desc()
            ).limit(limit + 1)

            rows = session.execute(statement).all()
            has_more = len(rows) > limit
            page = rows[:limit]
            next_cursor = None
            if has_more and page:
                last = page[-1][0]
                next_cursor = encode_cursor(
                    created_at=last.created_at, row_id=last.id, filters=fingerprint
                )
            items = tuple(
                ScenarioSummaryRecord(
                    id=scenario.id,
                    company_id=scenario.company_id,
                    deal_id=deal_id,
                    deal_reference=deal_reference,
                    supplier_quote_id=scenario.supplier_quote_id,
                    rfq_reference=rfq_reference,
                    supplier_name=supplier_name,
                    target_currency=scenario.target_currency,
                    status=scenario.status,
                    landed_total=_totals(scenario)["landed_total"],
                    sales_total=_totals(scenario)["sales_total"],
                    gross_margin=_totals(scenario)["gross_margin"],
                    gross_margin_pct=_totals(scenario)["gross_margin_pct"],
                    version=scenario.version,
                    created_at=scenario.created_at,
                    updated_at=scenario.updated_at,
                )
                for (
                    scenario,
                    _rfq_id,
                    rfq_reference,
                    deal_id,
                    deal_reference,
                    supplier_name,
                ) in page
            )
            return ScenarioPage(items=items, next_cursor=next_cursor)

    def get(self, *, company_id: UUID, scenario_id: UUID) -> ScenarioRecord:
        with self._database.transaction() as session:
            apply_company_context(session, company_id)
            return _load(session, company_id=company_id, scenario_id=scenario_id)

    # ----------------------------------------------------------------- writes
    def create(
        self, session: Session, *, meta: WriteMeta, data: ScenarioCreateData
    ) -> ScenarioRecord:
        quote = self._quotes.require_active_quote(
            session, company_id=meta.company_id, quote_id=data.supplier_quote_id
        )
        inputs, outcome, component_rows = _prepare(
            session, company_id=meta.company_id, quote=quote, data=data
        )
        now = datetime.now(tz=UTC)

        scenario = PricingScenario(
            company_id=meta.company_id,
            deal_id=quote.deal_id,
            supplier_quote_id=quote.id,
            target_currency=outcome.target_currency,
            sales_incoterm=(
                str(data.sales_incoterm).strip().upper() if data.sales_incoterm else None
            ),
            sales_named_place=(
                " ".join(data.sales_named_place.split()) if data.sales_named_place else None
            ),
            pricing_inputs=inputs,
            calculated_results=outcome.as_results(),
            calculation_version=CALCULATION_VERSION,
            status=outcome.status.value,
            completeness=outcome.completeness,
            created_by=meta.actor_id,
            created_at=now,
            updated_at=now,
            version=1,
        )
        session.add(scenario)
        session.flush()
        self._write_components(
            session, meta=meta, scenario_id=scenario.id, rows=component_rows, now=now
        )

        record_audit(
            session,
            action=AuditAction.PRICING_SCENARIO_CREATED,
            outcome=AuditOutcome.SUCCESS,
            actor_id=meta.actor_id,
            company_id=meta.company_id,
            request_id=meta.request_id,
            ip_address=meta.ip_address,
            user_agent=meta.user_agent,
            resource_type="pricing_scenario",
            resource_id=str(scenario.id),
            details={
                "supplier_quote_id": str(quote.id),
                "deal_id": str(quote.deal_id),
                "target_currency": scenario.target_currency,
                "status": scenario.status,
                "landed_total": str(outcome.landed_total),
                "sales_total": str(outcome.sales_total),
                "calculation_version": CALCULATION_VERSION,
            },
        )
        return _load(session, company_id=meta.company_id, scenario_id=scenario.id)

    def recalculate(
        self,
        session: Session,
        *,
        meta: WriteMeta,
        scenario_id: UUID,
        expected_version: int,
        data: ScenarioCreateData,
    ) -> ScenarioRecord:
        scenario = session.execute(
            select(PricingScenario)
            .where(
                PricingScenario.id == scenario_id,
                PricingScenario.company_id == meta.company_id,
            )
            .with_for_update()
        ).scalar_one_or_none()
        if scenario is None:
            raise NotFoundError("The pricing scenario does not exist.")
        if scenario.version != expected_version:
            raise VersionConflictError(
                "The pricing scenario was modified by another request.",
                details={"current_version": scenario.version},
                headers={"ETag": f'"v{scenario.version}"'},
            )
        if data.supplier_quote_id != scenario.supplier_quote_id:
            raise BadRequestError(
                "A scenario cannot be repointed; create a new scenario instead.",
                details=[
                    {
                        "field": "supplier_quote_id",
                        "message": "The scenario is bound to the quote it prices.",
                        "type": "value_error",
                    }
                ],
            )
        quote = self._quotes.require_active_quote(
            session, company_id=meta.company_id, quote_id=scenario.supplier_quote_id
        )
        inputs, outcome, component_rows = _prepare(
            session, company_id=meta.company_id, quote=quote, data=data
        )
        now = datetime.now(tz=UTC)

        session.execute(
            delete(PricingCostComponent).where(
                PricingCostComponent.scenario_id == scenario.id,
                PricingCostComponent.company_id == meta.company_id,
            )
        )
        scenario.target_currency = outcome.target_currency
        scenario.sales_incoterm = (
            str(data.sales_incoterm).strip().upper() if data.sales_incoterm else None
        )
        scenario.sales_named_place = (
            " ".join(data.sales_named_place.split()) if data.sales_named_place else None
        )
        scenario.pricing_inputs = inputs
        scenario.calculated_results = outcome.as_results()
        scenario.calculation_version = CALCULATION_VERSION
        scenario.status = outcome.status.value
        scenario.completeness = outcome.completeness
        scenario.version += 1
        scenario.updated_at = now
        session.flush()
        self._write_components(
            session, meta=meta, scenario_id=scenario.id, rows=component_rows, now=now
        )

        record_audit(
            session,
            action=AuditAction.PRICING_SCENARIO_UPDATED,
            outcome=AuditOutcome.SUCCESS,
            actor_id=meta.actor_id,
            company_id=meta.company_id,
            request_id=meta.request_id,
            ip_address=meta.ip_address,
            user_agent=meta.user_agent,
            resource_type="pricing_scenario",
            resource_id=str(scenario.id),
            details={
                "version": scenario.version,
                "status": scenario.status,
                "landed_total": str(outcome.landed_total),
                "sales_total": str(outcome.sales_total),
            },
        )
        return _load(session, company_id=meta.company_id, scenario_id=scenario.id)

    def _write_components(
        self,
        session: Session,
        *,
        meta: WriteMeta,
        scenario_id: UUID,
        rows: Sequence[dict[str, Any]],
        now: datetime,
    ) -> None:
        for row in rows:
            session.add(
                PricingCostComponent(
                    company_id=meta.company_id,
                    scenario_id=scenario_id,
                    created_at=now,
                    **row,
                )
            )
        session.flush()


__all__ = [
    "CostComponentInput",
    "PricingScenarioService",
    "ScenarioComponentRecord",
    "ScenarioCreateData",
    "ScenarioFilters",
    "ScenarioPage",
    "ScenarioRecord",
    "ScenarioSummaryRecord",
]

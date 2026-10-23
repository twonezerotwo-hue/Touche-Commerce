"""The read-only business tools.

Each tool mirrors a REST read that already exists and requires the same permission
(``company.view``); it calls the same service with the server-chosen company, so row
level security and the service's own company filter both apply. Handlers never
format a business number themselves: every amount is the exact string a deterministic
service produced. Free text from the database goes through the sanitiser and personal
contact data (e-mail, phone, contact name) is not exposed to the model at all.
"""

from __future__ import annotations

from datetime import UTC, date, datetime
from decimal import Decimal
from typing import Any

from app.ai.evidence import EvidenceBasis, EvidenceItem
from app.ai.tools.registry import (
    ToolClass,
    ToolContext,
    ToolDefinition,
    ToolRegistry,
    ToolResult,
    uuid_of,
)
from app.api.v1.presenters_intelligence import detail_response, exception_response
from app.api.v1.presenters_reconciliation import order_finance_response
from app.core.errors import NotFoundError
from app.db.models import DealStatus
from app.security.permissions import Permission
from app.services.catalog import ProductFilters, ProductService
from app.services.crm import CounterpartyFilters, CounterpartyService
from app.services.deal_state import TERMINAL_STATUSES
from app.services.documents import DocumentService
from app.services.intelligence import IntelligenceService
from app.services.pricing import PricingScenarioService, ScenarioFilters
from app.services.procurement import ProcurementService, PurchaseOrderFilters
from app.services.reconciliation import ReconciliationService
from app.services.sales_orders import OrderFilters, SalesOrderService
from app.services.shipments import ShipmentFilters, ShipmentService
from app.services.supplier_quotes import QuoteFilters, SupplierQuoteService
from app.services.trade import DealFilters, DealService

_UUID_PROP = {"type": "string", "format": "uuid", "maxLength": 36}
_LIMIT_PROP = {"type": "integer", "minimum": 1, "maximum": 50}
_QUERY_PROP = {"type": "string", "maxLength": 80}
_REFERENCE_PROP = {"type": "string", "maxLength": 40, "pattern": r"^[A-Za-z0-9][A-Za-z0-9._\-/]*$"}


def _schema(properties: dict[str, Any], required: tuple[str, ...] = ()) -> dict[str, Any]:
    return {
        "type": "object",
        "properties": properties,
        "required": list(required),
        "additionalProperties": False,
    }


def _text(value: Any) -> str | None:
    if value is None:
        return None
    if isinstance(value, bool):
        return "true" if value else "false"
    if isinstance(value, datetime):
        return value.astimezone(UTC).isoformat(timespec="seconds")
    if isinstance(value, (date, Decimal, int, str)) or hasattr(value, "value"):
        return str(getattr(value, "value", value))
    return str(value)


def _facts(**values: Any) -> tuple[tuple[str, str], ...]:
    pairs = [(key, text) for key, raw in values.items() if (text := _text(raw)) is not None]
    return tuple(sorted(pairs))


def _limit(ctx: ToolContext, args: dict[str, Any]) -> int:
    return min(int(args.get("limit", ctx.max_items)), ctx.max_items)


def _item(
    entity_type: str,
    entity_id: Any,
    reference: str,
    label: str,
    *,
    basis: EvidenceBasis = EvidenceBasis.CONFIRMED_SOURCE,
    as_of: Any = None,
    completeness: str = "COMPLETE",
    facts: tuple[tuple[str, str], ...] = (),
    warnings: tuple[str, ...] = (),
) -> EvidenceItem:
    return EvidenceItem(
        entity_type=entity_type,
        entity_id=str(entity_id),
        reference=reference[:80],
        label=label[:240],
        basis=basis,
        as_of=_text(as_of),
        completeness=completeness,
        facts=facts,
        warnings=warnings,
    )


# ---------------------------------------------------------------- overview
def get_company_trade_overview(ctx: ToolContext, args: dict[str, Any]) -> ToolResult:
    summary = DealService(ctx.database).dashboard(company_id=ctx.company_id)
    san = ctx.sanitiser
    evidence = [
        _item(
            "COMPANY",
            ctx.company_id,
            "Company overview",
            "Counts of deals, counterparties and products in the active company",
            as_of=datetime.now(UTC),
            facts=_facts(
                deals_total=summary.deals_total,
                counterparties_total=summary.counterparties_total,
                counterparties_active=summary.counterparties_active,
                products_total=summary.products_total,
                products_active=summary.products_active,
            ),
        )
    ]
    for aggregate in summary.pipeline:
        evidence.append(
            _item(
                "PIPELINE",
                aggregate.currency,
                f"Pipeline {aggregate.currency}",
                f"Deals recorded in {aggregate.currency} (never summed across currencies)",
                facts=_facts(
                    currency=aggregate.currency,
                    deal_count=aggregate.deal_count,
                    pipeline_value=aggregate.total_value,
                ),
            )
        )
    data = {
        "deals_total": summary.deals_total,
        "status_counts": [
            {"status": s.status, "deal_count": s.deal_count, "total_value": str(s.total_value)}
            for s in summary.status_counts
        ],
        "pipeline_by_currency": [
            {"currency": p.currency, "deal_count": p.deal_count, "total_value": str(p.total_value)}
            for p in summary.pipeline
        ],
        "counterparties": {
            "total": summary.counterparties_total,
            "active": summary.counterparties_active,
        },
        "products": {"total": summary.products_total, "active": summary.products_active},
        "recent_deals": [
            {
                "reference": d.reference,
                "title": san.text(d.title, limit=120),
                "status": str(d.status),
                "currency": d.currency,
                "total_value": str(d.total_value),
            }
            for d in summary.recent_deals[: ctx.max_items]
        ],
    }
    return ToolResult(data=data, evidence=evidence)


# ---------------------------------------------------------- counterparties
def search_counterparties(ctx: ToolContext, args: dict[str, Any]) -> ToolResult:
    page = CounterpartyService(ctx.database).list(
        company_id=ctx.company_id,
        filters=CounterpartyFilters(
            search=args.get("query"), status=args.get("status"), kind=args.get("type")
        ),
        limit=_limit(ctx, args),
        cursor=None,
    )
    san = ctx.sanitiser
    rows, evidence = [], []
    for c in page.items:
        name = san.text(c.name, limit=120) or ""
        rows.append(
            {
                "id": str(c.id),
                "name": name,
                "type": c.type,
                "country": c.country,
                "status": c.status,
            }
        )
        evidence.append(
            _item(
                "COUNTERPARTY",
                c.id,
                name,
                f"{c.type} counterparty ({c.status})",
                as_of=c.updated_at,
                facts=_facts(type=c.type, status=c.status, country=c.country),
            )
        )
    notices = ["MORE_RESULTS_AVAILABLE"] if page.next_cursor else []
    return ToolResult(data={"counterparties": rows}, evidence=evidence, notices=notices)


def search_products(ctx: ToolContext, args: dict[str, Any]) -> ToolResult:
    page = ProductService(ctx.database).list(
        company_id=ctx.company_id,
        filters=ProductFilters(search=args.get("query"), status=args.get("status")),
        limit=_limit(ctx, args),
        cursor=None,
    )
    san = ctx.sanitiser
    rows, evidence = [], []
    for p in page.items:
        name = san.text(p.name, limit=120) or ""
        rows.append(
            {
                "id": str(p.id),
                "sku": p.sku,
                "name": name,
                "unit": p.unit,
                "currency": p.currency,
                "unit_price": str(p.unit_price),
                "status": p.status,
            }
        )
        evidence.append(
            _item(
                "PRODUCT",
                p.id,
                p.sku,
                f"{name} ({p.unit})",
                as_of=p.updated_at,
                facts=_facts(
                    sku=p.sku,
                    unit=p.unit,
                    currency=p.currency,
                    unit_price=p.unit_price,
                    status=p.status,
                ),
            )
        )
    notices = ["MORE_RESULTS_AVAILABLE"] if page.next_cursor else []
    return ToolResult(data={"products": rows}, evidence=evidence, notices=notices)


# -------------------------------------------------------------------- deals
def _deal_evidence(ctx: ToolContext, deal: Any) -> EvidenceItem:
    san = ctx.sanitiser
    counterparty = san.text(deal.counterparty_name, limit=120) or ""
    warnings = () if deal.items else ("DEAL_HAS_NO_LINES",)
    return _item(
        "DEAL",
        deal.id,
        deal.reference,
        f"{deal.status} deal with {counterparty}",
        as_of=deal.updated_at,
        completeness="COMPLETE" if deal.items else "INCOMPLETE",
        basis=EvidenceBasis.CONFIRMED_SOURCE if deal.items else EvidenceBasis.INCOMPLETE,
        facts=_facts(
            status=deal.status,
            currency=deal.currency,
            total_value=deal.total_value,
            line_count=len(deal.items),
            expected_close_date=deal.expected_close_date,
            counterparty=counterparty,
        ),
        warnings=warnings,
    )


def list_active_deals(ctx: ToolContext, args: dict[str, Any]) -> ToolResult:
    service = DealService(ctx.database)
    wanted = args.get("status")
    limit = _limit(ctx, args)
    collected: list[Any] = []
    cursor: str | None = None
    for _ in range(5):
        page = service.list(
            company_id=ctx.company_id,
            filters=DealFilters(
                search=args.get("query"),
                status=wanted,
                counterparty_id=uuid_of(args, "counterparty_id"),
            ),
            limit=50,
            cursor=cursor,
        )
        for deal in page.items:
            if wanted or deal.status not in TERMINAL_STATUSES:
                collected.append(deal)
        cursor = page.next_cursor
        if not cursor or len(collected) >= limit:
            break
    shown = collected[:limit]
    san = ctx.sanitiser
    rows = [
        {
            "id": str(d.id),
            "reference": d.reference,
            "title": san.text(d.title, limit=120),
            "counterparty": san.text(d.counterparty_name, limit=120),
            "status": str(d.status),
            "currency": d.currency,
            "total_value": str(d.total_value),
            "line_count": len(d.items),
            "expected_close_date": _text(d.expected_close_date),
        }
        for d in shown
    ]
    notices = ["MORE_RESULTS_AVAILABLE"] if len(collected) > limit or cursor else []
    return ToolResult(
        data={"deals": rows},
        evidence=[_deal_evidence(ctx, d) for d in shown],
        notices=notices,
    )


def _find_deal(ctx: ToolContext, args: dict[str, Any]) -> Any:
    service = DealService(ctx.database)
    deal_id = uuid_of(args, "deal_id")
    if deal_id is not None:
        return service.get(company_id=ctx.company_id, deal_id=deal_id)
    reference = str(args.get("reference") or "").upper()
    if not reference:
        raise NotFoundError("The deal does not exist.")
    page = service.list(
        company_id=ctx.company_id,
        filters=DealFilters(search=reference),
        limit=20,
        cursor=None,
    )
    match = next((d for d in page.items if d.reference.upper() == reference), None)
    if match is None:
        raise NotFoundError("The deal does not exist.")
    return service.get(company_id=ctx.company_id, deal_id=match.id)


def get_deal_details(ctx: ToolContext, args: dict[str, Any]) -> ToolResult:
    deal = _find_deal(ctx, args)
    san = ctx.sanitiser
    data = {
        "deal": {
            "id": str(deal.id),
            "reference": deal.reference,
            "title": san.text(deal.title, limit=120),
            "counterparty": san.text(deal.counterparty_name, limit=120),
            "status": str(deal.status),
            "currency": deal.currency,
            "total_value": str(deal.total_value),
            "expected_close_date": _text(deal.expected_close_date),
            "notes": san.text(deal.notes, limit=300),
            "allowed_next_statuses": [str(s) for s in deal.allowed_transitions],
        },
        "lines": [
            {
                "sku": i.sku,
                "name": san.text(i.name, limit=100),
                "unit": i.unit,
                "quantity": str(i.quantity),
                "unit_price": str(i.unit_price),
                "line_total": str(i.line_total),
            }
            for i in deal.items[: ctx.max_items]
        ],
        "recent_transitions": [
            {
                "from": t.from_status,
                "to": t.to_status,
                "reason": san.text(t.reason, limit=200),
                "at": _text(t.occurred_at),
            }
            for t in deal.transitions[-5:]
        ],
    }
    return ToolResult(data=data, evidence=[_deal_evidence(ctx, deal)])


# -------------------------------------------------------------- quotes
def _quote_rows(ctx: ToolContext, args: dict[str, Any], *, active_only: bool) -> list[Any]:
    page = SupplierQuoteService(ctx.database).list(
        company_id=ctx.company_id,
        filters=QuoteFilters(
            status=args.get("status"),
            deal_id=uuid_of(args, "deal_id"),
            rfq_id=uuid_of(args, "rfq_id"),
            supplier_counterparty_id=uuid_of(args, "supplier_id"),
        ),
        limit=_limit(ctx, args),
        cursor=None,
    )
    rows = list(page.items)
    if active_only:
        rows = [q for q in rows if q.status == "RECEIVED" and q.superseded_by_quote_id is None]
    return rows


def _quote_evidence(ctx: ToolContext, quote: Any, today: date) -> EvidenceItem:
    warnings: list[str] = []
    if quote.valid_until < today:
        warnings.append("QUOTE_EXPIRED")
    if quote.superseded_by_quote_id is not None:
        warnings.append("QUOTE_SUPERSEDED")
    if quote.status != "RECEIVED":
        warnings.append(f"QUOTE_{quote.status}")
    supplier = ctx.sanitiser.text(quote.supplier_name, limit=120) or ""
    return _item(
        "SUPPLIER_QUOTE",
        quote.id,
        f"{quote.rfq_reference} / {supplier}",
        f"Supplier quote revision {quote.revision} from {supplier} ({quote.incoterm})",
        as_of=quote.received_at,
        facts=_facts(
            supplier=supplier,
            currency=quote.currency,
            incoterm=quote.incoterm,
            quoted_total=quote.total_value,
            valid_until=quote.valid_until,
            status=quote.status,
            revision=quote.revision,
            deal_reference=quote.deal_reference,
        ),
        warnings=tuple(warnings),
    )


def get_supplier_quotes(ctx: ToolContext, args: dict[str, Any]) -> ToolResult:
    today = datetime.now(UTC).date()
    quotes = _quote_rows(ctx, args, active_only=False)
    san = ctx.sanitiser
    rows = [
        {
            "id": str(q.id),
            "rfq_reference": q.rfq_reference,
            "deal_reference": q.deal_reference,
            "supplier": san.text(q.supplier_name, limit=120),
            "currency": q.currency,
            "incoterm": q.incoterm,
            "quoted_total": str(q.total_value),
            "item_count": q.item_count,
            "valid_until": _text(q.valid_until),
            "status": q.status,
            "revision": q.revision,
            "superseded": q.superseded_by_quote_id is not None,
        }
        for q in quotes
    ]
    return ToolResult(
        data={"quotes": rows},
        evidence=[_quote_evidence(ctx, q, today) for q in quotes],
    )


def _latest_scenario(ctx: ToolContext, quote_id: Any) -> Any | None:
    page = PricingScenarioService(ctx.database).list(
        company_id=ctx.company_id,
        filters=ScenarioFilters(supplier_quote_id=quote_id),
        limit=1,
        cursor=None,
    )
    return page.items[0] if page.items else None


def compare_supplier_offers(ctx: ToolContext, args: dict[str, Any]) -> ToolResult:
    """Compare the active quotes of one deal or RFQ with stored, deterministic figures."""
    if not args.get("deal_id") and not args.get("rfq_id"):
        raise NotFoundError("A deal or RFQ is required.")
    today = datetime.now(UTC).date()
    quotes = _quote_rows(ctx, args, active_only=True)
    service = SupplierQuoteService(ctx.database)
    san = ctx.sanitiser
    rows, evidence = [], []
    for summary in quotes:
        full = service.get(company_id=ctx.company_id, quote_id=summary.id)
        scenario = _latest_scenario(ctx, summary.id)
        supplier = san.text(full.supplier_name, limit=120) or ""
        row: dict[str, Any] = {
            "quote_id": str(full.id),
            "supplier": supplier,
            "currency": full.currency,
            "incoterm": full.incoterm,
            "payment_terms": san.text(full.payment_terms, limit=120),
            "lead_time_days": full.lead_time_days,
            "valid_until": _text(full.valid_until),
            "expired": full.valid_until < today,
            "purchase_total": str(full.total_value),
            "landed_cost": None,
        }
        if scenario is not None:
            row["landed_cost"] = {
                "scenario_id": str(scenario.id),
                "target_currency": scenario.target_currency,
                "landed_total": str(scenario.landed_total),
                "gross_margin_pct": str(scenario.gross_margin_pct),
                "status": scenario.status,
            }
            evidence.append(
                _item(
                    "PRICING_SCENARIO",
                    scenario.id,
                    f"Scenario {scenario.rfq_reference} / {supplier}",
                    f"Stored pricing scenario ({scenario.status})",
                    basis=(
                        EvidenceBasis.INCOMPLETE
                        if scenario.status == "INCOMPLETE"
                        else EvidenceBasis.ESTIMATED
                    ),
                    as_of=scenario.updated_at,
                    completeness="PARTIAL" if scenario.status == "INCOMPLETE" else "COMPLETE",
                    facts=_facts(
                        target_currency=scenario.target_currency,
                        landed_total=scenario.landed_total,
                        sales_total=scenario.sales_total,
                        gross_margin=scenario.gross_margin,
                        gross_margin_pct=scenario.gross_margin_pct,
                        status=scenario.status,
                    ),
                    warnings=("PRICING_INPUTS_INCOMPLETE",)
                    if scenario.status == "INCOMPLETE"
                    else (),
                )
            )
        else:
            row["landed_cost_note"] = "NOT_AVAILABLE: no pricing scenario is stored for this quote"
        rows.append(row)
        quote_warnings = []
        if full.valid_until < today:
            quote_warnings.append("QUOTE_EXPIRED")
        if scenario is None:
            quote_warnings.append("NO_PRICING_SCENARIO")
        evidence.append(
            _item(
                "SUPPLIER_QUOTE",
                full.id,
                f"{full.rfq_reference} / {supplier}",
                f"Active quote from {supplier} ({full.incoterm}, {full.lead_time_days} days)",
                as_of=full.received_at,
                completeness="COMPLETE" if scenario is not None else "PARTIAL",
                basis=(
                    EvidenceBasis.CONFIRMED_SOURCE
                    if scenario is not None
                    else EvidenceBasis.INCOMPLETE
                ),
                facts=_facts(
                    supplier=supplier,
                    currency=full.currency,
                    incoterm=full.incoterm,
                    purchase_total=full.total_value,
                    lead_time_days=full.lead_time_days,
                    valid_until=full.valid_until,
                ),
                warnings=tuple(quote_warnings),
            )
        )

    def ranking(key: Any, group: Any) -> list[dict[str, Any]]:
        groups: dict[str, list[dict[str, Any]]] = {}
        for row in rows:
            value = key(row)
            if value is not None:
                groups.setdefault(group(row), []).append(row)
        result = []
        for currency, members in sorted(groups.items()):
            ordered = sorted(members, key=lambda r: Decimal(key(r)))
            result.append(
                {
                    "currency": currency,
                    "comparable_quotes": len(ordered),
                    "lowest_first": [
                        {"rank": index + 1, "supplier": r["supplier"], "total": key(r)}
                        for index, r in enumerate(ordered)
                    ],
                }
            )
        return result

    data = {
        "quotes": rows,
        "ranking_by_purchase_total": ranking(
            lambda r: r["purchase_total"], lambda r: r["currency"]
        ),
        "ranking_by_landed_total": ranking(
            lambda r: r["landed_cost"]["landed_total"] if r["landed_cost"] else None,
            lambda r: r["landed_cost"]["target_currency"],
        ),
        "method": (
            "Quotes are ranked only within one currency; no currency conversion is applied here. "
            "Landed totals come from stored pricing scenarios."
        ),
    }
    return ToolResult(data=data, evidence=evidence)


def get_pricing_scenario(ctx: ToolContext, args: dict[str, Any]) -> ToolResult:
    service = PricingScenarioService(ctx.database)
    scenario_id = uuid_of(args, "scenario_id")
    if scenario_id is None:
        page = service.list(
            company_id=ctx.company_id,
            filters=ScenarioFilters(
                deal_id=uuid_of(args, "deal_id"),
                supplier_quote_id=uuid_of(args, "supplier_quote_id"),
            ),
            limit=1,
            cursor=None,
        )
        if not page.items:
            raise NotFoundError("The pricing scenario does not exist.")
        scenario_id = page.items[0].id
    s = service.get(company_id=ctx.company_id, scenario_id=scenario_id)
    totals = s.calculated_results.get("totals")
    totals = totals if isinstance(totals, dict) else {}
    issues = s.completeness.get("issues")
    issues_list = [str(i) for i in issues] if isinstance(issues, list) else []
    san = ctx.sanitiser
    data = {
        "scenario": {
            "id": str(s.id),
            "deal_reference": s.deal_reference,
            "supplier": san.text(s.supplier_name, limit=120),
            "quote_currency": s.quote_currency,
            "target_currency": s.target_currency,
            "status": s.status,
            "calculation_version": s.calculation_version,
            "totals": {k: str(v) for k, v in totals.items()},
            "issues": issues_list,
            "estimated_components": s.completeness.get("estimated_component_count"),
            "verified_components": s.completeness.get("verified_component_count"),
        },
        "cost_components": [
            {
                "cost_type": c.cost_type,
                "amount": str(c.amount),
                "currency": c.currency,
                "basis": c.basis,
                "verification_status": c.verification_status,
            }
            for c in s.components[: ctx.max_items]
        ],
    }
    incomplete = s.status == "INCOMPLETE"
    evidence = _item(
        "PRICING_SCENARIO",
        s.id,
        f"Scenario {s.deal_reference} / {san.text(s.supplier_name, limit=60)}",
        f"Pricing scenario for {s.deal_reference} ({s.status})",
        basis=EvidenceBasis.INCOMPLETE if incomplete else EvidenceBasis.ESTIMATED,
        as_of=s.updated_at,
        completeness="PARTIAL" if incomplete else "COMPLETE",
        facts=_facts(
            target_currency=s.target_currency,
            status=s.status,
            **{
                k: v
                for k, v in totals.items()
                if k
                in {
                    "landed_total",
                    "sales_total",
                    "gross_margin",
                    "gross_margin_pct",
                    "purchase_total",
                    "additional_cost_total",
                }
            },
        ),
        warnings=tuple(issues_list[:5]) or (("PRICING_INPUTS_INCOMPLETE",) if incomplete else ()),
    )
    return ToolResult(data=data, evidence=[evidence])


# ----------------------------------------------------------------- orders
def list_sales_orders(ctx: ToolContext, args: dict[str, Any]) -> ToolResult:
    page = SalesOrderService(ctx.database).list(
        company_id=ctx.company_id,
        filters=OrderFilters(
            search=args.get("query"),
            status=args.get("status"),
            customer_id=uuid_of(args, "customer_id"),
        ),
        limit=_limit(ctx, args),
        cursor=None,
    )
    san = ctx.sanitiser
    rows, evidence = [], []
    for o in page.items:
        customer = san.text(o.customer_name, limit=120) or ""
        rows.append(
            {
                "id": str(o.id),
                "order_number": o.order_number,
                "customer": customer,
                "status": o.status,
                "currency": o.currency,
                "order_total": str(o.order_total),
                "fulfilment_model": o.fulfilment_model,
                "expected_delivery_date": _text(o.expected_delivery_date),
            }
        )
        evidence.append(
            _item(
                "SALES_ORDER",
                o.id,
                o.order_number,
                f"{o.status} sales order for {customer}",
                as_of=o.updated_at,
                facts=_facts(
                    status=o.status,
                    currency=o.currency,
                    order_total=o.order_total,
                    customer=customer,
                    expected_delivery_date=o.expected_delivery_date,
                    fulfilment_model=o.fulfilment_model,
                ),
            )
        )
    notices = ["MORE_RESULTS_AVAILABLE"] if page.next_cursor else []
    return ToolResult(data={"orders": rows}, evidence=evidence, notices=notices)


def _order_id(ctx: ToolContext, args: dict[str, Any]) -> Any:
    order_id = uuid_of(args, "order_id")
    if order_id is not None:
        return order_id
    reference = str(args.get("reference") or "").strip()
    if not reference:
        raise NotFoundError("The sales order does not exist.")
    page = SalesOrderService(ctx.database).list(
        company_id=ctx.company_id,
        filters=OrderFilters(search=reference),
        limit=20,
        cursor=None,
    )
    match = next((o for o in page.items if o.order_number.upper() == reference.upper()), None)
    if match is None:
        raise NotFoundError("The sales order does not exist.")
    return match.id


def get_order_details(ctx: ToolContext, args: dict[str, Any]) -> ToolResult:
    order = SalesOrderService(ctx.database).get(
        company_id=ctx.company_id, sales_order_id=_order_id(ctx, args)
    )
    san = ctx.sanitiser
    customer = san.text(order.customer_name, limit=120) or ""
    data = {
        "order": {
            "id": str(order.id),
            "order_number": order.order_number,
            "deal_reference": order.deal_reference,
            "quote_number": order.quote_number,
            "customer": customer,
            "status": order.status,
            "currency": order.currency,
            "order_total": str(order.order_total),
            "incoterm": order.incoterm,
            "named_delivery_place": san.text(order.named_delivery_place, limit=120),
            "payment_terms": san.text(order.payment_terms_snapshot, limit=120),
            "fulfilment_model": order.fulfilment_model,
            "expected_delivery_date": _text(order.expected_delivery_date),
            "notes": san.text(order.notes, limit=300),
            "amendment_count": len(order.amendments),
            "allowed_next_statuses": list(order.allowed_transitions),
        },
        "lines": [
            {
                "sku": i.sku,
                "quantity": str(i.quantity),
                "unit": i.unit,
                "unit_price": str(i.unit_price),
                "line_total": str(i.line_total),
            }
            for i in order.items[: ctx.max_items]
        ],
    }
    evidence = _item(
        "SALES_ORDER",
        order.id,
        order.order_number,
        f"{order.status} sales order for {customer}",
        as_of=order.updated_at,
        facts=_facts(
            status=order.status,
            currency=order.currency,
            order_total=order.order_total,
            customer=customer,
            expected_delivery_date=order.expected_delivery_date,
            fulfilment_model=order.fulfilment_model,
            line_count=len(order.items),
        ),
    )
    return ToolResult(data=data, evidence=[evidence])


def get_purchase_commitments(ctx: ToolContext, args: dict[str, Any]) -> ToolResult:
    page = ProcurementService(ctx.database).list(
        company_id=ctx.company_id,
        filters=PurchaseOrderFilters(
            sales_order_id=uuid_of(args, "order_id"), status=args.get("status")
        ),
        limit=_limit(ctx, args),
        cursor=None,
    )
    san = ctx.sanitiser
    rows, evidence = [], []
    for po in page.items:
        supplier = san.text(po.supplier_name, limit=120) or ""
        committed = po.status not in {"DRAFT", "CANCELLED"}
        rows.append(
            {
                "id": str(po.id),
                "po_number": po.po_number,
                "order_number": po.order_number,
                "supplier": supplier,
                "status": po.status,
                "currency": po.currency,
                "total_cost": str(po.total_cost),
                "committed": committed,
                "expected_dispatch_date": _text(po.expected_dispatch_date),
                "expected_delivery_date": _text(po.expected_delivery_date),
            }
        )
        evidence.append(
            _item(
                "PURCHASE_ORDER",
                po.id,
                po.po_number,
                f"{po.status} purchase order to {supplier}",
                as_of=po.updated_at,
                facts=_facts(
                    status=po.status,
                    currency=po.currency,
                    total_cost=po.total_cost,
                    supplier=supplier,
                    committed=committed,
                    expected_delivery_date=po.expected_delivery_date,
                ),
                warnings=() if committed else ("NOT_COMMITTED",),
            )
        )
    return ToolResult(data={"purchase_orders": rows}, evidence=evidence)


def get_shipment_status(ctx: ToolContext, args: dict[str, Any]) -> ToolResult:
    service = ShipmentService(ctx.database)
    shipment_id = uuid_of(args, "shipment_id")
    if shipment_id is not None:
        records = [service.get(company_id=ctx.company_id, shipment_id=shipment_id)]
    else:
        page = service.list(
            company_id=ctx.company_id,
            filters=ShipmentFilters(
                sales_order_id=uuid_of(args, "order_id"), status=args.get("status")
            ),
            limit=_limit(ctx, args),
            cursor=None,
        )
        records = [service.get(company_id=ctx.company_id, shipment_id=s.id) for s in page.items]
    san = ctx.sanitiser
    rows, evidence = [], []
    for s in records:
        delay = san.text(s.delay_reason, limit=200)
        rows.append(
            {
                "id": str(s.id),
                "shipment_number": s.shipment_number,
                "order_number": s.order_number,
                "status": s.status,
                "transport_mode": s.transport_mode,
                "origin": san.text(s.origin, limit=80),
                "destination": san.text(s.destination, limit=80),
                "estimated_arrival_at": _text(s.estimated_arrival_at),
                "actual_dispatch_at": _text(s.actual_dispatch_at),
                "delivered_at": _text(s.delivered_at),
                "is_delayed": s.is_delayed,
                "delay_reason": delay,
                "recent_events": [
                    {
                        "type": e.event_type,
                        "at": _text(e.occurred_at),
                        "location": san.text(e.location, limit=80),
                    }
                    for e in s.events[-3:]
                ],
                "cost_lines": len(s.costs),
            }
        )
        warnings = []
        if s.is_delayed:
            warnings.append("SHIPMENT_DELAYED")
        if s.estimated_arrival_at is None and s.status not in {"DELIVERED", "CANCELLED"}:
            warnings.append("NO_ESTIMATED_ARRIVAL")
        evidence.append(
            _item(
                "SHIPMENT",
                s.id,
                s.shipment_number,
                f"{s.status} {s.transport_mode} shipment for {s.order_number}",
                as_of=s.updated_at,
                completeness="PARTIAL" if "NO_ESTIMATED_ARRIVAL" in warnings else "COMPLETE",
                basis=(
                    EvidenceBasis.INCOMPLETE
                    if "NO_ESTIMATED_ARRIVAL" in warnings
                    else EvidenceBasis.CONFIRMED_SOURCE
                ),
                facts=_facts(
                    status=s.status,
                    transport_mode=s.transport_mode,
                    estimated_arrival_at=s.estimated_arrival_at,
                    delivered_at=s.delivered_at,
                    is_delayed=s.is_delayed,
                    order_number=s.order_number,
                ),
                warnings=tuple(warnings),
            )
        )
    return ToolResult(data={"shipments": rows}, evidence=evidence)


def get_document_metadata(ctx: ToolContext, args: dict[str, Any]) -> ToolResult:
    """Document *metadata* only: never a file body, a storage key or a checksum."""
    documents = DocumentService(ctx.database, ctx.settings).list(
        company_id=ctx.company_id,
        document_type=args.get("document_type"),
        linked_entity_type=args.get("entity_type"),
        linked_entity_id=uuid_of(args, "entity_id"),
        status="ACTIVE",
        search=args.get("query"),
        limit=_limit(ctx, args),
    )
    san = ctx.sanitiser
    rows, evidence = [], []
    for d in documents:
        title = san.text(d.title, limit=120) or ""
        rows.append(
            {
                "id": str(d.id),
                "document_type": d.document_type,
                "title": title,
                "linked_entity_type": d.linked_entity_type,
                "linked_entity_id": str(d.linked_entity_id),
                "mime_type": d.mime_type,
                "size_bytes": d.size_bytes,
                "version": d.version,
                "verification_status": d.verification_status,
                "is_draft": d.is_draft,
                "uploaded_at": _text(d.uploaded_at),
            }
        )
        unverified = d.verification_status != "VERIFIED"
        evidence.append(
            _item(
                "DOCUMENT",
                d.id,
                title,
                f"{d.document_type} ({d.verification_status})",
                as_of=d.uploaded_at,
                completeness="PARTIAL" if unverified or d.is_draft else "COMPLETE",
                basis=(
                    EvidenceBasis.INCOMPLETE
                    if unverified or d.is_draft
                    else EvidenceBasis.CONFIRMED_SOURCE
                ),
                facts=_facts(
                    document_type=d.document_type,
                    verification_status=d.verification_status,
                    is_draft=d.is_draft,
                    version=d.version,
                    linked_entity_type=d.linked_entity_type,
                ),
                warnings=tuple(
                    w
                    for w, on in (
                        ("DOCUMENT_UNVERIFIED", unverified),
                        ("DOCUMENT_IS_DRAFT", d.is_draft),
                    )
                    if on
                ),
            )
        )
    notices = [] if rows else ["NO_DOCUMENTS_FOUND"]
    return ToolResult(data={"documents": rows}, evidence=evidence, notices=notices)


# ----------------------------------------------------------------- finance
_PROFIT_FACTS = (
    "sales_value",
    "estimated_purchase_cost",
    "estimated_landed_cost",
    "committed_purchase_cost",
    "documented_total_cost",
    "estimated_gross_profit",
    "estimated_gross_margin_pct",
    "committed_gross_profit",
    "committed_gross_margin_pct",
    "cost_variance",
    "cost_variance_pct",
)


def get_order_profitability(ctx: ToolContext, args: dict[str, Any]) -> ToolResult:
    """Operational analysis from the deterministic intelligence service; never accounting profit."""
    record = IntelligenceService(ctx.database).order_detail(
        company_id=ctx.company_id, sales_order_id=_order_id(ctx, args)
    )
    detail = detail_response(record).model_dump(mode="json")
    order = detail["order"]
    san = ctx.sanitiser
    present = {k: order[k] for k in _PROFIT_FACTS if order.get(k) is not None}
    missing = [str(m) for m in order.get("missing_components", [])]
    complete = order.get("completeness") == "COMPLETE"
    checks = [
        {
            "label": c["label"],
            "satisfied": c["satisfied"],
            "detail": san.text(c.get("detail"), limit=200),
        }
        for c in detail["checks"][:10]
    ]
    data = {
        "order_number": order["order_number"],
        "customer": san.text(order["customer_name"], limit=120),
        "currency": order["currency"],
        "status": order["status"],
        "completeness": order["completeness"],
        "estimate_status": order["estimate_status"],
        "committed_status": order["committed_status"],
        "figures": present,
        "classifications": order["classifications"],
        "missing_components": missing,
        "checks": checks,
        "limitations": [str(x)[:240] for x in detail["limitations"][:8]],
        "reconciliation_status": order.get("reconciliation_status"),
        "open_discrepancies": order["open_discrepancy_count"],
        "statement": (
            "Operational analysis of recorded commitments and documented costs; "
            "not accounting profit."
        ),
    }
    evidence = _item(
        "ORDER_PROFITABILITY",
        order["sales_order_id"],
        f"Profitability {order['order_number']}",
        f"Operational profitability analysis ({order['completeness']})",
        basis=EvidenceBasis.ESTIMATED if complete else EvidenceBasis.INCOMPLETE,
        as_of=order.get("data_through"),
        completeness=order["completeness"],
        facts=_facts(
            currency=order["currency"],
            reconciliation_status=order.get("reconciliation_status"),
            **present,
        ),
        warnings=tuple(missing[:6]),
    )
    return ToolResult(data=data, evidence=[evidence])


def get_finance_reconciliation(ctx: ToolContext, args: dict[str, Any]) -> ToolResult:
    """The Commerce-side reconciliation view; the live Finance database is never opened."""
    record = ReconciliationService(ctx.database).order_finance_view(
        company_id=ctx.company_id, sales_order_id=_order_id(ctx, args)
    )
    view = order_finance_response(record).model_dump(mode="json")
    san = ctx.sanitiser
    gaps = view["missing_evidence"]
    data = {
        "order": {
            k: san.text(v, limit=120) if isinstance(v, str) else v
            for k, v in view["order"].items()
            if k in {"order_number", "customer_name", "currency", "status", "sales_value"}
        },
        "latest_run_status": view.get("latest_run_status"),
        "latest_run_at": view.get("latest_run_at"),
        "classifications": view["classifications"],
        "limitations": [str(x)[:240] for x in view["limitations"][:8]],
        "missing_evidence": [
            {k: (san.text(v, limit=160) if isinstance(v, str) else v) for k, v in g.items()}
            for g in gaps[:10]
        ],
        "purchase_order_count": len(view["purchase_orders"]),
        "shipment_count": len(view["shipments"]),
        "statement": (
            "Read-only evidence view. No accounting entry or payment is created or implied."
        ),
    }
    status = view.get("latest_run_status")
    evidence = _item(
        "ORDER_FINANCE",
        record.sales_order_id,
        f"Finance reconciliation {record.order_number}",
        f"Finance evidence view (latest run: {status or 'none'})",
        basis=EvidenceBasis.CONFIRMED_SOURCE if status else EvidenceBasis.INCOMPLETE,
        as_of=view.get("latest_run_at"),
        completeness="COMPLETE" if status and not gaps else "PARTIAL",
        facts=_facts(
            latest_run_status=status,
            missing_evidence_count=len(gaps),
            currency=record.currency,
        ),
        warnings=("NO_RECONCILIATION_RUN",) if not status else (),
    )
    return ToolResult(data=data, evidence=[evidence])


def list_financial_discrepancies(ctx: ToolContext, args: dict[str, Any]) -> ToolResult:
    page = IntelligenceService(ctx.database).exceptions(
        company_id=ctx.company_id,
        status=args.get("status", "OPEN"),
        severity=args.get("severity"),
        code=args.get("code"),
        order_id=uuid_of(args, "order_id"),
        limit=_limit(ctx, args),
        offset=0,
    )
    san = ctx.sanitiser
    rows, evidence = [], []
    for record in page.items:
        item = exception_response(record).model_dump(mode="json")
        title = san.text(item["title"], limit=160) or ""
        rows.append(
            {
                "id": item["id"],
                "order_number": item["order_number"],
                "code": item["code"],
                "severity": item["severity"],
                "status": item["status"],
                "title": title,
                "detail": san.text(item["detail"], limit=240),
                "currency": item["currency"],
            }
        )
        evidence.append(
            _item(
                "DISCREPANCY",
                item["id"],
                f"{item['order_number']} / {item['code']}",
                title,
                as_of=item["created_at"],
                facts=_facts(
                    code=item["code"],
                    severity=item["severity"],
                    status=item["status"],
                    order_number=item["order_number"],
                ),
                warnings=(f"SEVERITY_{item['severity']}",)
                if item["severity"] in {"ERROR", "BLOCKING"}
                else (),
            )
        )
    data = {"total_matching": page.total, "discrepancies": rows}
    return ToolResult(data=data, evidence=evidence)


# ---------------------------------------------------------------- registry
def _tool(
    name: str,
    description: str,
    properties: dict[str, Any],
    handler: Any,
    required: tuple[str, ...] = (),
) -> ToolDefinition:
    return ToolDefinition(
        name=name,
        description=description,
        parameters=_schema(properties, required),
        permission=Permission.COMPANY_VIEW,
        handler=handler,
        tool_class=ToolClass.READ_ONLY,
    )


def build_registry() -> ToolRegistry:
    status_prop = {"type": "string", "maxLength": 40}
    return ToolRegistry(
        [
            _tool(
                "get_company_trade_overview",
                "Counts and per-currency pipeline totals for the active company, plus recent "
                "deals.",
                {},
                get_company_trade_overview,
            ),
            _tool(
                "search_counterparties",
                "Search customers and suppliers by name. Contact details are not returned.",
                {
                    "query": _QUERY_PROP,
                    "type": {"type": "string", "enum": ["buyer", "supplier", "both"]},
                    "status": {"type": "string", "enum": ["active", "archived"]},
                    "limit": _LIMIT_PROP,
                },
                search_counterparties,
            ),
            _tool(
                "search_products",
                "Search the product catalogue by SKU or name.",
                {
                    "query": _QUERY_PROP,
                    "status": {"type": "string", "enum": ["active", "archived"]},
                    "limit": _LIMIT_PROP,
                },
                search_products,
            ),
            _tool(
                "list_active_deals",
                "List open deals (not won, lost or cancelled) with value per currency.",
                {
                    "query": _QUERY_PROP,
                    "status": {"type": "string", "enum": [s.value for s in DealStatus]},
                    "counterparty_id": _UUID_PROP,
                    "limit": _LIMIT_PROP,
                },
                list_active_deals,
            ),
            _tool(
                "get_deal_details",
                "One deal with its lines and recent status history. Give deal_id or reference.",
                {"deal_id": _UUID_PROP, "reference": _REFERENCE_PROP},
                get_deal_details,
            ),
            _tool(
                "get_supplier_quotes",
                "Supplier quotes filtered by deal, RFQ or supplier, including expiry warnings.",
                {
                    "deal_id": _UUID_PROP,
                    "rfq_id": _UUID_PROP,
                    "supplier_id": _UUID_PROP,
                    "status": {"type": "string", "enum": ["RECEIVED", "WITHDRAWN"]},
                    "limit": _LIMIT_PROP,
                },
                get_supplier_quotes,
            ),
            _tool(
                "compare_supplier_offers",
                "Compare the active supplier quotes of a deal or RFQ using stored, deterministic "
                "figures. Ranks only within one currency.",
                {"deal_id": _UUID_PROP, "rfq_id": _UUID_PROP, "limit": _LIMIT_PROP},
                compare_supplier_offers,
            ),
            _tool(
                "get_pricing_scenario",
                "A stored landed-cost and margin scenario. Give scenario_id, deal_id or "
                "supplier_quote_id (the newest matching scenario is used).",
                {
                    "scenario_id": _UUID_PROP,
                    "deal_id": _UUID_PROP,
                    "supplier_quote_id": _UUID_PROP,
                },
                get_pricing_scenario,
            ),
            _tool(
                "list_sales_orders",
                "List confirmed sales orders, newest first.",
                {
                    "query": _QUERY_PROP,
                    "status": {
                        "type": "string",
                        "enum": ["CONFIRMED", "IN_FULFILLMENT", "FULFILLED", "CLOSED", "CANCELLED"],
                    },
                    "customer_id": _UUID_PROP,
                    "limit": _LIMIT_PROP,
                },
                list_sales_orders,
            ),
            _tool(
                "get_order_details",
                "One sales order with its lines. Give order_id or the order number as reference.",
                {"order_id": _UUID_PROP, "reference": _REFERENCE_PROP},
                get_order_details,
            ),
            _tool(
                "get_purchase_commitments",
                "Purchase orders (supplier commitments), optionally for one sales order.",
                {
                    "order_id": _UUID_PROP,
                    "status": {"type": "string", "maxLength": 24},
                    "limit": _LIMIT_PROP,
                },
                get_purchase_commitments,
            ),
            _tool(
                "get_shipment_status",
                "Shipments for a sales order (or one shipment) with recorded dates and delay "
                "flags.",
                {
                    "order_id": _UUID_PROP,
                    "shipment_id": _UUID_PROP,
                    "status": status_prop,
                    "limit": _LIMIT_PROP,
                },
                get_shipment_status,
            ),
            _tool(
                "get_document_metadata",
                "Document metadata (type, verification, version) for an entity. Never file "
                "contents.",
                {
                    "entity_type": {
                        "type": "string",
                        "enum": [
                            "DEAL",
                            "SALES_ORDER",
                            "PURCHASE_ORDER",
                            "SHIPMENT",
                            "CUSTOMER_ACCEPTANCE",
                        ],
                    },
                    "entity_id": _UUID_PROP,
                    "document_type": status_prop,
                    "query": _QUERY_PROP,
                    "limit": _LIMIT_PROP,
                },
                get_document_metadata,
            ),
            _tool(
                "get_order_profitability",
                "Operational profitability analysis of one order: estimates, commitments, "
                "documented costs, completeness and limitations. Not accounting profit.",
                {"order_id": _UUID_PROP, "reference": _REFERENCE_PROP},
                get_order_profitability,
            ),
            _tool(
                "get_finance_reconciliation",
                "The read-only Finance evidence view of one order and its latest reconciliation "
                "run.",
                {"order_id": _UUID_PROP, "reference": _REFERENCE_PROP},
                get_finance_reconciliation,
            ),
            _tool(
                "list_financial_discrepancies",
                "Open financial reconciliation exceptions across orders.",
                {
                    "status": {"type": "string", "enum": ["OPEN", "RESOLVED", "DISMISSED"]},
                    "severity": {
                        "type": "string",
                        "enum": ["INFO", "WARNING", "ERROR", "BLOCKING"],
                    },
                    "code": {"type": "string", "maxLength": 40},
                    "order_id": _UUID_PROP,
                    "limit": _LIMIT_PROP,
                },
                list_financial_discrepancies,
            ),
        ]
    )


__all__ = ["build_registry"]

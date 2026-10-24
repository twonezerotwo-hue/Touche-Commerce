"""Stage 13: turn stored trade records into a neutral :class:`DocumentSpec`.

Every builder runs inside a session whose company context is already set (row level
security), loads only the requested record plus its lines and parties, and decides what the
document *is*: a draft or not, and what it is allowed to claim. Rules enforced here:

* a Commerce commercial invoice is **always** a draft and says it is not a tax invoice; the
  platform never posts an accounting invoice (that belongs to the Finance system);
* a quotation, purchase order, RFQ or packing list that is not yet in its final state is a
  draft; a rejected, withdrawn or cancelled record produces no customer document at all;
* the seller's legal name, tax number, address and bank details come only from the company
  profile; whatever is missing is listed on the document instead of being invented;
* stored trade data (names, descriptions, notes) is printed as entered, never translated.
"""

from __future__ import annotations

import re
from collections.abc import Callable, Sequence
from datetime import UTC, date, datetime
from decimal import Decimal
from typing import Literal
from uuid import UUID
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.core.errors import ConflictError, NotFoundError
from app.db.models import (
    Company,
    CompanyProfile,
    CompanySettings,
    Counterparty,
    Product,
    PurchaseOrder,
    PurchaseOrderItem,
    PurchaseOrderStatus,
    RfqStatus,
    SalesOrder,
    SalesOrderItem,
    SalesOrderStatus,
    SalesQuote,
    SalesQuoteItem,
    SalesQuoteStatus,
    Shipment,
    ShipmentItem,
    ShipmentStatus,
    SupplierRfq,
    SupplierRfqItem,
)
from app.render.formatting import format_date
from app.render.labels import label
from app.render.spec import Column, DocumentSpec, Locale, Party

DocumentKind = Literal[
    "rfq",
    "sales_quotation",
    "proforma_invoice",
    "order_confirmation",
    "commercial_invoice",
    "purchase_order",
    "packing_list",
    "shipment_register",
]
#: Kinds that need the id of the record they describe (the register lists them all).
KINDS_WITH_ENTITY: frozenset[str] = frozenset(
    {
        "rfq",
        "sales_quotation",
        "proforma_invoice",
        "order_confirmation",
        "commercial_invoice",
        "purchase_order",
        "packing_list",
    }
)
_MONEY_KINDS = {
    "sales_quotation",
    "proforma_invoice",
    "order_confirmation",
    "commercial_invoice",
    "purchase_order",
}
_BANK_KINDS = {"sales_quotation", "proforma_invoice", "commercial_invoice", "order_confirmation"}
_SAFE_NAME = re.compile(r"[^A-Za-z0-9._-]+")


def _title(locale: Locale, kind: str) -> str:
    return label(locale, f"title.{kind}")


def _safe_filename(kind: str, number: str, locale: Locale) -> str:
    stem = _SAFE_NAME.sub("-", f"{kind}-{number}-{locale}").strip("-")
    return stem or kind


def _today(session: Session, company_id: UUID) -> date:
    zone_name = session.execute(
        select(CompanySettings.timezone).where(CompanySettings.company_id == company_id)
    ).scalar_one_or_none()
    try:
        return datetime.now(ZoneInfo(zone_name or "UTC")).date()
    except ZoneInfoNotFoundError:
        return datetime.now(UTC).date()


def company_locale(session: Session, company_id: UUID) -> Locale:
    value = session.execute(
        select(CompanySettings.locale).where(CompanySettings.company_id == company_id)
    ).scalar_one_or_none()
    return "tr" if value == "tr" else "en"


def _issuer(
    session: Session, company_id: UUID, locale: Locale, *, kind: str
) -> tuple[Party, tuple[str, ...]]:
    company = session.get(Company, company_id)
    if company is None:
        raise NotFoundError("The company does not exist.")
    profile = session.get(CompanyProfile, company_id)
    values = {
        column: getattr(profile, column, None)
        for column in (
            "legal_name",
            "tax_office",
            "tax_number",
            "address",
            "city",
            "postal_code",
            "phone",
            "email",
            "website",
            "bank_name",
            "iban",
            "swift_bic",
        )
    }
    lines: list[str] = []
    if values["address"]:
        lines.append(str(values["address"]))
    place = " ".join(part for part in (values["postal_code"], values["city"]) if part)
    lines.append(", ".join(part for part in (place, company.country) if part))
    if values["tax_number"]:
        office = f"{values['tax_office']} / " if values["tax_office"] else ""
        lines.append(f"VKN/Tax: {office}{values['tax_number']}")
    contact = " | ".join(part for part in (values["phone"], values["email"]) if part)
    if contact:
        lines.append(contact)
    if values["website"]:
        lines.append(str(values["website"]))
    if kind in _BANK_KINDS and values["iban"]:
        bank = " ".join(part for part in (values["bank_name"], values["swift_bic"]) if part)
        lines.append(f"IBAN: {values['iban']}" + (f" ({bank})" if bank else ""))

    warnings: list[str] = []
    if kind in _MONEY_KINDS:
        for field in ("legal_name", "tax_number", "address"):
            if not values[field]:
                warnings.append(label(locale, f"warn.{field}"))
    return Party(
        str(values["legal_name"] or company.name), tuple(line for line in lines if line)
    ), (tuple(warnings))


def _party(counterparty: Counterparty | None) -> Party:
    if counterparty is None:
        return Party("-")
    lines = [
        line
        for line in (
            counterparty.contact_name,
            counterparty.email,
            counterparty.phone,
            counterparty.country,
        )
        if line
    ]
    return Party(counterparty.name, tuple(lines))


def _get[T](session: Session, model: type[T], entity_id: UUID, company_id: UUID, what: str) -> T:
    row = session.execute(
        select(model).where(model.id == entity_id, model.company_id == company_id)  # type: ignore[attr-defined]
    ).scalar_one_or_none()
    if row is None:
        raise NotFoundError(f"The {what} does not exist.")
    return row


def _skus(session: Session, product_ids: Sequence[UUID]) -> dict[UUID, str]:
    if not product_ids:
        return {}
    rows = session.execute(select(Product.id, Product.sku).where(Product.id.in_(product_ids))).all()
    return {row.id: row.sku for row in rows}


def _spec(
    *,
    session: Session,
    company_id: UUID,
    locale: Locale,
    kind: str,
    number: str,
    draft: bool,
    notice: str | None,
    parties: tuple[tuple[str, Party], ...],
    facts: tuple[tuple[str, str], ...],
    columns: tuple[Column, ...],
    rows: tuple[dict[str, object], ...],
    currency: str | None = None,
    totals: tuple[tuple[str, Decimal], ...] = (),
    notes: str | None = None,
) -> DocumentSpec:
    issuer, warnings = _issuer(session, company_id, locale, kind=kind)
    issued = _today(session, company_id)
    return DocumentSpec(
        kind=kind,
        locale=locale,
        title=_title(locale, kind),
        number=number,
        issue_date=issued,
        draft=draft,
        notice=notice,
        issuer=issuer,
        parties=parties,
        facts=facts,
        columns=columns,
        rows=rows,
        currency=currency,
        totals=totals,
        notes=notes,
        warnings=warnings,
        footer=f"{label(locale, 'generated_by')} - {format_date(issued, locale)}",
        filename=_safe_filename(kind, number, locale),
    )


def _priced_columns(locale: Locale, currency: str) -> tuple[Column, ...]:
    return (
        Column("line", label(locale, "col.line")),
        Column("sku", label(locale, "col.sku")),
        Column("description", label(locale, "col.description")),
        Column("quantity", label(locale, "col.quantity"), "qty"),
        Column("unit", label(locale, "col.unit")),
        Column("unit_price", f"{label(locale, 'col.unit_price')} ({currency})", "money"),
        Column("line_total", f"{label(locale, 'col.line_total')} ({currency})", "money"),
    )


def _plain_columns(locale: Locale) -> tuple[Column, ...]:
    return (
        Column("line", label(locale, "col.line")),
        Column("sku", label(locale, "col.sku")),
        Column("description", label(locale, "col.description")),
        Column("quantity", label(locale, "col.quantity"), "qty"),
        Column("unit", label(locale, "col.unit")),
    )


def _terms(locale: Locale, incoterm: str, place: str, payment: str) -> tuple[tuple[str, str], ...]:
    return (
        (label(locale, "fact.incoterm"), incoterm),
        (label(locale, "fact.delivery_place"), place),
        (label(locale, "fact.payment_terms"), payment),
    )


def _sales_quotation(
    session: Session, company_id: UUID, entity_id: UUID, locale: Locale
) -> DocumentSpec:
    quote = _get(session, SalesQuote, entity_id, company_id, "sales quotation")
    if quote.status in (SalesQuoteStatus.REJECTED.value, SalesQuoteStatus.WITHDRAWN.value):
        raise ConflictError("A rejected or withdrawn quotation cannot be issued to a customer.")
    items = (
        session.execute(
            select(SalesQuoteItem)
            .where(SalesQuoteItem.sales_quote_id == quote.id)
            .order_by(SalesQuoteItem.created_at, SalesQuoteItem.id)
        )
        .scalars()
        .all()
    )
    skus = _skus(session, [item.product_id for item in items])
    rows = tuple(
        {
            "line": index,
            "sku": skus.get(item.product_id, ""),
            "description": item.description,
            "quantity": item.quantity,
            "unit": item.unit,
            "unit_price": item.unit_price,
            "line_total": item.line_total,
        }
        for index, item in enumerate(items, start=1)
    )
    total = sum((item.line_total for item in items), Decimal(0))
    approved = quote.status == SalesQuoteStatus.APPROVED.value
    customer = session.get(Counterparty, quote.customer_id)
    return _spec(
        session=session,
        company_id=company_id,
        locale=locale,
        kind="sales_quotation",
        number=quote.quote_number,
        draft=not approved,
        notice=None if approved else label(locale, "notice.draft_unapproved"),
        parties=((label(locale, "buyer"), _party(customer)),),
        facts=(
            (label(locale, "fact.revision"), str(quote.revision)),
            (label(locale, "fact.valid_until"), format_date(quote.valid_until, locale)),
            (label(locale, "fact.currency"), quote.currency),
            *_terms(locale, quote.incoterm, quote.named_delivery_place, quote.payment_terms),
        ),
        columns=_priced_columns(locale, quote.currency),
        rows=rows,
        currency=quote.currency,
        totals=((label(locale, "total.total"), total),),
        notes=quote.notes,
    )


def _order_document(
    session: Session, company_id: UUID, entity_id: UUID, locale: Locale, kind: str
) -> DocumentSpec:
    order = _get(session, SalesOrder, entity_id, company_id, "sales order")
    if order.status == SalesOrderStatus.CANCELLED.value:
        raise ConflictError("A cancelled sales order cannot be turned into a customer document.")
    items = (
        session.execute(
            select(SalesOrderItem)
            .where(SalesOrderItem.sales_order_id == order.id)
            .order_by(SalesOrderItem.created_at, SalesOrderItem.id)
        )
        .scalars()
        .all()
    )
    rows = tuple(
        {
            "line": index,
            "sku": item.sku,
            "description": item.description or item.name,
            "quantity": item.quantity,
            "unit": item.unit,
            "unit_price": item.unit_price,
            "line_total": item.line_total,
        }
        for index, item in enumerate(items, start=1)
    )
    customer = session.get(Counterparty, order.customer_id)
    number = {
        "order_confirmation": order.order_number,
        "proforma_invoice": f"PF-{order.order_number}",
        "commercial_invoice": f"CI-DRAFT-{order.order_number}",
    }[kind]
    invoice = kind == "commercial_invoice"
    notice = {
        "commercial_invoice": label(locale, "notice.not_tax_invoice"),
        "proforma_invoice": label(locale, "notice.proforma"),
        "order_confirmation": None,
    }[kind]
    expected = (
        [
            (
                label(locale, "fact.expected_delivery"),
                format_date(order.expected_delivery_date, locale),
            )
        ]
        if order.expected_delivery_date
        else []
    )
    return _spec(
        session=session,
        company_id=company_id,
        locale=locale,
        kind=kind,
        number=number,
        draft=invoice,
        notice=notice,
        parties=((label(locale, "buyer"), _party(customer)),),
        facts=(
            (label(locale, "fact.order"), order.order_number),
            (label(locale, "fact.currency"), order.currency),
            *_terms(
                locale, order.incoterm, order.named_delivery_place, order.payment_terms_snapshot
            ),
            *expected,
        ),
        columns=_priced_columns(locale, order.currency),
        rows=rows,
        currency=order.currency,
        totals=((label(locale, "total.total"), order.order_total),),
        notes=order.notes,
    )


def _purchase_order(
    session: Session, company_id: UUID, entity_id: UUID, locale: Locale
) -> DocumentSpec:
    po = _get(session, PurchaseOrder, entity_id, company_id, "purchase order")
    if po.status == PurchaseOrderStatus.CANCELLED.value:
        raise ConflictError("A cancelled purchase order cannot be issued to a supplier.")
    items = (
        session.execute(
            select(PurchaseOrderItem)
            .where(PurchaseOrderItem.purchase_order_id == po.id)
            .order_by(PurchaseOrderItem.created_at, PurchaseOrderItem.id)
        )
        .scalars()
        .all()
    )
    skus = _skus(session, [item.product_id for item in items])
    rows = tuple(
        {
            "line": index,
            "sku": skus.get(item.product_id, ""),
            "description": item.description,
            "quantity": item.quantity,
            "unit": item.unit,
            "unit_price": item.unit_cost,
            "line_total": item.line_total,
        }
        for index, item in enumerate(items, start=1)
    )
    supplier = session.get(Counterparty, po.supplier_id)
    delivery = (
        [(label(locale, "fact.expected_delivery"), format_date(po.expected_delivery_date, locale))]
        if po.expected_delivery_date
        else []
    )
    draft = po.status == PurchaseOrderStatus.DRAFT.value
    return _spec(
        session=session,
        company_id=company_id,
        locale=locale,
        kind="purchase_order",
        number=po.po_number,
        draft=draft,
        notice=label(locale, "notice.draft_unapproved") if draft else None,
        parties=((label(locale, "supplier"), _party(supplier)),),
        facts=(
            (label(locale, "fact.currency"), po.currency),
            *_terms(locale, po.incoterm, po.named_delivery_place, po.payment_terms),
            *delivery,
        ),
        columns=_priced_columns(locale, po.currency),
        rows=rows,
        currency=po.currency,
        totals=((label(locale, "total.total"), po.total_cost),),
        notes=po.notes,
    )


def _rfq(session: Session, company_id: UUID, entity_id: UUID, locale: Locale) -> DocumentSpec:
    rfq = _get(session, SupplierRfq, entity_id, company_id, "request for quotation")
    if rfq.status == RfqStatus.CANCELLED.value:
        raise ConflictError("A cancelled RFQ cannot be issued to a supplier.")
    items = (
        session.execute(
            select(SupplierRfqItem)
            .where(SupplierRfqItem.rfq_id == rfq.id)
            .order_by(SupplierRfqItem.created_at, SupplierRfqItem.id)
        )
        .scalars()
        .all()
    )
    skus = _skus(session, [item.product_id for item in items])
    rows = tuple(
        {
            "line": index,
            "sku": skus.get(item.product_id, ""),
            "description": item.description,
            "quantity": item.quantity,
            "unit": item.unit,
        }
        for index, item in enumerate(items, start=1)
    )
    supplier = session.get(Counterparty, rfq.supplier_counterparty_id)
    facts: list[tuple[str, str]] = [
        (label(locale, "fact.revision"), str(rfq.revision)),
        (label(locale, "fact.currency"), rfq.requested_currency),
        (label(locale, "fact.delivery_location"), rfq.delivery_location),
    ]
    if rfq.requested_delivery_terms:
        facts.append((label(locale, "fact.requested_terms"), rfq.requested_delivery_terms))
    if rfq.response_due_date:
        facts.append(
            (label(locale, "fact.response_due"), format_date(rfq.response_due_date, locale))
        )
    draft = rfq.status in (RfqStatus.DRAFT.value, RfqStatus.PREPARED.value)
    return _spec(
        session=session,
        company_id=company_id,
        locale=locale,
        kind="rfq",
        number=rfq.reference_number,
        draft=draft,
        notice=label(locale, "notice.draft_unapproved") if draft else None,
        parties=((label(locale, "supplier"), _party(supplier)),),
        facts=tuple(facts),
        columns=_plain_columns(locale),
        rows=rows,
        notes=rfq.notes,
    )


def _shipment_facts(locale: Locale, shipment: Shipment) -> tuple[tuple[str, str], ...]:
    facts = [
        (label(locale, "fact.mode"), shipment.transport_mode),
        (label(locale, "fact.origin"), shipment.origin),
        (label(locale, "fact.destination"), shipment.destination),
    ]
    if shipment.carrier:
        facts.append((label(locale, "fact.carrier"), shipment.carrier))
    if shipment.tracking_reference:
        facts.append((label(locale, "fact.tracking"), shipment.tracking_reference))
    dispatch = shipment.actual_dispatch_at or shipment.planned_dispatch_at
    if dispatch:
        facts.append((label(locale, "fact.dispatch"), format_date(dispatch, locale)))
    if shipment.estimated_arrival_at:
        facts.append(
            (label(locale, "fact.eta"), format_date(shipment.estimated_arrival_at, locale))
        )
    return tuple(facts)


def _packing_list(
    session: Session, company_id: UUID, entity_id: UUID, locale: Locale
) -> DocumentSpec:
    shipment = _get(session, Shipment, entity_id, company_id, "shipment")
    if shipment.status == ShipmentStatus.CANCELLED.value:
        raise ConflictError("A cancelled shipment has no packing list.")
    lines = session.execute(
        select(ShipmentItem, SalesOrderItem)
        .join(SalesOrderItem, SalesOrderItem.id == ShipmentItem.sales_order_item_id)
        .where(ShipmentItem.shipment_id == shipment.id)
        .order_by(ShipmentItem.created_at, ShipmentItem.id)
    ).all()
    rows = tuple(
        {
            "line": index,
            "sku": order_item.sku,
            "description": order_item.description or order_item.name,
            "quantity": ship_item.quantity,
            "unit": ship_item.unit,
        }
        for index, (ship_item, order_item) in enumerate(lines, start=1)
    )
    order = session.get(SalesOrder, shipment.sales_order_id)
    customer = session.get(Counterparty, order.customer_id) if order is not None else None
    facts = [
        (label(locale, "fact.order"), order.order_number if order is not None else "-"),
        *_shipment_facts(locale, shipment),
    ]
    draft = shipment.status in (ShipmentStatus.PLANNED.value, ShipmentStatus.BOOKED.value)
    return _spec(
        session=session,
        company_id=company_id,
        locale=locale,
        kind="packing_list",
        number=shipment.shipment_number,
        draft=draft,
        notice=label(locale, "notice.draft_unapproved") if draft else None,
        parties=((label(locale, "ship_to"), _party(customer)),),
        facts=tuple(facts),
        columns=_plain_columns(locale),
        rows=rows,
        notes=shipment.notes,
    )


def _shipment_register(session: Session, company_id: UUID, locale: Locale) -> DocumentSpec:
    shipments = session.execute(
        select(Shipment, SalesOrder.order_number)
        .join(SalesOrder, SalesOrder.id == Shipment.sales_order_id)
        .where(Shipment.company_id == company_id)
        .order_by(Shipment.created_at.desc(), Shipment.id)
    ).all()
    rows: tuple[dict[str, object], ...] = tuple(
        {
            "shipment": shipment.shipment_number,
            "order": order_number,
            "mode": shipment.transport_mode,
            "origin": shipment.origin,
            "destination": shipment.destination,
            "status": shipment.status,
            "eta": shipment.estimated_arrival_at,
            "tracking": shipment.tracking_reference or "",
        }
        for shipment, order_number in shipments
    )
    columns = (
        Column("shipment", label(locale, "col.shipment")),
        Column("order", label(locale, "col.order")),
        Column("mode", label(locale, "col.mode")),
        Column("origin", label(locale, "col.origin")),
        Column("destination", label(locale, "col.destination")),
        Column("status", label(locale, "col.status")),
        Column("eta", label(locale, "col.eta"), "date"),
        Column("tracking", label(locale, "col.tracking")),
    )
    issued = _today(session, company_id)
    return _spec(
        session=session,
        company_id=company_id,
        locale=locale,
        kind="shipment_register",
        number=issued.isoformat(),
        draft=False,
        notice=None,
        parties=(),
        facts=(),
        columns=columns,
        rows=rows,
    )


_ENTITY_BUILDERS: dict[str, Callable[[Session, UUID, UUID, Locale], DocumentSpec]] = {
    "sales_quotation": _sales_quotation,
    "purchase_order": _purchase_order,
    "rfq": _rfq,
    "packing_list": _packing_list,
}


def build_document(
    session: Session,
    *,
    company_id: UUID,
    kind: DocumentKind,
    entity_id: UUID | None,
    locale: Locale,
) -> DocumentSpec:
    """Load the record and describe the document. Raises ``NotFoundError`` / ``ConflictError``."""
    if kind == "shipment_register":
        return _shipment_register(session, company_id, locale)
    if entity_id is None:
        raise NotFoundError("This document needs the id of the record it describes.")
    if kind in ("proforma_invoice", "order_confirmation", "commercial_invoice"):
        return _order_document(session, company_id, entity_id, locale, kind)
    return _ENTITY_BUILDERS[kind](session, company_id, entity_id, locale)

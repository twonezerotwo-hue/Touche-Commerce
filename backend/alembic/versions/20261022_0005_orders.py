"""stage 4 execution: sales orders, procurement, shipments and documents

Creates the execution chain of TOUCHE COMMERCE:

* ``customer_acceptance_evidence`` -- append-only proof of customer acceptance
* ``sales_order`` / ``sales_order_item`` -- confirmed order and its frozen lines
* ``sales_order_transition``       -- append-only order history
* ``order_amendment``              -- append-only, reasoned post-acceptance change
* ``purchase_order`` (+ items, transitions) -- supplier orders and their evidence
* ``shipment`` (+ items, events, references, costs) -- partial deliveries
* ``trade_document``               -- private document metadata and versions

Every child row uses a composite ``(id, company_id)`` foreign key, every table is
protected by row level security, and history tables are append-only for the
runtime role.  No existing table is altered apart from the audit-action CHECK, so
a Stage 3 database upgrades in place.

Revision ID: 0005_orders
Revises: 0004_sourcing
Create Date: 2026-10-22
"""

from __future__ import annotations

import os
from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision: str = "0005_orders"
down_revision: str | None = "0004_sourcing"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

SCHEMA = "touche"
_APP_ROLE_ENV = "TOUCHE_DB_APP_USER"
_DEFAULT_APP_ROLE = "touche_app"
_UUID = postgresql.UUID(as_uuid=True)
_TS = sa.DateTime(timezone=True)
_JSONB = postgresql.JSONB(astext_type=sa.Text())

_TABLES = (
    "customer_acceptance_evidence",
    "sales_order",
    "sales_order_item",
    "sales_order_transition",
    "order_amendment",
    "purchase_order",
    "purchase_order_item",
    "purchase_order_transition",
    "shipment",
    "shipment_item",
    "shipment_event",
    "shipment_reference",
    "shipment_cost",
    "trade_document",
)
_APPEND_ONLY_TABLES = (
    "customer_acceptance_evidence",
    "sales_order_transition",
    "order_amendment",
    "purchase_order_transition",
    "shipment_event",
)

_UNITS = "'kg', 'mt', 'lb', 'unit', 'l', 'm3'"
_INCOTERMS = "'EXW', 'FCA', 'FAS', 'FOB', 'CFR', 'CIF', 'CPT', 'CIP', 'DAP', 'DPU', 'DDP'"
_CURRENCY = "~ '^[A-Z]{3}$'"
_FULFILMENT_MODELS = "'PURCHASE_RESALE', 'BROKERAGE'"
_ACCEPTANCE_CHANNELS = "'SIGNED_QUOTE', 'PURCHASE_ORDER', 'EMAIL', 'PORTAL', 'OTHER'"
_SALES_ORDER_STATUSES = "'CONFIRMED', 'IN_FULFILLMENT', 'FULFILLED', 'CLOSED', 'CANCELLED'"
_PURCHASE_ORDER_STATUSES = (
    "'DRAFT', 'APPROVED', 'RECORDED_SENT', 'SUPPLIER_CONFIRMED', 'IN_FULFILLMENT', "
    "'RECEIVED', 'CANCELLED'"
)
_TRANSPORT_MODES = "'SEA', 'AIR', 'ROAD', 'RAIL', 'MULTIMODAL'"
_SHIPMENT_STATUSES = (
    "'PLANNED', 'BOOKED', 'DISPATCHED', 'IN_TRANSIT', 'ARRIVED', 'DELIVERED', 'CANCELLED'"
)
_TRACKING_SOURCES = "'MANUAL', 'DOCUMENT_EVIDENCE', 'VERIFIED_EXTERNAL'"
_EVENT_TYPES = (
    "'PLANNED', 'BOOKED', 'DISPATCHED', 'IN_TRANSIT', 'ARRIVED', 'DELIVERED', "
    "'DELAY_RECORDED', 'CANCELLED'"
)
_COST_STAGES = "'ESTIMATED', 'QUOTED', 'INCURRED', 'DOCUMENTED'"
_DOCUMENT_TYPES = (
    "'COMMERCIAL_INVOICE', 'PROFORMA_INVOICE', 'PACKING_LIST', 'BILL_OF_LADING', "
    "'AIR_WAYBILL', 'CMR_CONSIGNMENT_NOTE', 'CERTIFICATE_OF_ORIGIN', "
    "'INSURANCE_CERTIFICATE', 'QUALITY_INSPECTION_CERTIFICATE', 'CUSTOMS_DECLARATION', "
    "'PURCHASE_ORDER', 'SALES_ORDER', 'DELIVERY_CONFIRMATION', 'OTHER'"
)
_ENTITY_TYPES = "'DEAL', 'SALES_ORDER', 'PURCHASE_ORDER', 'SHIPMENT', 'CUSTOMER_ACCEPTANCE'"
_DOCUMENT_STATUSES = "'ACTIVE', 'ARCHIVED'"
_VERIFICATION_STATUSES = "'UNVERIFIED', 'VERIFIED', 'REJECTED'"


def _quote(value: str) -> str:
    return postgresql.dialect().identifier_preparer.quote(value)


def _app_role() -> str:
    role = os.environ.get(_APP_ROLE_ENV, _DEFAULT_APP_ROLE).strip()
    if not role:
        raise RuntimeError(f"{_APP_ROLE_ENV} must not be empty")
    return _quote(role)


def _pk() -> sa.Column:
    return sa.Column("id", _UUID, primary_key=True, server_default=sa.text("gen_random_uuid()"))


def _company_id() -> sa.Column:
    return sa.Column("company_id", _UUID, nullable=False)


def _created_at() -> sa.Column:
    return sa.Column("created_at", _TS, nullable=False, server_default=sa.text("now()"))


def _updated_at() -> sa.Column:
    return sa.Column("updated_at", _TS, nullable=False, server_default=sa.text("now()"))


def _version() -> sa.Column:
    return sa.Column("version", sa.Integer(), nullable=False, server_default=sa.text("1"))


def _actor_fk(column: str, constraint: str, *, nullable: bool) -> sa.Column:
    return sa.Column(
        column,
        _UUID,
        sa.ForeignKey(f"{SCHEMA}.app_user.id", name=constraint),
        nullable=nullable,
    )


def _tenant_fk(
    name: str, columns: list[str], target: str, *, ondelete: str
) -> sa.ForeignKeyConstraint:
    return sa.ForeignKeyConstraint(
        columns,
        [f"{SCHEMA}.{target}.{part}" for part in ("id", "company_id")],
        name=name,
        ondelete=ondelete,
    )


def _create_acceptance() -> None:
    op.create_table(
        "customer_acceptance_evidence",
        _pk(),
        _company_id(),
        sa.Column("deal_id", _UUID, nullable=False),
        sa.Column("sales_quote_id", _UUID, nullable=False),
        sa.Column("sales_quote_revision", sa.Integer(), nullable=False),
        sa.Column("channel", sa.String(length=24), nullable=False),
        sa.Column("accepted_at", _TS, nullable=False),
        sa.Column("accepted_by_name", sa.Text(), nullable=False),
        sa.Column("evidence_reference", sa.Text(), nullable=False),
        sa.Column("evidence_document_id", _UUID, nullable=True),
        sa.Column("notes", sa.Text(), nullable=True),
        _actor_fk("recorded_by", "fk_customer_acceptance_recorded_by_app_user", nullable=False),
        sa.Column("recorded_at", _TS, nullable=False, server_default=sa.text("now()")),
        _tenant_fk(
            "fk_customer_acceptance_deal_company",
            ["deal_id", "company_id"],
            "deal",
            ondelete="CASCADE",
        ),
        _tenant_fk(
            "fk_customer_acceptance_quote_company",
            ["sales_quote_id", "company_id"],
            "sales_quote",
            ondelete="RESTRICT",
        ),
        sa.UniqueConstraint(
            "id", "company_id", name="uq_customer_acceptance_evidence_id_company_id"
        ),
        sa.CheckConstraint(
            f"channel IN ({_ACCEPTANCE_CHANNELS})", name="ck_customer_acceptance_channel"
        ),
        sa.CheckConstraint("sales_quote_revision >= 1", name="ck_customer_acceptance_revision"),
        sa.CheckConstraint(
            "char_length(btrim(accepted_by_name)) BETWEEN 2 AND 160",
            name="ck_customer_acceptance_name",
        ),
        sa.CheckConstraint(
            "char_length(btrim(evidence_reference)) BETWEEN 3 AND 500",
            name="ck_customer_acceptance_evidence",
        ),
        sa.CheckConstraint(
            "notes IS NULL OR char_length(notes) <= 2000", name="ck_customer_acceptance_notes"
        ),
        schema=SCHEMA,
        comment="Append-only customer acceptance evidence (RLS protected).",
    )
    op.create_index(
        "ix_customer_acceptance_company_quote",
        "customer_acceptance_evidence",
        ["company_id", "sales_quote_id", "sales_quote_revision"],
        schema=SCHEMA,
    )
    op.create_index(
        "ix_customer_acceptance_company_deal",
        "customer_acceptance_evidence",
        ["company_id", "deal_id"],
        schema=SCHEMA,
    )


def _create_sales_order() -> None:
    op.create_table(
        "sales_order",
        _pk(),
        _company_id(),
        sa.Column("order_number", sa.String(length=40), nullable=False),
        sa.Column("deal_id", _UUID, nullable=False),
        sa.Column("sales_quote_id", _UUID, nullable=False),
        sa.Column("sales_quote_revision", sa.Integer(), nullable=False),
        sa.Column("acceptance_evidence_id", _UUID, nullable=False),
        sa.Column("customer_id", _UUID, nullable=False),
        sa.Column("currency", sa.String(length=3), nullable=False),
        sa.Column("incoterm", sa.String(length=3), nullable=False),
        sa.Column("named_delivery_place", sa.Text(), nullable=False),
        sa.Column("payment_terms_snapshot", sa.Text(), nullable=False),
        sa.Column("fulfilment_model", sa.String(length=24), nullable=False),
        sa.Column("order_total", sa.Numeric(precision=18, scale=2), nullable=False),
        sa.Column(
            "status", sa.String(length=16), nullable=False, server_default=sa.text("'CONFIRMED'")
        ),
        sa.Column("accepted_terms", _JSONB, nullable=False),
        sa.Column("expected_delivery_date", sa.Date(), nullable=True),
        sa.Column("notes", sa.Text(), nullable=True),
        sa.Column("confirmed_at", _TS, nullable=False),
        sa.Column("cancelled_at", _TS, nullable=True),
        sa.Column("cancellation_reason", sa.Text(), nullable=True),
        _actor_fk("created_by", "fk_sales_order_created_by_app_user", nullable=False),
        _created_at(),
        _updated_at(),
        _version(),
        _tenant_fk(
            "fk_sales_order_deal_company", ["deal_id", "company_id"], "deal", ondelete="RESTRICT"
        ),
        _tenant_fk(
            "fk_sales_order_quote_company",
            ["sales_quote_id", "company_id"],
            "sales_quote",
            ondelete="RESTRICT",
        ),
        _tenant_fk(
            "fk_sales_order_customer_company",
            ["customer_id", "company_id"],
            "counterparty",
            ondelete="RESTRICT",
        ),
        _tenant_fk(
            "fk_sales_order_acceptance_company",
            ["acceptance_evidence_id", "company_id"],
            "customer_acceptance_evidence",
            ondelete="RESTRICT",
        ),
        sa.UniqueConstraint("id", "company_id", name="uq_sales_order_id_company_id"),
        sa.UniqueConstraint("company_id", "order_number", name="uq_sales_order_company_number"),
        sa.UniqueConstraint("company_id", "deal_id", name="uq_sales_order_company_deal"),
        sa.CheckConstraint(f"currency {_CURRENCY}", name="ck_sales_order_currency_iso"),
        sa.CheckConstraint(f"incoterm IN ({_INCOTERMS})", name="ck_sales_order_incoterm"),
        sa.CheckConstraint(f"status IN ({_SALES_ORDER_STATUSES})", name="ck_sales_order_status"),
        sa.CheckConstraint(
            f"fulfilment_model IN ({_FULFILMENT_MODELS})",
            name="ck_sales_order_fulfilment_model",
        ),
        sa.CheckConstraint(
            "char_length(btrim(order_number)) BETWEEN 3 AND 40", name="ck_sales_order_number"
        ),
        sa.CheckConstraint(
            "char_length(btrim(named_delivery_place)) BETWEEN 2 AND 160",
            name="ck_sales_order_place",
        ),
        sa.CheckConstraint(
            "char_length(btrim(payment_terms_snapshot)) BETWEEN 2 AND 200",
            name="ck_sales_order_payment_terms",
        ),
        sa.CheckConstraint("order_total >= 0", name="ck_sales_order_total"),
        sa.CheckConstraint("sales_quote_revision >= 1", name="ck_sales_order_quote_revision"),
        sa.CheckConstraint("version >= 1", name="ck_sales_order_version"),
        sa.CheckConstraint(
            "jsonb_typeof(accepted_terms) = 'object'", name="ck_sales_order_accepted_terms"
        ),
        sa.CheckConstraint(
            "(status = 'CANCELLED') = (cancelled_at IS NOT NULL)",
            name="ck_sales_order_cancelled_at",
        ),
        sa.CheckConstraint(
            "status <> 'CANCELLED' OR cancellation_reason IS NOT NULL",
            name="ck_sales_order_cancellation_reason",
        ),
        schema=SCHEMA,
        comment="Tenant-scoped sales orders (RLS protected).",
    )
    for index, columns in (
        ("ix_sales_order_company_status", ["company_id", "status"]),
        ("ix_sales_order_company_created_at", ["company_id", "created_at"]),
        ("ix_sales_order_company_customer", ["company_id", "customer_id"]),
    ):
        op.create_index(index, "sales_order", columns, schema=SCHEMA)


def _create_sales_order_item() -> None:
    op.create_table(
        "sales_order_item",
        _pk(),
        _company_id(),
        sa.Column("sales_order_id", _UUID, nullable=False),
        sa.Column("product_id", _UUID, nullable=False),
        sa.Column("sku", sa.String(length=40), nullable=False),
        sa.Column("name", sa.Text(), nullable=False),
        sa.Column("description", sa.Text(), nullable=False),
        sa.Column("quantity", sa.Numeric(precision=18, scale=3), nullable=False),
        sa.Column("unit", sa.String(length=16), nullable=False),
        sa.Column("unit_price", sa.Numeric(precision=18, scale=4), nullable=False),
        sa.Column("line_total", sa.Numeric(precision=18, scale=2), nullable=False),
        _created_at(),
        _tenant_fk(
            "fk_sales_order_item_order_company",
            ["sales_order_id", "company_id"],
            "sales_order",
            ondelete="CASCADE",
        ),
        _tenant_fk(
            "fk_sales_order_item_product_company",
            ["product_id", "company_id"],
            "product",
            ondelete="RESTRICT",
        ),
        sa.UniqueConstraint(
            "sales_order_id", "product_id", name="uq_sales_order_item_order_id_product_id"
        ),
        sa.UniqueConstraint("id", "company_id", name="uq_sales_order_item_id_company_id"),
        sa.CheckConstraint("quantity > 0", name="ck_sales_order_item_quantity"),
        sa.CheckConstraint("unit_price >= 0", name="ck_sales_order_item_unit_price"),
        sa.CheckConstraint("line_total >= 0", name="ck_sales_order_item_line_total"),
        sa.CheckConstraint(f"unit IN ({_UNITS})", name="ck_sales_order_item_unit"),
        schema=SCHEMA,
        comment="Tenant-scoped sales order lines (RLS protected).",
    )
    op.create_index(
        "ix_sales_order_item_company_order",
        "sales_order_item",
        ["company_id", "sales_order_id"],
        schema=SCHEMA,
    )


def _create_sales_order_transition() -> None:
    op.create_table(
        "sales_order_transition",
        _pk(),
        _company_id(),
        sa.Column("sales_order_id", _UUID, nullable=False),
        sa.Column("from_status", sa.String(length=16), nullable=True),
        sa.Column("to_status", sa.String(length=16), nullable=False),
        sa.Column("reason", sa.Text(), nullable=True),
        _actor_fk("actor_id", "fk_sales_order_transition_actor_app_user", nullable=False),
        sa.Column("request_id", sa.String(length=128), nullable=True),
        sa.Column("version_after", sa.Integer(), nullable=False),
        sa.Column("occurred_at", _TS, nullable=False, server_default=sa.text("now()")),
        _tenant_fk(
            "fk_sales_order_transition_order_company",
            ["sales_order_id", "company_id"],
            "sales_order",
            ondelete="CASCADE",
        ),
        sa.CheckConstraint(
            f"to_status IN ({_SALES_ORDER_STATUSES})", name="ck_sales_order_transition_to_status"
        ),
        sa.CheckConstraint(
            f"from_status IS NULL OR from_status IN ({_SALES_ORDER_STATUSES})",
            name="ck_sales_order_transition_from_status",
        ),
        sa.CheckConstraint(
            "reason IS NULL OR char_length(btrim(reason)) BETWEEN 3 AND 500",
            name="ck_sales_order_transition_reason",
        ),
        sa.CheckConstraint(
            "to_status NOT IN ('CANCELLED') OR reason IS NOT NULL",
            name="ck_sales_order_transition_cancel_reason",
        ),
        sa.CheckConstraint("version_after >= 1", name="ck_sales_order_transition_version"),
        schema=SCHEMA,
        comment="Immutable sales order history (RLS protected).",
    )
    op.create_index(
        "ix_sales_order_transition_company_order",
        "sales_order_transition",
        ["company_id", "sales_order_id", "occurred_at"],
        schema=SCHEMA,
    )


def _create_order_amendment() -> None:
    op.create_table(
        "order_amendment",
        _pk(),
        _company_id(),
        sa.Column("sales_order_id", _UUID, nullable=False),
        sa.Column("reason", sa.Text(), nullable=False),
        sa.Column("changes", _JSONB, nullable=False),
        _actor_fk("actor_id", "fk_order_amendment_actor_app_user", nullable=False),
        sa.Column("request_id", sa.String(length=128), nullable=True),
        sa.Column("version_after", sa.Integer(), nullable=False),
        _created_at(),
        _tenant_fk(
            "fk_order_amendment_order_company",
            ["sales_order_id", "company_id"],
            "sales_order",
            ondelete="CASCADE",
        ),
        sa.CheckConstraint(
            "char_length(btrim(reason)) BETWEEN 3 AND 500", name="ck_order_amendment_reason"
        ),
        sa.CheckConstraint("jsonb_typeof(changes) = 'object'", name="ck_order_amendment_changes"),
        sa.CheckConstraint("version_after >= 1", name="ck_order_amendment_version"),
        schema=SCHEMA,
        comment="Immutable order amendments (RLS protected).",
    )
    op.create_index(
        "ix_order_amendment_company_order",
        "order_amendment",
        ["company_id", "sales_order_id", "created_at"],
        schema=SCHEMA,
    )


def _create_purchase_order() -> None:
    op.create_table(
        "purchase_order",
        _pk(),
        _company_id(),
        sa.Column("po_number", sa.String(length=40), nullable=False),
        sa.Column("sales_order_id", _UUID, nullable=False),
        sa.Column("supplier_id", _UUID, nullable=False),
        sa.Column("supplier_quote_id", _UUID, nullable=True),
        sa.Column("currency", sa.String(length=3), nullable=False),
        sa.Column("incoterm", sa.String(length=3), nullable=False),
        sa.Column("named_delivery_place", sa.Text(), nullable=False),
        sa.Column("payment_terms", sa.Text(), nullable=False),
        sa.Column("total_cost", sa.Numeric(precision=18, scale=2), nullable=False),
        sa.Column(
            "status", sa.String(length=24), nullable=False, server_default=sa.text("'DRAFT'")
        ),
        sa.Column("expected_dispatch_date", sa.Date(), nullable=True),
        sa.Column("expected_delivery_date", sa.Date(), nullable=True),
        sa.Column("dispatch_channel", sa.String(length=32), nullable=True),
        sa.Column("dispatched_at", _TS, nullable=True),
        sa.Column("dispatch_reference", sa.Text(), nullable=True),
        sa.Column("supplier_confirmation_reference", sa.Text(), nullable=True),
        sa.Column("supplier_confirmed_at", _TS, nullable=True),
        sa.Column("approved_at", _TS, nullable=True),
        sa.Column("notes", sa.Text(), nullable=True),
        sa.Column("cancelled_at", _TS, nullable=True),
        sa.Column("cancellation_reason", sa.Text(), nullable=True),
        _actor_fk("created_by", "fk_purchase_order_created_by_app_user", nullable=False),
        _actor_fk("approved_by", "fk_purchase_order_approved_by_app_user", nullable=True),
        _created_at(),
        _updated_at(),
        _version(),
        _tenant_fk(
            "fk_purchase_order_sales_order_company",
            ["sales_order_id", "company_id"],
            "sales_order",
            ondelete="RESTRICT",
        ),
        _tenant_fk(
            "fk_purchase_order_supplier_company",
            ["supplier_id", "company_id"],
            "counterparty",
            ondelete="RESTRICT",
        ),
        sa.UniqueConstraint("id", "company_id", name="uq_purchase_order_id_company_id"),
        sa.UniqueConstraint("company_id", "po_number", name="uq_purchase_order_company_number"),
        sa.CheckConstraint(f"currency {_CURRENCY}", name="ck_purchase_order_currency_iso"),
        sa.CheckConstraint(f"incoterm IN ({_INCOTERMS})", name="ck_purchase_order_incoterm"),
        sa.CheckConstraint(
            f"status IN ({_PURCHASE_ORDER_STATUSES})", name="ck_purchase_order_status"
        ),
        sa.CheckConstraint(
            "char_length(btrim(po_number)) BETWEEN 3 AND 40", name="ck_purchase_order_number"
        ),
        sa.CheckConstraint(
            "char_length(btrim(named_delivery_place)) BETWEEN 2 AND 160",
            name="ck_purchase_order_place",
        ),
        sa.CheckConstraint(
            "char_length(btrim(payment_terms)) BETWEEN 2 AND 200",
            name="ck_purchase_order_payment_terms",
        ),
        sa.CheckConstraint("total_cost >= 0", name="ck_purchase_order_total"),
        sa.CheckConstraint("version >= 1", name="ck_purchase_order_version"),
        sa.CheckConstraint(
            "(status = 'RECORDED_SENT') = (dispatched_at IS NOT NULL)",
            name="ck_purchase_order_dispatched_at",
        ),
        sa.CheckConstraint(
            "status <> 'RECORDED_SENT' OR dispatch_channel IS NOT NULL",
            name="ck_purchase_order_dispatch_channel",
        ),
        sa.CheckConstraint(
            "status NOT IN ('SUPPLIER_CONFIRMED', 'IN_FULFILLMENT', 'RECEIVED') "
            "OR supplier_confirmation_reference IS NOT NULL",
            name="ck_purchase_order_supplier_confirmation",
        ),
        sa.CheckConstraint(
            "(status = 'CANCELLED') = (cancelled_at IS NOT NULL)",
            name="ck_purchase_order_cancelled_at",
        ),
        schema=SCHEMA,
        comment="Tenant-scoped purchase orders (RLS protected).",
    )
    for index, columns in (
        ("ix_purchase_order_company_status", ["company_id", "status"]),
        ("ix_purchase_order_company_sales_order", ["company_id", "sales_order_id"]),
        ("ix_purchase_order_company_supplier", ["company_id", "supplier_id"]),
    ):
        op.create_index(index, "purchase_order", columns, schema=SCHEMA)


def _create_purchase_order_item() -> None:
    op.create_table(
        "purchase_order_item",
        _pk(),
        _company_id(),
        sa.Column("purchase_order_id", _UUID, nullable=False),
        sa.Column("product_id", _UUID, nullable=False),
        sa.Column("description", sa.Text(), nullable=False),
        sa.Column("quantity", sa.Numeric(precision=18, scale=3), nullable=False),
        sa.Column("unit", sa.String(length=16), nullable=False),
        sa.Column("unit_cost", sa.Numeric(precision=18, scale=4), nullable=False),
        sa.Column("line_total", sa.Numeric(precision=18, scale=2), nullable=False),
        _created_at(),
        _tenant_fk(
            "fk_purchase_order_item_order_company",
            ["purchase_order_id", "company_id"],
            "purchase_order",
            ondelete="CASCADE",
        ),
        _tenant_fk(
            "fk_purchase_order_item_product_company",
            ["product_id", "company_id"],
            "product",
            ondelete="RESTRICT",
        ),
        sa.UniqueConstraint(
            "purchase_order_id", "product_id", name="uq_purchase_order_item_order_id_product_id"
        ),
        sa.CheckConstraint("quantity > 0", name="ck_purchase_order_item_quantity"),
        sa.CheckConstraint("unit_cost >= 0", name="ck_purchase_order_item_unit_cost"),
        sa.CheckConstraint("line_total >= 0", name="ck_purchase_order_item_line_total"),
        sa.CheckConstraint(f"unit IN ({_UNITS})", name="ck_purchase_order_item_unit"),
        schema=SCHEMA,
        comment="Tenant-scoped purchase order lines (RLS protected).",
    )
    op.create_index(
        "ix_purchase_order_item_company_order",
        "purchase_order_item",
        ["company_id", "purchase_order_id"],
        schema=SCHEMA,
    )


def _create_purchase_order_transition() -> None:
    op.create_table(
        "purchase_order_transition",
        _pk(),
        _company_id(),
        sa.Column("purchase_order_id", _UUID, nullable=False),
        sa.Column("from_status", sa.String(length=24), nullable=True),
        sa.Column("to_status", sa.String(length=24), nullable=False),
        sa.Column("reason", sa.Text(), nullable=True),
        sa.Column("evidence_reference", sa.Text(), nullable=True),
        _actor_fk("actor_id", "fk_purchase_order_transition_actor_app_user", nullable=False),
        sa.Column("request_id", sa.String(length=128), nullable=True),
        sa.Column("version_after", sa.Integer(), nullable=False),
        sa.Column("occurred_at", _TS, nullable=False, server_default=sa.text("now()")),
        _tenant_fk(
            "fk_purchase_order_transition_order_company",
            ["purchase_order_id", "company_id"],
            "purchase_order",
            ondelete="CASCADE",
        ),
        sa.CheckConstraint(
            f"to_status IN ({_PURCHASE_ORDER_STATUSES})",
            name="ck_purchase_order_transition_to_status",
        ),
        sa.CheckConstraint(
            f"from_status IS NULL OR from_status IN ({_PURCHASE_ORDER_STATUSES})",
            name="ck_purchase_order_transition_from_status",
        ),
        sa.CheckConstraint(
            "reason IS NULL OR char_length(btrim(reason)) BETWEEN 3 AND 500",
            name="ck_purchase_order_transition_reason",
        ),
        sa.CheckConstraint("version_after >= 1", name="ck_purchase_order_transition_version"),
        schema=SCHEMA,
        comment="Immutable purchase order history (RLS protected).",
    )
    op.create_index(
        "ix_purchase_order_transition_company_order",
        "purchase_order_transition",
        ["company_id", "purchase_order_id", "occurred_at"],
        schema=SCHEMA,
    )


def _create_shipment() -> None:
    op.create_table(
        "shipment",
        _pk(),
        _company_id(),
        sa.Column("shipment_number", sa.String(length=40), nullable=False),
        sa.Column("sales_order_id", _UUID, nullable=False),
        sa.Column("purchase_order_id", _UUID, nullable=True),
        sa.Column("transport_mode", sa.String(length=16), nullable=False),
        sa.Column("origin", sa.Text(), nullable=False),
        sa.Column("destination", sa.Text(), nullable=False),
        sa.Column("carrier", sa.Text(), nullable=True),
        sa.Column("forwarder", sa.Text(), nullable=True),
        sa.Column("planned_dispatch_at", _TS, nullable=True),
        sa.Column("actual_dispatch_at", _TS, nullable=True),
        sa.Column("estimated_arrival_at", _TS, nullable=True),
        sa.Column("actual_arrival_at", _TS, nullable=True),
        sa.Column("delivered_at", _TS, nullable=True),
        sa.Column(
            "status", sa.String(length=16), nullable=False, server_default=sa.text("'PLANNED'")
        ),
        sa.Column("tracking_reference", sa.Text(), nullable=True),
        sa.Column("tracking_source", sa.String(length=24), nullable=True),
        sa.Column("delivery_evidence_reference", sa.Text(), nullable=True),
        sa.Column("delay_reason", sa.Text(), nullable=True),
        sa.Column("cancellation_reason", sa.Text(), nullable=True),
        sa.Column("notes", sa.Text(), nullable=True),
        _actor_fk("created_by", "fk_shipment_created_by_app_user", nullable=False),
        _created_at(),
        _updated_at(),
        _version(),
        _tenant_fk(
            "fk_shipment_sales_order_company",
            ["sales_order_id", "company_id"],
            "sales_order",
            ondelete="RESTRICT",
        ),
        _tenant_fk(
            "fk_shipment_purchase_order_company",
            ["purchase_order_id", "company_id"],
            "purchase_order",
            ondelete="RESTRICT",
        ),
        sa.UniqueConstraint("id", "company_id", name="uq_shipment_id_company_id"),
        sa.UniqueConstraint("company_id", "shipment_number", name="uq_shipment_company_number"),
        sa.CheckConstraint(f"status IN ({_SHIPMENT_STATUSES})", name="ck_shipment_status"),
        sa.CheckConstraint(
            f"transport_mode IN ({_TRANSPORT_MODES})", name="ck_shipment_transport_mode"
        ),
        sa.CheckConstraint(
            f"tracking_source IS NULL OR tracking_source IN ({_TRACKING_SOURCES})",
            name="ck_shipment_tracking_source",
        ),
        sa.CheckConstraint(
            "char_length(btrim(shipment_number)) BETWEEN 3 AND 40", name="ck_shipment_number"
        ),
        sa.CheckConstraint(
            "char_length(btrim(origin)) BETWEEN 2 AND 160", name="ck_shipment_origin"
        ),
        sa.CheckConstraint(
            "char_length(btrim(destination)) BETWEEN 2 AND 160", name="ck_shipment_destination"
        ),
        sa.CheckConstraint("version >= 1", name="ck_shipment_version"),
        sa.CheckConstraint(
            "actual_dispatch_at IS NULL OR planned_dispatch_at IS NULL "
            "OR actual_dispatch_at >= planned_dispatch_at",
            name="ck_shipment_dispatch_order",
        ),
        sa.CheckConstraint(
            "actual_arrival_at IS NULL OR actual_dispatch_at IS NULL "
            "OR actual_arrival_at >= actual_dispatch_at",
            name="ck_shipment_arrival_order",
        ),
        sa.CheckConstraint(
            "delivered_at IS NULL OR actual_arrival_at IS NULL "
            "OR delivered_at >= actual_arrival_at",
            name="ck_shipment_delivery_order",
        ),
        sa.CheckConstraint(
            "status <> 'CANCELLED' OR cancellation_reason IS NOT NULL",
            name="ck_shipment_cancellation_reason",
        ),
        sa.CheckConstraint(
            "status <> 'DELIVERED' OR delivery_evidence_reference IS NOT NULL",
            name="ck_shipment_delivery_evidence",
        ),
        schema=SCHEMA,
        comment="Tenant-scoped shipments (RLS protected).",
    )
    for index, columns in (
        ("ix_shipment_company_status", ["company_id", "status"]),
        ("ix_shipment_company_sales_order", ["company_id", "sales_order_id"]),
        ("ix_shipment_company_eta", ["company_id", "estimated_arrival_at"]),
    ):
        op.create_index(index, "shipment", columns, schema=SCHEMA)


def _create_shipment_item() -> None:
    op.create_table(
        "shipment_item",
        _pk(),
        _company_id(),
        sa.Column("shipment_id", _UUID, nullable=False),
        sa.Column("sales_order_item_id", _UUID, nullable=False),
        sa.Column("product_id", _UUID, nullable=False),
        sa.Column("quantity", sa.Numeric(precision=18, scale=3), nullable=False),
        sa.Column("unit", sa.String(length=16), nullable=False),
        _created_at(),
        _tenant_fk(
            "fk_shipment_item_shipment_company",
            ["shipment_id", "company_id"],
            "shipment",
            ondelete="CASCADE",
        ),
        _tenant_fk(
            "fk_shipment_item_order_item_company",
            ["sales_order_item_id", "company_id"],
            "sales_order_item",
            ondelete="RESTRICT",
        ),
        sa.UniqueConstraint(
            "shipment_id", "sales_order_item_id", name="uq_shipment_item_shipment_id_order_item"
        ),
        sa.CheckConstraint("quantity > 0", name="ck_shipment_item_quantity"),
        sa.CheckConstraint(f"unit IN ({_UNITS})", name="ck_shipment_item_unit"),
        schema=SCHEMA,
        comment="Tenant-scoped shipment lines (RLS protected).",
    )
    op.create_index(
        "ix_shipment_item_company_shipment",
        "shipment_item",
        ["company_id", "shipment_id"],
        schema=SCHEMA,
    )
    op.create_index(
        "ix_shipment_item_company_order_item",
        "shipment_item",
        ["company_id", "sales_order_item_id"],
        schema=SCHEMA,
    )


def _create_shipment_event() -> None:
    op.create_table(
        "shipment_event",
        _pk(),
        _company_id(),
        sa.Column("shipment_id", _UUID, nullable=False),
        sa.Column("event_type", sa.String(length=24), nullable=False),
        sa.Column("occurred_at", _TS, nullable=False),
        sa.Column("location", sa.Text(), nullable=True),
        sa.Column("notes", sa.Text(), nullable=True),
        sa.Column("evidence_reference", sa.Text(), nullable=True),
        sa.Column("tracking_source", sa.String(length=24), nullable=True),
        _actor_fk("recorded_by", "fk_shipment_event_recorded_by_app_user", nullable=False),
        sa.Column("recorded_at", _TS, nullable=False, server_default=sa.text("now()")),
        _tenant_fk(
            "fk_shipment_event_shipment_company",
            ["shipment_id", "company_id"],
            "shipment",
            ondelete="CASCADE",
        ),
        sa.CheckConstraint(
            f"event_type IN ({_EVENT_TYPES})", name="ck_shipment_event_type"
        ),
        sa.CheckConstraint(
            f"tracking_source IS NULL OR tracking_source IN ({_TRACKING_SOURCES})",
            name="ck_shipment_event_tracking_source",
        ),
        sa.CheckConstraint(
            "notes IS NULL OR char_length(notes) <= 2000", name="ck_shipment_event_notes"
        ),
        schema=SCHEMA,
        comment="Immutable shipment milestones (RLS protected).",
    )
    op.create_index(
        "ix_shipment_event_company_shipment",
        "shipment_event",
        ["company_id", "shipment_id", "occurred_at"],
        schema=SCHEMA,
    )


def _create_shipment_reference() -> None:
    op.create_table(
        "shipment_reference",
        _pk(),
        _company_id(),
        sa.Column("shipment_id", _UUID, nullable=False),
        sa.Column("reference_type", sa.String(length=24), nullable=False),
        sa.Column("reference_value", sa.Text(), nullable=False),
        sa.Column("provenance", sa.String(length=24), nullable=False),
        _created_at(),
        _tenant_fk(
            "fk_shipment_reference_shipment_company",
            ["shipment_id", "company_id"],
            "shipment",
            ondelete="CASCADE",
        ),
        sa.UniqueConstraint(
            "company_id",
            "reference_type",
            "reference_value",
            name="uq_shipment_reference_company_type_value",
        ),
        sa.CheckConstraint(
            "reference_type IN ('BOOKING','CONTAINER','BILL_OF_LADING','AIR_WAYBILL',"
            "'CMR','TRACKING','OTHER')",
            name="ck_shipment_reference_type",
        ),
        sa.CheckConstraint(
            "char_length(btrim(reference_value)) BETWEEN 2 AND 120",
            name="ck_shipment_reference_value",
        ),
        sa.CheckConstraint(
            f"provenance IN ({_TRACKING_SOURCES})", name="ck_shipment_reference_provenance"
        ),
        schema=SCHEMA,
        comment="Tenant-scoped shipment references (RLS protected).",
    )
    op.create_index(
        "ix_shipment_reference_company_shipment",
        "shipment_reference",
        ["company_id", "shipment_id"],
        schema=SCHEMA,
    )


def _create_shipment_cost() -> None:
    op.create_table(
        "shipment_cost",
        _pk(),
        _company_id(),
        sa.Column("shipment_id", _UUID, nullable=False),
        sa.Column("cost_type", sa.String(length=24), nullable=False),
        sa.Column("stage", sa.String(length=16), nullable=False),
        sa.Column("amount", sa.Numeric(precision=18, scale=2), nullable=False),
        sa.Column("currency", sa.String(length=3), nullable=False),
        sa.Column("reference", sa.Text(), nullable=False),
        sa.Column("notes", sa.Text(), nullable=True),
        _actor_fk("recorded_by", "fk_shipment_cost_recorded_by_app_user", nullable=False),
        sa.Column("recorded_at", _TS, nullable=False, server_default=sa.text("now()")),
        _tenant_fk(
            "fk_shipment_cost_shipment_company",
            ["shipment_id", "company_id"],
            "shipment",
            ondelete="CASCADE",
        ),
        sa.CheckConstraint(
            "cost_type IN ('FREIGHT','INSURANCE','HANDLING','CUSTOMS_BROKERAGE',"
            "'DOMESTIC_TRANSPORT','OTHER')",
            name="ck_shipment_cost_type",
        ),
        sa.CheckConstraint(f"stage IN ({_COST_STAGES})", name="ck_shipment_cost_stage"),
        sa.CheckConstraint("amount >= 0", name="ck_shipment_cost_amount"),
        sa.CheckConstraint(
            "char_length(btrim(reference)) BETWEEN 2 AND 200", name="ck_shipment_cost_reference"
        ),
        schema=SCHEMA,
        comment="Tenant-scoped shipment costs (RLS protected).",
    )
    op.create_index(
        "ix_shipment_cost_company_shipment",
        "shipment_cost",
        ["company_id", "shipment_id"],
        schema=SCHEMA,
    )


def _create_trade_document() -> None:
    op.create_table(
        "trade_document",
        _pk(),
        _company_id(),
        sa.Column("document_type", sa.String(length=48), nullable=False),
        sa.Column("linked_entity_type", sa.String(length=32), nullable=False),
        sa.Column("linked_entity_id", _UUID, nullable=False),
        sa.Column("title", sa.Text(), nullable=False),
        sa.Column("original_filename", sa.Text(), nullable=False),
        sa.Column("storage_key", sa.Text(), nullable=False),
        sa.Column("mime_type", sa.String(length=160), nullable=False),
        sa.Column("size_bytes", sa.BigInteger(), nullable=False),
        sa.Column("sha256", sa.String(length=64), nullable=False),
        _version(),
        sa.Column("supersedes_document_id", _UUID, nullable=True),
        sa.Column(
            "status", sa.String(length=16), nullable=False, server_default=sa.text("'ACTIVE'")
        ),
        sa.Column(
            "verification_status",
            sa.String(length=16),
            nullable=False,
            server_default=sa.text("'UNVERIFIED'"),
        ),
        sa.Column(
            "is_draft", sa.Boolean(), nullable=False, server_default=sa.text("false")
        ),
        sa.Column("archived_at", _TS, nullable=True),
        _actor_fk("archived_by", "fk_trade_document_archived_by_app_user", nullable=True),
        _actor_fk("uploaded_by", "fk_trade_document_uploaded_by_app_user", nullable=False),
        sa.Column("uploaded_at", _TS, nullable=False, server_default=sa.text("now()")),
        _tenant_fk(
            "fk_trade_document_supersedes_company",
            ["supersedes_document_id", "company_id"],
            "trade_document",
            ondelete="RESTRICT",
        ),
        sa.UniqueConstraint("id", "company_id", name="uq_trade_document_id_company_id"),
        sa.UniqueConstraint("storage_key", name="uq_trade_document_storage_key"),
        sa.CheckConstraint(f"document_type IN ({_DOCUMENT_TYPES})", name="ck_trade_document_type"),
        sa.CheckConstraint(
            f"linked_entity_type IN ({_ENTITY_TYPES})", name="ck_trade_document_entity_type"
        ),
        sa.CheckConstraint(
            f"status IN ({_DOCUMENT_STATUSES})", name="ck_trade_document_status"
        ),
        sa.CheckConstraint(
            f"verification_status IN ({_VERIFICATION_STATUSES})",
            name="ck_trade_document_verification",
        ),
        sa.CheckConstraint("version >= 1", name="ck_trade_document_version"),
        sa.CheckConstraint("size_bytes > 0", name="ck_trade_document_size"),
        sa.CheckConstraint("sha256 ~ '^[0-9a-f]{64}$'", name="ck_trade_document_sha256"),
        sa.CheckConstraint(
            "char_length(btrim(original_filename)) BETWEEN 1 AND 255",
            name="ck_trade_document_filename",
        ),
        schema=SCHEMA,
        comment="Tenant-scoped document metadata (RLS protected).",
    )
    for index, columns in (
        (
            "ix_trade_document_company_entity",
            ["company_id", "linked_entity_type", "linked_entity_id"],
        ),
        ("ix_trade_document_company_type", ["company_id", "document_type"]),
        ("ix_trade_document_company_status", ["company_id", "status"]),
    ):
        op.create_index(index, "trade_document", columns, schema=SCHEMA)


def _apply_tenant_rls() -> None:
    """Company-scoped policies for every Stage 4 table (fail closed)."""
    for table in _TABLES:
        qualified = f"{SCHEMA}.{table}"
        predicate = f"company_id = {SCHEMA}.current_company_id()"
        op.execute(f"ALTER TABLE {qualified} ENABLE ROW LEVEL SECURITY")
        op.execute(
            f"CREATE POLICY {table}_tenant_select ON {qualified} "
            f"FOR SELECT USING ({predicate})"
        )
        op.execute(
            f"CREATE POLICY {table}_tenant_insert ON {qualified} "
            f"FOR INSERT WITH CHECK ({predicate})"
        )
        op.execute(
            f"CREATE POLICY {table}_tenant_update ON {qualified} "
            f"FOR UPDATE USING ({predicate}) WITH CHECK ({predicate})"
        )
        op.execute(
            f"CREATE POLICY {table}_tenant_delete ON {qualified} FOR DELETE USING ({predicate})"
        )


def _apply_grants() -> None:
    role = _app_role()
    schema = _quote(SCHEMA)
    op.execute(
        "GRANT SELECT, INSERT, UPDATE, DELETE ON "
        + ", ".join(f"{schema}.{table}" for table in _TABLES)
        + f" TO {role}"
    )
    # Recorded commercial facts are append-only for the runtime role.
    op.execute(
        "REVOKE UPDATE, DELETE ON "
        + ", ".join(f"{schema}.{table}" for table in _APPEND_ONLY_TABLES)
        + f" FROM {role}"
    )


_STAGE_1A_ACTIONS = (
    "'auth.login.success', 'auth.login.failure', 'auth.logout', "
    "'session.company.switch', 'session.revoked', 'membership.changed', "
    "'access.denied', 'identity.bootstrap'"
)
_STAGE_1B_ACTIONS = (
    "'counterparty.created', 'counterparty.updated', 'product.created', "
    "'product.updated', 'deal.created', 'deal.updated', 'deal.transitioned'"
)
_STAGE_3_ACTIONS = (
    "'rfq.created', 'rfq.updated', 'rfq.prepared', 'rfq.sent', 'rfq.cancelled', "
    "'rfq.closed', 'supplier_quote.recorded', 'supplier_quote.revised', "
    "'supplier_quote.withdrawn', 'fx_rate.recorded', 'pricing_scenario.created', "
    "'pricing_scenario.updated', 'sales_quote.created', 'sales_quote.submitted', "
    "'sales_quote.approved', 'sales_quote.rejected', 'sales_quote.withdrawn'"
)
_STAGE_4_ACTIONS = (
    "'deal.won', 'customer_acceptance.recorded', 'sales_order.created', "
    "'sales_order.transitioned', 'sales_order.amended', 'purchase_order.created', "
    "'purchase_order.transitioned', 'shipment.created', 'shipment.updated', "
    "'shipment.transitioned', 'shipment.cost_recorded', 'document.uploaded', "
    "'document.downloaded', 'document.archived', 'document.verified'"
)


def _set_audit_actions(actions: str) -> None:
    op.drop_constraint("ck_audit_action", "audit_record", schema=SCHEMA, type_="check")
    op.create_check_constraint(
        "ck_audit_action", "audit_record", f"action IN ({actions})", schema=SCHEMA
    )


def upgrade() -> None:
    _create_acceptance()
    _create_sales_order()
    _create_sales_order_item()
    _create_sales_order_transition()
    _create_order_amendment()
    _create_purchase_order()
    _create_purchase_order_item()
    _create_purchase_order_transition()
    _create_shipment()
    _create_shipment_item()
    _create_shipment_event()
    _create_shipment_reference()
    _create_shipment_cost()
    _create_trade_document()
    _apply_tenant_rls()
    _apply_grants()
    _set_audit_actions(
        f"{_STAGE_1A_ACTIONS}, {_STAGE_1B_ACTIONS}, {_STAGE_3_ACTIONS}, {_STAGE_4_ACTIONS}"
    )


def downgrade() -> None:
    _set_audit_actions(f"{_STAGE_1A_ACTIONS}, {_STAGE_1B_ACTIONS}, {_STAGE_3_ACTIONS}")
    for table in reversed(_TABLES):
        op.drop_table(table, schema=SCHEMA)

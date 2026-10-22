"""stage 3 sourcing: RFQs, supplier quotes, FX snapshots, landing cost, sales quotes

Creates the sourcing chain of TOUCHE COMMERCE:

* ``fx_rate_snapshot``        -- sourced FX observations, never inferred rates
* ``supplier_rfq``            -- one RFQ per supplier per deal
* ``supplier_rfq_item``       -- requested lines
* ``supplier_rfq_revision``   -- append-only RFQ snapshots
* ``supplier_quote``          -- a supplier's priced response
* ``supplier_quote_item``     -- priced lines
* ``supplier_quote_revision`` -- append-only quote snapshots
* ``pricing_scenario``        -- deterministic landed-cost calculation
* ``pricing_cost_component``  -- every cost line with its source and FX snapshot
* ``sales_quote``             -- customer-facing quotation of a scenario
* ``sales_quote_item``        -- quoted lines
* ``sales_quote_revision``    -- append-only sales quote snapshots

Money is ``numeric``; every child row references its parent through a composite
``(id, company_id)`` foreign key; every table is protected by row level security
and the runtime role receives no UPDATE/DELETE on the revision tables.  The
migration widens the audit action constraint and touches no existing data, so a
Stage 1B database upgrades in place.

Revision ID: 0004_sourcing
Revises: 0003_trade
Create Date: 2026-10-22
"""

from __future__ import annotations

import os
from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision: str = "0004_sourcing"
down_revision: str | None = "0003_trade"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

SCHEMA = "touche"
_APP_ROLE_ENV = "TOUCHE_DB_APP_USER"
_DEFAULT_APP_ROLE = "touche_app"
_UUID = postgresql.UUID(as_uuid=True)
_TS = sa.DateTime(timezone=True)
_JSONB = postgresql.JSONB(astext_type=sa.Text())

_SOURCING_TABLES = (
    "fx_rate_snapshot",
    "supplier_rfq",
    "supplier_rfq_item",
    "supplier_rfq_revision",
    "supplier_quote",
    "supplier_quote_item",
    "supplier_quote_revision",
    "pricing_scenario",
    "pricing_cost_component",
    "sales_quote",
    "sales_quote_item",
    "sales_quote_revision",
)
_APPEND_ONLY_TABLES = (
    "supplier_rfq_revision",
    "supplier_quote_revision",
    "sales_quote_revision",
)

_RFQ_STATUSES = "'DRAFT', 'PREPARED', 'SENT', 'RESPONDED', 'CLOSED', 'CANCELLED'"
_QUOTE_STATUSES = "'RECEIVED', 'WITHDRAWN'"
_INCOTERMS = (
    "'EXW', 'FCA', 'FAS', 'FOB', 'CFR', 'CIF', 'CPT', 'CIP', 'DAP', 'DPU', 'DDP'"
)
_COST_TYPES = (
    "'PURCHASE', 'FREIGHT', 'DOMESTIC_TRANSPORT', 'INSURANCE', 'CUSTOMS_DUTY', "
    "'CUSTOMS_BROKERAGE', 'QUALITY_INSPECTION', 'BANKING_FINANCE', 'OTHER', "
    "'CONTINGENCY', 'VAT_CASHFLOW'"
)
_COST_BASES = "'ORDER', 'LINE'"
_VERIFICATION_STATUSES = "'ESTIMATED', 'VERIFIED'"
_SCENARIO_STATUSES = "'INCOMPLETE', 'ESTIMATED', 'VERIFIED_INPUTS'"
_SALES_QUOTE_STATUSES = "'DRAFT', 'PENDING_APPROVAL', 'APPROVED', 'REJECTED', 'WITHDRAWN'"
_UNITS = "'kg', 'mt', 'lb', 'unit', 'l', 'm3'"
_CURRENCY = "currency ~ '^[A-Z]{3}$'"


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
    """A foreign key to ``app_user`` with the same constraint name as the model."""
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


def _create_fx_rate_snapshot() -> None:
    op.create_table(
        "fx_rate_snapshot",
        _pk(),
        _company_id(),
        sa.Column("base_currency", sa.String(length=3), nullable=False),
        sa.Column("quote_currency", sa.String(length=3), nullable=False),
        sa.Column("rate", sa.Numeric(precision=20, scale=10), nullable=False),
        sa.Column("effective_at", _TS, nullable=False),
        sa.Column("source", sa.Text(), nullable=False),
        _actor_fk(
            "recorded_by", "fk_fx_rate_snapshot_recorded_by_app_user", nullable=False
        ),
        sa.Column("recorded_at", _TS, nullable=False, server_default=sa.text("now()")),
        sa.ForeignKeyConstraint(
            ["company_id"],
            [f"{SCHEMA}.company.id"],
            name="fk_fx_rate_snapshot_company_id_company",
            ondelete="CASCADE",
        ),
        sa.UniqueConstraint(
            "company_id",
            "base_currency",
            "quote_currency",
            "effective_at",
            name="uq_fx_rate_snapshot_company_pair_effective",
        ),
        sa.UniqueConstraint("id", "company_id", name="uq_fx_rate_snapshot_id_company_id"),
        sa.CheckConstraint("base_currency ~ '^[A-Z]{3}$'", name="ck_fx_rate_base_currency"),
        sa.CheckConstraint("quote_currency ~ '^[A-Z]{3}$'", name="ck_fx_rate_quote_currency"),
        sa.CheckConstraint("base_currency <> quote_currency", name="ck_fx_rate_distinct_currency"),
        sa.CheckConstraint("rate > 0", name="ck_fx_rate_positive"),
        sa.CheckConstraint(
            "char_length(btrim(source)) BETWEEN 3 AND 160", name="ck_fx_rate_source_length"
        ),
        schema=SCHEMA,
        comment="Sourced FX observations (RLS protected).",
    )
    op.create_index(
        "ix_fx_rate_snapshot_company_pair",
        "fx_rate_snapshot",
        ["company_id", "base_currency", "quote_currency"],
        schema=SCHEMA,
    )


def _create_supplier_rfq() -> None:
    op.create_table(
        "supplier_rfq",
        _pk(),
        _company_id(),
        sa.Column("deal_id", _UUID, nullable=False),
        sa.Column("supplier_counterparty_id", _UUID, nullable=False),
        sa.Column("reference_number", sa.String(length=40), nullable=False),
        sa.Column("requested_currency", sa.String(length=3), nullable=False),
        sa.Column("requested_delivery_terms", sa.String(length=40), nullable=True),
        sa.Column("delivery_location", sa.Text(), nullable=False),
        sa.Column("response_due_date", sa.Date(), nullable=True),
        sa.Column("notes", sa.Text(), nullable=True),
        sa.Column("status", sa.String(length=16), nullable=False, server_default=sa.text("'DRAFT'")),
        sa.Column("revision", sa.Integer(), nullable=False, server_default=sa.text("1")),
        _version(),
        sa.Column("sent_channel", sa.String(length=40), nullable=True),
        sa.Column("sent_at", _TS, nullable=True),
        sa.Column("sent_evidence", sa.Text(), nullable=True),
        _actor_fk("created_by", "fk_supplier_rfq_created_by_app_user", nullable=False),
        _created_at(),
        _updated_at(),
        _tenant_fk(
            "fk_supplier_rfq_deal_company", ["deal_id", "company_id"], "deal", ondelete="CASCADE"
        ),
        _tenant_fk(
            "fk_supplier_rfq_supplier_company",
            ["supplier_counterparty_id", "company_id"],
            "counterparty",
            ondelete="RESTRICT",
        ),
        sa.UniqueConstraint(
            "company_id", "reference_number", name="uq_supplier_rfq_company_reference"
        ),
        sa.UniqueConstraint("id", "company_id", name="uq_supplier_rfq_id_company_id"),
        sa.CheckConstraint("reference_number = upper(reference_number)", name="ck_supplier_rfq_ref_upper"),
        sa.CheckConstraint(
            "char_length(reference_number) BETWEEN 3 AND 40", name="ck_supplier_rfq_ref_length"
        ),
        sa.CheckConstraint(
            "requested_currency ~ '^[A-Z]{3}$'", name="ck_supplier_rfq_currency_iso"
        ),
        sa.CheckConstraint(f"status IN ({_RFQ_STATUSES})", name="ck_supplier_rfq_status"),
        sa.CheckConstraint(
            "char_length(btrim(delivery_location)) BETWEEN 2 AND 160",
            name="ck_supplier_rfq_delivery_location",
        ),
        sa.CheckConstraint(
            "requested_delivery_terms IS NULL OR "
            "char_length(requested_delivery_terms) BETWEEN 3 AND 40",
            name="ck_supplier_rfq_delivery_terms",
        ),
        sa.CheckConstraint("revision >= 1", name="ck_supplier_rfq_revision"),
        sa.CheckConstraint("version >= 1", name="ck_supplier_rfq_version"),
        sa.CheckConstraint(
            "status NOT IN ('SENT', 'RESPONDED') OR sent_at IS NOT NULL",
            name="ck_supplier_rfq_sent_evidence",
        ),
        schema=SCHEMA,
        comment="Tenant-scoped supplier RFQs (RLS protected).",
    )
    op.create_index(
        "ix_supplier_rfq_company_deal",
        "supplier_rfq",
        ["company_id", "deal_id", "created_at"],
        schema=SCHEMA,
    )
    op.create_index(
        "ix_supplier_rfq_company_status", "supplier_rfq", ["company_id", "status"], schema=SCHEMA
    )
    op.create_index(
        "ix_supplier_rfq_company_supplier",
        "supplier_rfq",
        ["company_id", "supplier_counterparty_id"],
        schema=SCHEMA,
    )


def _create_supplier_rfq_item() -> None:
    op.create_table(
        "supplier_rfq_item",
        _pk(),
        _company_id(),
        sa.Column("rfq_id", _UUID, nullable=False),
        sa.Column("product_id", _UUID, nullable=False),
        sa.Column("description", sa.Text(), nullable=False),
        sa.Column("quantity", sa.Numeric(precision=18, scale=3), nullable=False),
        sa.Column("unit", sa.String(length=16), nullable=False),
        sa.Column("notes", sa.Text(), nullable=True),
        _created_at(),
        _tenant_fk(
            "fk_supplier_rfq_item_rfq_company",
            ["rfq_id", "company_id"],
            "supplier_rfq",
            ondelete="CASCADE",
        ),
        _tenant_fk(
            "fk_supplier_rfq_item_product_company",
            ["product_id", "company_id"],
            "product",
            ondelete="RESTRICT",
        ),
        sa.UniqueConstraint(
            "rfq_id", "product_id", name="uq_supplier_rfq_item_rfq_id_product_id"
        ),
        sa.CheckConstraint("quantity > 0", name="ck_supplier_rfq_item_quantity"),
        sa.CheckConstraint(f"unit IN ({_UNITS})", name="ck_supplier_rfq_item_unit"),
        sa.CheckConstraint(
            "char_length(btrim(description)) BETWEEN 1 AND 500",
            name="ck_supplier_rfq_item_description",
        ),
        schema=SCHEMA,
        comment="Tenant-scoped RFQ lines (RLS protected).",
    )
    op.create_index(
        "ix_supplier_rfq_item_company_rfq",
        "supplier_rfq_item",
        ["company_id", "rfq_id"],
        schema=SCHEMA,
    )


def _create_supplier_rfq_revision() -> None:
    op.create_table(
        "supplier_rfq_revision",
        _pk(),
        _company_id(),
        sa.Column("rfq_id", _UUID, nullable=False),
        sa.Column("revision", sa.Integer(), nullable=False),
        sa.Column("snapshot", _JSONB, nullable=False),
        sa.Column("reason", sa.Text(), nullable=True),
        _actor_fk("actor_id", "fk_supplier_rfq_revision_actor_app_user", nullable=False),
        _created_at(),
        _tenant_fk(
            "fk_supplier_rfq_revision_rfq_company",
            ["rfq_id", "company_id"],
            "supplier_rfq",
            ondelete="CASCADE",
        ),
        sa.UniqueConstraint(
            "rfq_id", "revision", name="uq_supplier_rfq_revision_rfq_revision"
        ),
        sa.CheckConstraint("revision >= 1", name="ck_supplier_rfq_revision_no"),
        sa.CheckConstraint(
            "jsonb_typeof(snapshot) = 'object'", name="ck_supplier_rfq_revision_snapshot"
        ),
        schema=SCHEMA,
        comment="Append-only RFQ revision history (RLS protected).",
    )
    op.create_index(
        "ix_supplier_rfq_revision_company_rfq",
        "supplier_rfq_revision",
        ["company_id", "rfq_id"],
        schema=SCHEMA,
    )


def _create_supplier_quote() -> None:
    op.create_table(
        "supplier_quote",
        _pk(),
        _company_id(),
        sa.Column("rfq_id", _UUID, nullable=False),
        sa.Column("supplier_counterparty_id", _UUID, nullable=False),
        sa.Column("supplier_reference", sa.String(length=80), nullable=True),
        sa.Column("currency", sa.String(length=3), nullable=False),
        sa.Column("incoterm", sa.String(length=3), nullable=False),
        sa.Column("named_delivery_place", sa.Text(), nullable=False),
        sa.Column("payment_terms", sa.Text(), nullable=False),
        sa.Column("shipping_conditions", sa.Text(), nullable=True),
        sa.Column("lead_time_days", sa.Integer(), nullable=False),
        sa.Column("valid_until", sa.Date(), nullable=False),
        sa.Column(
            "status", sa.String(length=16), nullable=False, server_default=sa.text("'RECEIVED'")
        ),
        sa.Column("revision", sa.Integer(), nullable=False, server_default=sa.text("1")),
        sa.Column("source_reference", sa.Text(), nullable=False),
        sa.Column("notes", sa.Text(), nullable=True),
        sa.Column("received_at", _TS, nullable=False),
        sa.Column("supersedes_quote_id", _UUID, nullable=True),
        _version(),
        _actor_fk("created_by", "fk_supplier_quote_created_by_app_user", nullable=False),
        _created_at(),
        _updated_at(),
        _tenant_fk(
            "fk_supplier_quote_rfq_company",
            ["rfq_id", "company_id"],
            "supplier_rfq",
            ondelete="CASCADE",
        ),
        _tenant_fk(
            "fk_supplier_quote_supplier_company",
            ["supplier_counterparty_id", "company_id"],
            "counterparty",
            ondelete="RESTRICT",
        ),
        _tenant_fk(
            "fk_supplier_quote_supersedes_company",
            ["supersedes_quote_id", "company_id"],
            "supplier_quote",
            ondelete="RESTRICT",
        ),
        sa.UniqueConstraint("id", "company_id", name="uq_supplier_quote_id_company_id"),
        sa.UniqueConstraint("supersedes_quote_id", name="uq_supplier_quote_supersedes"),
        sa.CheckConstraint("currency ~ '^[A-Z]{3}$'", name="ck_supplier_quote_currency_iso"),
        sa.CheckConstraint(f"incoterm IN ({_INCOTERMS})", name="ck_supplier_quote_incoterm"),
        sa.CheckConstraint(f"status IN ({_QUOTE_STATUSES})", name="ck_supplier_quote_status"),
        sa.CheckConstraint(
            "char_length(btrim(named_delivery_place)) BETWEEN 2 AND 160",
            name="ck_supplier_quote_place",
        ),
        sa.CheckConstraint(
            "char_length(btrim(payment_terms)) BETWEEN 2 AND 200",
            name="ck_supplier_quote_payment_terms",
        ),
        sa.CheckConstraint(
            "char_length(btrim(source_reference)) BETWEEN 3 AND 200",
            name="ck_supplier_quote_source_reference",
        ),
        sa.CheckConstraint("lead_time_days >= 0", name="ck_supplier_quote_lead_time"),
        sa.CheckConstraint("revision >= 1", name="ck_supplier_quote_revision"),
        sa.CheckConstraint("version >= 1", name="ck_supplier_quote_version"),
        schema=SCHEMA,
        comment="Tenant-scoped supplier quotes (RLS protected).",
    )
    for index, columns in (
        ("ix_supplier_quote_company_rfq", ["company_id", "rfq_id", "revision"]),
        ("ix_supplier_quote_company_supplier", ["company_id", "supplier_counterparty_id"]),
        ("ix_supplier_quote_company_valid_until", ["company_id", "valid_until"]),
    ):
        op.create_index(index, "supplier_quote", columns, schema=SCHEMA)


def _create_supplier_quote_item() -> None:
    op.create_table(
        "supplier_quote_item",
        _pk(),
        _company_id(),
        sa.Column("quote_id", _UUID, nullable=False),
        sa.Column("product_id", _UUID, nullable=False),
        sa.Column("description", sa.Text(), nullable=False),
        sa.Column("quantity", sa.Numeric(precision=18, scale=3), nullable=False),
        sa.Column("unit", sa.String(length=16), nullable=False),
        sa.Column("unit_price", sa.Numeric(precision=18, scale=4), nullable=False),
        sa.Column("moq", sa.Numeric(precision=18, scale=3), nullable=True),
        sa.Column("line_notes", sa.Text(), nullable=True),
        _created_at(),
        _tenant_fk(
            "fk_supplier_quote_item_quote_company",
            ["quote_id", "company_id"],
            "supplier_quote",
            ondelete="CASCADE",
        ),
        _tenant_fk(
            "fk_supplier_quote_item_product_company",
            ["product_id", "company_id"],
            "product",
            ondelete="RESTRICT",
        ),
        sa.UniqueConstraint(
            "quote_id", "product_id", name="uq_supplier_quote_item_quote_product"
        ),
        sa.CheckConstraint("quantity > 0", name="ck_supplier_quote_item_quantity"),
        sa.CheckConstraint("unit_price >= 0", name="ck_supplier_quote_item_unit_price"),
        sa.CheckConstraint("moq IS NULL OR moq > 0", name="ck_supplier_quote_item_moq"),
        sa.CheckConstraint(f"unit IN ({_UNITS})", name="ck_supplier_quote_item_unit"),
        schema=SCHEMA,
        comment="Tenant-scoped supplier quote lines (RLS protected).",
    )
    op.create_index(
        "ix_supplier_quote_item_company_quote",
        "supplier_quote_item",
        ["company_id", "quote_id"],
        schema=SCHEMA,
    )


def _create_supplier_quote_revision() -> None:
    op.create_table(
        "supplier_quote_revision",
        _pk(),
        _company_id(),
        sa.Column("quote_id", _UUID, nullable=False),
        sa.Column("revision", sa.Integer(), nullable=False),
        sa.Column("snapshot", _JSONB, nullable=False),
        sa.Column("reason", sa.Text(), nullable=True),
        _actor_fk("actor_id", "fk_supplier_quote_revision_actor_app_user", nullable=False),
        _created_at(),
        _tenant_fk(
            "fk_supplier_quote_revision_quote_company",
            ["quote_id", "company_id"],
            "supplier_quote",
            ondelete="CASCADE",
        ),
        sa.UniqueConstraint(
            "quote_id", "revision", name="uq_supplier_quote_revision_quote_revision"
        ),
        sa.CheckConstraint("revision >= 1", name="ck_supplier_quote_revision_no"),
        sa.CheckConstraint(
            "jsonb_typeof(snapshot) = 'object'", name="ck_supplier_quote_revision_snapshot"
        ),
        schema=SCHEMA,
        comment="Append-only supplier quote revisions (RLS protected).",
    )
    op.create_index(
        "ix_supplier_quote_revision_company_quote",
        "supplier_quote_revision",
        ["company_id", "quote_id"],
        schema=SCHEMA,
    )


def _create_pricing_scenario() -> None:
    op.create_table(
        "pricing_scenario",
        _pk(),
        _company_id(),
        sa.Column("deal_id", _UUID, nullable=False),
        sa.Column("supplier_quote_id", _UUID, nullable=False),
        sa.Column("target_currency", sa.String(length=3), nullable=False),
        sa.Column("sales_incoterm", sa.String(length=3), nullable=True),
        sa.Column("sales_named_place", sa.Text(), nullable=True),
        sa.Column("pricing_inputs", _JSONB, nullable=False),
        sa.Column("calculated_results", _JSONB, nullable=False),
        sa.Column("calculation_version", sa.String(length=40), nullable=False),
        sa.Column(
            "status", sa.String(length=24), nullable=False, server_default=sa.text("'INCOMPLETE'")
        ),
        sa.Column(
            "completeness", _JSONB, nullable=False, server_default=sa.text("'{}'::jsonb")
        ),
        _actor_fk("created_by", "fk_pricing_scenario_created_by_app_user", nullable=False),
        _created_at(),
        _updated_at(),
        _version(),
        _tenant_fk(
            "fk_pricing_scenario_deal_company",
            ["deal_id", "company_id"],
            "deal",
            ondelete="CASCADE",
        ),
        _tenant_fk(
            "fk_pricing_scenario_quote_company",
            ["supplier_quote_id", "company_id"],
            "supplier_quote",
            ondelete="RESTRICT",
        ),
        sa.UniqueConstraint("id", "company_id", name="uq_pricing_scenario_id_company_id"),
        sa.CheckConstraint(
            "target_currency ~ '^[A-Z]{3}$'", name="ck_pricing_scenario_currency_iso"
        ),
        sa.CheckConstraint(f"status IN ({_SCENARIO_STATUSES})", name="ck_pricing_scenario_status"),
        sa.CheckConstraint(
            "char_length(btrim(calculation_version)) BETWEEN 3 AND 40",
            name="ck_pricing_scenario_calculation_version",
        ),
        sa.CheckConstraint("version >= 1", name="ck_pricing_scenario_version"),
        sa.CheckConstraint(
            "jsonb_typeof(pricing_inputs) = 'object'", name="ck_pricing_scenario_inputs_object"
        ),
        sa.CheckConstraint(
            "jsonb_typeof(calculated_results) = 'object'",
            name="ck_pricing_scenario_results_object",
        ),
        schema=SCHEMA,
        comment="Tenant-scoped landed-cost scenarios (RLS protected).",
    )
    for index, columns in (
        ("ix_pricing_scenario_company_deal", ["company_id", "deal_id", "created_at"]),
        ("ix_pricing_scenario_company_quote", ["company_id", "supplier_quote_id"]),
        ("ix_pricing_scenario_company_status", ["company_id", "status"]),
    ):
        op.create_index(index, "pricing_scenario", columns, schema=SCHEMA)


def _create_pricing_cost_component() -> None:
    op.create_table(
        "pricing_cost_component",
        _pk(),
        _company_id(),
        sa.Column("scenario_id", _UUID, nullable=False),
        sa.Column("cost_type", sa.String(length=32), nullable=False),
        sa.Column("amount", sa.Numeric(precision=18, scale=2), nullable=False),
        sa.Column("currency", sa.String(length=3), nullable=False),
        sa.Column("basis", sa.String(length=8), nullable=False, server_default=sa.text("'ORDER'")),
        sa.Column("source_reference", sa.Text(), nullable=False),
        sa.Column("verification_status", sa.String(length=16), nullable=False),
        sa.Column("fx_rate_snapshot_id", _UUID, nullable=True),
        sa.Column("product_id", _UUID, nullable=True),
        sa.Column("notes", sa.Text(), nullable=True),
        _created_at(),
        _tenant_fk(
            "fk_pricing_cost_component_scenario_company",
            ["scenario_id", "company_id"],
            "pricing_scenario",
            ondelete="CASCADE",
        ),
        _tenant_fk(
            "fk_pricing_cost_component_fx_company",
            ["fx_rate_snapshot_id", "company_id"],
            "fx_rate_snapshot",
            ondelete="RESTRICT",
        ),
        _tenant_fk(
            "fk_pricing_cost_component_product_company",
            ["product_id", "company_id"],
            "product",
            ondelete="RESTRICT",
        ),
        sa.CheckConstraint(f"cost_type IN ({_COST_TYPES})", name="ck_pricing_cost_component_type"),
        sa.CheckConstraint(f"basis IN ({_COST_BASES})", name="ck_pricing_cost_component_basis"),
        sa.CheckConstraint(
            f"verification_status IN ({_VERIFICATION_STATUSES})",
            name="ck_pricing_cost_component_verification",
        ),
        sa.CheckConstraint("amount >= 0", name="ck_pricing_cost_component_amount"),
        sa.CheckConstraint(
            "(basis = 'LINE') = (product_id IS NOT NULL)",
            name="ck_pricing_cost_component_line_product",
        ),
        sa.CheckConstraint("currency ~ '^[A-Z]{3}$'", name="ck_pricing_cost_component_currency_iso"),
        sa.CheckConstraint(
            "char_length(btrim(source_reference)) BETWEEN 3 AND 200",
            name="ck_pricing_cost_component_source",
        ),
        schema=SCHEMA,
        comment="Tenant-scoped cost components (RLS protected).",
    )
    op.create_index(
        "ix_pricing_cost_component_company_scenario",
        "pricing_cost_component",
        ["company_id", "scenario_id"],
        schema=SCHEMA,
    )


def _create_sales_quote() -> None:
    op.create_table(
        "sales_quote",
        _pk(),
        _company_id(),
        sa.Column("deal_id", _UUID, nullable=False),
        sa.Column("quote_number", sa.String(length=40), nullable=False),
        sa.Column("revision", sa.Integer(), nullable=False, server_default=sa.text("1")),
        sa.Column("scenario_id", _UUID, nullable=False),
        sa.Column("customer_id", _UUID, nullable=False),
        sa.Column("currency", sa.String(length=3), nullable=False),
        sa.Column("valid_until", sa.Date(), nullable=False),
        sa.Column("incoterm", sa.String(length=3), nullable=False),
        sa.Column("named_delivery_place", sa.Text(), nullable=False),
        sa.Column("payment_terms", sa.Text(), nullable=False),
        sa.Column("status", sa.String(length=24), nullable=False, server_default=sa.text("'DRAFT'")),
        sa.Column("notes", sa.Text(), nullable=True),
        _actor_fk("approved_by", "fk_sales_quote_approved_by_app_user", nullable=True),
        sa.Column("approved_at", _TS, nullable=True),
        sa.Column("rejection_reason", sa.Text(), nullable=True),
        _actor_fk("submitted_by", "fk_sales_quote_submitted_by_app_user", nullable=True),
        sa.Column("submitted_at", _TS, nullable=True),
        sa.Column("supersedes_sales_quote_id", _UUID, nullable=True),
        _actor_fk("created_by", "fk_sales_quote_created_by_app_user", nullable=False),
        _created_at(),
        _updated_at(),
        _version(),
        _tenant_fk(
            "fk_sales_quote_deal_company",
            ["deal_id", "company_id"],
            "deal",
            ondelete="CASCADE",
        ),
        _tenant_fk(
            "fk_sales_quote_scenario_company",
            ["scenario_id", "company_id"],
            "pricing_scenario",
            ondelete="RESTRICT",
        ),
        _tenant_fk(
            "fk_sales_quote_customer_company",
            ["customer_id", "company_id"],
            "counterparty",
            ondelete="RESTRICT",
        ),
        _tenant_fk(
            "fk_sales_quote_supersedes_company",
            ["supersedes_sales_quote_id", "company_id"],
            "sales_quote",
            ondelete="RESTRICT",
        ),
        sa.UniqueConstraint("id", "company_id", name="uq_sales_quote_id_company_id"),
        sa.UniqueConstraint(
            "company_id", "quote_number", "revision", name="uq_sales_quote_company_number_revision"
        ),
        sa.UniqueConstraint("supersedes_sales_quote_id", name="uq_sales_quote_supersedes"),
        sa.CheckConstraint("currency ~ '^[A-Z]{3}$'", name="ck_sales_quote_currency_iso"),
        sa.CheckConstraint(f"status IN ({_SALES_QUOTE_STATUSES})", name="ck_sales_quote_status"),
        sa.CheckConstraint(
            "char_length(btrim(quote_number)) BETWEEN 3 AND 40", name="ck_sales_quote_number"
        ),
        sa.CheckConstraint(
            "char_length(btrim(named_delivery_place)) BETWEEN 2 AND 160",
            name="ck_sales_quote_place",
        ),
        sa.CheckConstraint(
            "char_length(btrim(payment_terms)) BETWEEN 2 AND 200",
            name="ck_sales_quote_payment_terms",
        ),
        sa.CheckConstraint("revision >= 1", name="ck_sales_quote_revision"),
        sa.CheckConstraint("version >= 1", name="ck_sales_quote_version"),
        sa.CheckConstraint(
            "(status = 'APPROVED') = (approved_by IS NOT NULL AND approved_at IS NOT NULL)",
            name="ck_sales_quote_approval_pair",
        ),
        sa.CheckConstraint(
            "status <> 'REJECTED' OR rejection_reason IS NOT NULL",
            name="ck_sales_quote_rejection_reason",
        ),
        schema=SCHEMA,
        comment="Tenant-scoped sales quotes (RLS protected).",
    )
    for index, columns in (
        ("ix_sales_quote_company_deal", ["company_id", "deal_id", "created_at"]),
        ("ix_sales_quote_company_status", ["company_id", "status"]),
        ("ix_sales_quote_company_number", ["company_id", "quote_number"]),
    ):
        op.create_index(index, "sales_quote", columns, schema=SCHEMA)


def _create_sales_quote_item() -> None:
    op.create_table(
        "sales_quote_item",
        _pk(),
        _company_id(),
        sa.Column("sales_quote_id", _UUID, nullable=False),
        sa.Column("product_id", _UUID, nullable=False),
        sa.Column("description", sa.Text(), nullable=False),
        sa.Column("quantity", sa.Numeric(precision=18, scale=3), nullable=False),
        sa.Column("unit", sa.String(length=16), nullable=False),
        sa.Column("unit_price", sa.Numeric(precision=18, scale=4), nullable=False),
        sa.Column("line_total", sa.Numeric(precision=18, scale=2), nullable=False),
        _created_at(),
        _tenant_fk(
            "fk_sales_quote_item_quote_company",
            ["sales_quote_id", "company_id"],
            "sales_quote",
            ondelete="CASCADE",
        ),
        _tenant_fk(
            "fk_sales_quote_item_product_company",
            ["product_id", "company_id"],
            "product",
            ondelete="RESTRICT",
        ),
        sa.UniqueConstraint(
            "sales_quote_id", "product_id", name="uq_sales_quote_item_quote_id_product_id"
        ),
        sa.CheckConstraint("quantity > 0", name="ck_sales_quote_item_quantity"),
        sa.CheckConstraint("unit_price >= 0", name="ck_sales_quote_item_unit_price"),
        sa.CheckConstraint("line_total >= 0", name="ck_sales_quote_item_line_total"),
        sa.CheckConstraint(f"unit IN ({_UNITS})", name="ck_sales_quote_item_unit"),
        schema=SCHEMA,
        comment="Tenant-scoped sales quote lines (RLS protected).",
    )
    op.create_index(
        "ix_sales_quote_item_company_quote",
        "sales_quote_item",
        ["company_id", "sales_quote_id"],
        schema=SCHEMA,
    )


def _create_sales_quote_revision() -> None:
    op.create_table(
        "sales_quote_revision",
        _pk(),
        _company_id(),
        sa.Column("sales_quote_id", _UUID, nullable=False),
        sa.Column("revision", sa.Integer(), nullable=False),
        sa.Column("snapshot", _JSONB, nullable=False),
        sa.Column("reason", sa.Text(), nullable=True),
        _actor_fk("actor_id", "fk_sales_quote_revision_actor_app_user", nullable=False),
        _created_at(),
        _tenant_fk(
            "fk_sales_quote_revision_quote_company",
            ["sales_quote_id", "company_id"],
            "sales_quote",
            ondelete="CASCADE",
        ),
        sa.UniqueConstraint(
            "sales_quote_id", "revision", name="uq_sales_quote_revision_quote_revision"
        ),
        sa.CheckConstraint("revision >= 1", name="ck_sales_quote_revision_no"),
        sa.CheckConstraint(
            "jsonb_typeof(snapshot) = 'object'", name="ck_sales_quote_revision_snapshot"
        ),
        schema=SCHEMA,
        comment="Append-only sales quote revisions (RLS protected).",
    )
    op.create_index(
        "ix_sales_quote_revision_company_quote",
        "sales_quote_revision",
        ["company_id", "sales_quote_id"],
        schema=SCHEMA,
    )


def _apply_tenant_rls() -> None:
    """Company-scoped policies for every sourcing table (fail closed)."""
    for table in _SOURCING_TABLES:
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
        + ", ".join(f"{schema}.{table}" for table in _SOURCING_TABLES)
        + f" TO {role}"
    )
    # Revision history is append-only for the runtime role: no UPDATE, no DELETE.
    op.execute(
        f"REVOKE UPDATE, DELETE ON "
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


def _set_audit_actions(actions: str) -> None:
    op.drop_constraint("ck_audit_action", "audit_record", schema=SCHEMA, type_="check")
    op.create_check_constraint(
        "ck_audit_action", "audit_record", f"action IN ({actions})", schema=SCHEMA
    )


def upgrade() -> None:
    _create_fx_rate_snapshot()
    _create_supplier_rfq()
    _create_supplier_rfq_item()
    _create_supplier_rfq_revision()
    _create_supplier_quote()
    _create_supplier_quote_item()
    _create_supplier_quote_revision()
    _create_pricing_scenario()
    _create_pricing_cost_component()
    _create_sales_quote()
    _create_sales_quote_item()
    _create_sales_quote_revision()
    _apply_tenant_rls()
    _apply_grants()
    _set_audit_actions(f"{_STAGE_1A_ACTIONS}, {_STAGE_1B_ACTIONS}, {_STAGE_3_ACTIONS}")


def downgrade() -> None:
    _set_audit_actions(f"{_STAGE_1A_ACTIONS}, {_STAGE_1B_ACTIONS}")
    for table in reversed(_SOURCING_TABLES):
        op.drop_table(table, schema=SCHEMA)

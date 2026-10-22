"""stage 1b trade: counterparties, products, deals, lines, transition history

Creates the first business tables of TOUCHE COMMERCE:

* ``counterparty``  — customers/suppliers, tenant scoped
* ``product``       — catalogue with SKU, unit, currency and unit price
* ``deal``          — trade deal header with a versioned status
* ``deal_item``     — product lines, linked through composite FKs
* ``deal_transition`` — append-only status history (no UPDATE/DELETE grant)

Every table is protected by row level security driven by the transaction-scoped
``touche.company_id`` setting, following the Stage 1A pattern.  The migration also
widens the audit action constraint and adds ``endpoint`` to
``idempotency_record`` so a replayed request is scoped exactly as ADR-012
specifies.

Revision ID: 0003_trade
Revises: 0002_identity
Create Date: 2026-10-22
"""

from __future__ import annotations

import os
from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision: str = "0003_trade"
down_revision: str | None = "0002_identity"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

SCHEMA = "touche"
_APP_ROLE_ENV = "TOUCHE_DB_APP_USER"
_DEFAULT_APP_ROLE = "touche_app"
_UUID = postgresql.UUID(as_uuid=True)
_TS = sa.DateTime(timezone=True)
_JSONB = postgresql.JSONB(astext_type=sa.Text())

_TRADE_TABLES = ("counterparty", "product", "deal", "deal_item", "deal_transition")
_DEAL_STATUSES = "'DRAFT', 'OPEN', 'NEGOTIATION', 'WON', 'LOST', 'CANCELLED'"
_RECORD_STATUSES = "'active', 'archived'"

_STAGE_1A_ACTIONS = (
    "'auth.login.success', 'auth.login.failure', 'auth.logout', "
    "'session.company.switch', 'session.revoked', 'membership.changed', "
    "'access.denied', 'identity.bootstrap'"
)
_TRADE_ACTIONS = (
    "'counterparty.created', 'counterparty.updated', 'product.created', "
    "'product.updated', 'deal.created', 'deal.updated', 'deal.transitioned'"
)


def _quote(value: str) -> str:
    return postgresql.dialect().identifier_preparer.quote(value)


def _app_role() -> str:
    role = os.environ.get(_APP_ROLE_ENV, _DEFAULT_APP_ROLE).strip()
    if not role:
        raise RuntimeError(f"{_APP_ROLE_ENV} must not be empty")
    return _quote(role)


def _pk() -> sa.Column:
    return sa.Column("id", _UUID, primary_key=True, server_default=sa.text("gen_random_uuid()"))


def _created_at() -> sa.Column:
    return sa.Column("created_at", _TS, nullable=False, server_default=sa.text("now()"))


def _updated_at() -> sa.Column:
    return sa.Column("updated_at", _TS, nullable=False, server_default=sa.text("now()"))


def _company_id() -> sa.Column:
    return sa.Column("company_id", _UUID, nullable=False)


def _version() -> sa.Column:
    return sa.Column("version", sa.Integer(), nullable=False, server_default=sa.text("1"))



def _create_counterparty() -> None:
    op.create_table(
        "counterparty",
        _pk(),
        _company_id(),
        sa.Column("name", sa.Text(), nullable=False),
        sa.Column("type", sa.String(length=16), nullable=False, server_default=sa.text("'buyer'")),
        sa.Column("country", sa.String(length=2), nullable=True),
        sa.Column("contact_name", sa.Text(), nullable=True),
        sa.Column("email", sa.Text(), nullable=True),
        sa.Column("phone", sa.String(length=40), nullable=True),
        sa.Column("notes", sa.Text(), nullable=True),
        sa.Column(
            "status", sa.String(length=16), nullable=False, server_default=sa.text("'active'")
        ),
        _version(),
        _created_at(),
        _updated_at(),
        sa.ForeignKeyConstraint(
            ["company_id"],
            [f"{SCHEMA}.company.id"],
            name="fk_counterparty_company_id_company",
            ondelete="CASCADE",
        ),
        sa.CheckConstraint("name = btrim(name)", name="ck_counterparty_name_trimmed"),
        sa.CheckConstraint("char_length(name) BETWEEN 1 AND 160", name="ck_counterparty_name_length"),
        sa.CheckConstraint(
            "type IN ('buyer', 'supplier', 'both')", name="ck_counterparty_type"
        ),
        sa.CheckConstraint(f"status IN ({_RECORD_STATUSES})", name="ck_counterparty_status"),
        sa.CheckConstraint(
            "country IS NULL OR country ~ '^[A-Z]{2}$'", name="ck_counterparty_country_iso"
        ),
        sa.CheckConstraint(
            "contact_name IS NULL OR char_length(contact_name) BETWEEN 1 AND 120",
            name="ck_counterparty_contact_name",
        ),
        sa.CheckConstraint(
            "email IS NULL OR (email = lower(email) AND char_length(email) BETWEEN 3 AND 320)",
            name="ck_counterparty_email",
        ),
        sa.CheckConstraint(
            "notes IS NULL OR char_length(notes) <= 2000", name="ck_counterparty_notes"
        ),
        sa.CheckConstraint("version >= 1", name="ck_counterparty_version"),
        sa.UniqueConstraint("company_id", "name", name="uq_counterparty_company_id_name"),
        sa.UniqueConstraint("id", "company_id", name="uq_counterparty_id_company_id"),
        schema=SCHEMA,
        comment="Tenant-scoped customers and suppliers (RLS protected).",
    )
    op.create_index(
        "ix_counterparty_company_status", "counterparty", ["company_id", "status"], schema=SCHEMA
    )
    op.create_index(
        "ix_counterparty_company_created_at",
        "counterparty",
        ["company_id", "created_at"],
        schema=SCHEMA,
    )


def _create_product() -> None:
    op.create_table(
        "product",
        _pk(),
        _company_id(),
        sa.Column("sku", sa.String(length=40), nullable=False),
        sa.Column("name", sa.Text(), nullable=False),
        sa.Column("unit", sa.String(length=16), nullable=False),
        sa.Column("currency", sa.String(length=3), nullable=False),
        sa.Column("unit_price", sa.Numeric(18, 4), nullable=False),
        sa.Column(
            "status", sa.String(length=16), nullable=False, server_default=sa.text("'active'")
        ),
        _version(),
        _created_at(),
        _updated_at(),
        sa.ForeignKeyConstraint(
            ["company_id"],
            [f"{SCHEMA}.company.id"],
            name="fk_product_company_id_company",
            ondelete="CASCADE",
        ),
        sa.CheckConstraint("sku = upper(sku)", name="ck_product_sku_upper"),
        sa.CheckConstraint("char_length(sku) BETWEEN 1 AND 40", name="ck_product_sku_length"),
        sa.CheckConstraint("char_length(name) BETWEEN 1 AND 160", name="ck_product_name_length"),
        sa.CheckConstraint(
            "unit IN ('kg', 'mt', 'lb', 'unit', 'l', 'm3')", name="ck_product_unit"
        ),
        sa.CheckConstraint("currency ~ '^[A-Z]{3}$'", name="ck_product_currency_iso"),
        sa.CheckConstraint("unit_price >= 0", name="ck_product_unit_price"),
        sa.CheckConstraint(f"status IN ({_RECORD_STATUSES})", name="ck_product_status"),
        sa.CheckConstraint("version >= 1", name="ck_product_version"),
        sa.UniqueConstraint("company_id", "sku", name="uq_product_company_id_sku"),
        sa.UniqueConstraint("id", "company_id", name="uq_product_id_company_id"),
        schema=SCHEMA,
        comment="Tenant-scoped product catalogue (RLS protected).",
    )
    op.create_index("ix_product_company_status", "product", ["company_id", "status"], schema=SCHEMA)
    op.create_index(
        "ix_product_company_created_at", "product", ["company_id", "created_at"], schema=SCHEMA
    )


def _create_deal() -> None:
    op.create_table(
        "deal",
        _pk(),
        _company_id(),
        sa.Column("reference", sa.String(length=32), nullable=False),
        sa.Column("title", sa.Text(), nullable=False),
        sa.Column(
            "status", sa.String(length=16), nullable=False, server_default=sa.text("'DRAFT'")
        ),
        sa.Column("counterparty_id", _UUID, nullable=False),
        sa.Column("currency", sa.String(length=3), nullable=False),
        sa.Column("expected_close_date", sa.Date(), nullable=True),
        sa.Column("notes", sa.Text(), nullable=True),
        _version(),
        sa.Column("created_by", _UUID, nullable=False),
        sa.Column("closed_at", _TS, nullable=True),
        _created_at(),
        _updated_at(),
        sa.ForeignKeyConstraint(
            ["company_id"],
            [f"{SCHEMA}.company.id"],
            name="fk_deal_company_id_company",
            ondelete="CASCADE",
        ),
        sa.ForeignKeyConstraint(
            ["created_by"],
            [f"{SCHEMA}.app_user.id"],
            name="fk_deal_created_by_app_user",
            ondelete="RESTRICT",
        ),
        # Composite FK: a deal can only reference a counterparty of its own tenant.
        sa.ForeignKeyConstraint(
            ["counterparty_id", "company_id"],
            [f"{SCHEMA}.counterparty.id", f"{SCHEMA}.counterparty.company_id"],
            name="fk_deal_counterparty_company",
            ondelete="RESTRICT",
        ),
        sa.CheckConstraint("reference = upper(reference)", name="ck_deal_reference_upper"),
        sa.CheckConstraint(
            "char_length(reference) BETWEEN 3 AND 32", name="ck_deal_reference_length"
        ),
        sa.CheckConstraint("char_length(title) BETWEEN 1 AND 160", name="ck_deal_title_length"),
        sa.CheckConstraint(f"status IN ({_DEAL_STATUSES})", name="ck_deal_status"),
        sa.CheckConstraint("currency ~ '^[A-Z]{3}$'", name="ck_deal_currency_iso"),
        sa.CheckConstraint(
            "notes IS NULL OR char_length(notes) <= 2000", name="ck_deal_notes_length"
        ),
        sa.CheckConstraint("version >= 1", name="ck_deal_version"),
        sa.CheckConstraint(
            "(status IN ('WON', 'LOST', 'CANCELLED')) = (closed_at IS NOT NULL)",
            name="ck_deal_closed_at",
        ),
        sa.UniqueConstraint("company_id", "reference", name="uq_deal_company_id_reference"),
        sa.UniqueConstraint("id", "company_id", name="uq_deal_id_company_id"),
        schema=SCHEMA,
        comment="Tenant-scoped trade deals (RLS protected).",
    )
    op.create_index("ix_deal_company_status", "deal", ["company_id", "status"], schema=SCHEMA)
    op.create_index(
        "ix_deal_company_created_at", "deal", ["company_id", "created_at"], schema=SCHEMA
    )
    op.create_index(
        "ix_deal_company_counterparty",
        "deal",
        ["company_id", "counterparty_id"],
        schema=SCHEMA,
    )



def _create_deal_item() -> None:
    op.create_table(
        "deal_item",
        _pk(),
        _company_id(),
        sa.Column("deal_id", _UUID, nullable=False),
        sa.Column("product_id", _UUID, nullable=False),
        sa.Column("quantity", sa.Numeric(18, 3), nullable=False),
        sa.Column("unit_price", sa.Numeric(18, 4), nullable=False),
        _created_at(),
        sa.ForeignKeyConstraint(
            ["deal_id", "company_id"],
            [f"{SCHEMA}.deal.id", f"{SCHEMA}.deal.company_id"],
            name="fk_deal_item_deal_company",
            ondelete="CASCADE",
        ),
        sa.ForeignKeyConstraint(
            ["product_id", "company_id"],
            [f"{SCHEMA}.product.id", f"{SCHEMA}.product.company_id"],
            name="fk_deal_item_product_company",
            ondelete="RESTRICT",
        ),
        sa.CheckConstraint("quantity > 0", name="ck_deal_item_quantity"),
        sa.CheckConstraint("unit_price >= 0", name="ck_deal_item_unit_price"),
        sa.UniqueConstraint("deal_id", "product_id", name="uq_deal_item_deal_id_product_id"),
        schema=SCHEMA,
        comment="Tenant-scoped deal lines (RLS protected).",
    )
    op.create_index(
        "ix_deal_item_company_deal", "deal_item", ["company_id", "deal_id"], schema=SCHEMA
    )


def _create_deal_transition() -> None:
    op.create_table(
        "deal_transition",
        _pk(),
        _company_id(),
        sa.Column("deal_id", _UUID, nullable=False),
        sa.Column("from_status", sa.String(length=16), nullable=True),
        sa.Column("to_status", sa.String(length=16), nullable=False),
        sa.Column("reason", sa.Text(), nullable=True),
        sa.Column("actor_id", _UUID, nullable=False),
        sa.Column("request_id", sa.String(length=128), nullable=True),
        sa.Column("version_after", sa.Integer(), nullable=False),
        sa.Column("occurred_at", _TS, nullable=False, server_default=sa.text("now()")),
        sa.ForeignKeyConstraint(
            ["deal_id", "company_id"],
            [f"{SCHEMA}.deal.id", f"{SCHEMA}.deal.company_id"],
            name="fk_deal_transition_deal_company",
            ondelete="CASCADE",
        ),
        sa.ForeignKeyConstraint(
            ["actor_id"],
            [f"{SCHEMA}.app_user.id"],
            name="fk_deal_transition_actor_app_user",
        ),
        sa.CheckConstraint(f"to_status IN ({_DEAL_STATUSES})", name="ck_deal_transition_to_status"),
        sa.CheckConstraint(
            f"from_status IS NULL OR from_status IN ({_DEAL_STATUSES})",
            name="ck_deal_transition_from_status",
        ),
        sa.CheckConstraint(
            "reason IS NULL OR char_length(btrim(reason)) BETWEEN 3 AND 500",
            name="ck_deal_transition_reason",
        ),
        sa.CheckConstraint(
            "to_status NOT IN ('LOST', 'CANCELLED') OR reason IS NOT NULL",
            name="ck_deal_transition_terminal_reason",
        ),
        sa.CheckConstraint("version_after >= 1", name="ck_deal_transition_version"),
        schema=SCHEMA,
        comment="Immutable deal status history (RLS protected).",
    )
    op.create_index(
        "ix_deal_transition_company_deal",
        "deal_transition",
        ["company_id", "deal_id", "occurred_at"],
        schema=SCHEMA,
    )


def _apply_tenant_rls() -> None:
    """Company-scoped policies for every trade table (fail closed)."""
    for table in _TRADE_TABLES:
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
        + ", ".join(f"{schema}.{table}" for table in _TRADE_TABLES)
        + f" TO {role}"
    )
    # Deal history is append-only for the runtime role: no UPDATE, no DELETE.
    op.execute(f"REVOKE UPDATE, DELETE ON {schema}.deal_transition FROM {role}")


def _widen_audit_actions() -> None:
    op.drop_constraint("ck_audit_action", "audit_record", schema=SCHEMA, type_="check")
    op.create_check_constraint(
        "ck_audit_action",
        "audit_record",
        f"action IN ({_STAGE_1A_ACTIONS}, {_TRADE_ACTIONS})",
        schema=SCHEMA,
    )


def _restore_audit_actions() -> None:
    op.drop_constraint("ck_audit_action", "audit_record", schema=SCHEMA, type_="check")
    op.create_check_constraint(
        "ck_audit_action",
        "audit_record",
        f"action IN ({_STAGE_1A_ACTIONS})",
        schema=SCHEMA,
    )


def _extend_idempotency_scope() -> None:
    """Add the endpoint to the idempotency identity (ADR-012)."""
    op.add_column(
        "idempotency_record",
        sa.Column(
            "endpoint", sa.String(length=160), nullable=False, server_default=sa.text("''")
        ),
        schema=SCHEMA,
    )
    op.alter_column("idempotency_record", "endpoint", server_default=None, schema=SCHEMA)
    op.drop_constraint(
        "uq_idempotency_record_actor_company_key",
        "idempotency_record",
        schema=SCHEMA,
        type_="unique",
    )
    op.create_unique_constraint(
        "uq_idempotency_record_actor_company_endpoint_key",
        "idempotency_record",
        ["actor_id", "company_id", "endpoint", "key"],
        schema=SCHEMA,
    )
    op.create_check_constraint(
        "ck_idempotency_endpoint_length",
        "idempotency_record",
        "char_length(endpoint) BETWEEN 1 AND 160",
        schema=SCHEMA,
    )


def upgrade() -> None:
    _create_counterparty()
    _create_product()
    _create_deal()
    _create_deal_item()
    _create_deal_transition()
    _apply_tenant_rls()
    _apply_grants()
    _widen_audit_actions()
    _extend_idempotency_scope()


def downgrade() -> None:
    op.drop_constraint(
        "ck_idempotency_endpoint_length",
        "idempotency_record",
        schema=SCHEMA,
        type_="check",
    )
    op.drop_constraint(
        "uq_idempotency_record_actor_company_endpoint_key",
        "idempotency_record",
        schema=SCHEMA,
        type_="unique",
    )
    op.create_unique_constraint(
        "uq_idempotency_record_actor_company_key",
        "idempotency_record",
        ["actor_id", "company_id", "key"],
        schema=SCHEMA,
    )
    op.drop_column("idempotency_record", "endpoint", schema=SCHEMA)
    _restore_audit_actions()
    for table in reversed(_TRADE_TABLES):
        op.drop_table(table, schema=SCHEMA)


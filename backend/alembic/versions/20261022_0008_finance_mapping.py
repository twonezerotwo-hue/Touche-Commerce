"""Stage 5C: explicit tenant-scoped Commerce → Finance company mapping.

Creates ``touche.finance_company_mapping``. The runtime role receives ``SELECT``
only; configuration is performed by an authorised operator through the
privileged CLI (migration role) and recorded in the audit trail. Row level
security uses the same transaction-scoped ``touche.company_id`` predicate as
every other tenant table, so a runtime bug cannot read another company's map.

The audit-action CHECK is widened with the three Stage 5C actions. Existing audit
rows are untouched.

Revision ID: 0008_finance_mapping
Revises: 0007_purchase_order_dispatch
Create Date: 2026-10-22
"""

from __future__ import annotations

import os
from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision: str = "0008_finance_mapping"
down_revision: str | None = "0007_purchase_order_dispatch"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

SCHEMA = "touche"
_APP_ROLE_ENV = "TOUCHE_DB_APP_USER"
_DEFAULT_APP_ROLE = "touche_app"

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
_STAGE_5C_ACTIONS = (
    "'finance.mapping.configured', 'finance.mapping.disabled', 'finance.read'"
)
_PREVIOUS_ACTIONS = (
    f"{_STAGE_1A_ACTIONS}, {_STAGE_1B_ACTIONS}, {_STAGE_3_ACTIONS}, {_STAGE_4_ACTIONS}"
)
_ALL_ACTIONS = f"{_PREVIOUS_ACTIONS}, {_STAGE_5C_ACTIONS}"


def _quote(value: str) -> str:
    return postgresql.dialect().identifier_preparer.quote(value)


def _app_role() -> str:
    role = os.environ.get(_APP_ROLE_ENV, _DEFAULT_APP_ROLE).strip()
    if not role:
        raise RuntimeError(f"{_APP_ROLE_ENV} must not be empty")
    return _quote(role)



def _create_mapping() -> None:
    op.create_table(
        "finance_company_mapping",
        sa.Column(
            "id",
            postgresql.UUID(as_uuid=True),
            primary_key=True,
            server_default=sa.text("gen_random_uuid()"),
        ),
        sa.Column("company_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("finance_company_id", sa.String(length=64), nullable=False),
        sa.Column("finance_company_name", sa.Text(), nullable=True),
        sa.Column(
            "status", sa.String(length=16), nullable=False, server_default=sa.text("'pending'")
        ),
        sa.Column(
            "source", sa.String(length=32), nullable=False, server_default=sa.text("'manual_cli'")
        ),
        sa.Column("configured_by", postgresql.UUID(as_uuid=True), nullable=True),
        sa.Column(
            "configured_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.text("now()"),
        ),
        sa.Column("last_verified_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("last_verification_error", sa.Text(), nullable=True),
        sa.Column(
            "verification_details",
            postgresql.JSONB(astext_type=sa.Text()),
            nullable=False,
            server_default=sa.text("'{}'::jsonb"),
        ),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.text("now()"),
        ),
        sa.Column(
            "updated_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.text("now()"),
        ),
        sa.ForeignKeyConstraint(
            ["company_id"],
            [f"{SCHEMA}.company.id"],
            name="fk_finance_company_mapping_company_id_company",
            ondelete="CASCADE",
        ),
        sa.ForeignKeyConstraint(
            ["configured_by"],
            [f"{SCHEMA}.app_user.id"],
            name="fk_finance_company_mapping_configured_by_app_user",
            ondelete="SET NULL",
        ),
        sa.UniqueConstraint("company_id", name="uq_finance_company_mapping_company_id"),
        sa.CheckConstraint(
            "finance_company_id ~ '^[a-z][a-z0-9_]{1,63}$'",
            name="ck_finance_company_mapping_finance_id",
        ),
        sa.CheckConstraint(
            "status IN ('pending', 'verified', 'disabled', 'invalid')",
            name="ck_finance_company_mapping_status",
        ),
        sa.CheckConstraint(
            "source IN ('manual_cli')", name="ck_finance_company_mapping_source"
        ),
        sa.CheckConstraint(
            "last_verification_error IS NULL OR char_length(last_verification_error) <= 512",
            name="ck_finance_company_mapping_verification_error_length",
        ),
        sa.CheckConstraint(
            "jsonb_typeof(verification_details) = 'object'",
            name="ck_finance_company_mapping_details_object",
        ),
        schema=SCHEMA,
        comment="Explicit tenant-scoped Commerce → Finance company mapping (RLS protected).",
    )
    op.create_index(
        "ix_finance_company_mapping_status",
        "finance_company_mapping",
        ["status"],
        schema=SCHEMA,
    )


def _apply_rls() -> None:
    qualified = f"{SCHEMA}.finance_company_mapping"
    predicate = f"company_id = {SCHEMA}.current_company_id()"
    op.execute(f"ALTER TABLE {qualified} ENABLE ROW LEVEL SECURITY")
    op.execute(
        f"CREATE POLICY finance_company_mapping_tenant_select ON {qualified} "
        f"FOR SELECT USING ({predicate})"
    )
    op.execute(
        f"CREATE POLICY finance_company_mapping_tenant_insert ON {qualified} "
        f"FOR INSERT WITH CHECK ({predicate})"
    )
    op.execute(
        f"CREATE POLICY finance_company_mapping_tenant_update ON {qualified} "
        f"FOR UPDATE USING ({predicate}) WITH CHECK ({predicate})"
    )
    op.execute(
        f"CREATE POLICY finance_company_mapping_tenant_delete ON {qualified} "
        f"FOR DELETE USING ({predicate})"
    )


def _grant_read_only() -> None:
    role = _app_role()
    op.execute(f"GRANT SELECT ON {_quote(SCHEMA)}.finance_company_mapping TO {role}")


def _set_audit_actions(actions: str) -> None:
    op.drop_constraint("ck_audit_action", "audit_record", schema=SCHEMA, type_="check")
    op.create_check_constraint(
        "ck_audit_action", "audit_record", f"action IN ({actions})", schema=SCHEMA
    )


def upgrade() -> None:
    _create_mapping()
    _apply_rls()
    _grant_read_only()
    _set_audit_actions(_ALL_ACTIONS)


def downgrade() -> None:
    _set_audit_actions(_PREVIOUS_ACTIONS)
    op.drop_index(
        "ix_finance_company_mapping_status",
        table_name="finance_company_mapping",
        schema=SCHEMA,
    )
    op.drop_table("finance_company_mapping", schema=SCHEMA)

"""Stage 13: company profile (document details) and document audit actions.

Creates ``touche.company_profile`` (one optional row per company; RLS on every statement;
runtime SELECT/INSERT/UPDATE only) and extends the audit action CHECK with
``company_profile.updated`` and ``document.generated``.

Revision ID: 0014_company_profile
Revises: 0013_import_batch
Create Date: 2026-10-24
"""

from __future__ import annotations

import os
from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision: str = "0014_company_profile"
down_revision: str | None = "0013_import_batch"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

SCHEMA = "touche"
_APP_ROLE_ENV = "TOUCHE_DB_APP_USER"
_DEFAULT_APP_ROLE = "touche_app"
_UUID = postgresql.UUID(as_uuid=True)

_PREVIOUS_ACTIONS = "'auth.login.success', 'auth.login.failure', 'auth.logout', 'session.company.switch', 'session.revoked', 'membership.changed', 'access.denied', 'identity.bootstrap', 'counterparty.created', 'counterparty.updated', 'product.created', 'product.updated', 'deal.created', 'deal.updated', 'deal.transitioned', 'rfq.created', 'rfq.updated', 'rfq.prepared', 'rfq.sent', 'rfq.cancelled', 'rfq.closed', 'supplier_quote.recorded', 'supplier_quote.revised', 'supplier_quote.withdrawn', 'fx_rate.recorded', 'pricing_scenario.created', 'pricing_scenario.updated', 'sales_quote.created', 'sales_quote.submitted', 'sales_quote.approved', 'sales_quote.rejected', 'sales_quote.withdrawn', 'deal.won', 'customer_acceptance.recorded', 'sales_order.created', 'sales_order.transitioned', 'sales_order.amended', 'purchase_order.created', 'purchase_order.transitioned', 'shipment.created', 'shipment.updated', 'shipment.transitioned', 'shipment.cost_recorded', 'document.uploaded', 'document.downloaded', 'document.archived', 'document.verified', 'finance.mapping.configured', 'finance.mapping.disabled', 'finance.read', 'finance.reconciliation_run.created', 'finance.evidence.linked', 'finance.discrepancy.resolved', 'finance.reconciliation.reviewed', 'ai.conversation.created', 'ai.run.completed', 'ai.run.failed', 'ai.run.cancelled', 'ai.tool.executed', 'ai.tool.denied', 'ai.action.blocked', 'ai.proposal.created', 'ai.proposal.edited', 'ai.proposal.approved', 'ai.proposal.rejected', 'communications.suppression.recorded', 'import.committed'"
_ALL_ACTIONS = f"{_PREVIOUS_ACTIONS}, 'company_profile.updated', 'document.generated'"

_TEXT_LIMITS = {
    "legal_name": 200,
    "tax_office": 120,
    "tax_number": 40,
    "city": 120,
    "postal_code": 20,
    "phone": 40,
    "email": 254,
    "website": 200,
    "bank_name": 120,
    "iban": 40,
    "swift_bic": 11,
}


def _quote(value: str) -> str:
    return postgresql.dialect().identifier_preparer.quote(value)


def _app_role() -> str:
    role = os.environ.get(_APP_ROLE_ENV, _DEFAULT_APP_ROLE).strip()
    if not role:
        raise RuntimeError(f"{_APP_ROLE_ENV} must not be empty")
    return _quote(role)


def _set_audit_actions(actions: str) -> None:
    op.drop_constraint("ck_audit_action", "audit_record", schema=SCHEMA, type_="check")
    op.create_check_constraint(
        "ck_audit_action", "audit_record", f"action IN ({actions})", schema=SCHEMA
    )


def upgrade() -> None:
    columns = [
        sa.Column("company_id", _UUID, primary_key=True),
        sa.Column("legal_name", sa.String(200)),
        sa.Column("tax_office", sa.String(120)),
        sa.Column("tax_number", sa.String(40)),
        sa.Column("address", sa.Text()),
        sa.Column("city", sa.String(120)),
        sa.Column("postal_code", sa.String(20)),
        sa.Column("phone", sa.String(40)),
        sa.Column("email", sa.String(254)),
        sa.Column("website", sa.String(200)),
        sa.Column("bank_name", sa.String(120)),
        sa.Column("iban", sa.String(40)),
        sa.Column("swift_bic", sa.String(11)),
        sa.Column("version", sa.Integer(), nullable=False, server_default="1"),
        sa.Column("updated_by", _UUID, nullable=False),
        sa.Column(
            "updated_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.text("now()"),
        ),
    ]
    constraints: list[sa.schema.SchemaItem] = [
        sa.ForeignKeyConstraint(
            ["company_id"], [f"{SCHEMA}.company.id"], name="fk_company_profile_company_id_company"
        ),
        sa.ForeignKeyConstraint(
            ["updated_by"], [f"{SCHEMA}.app_user.id"], name="fk_company_profile_updated_by_app_user"
        ),
        sa.CheckConstraint("version >= 1", name="ck_company_profile_version"),
        sa.CheckConstraint(
            "address IS NULL OR char_length(btrim(address)) BETWEEN 1 AND 400",
            name="ck_company_profile_address",
        ),
    ]
    for name, limit in _TEXT_LIMITS.items():
        constraints.append(
            sa.CheckConstraint(
                f"{name} IS NULL OR char_length(btrim({name})) BETWEEN 1 AND {limit}",
                name=f"ck_company_profile_{name}",
            )
        )
    op.create_table(
        "company_profile",
        *columns,
        *constraints,
        schema=SCHEMA,
        comment="Optional legal details printed on trade documents.",
    )

    predicate = f"company_id = {SCHEMA}.current_company_id()"
    qualified = f"{SCHEMA}.company_profile"
    op.execute(f"ALTER TABLE {qualified} ENABLE ROW LEVEL SECURITY")
    for verb, clause in (
        ("SELECT", f"USING ({predicate})"),
        ("INSERT", f"WITH CHECK ({predicate})"),
        ("UPDATE", f"USING ({predicate}) WITH CHECK ({predicate})"),
    ):
        op.execute(
            f"CREATE POLICY company_profile_tenant_{verb.lower()} ON {qualified} "
            f"FOR {verb} {clause}"
        )
    role = _app_role()
    op.execute(f"REVOKE ALL ON {qualified} FROM {role}")
    op.execute(f"GRANT SELECT, INSERT, UPDATE ON {qualified} TO {role}")
    _set_audit_actions(_ALL_ACTIONS)


def downgrade() -> None:
    op.execute(
        f"DO $$ BEGIN IF EXISTS (SELECT 1 FROM {SCHEMA}.audit_record WHERE action IN "
        "('company_profile.updated', 'document.generated')) "
        "THEN RAISE EXCEPTION 'profile/document audit rows exist; the audit trail is append-only.'; "
        "END IF; END $$"
    )
    _set_audit_actions(_PREVIOUS_ACTIONS)
    op.drop_table("company_profile", schema=SCHEMA)

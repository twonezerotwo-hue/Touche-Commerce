"""Stage 13C: durable ledger of web CSV/XLSX imports.

Creates ``touche.import_batch`` (company scoped, RLS, composite uniqueness on the file
hash so the same file can never be imported twice into one company) and extends the audit
action CHECK with ``import.committed``. Runtime grants are SELECT and INSERT only: a
batch row is evidence and is never updated or deleted by the application.

Revision ID: 0013_import_batch
Revises: 0012_ai_monthly_reservation
Create Date: 2026-10-24
"""

from __future__ import annotations

import os
from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision: str = "0013_import_batch"
down_revision: str | None = "0012_ai_monthly_reservation"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

SCHEMA = "touche"
_APP_ROLE_ENV = "TOUCHE_DB_APP_USER"
_DEFAULT_APP_ROLE = "touche_app"
_UUID = postgresql.UUID(as_uuid=True)

_PREVIOUS_ACTIONS = "'auth.login.success', 'auth.login.failure', 'auth.logout', 'session.company.switch', 'session.revoked', 'membership.changed', 'access.denied', 'identity.bootstrap', 'counterparty.created', 'counterparty.updated', 'product.created', 'product.updated', 'deal.created', 'deal.updated', 'deal.transitioned', 'rfq.created', 'rfq.updated', 'rfq.prepared', 'rfq.sent', 'rfq.cancelled', 'rfq.closed', 'supplier_quote.recorded', 'supplier_quote.revised', 'supplier_quote.withdrawn', 'fx_rate.recorded', 'pricing_scenario.created', 'pricing_scenario.updated', 'sales_quote.created', 'sales_quote.submitted', 'sales_quote.approved', 'sales_quote.rejected', 'sales_quote.withdrawn', 'deal.won', 'customer_acceptance.recorded', 'sales_order.created', 'sales_order.transitioned', 'sales_order.amended', 'purchase_order.created', 'purchase_order.transitioned', 'shipment.created', 'shipment.updated', 'shipment.transitioned', 'shipment.cost_recorded', 'document.uploaded', 'document.downloaded', 'document.archived', 'document.verified', 'finance.mapping.configured', 'finance.mapping.disabled', 'finance.read', 'finance.reconciliation_run.created', 'finance.evidence.linked', 'finance.discrepancy.resolved', 'finance.reconciliation.reviewed', 'ai.conversation.created', 'ai.run.completed', 'ai.run.failed', 'ai.run.cancelled', 'ai.tool.executed', 'ai.tool.denied', 'ai.action.blocked', 'ai.proposal.created', 'ai.proposal.edited', 'ai.proposal.approved', 'ai.proposal.rejected', 'communications.suppression.recorded'"
_ALL_ACTIONS = f"{_PREVIOUS_ACTIONS}, 'import.committed'"


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
    op.create_table(
        "import_batch",
        sa.Column("id", _UUID, primary_key=True, server_default=sa.text("gen_random_uuid()")),
        sa.Column("company_id", _UUID, nullable=False),
        sa.Column("kind", sa.String(16), nullable=False),
        sa.Column("source_sha256", sa.String(64), nullable=False),
        sa.Column("filename", sa.String(120), nullable=False),
        sa.Column("total_rows", sa.Integer(), nullable=False),
        sa.Column("created_rows", sa.Integer(), nullable=False),
        sa.Column("skipped_rows", sa.Integer(), nullable=False),
        sa.Column("created_by", _UUID, nullable=False),
        sa.Column(
            "created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.text("now()")
        ),
        sa.ForeignKeyConstraint(
            ["company_id"], [f"{SCHEMA}.company.id"], name="fk_import_batch_company_id_company"
        ),
        sa.ForeignKeyConstraint(
            ["created_by"], [f"{SCHEMA}.app_user.id"], name="fk_import_batch_created_by_app_user"
        ),
        sa.UniqueConstraint(
            "company_id", "kind", "source_sha256", name="uq_import_batch_company_kind_hash"
        ),
        sa.CheckConstraint("kind IN ('products', 'counterparties')", name="ck_import_batch_kind"),
        sa.CheckConstraint("source_sha256 ~ '^[0-9a-f]{64}$'", name="ck_import_batch_hash"),
        sa.CheckConstraint(
            "total_rows >= 1 AND created_rows >= 0 AND skipped_rows >= 0 "
            "AND created_rows + skipped_rows = total_rows",
            name="ck_import_batch_counts",
        ),
        sa.CheckConstraint(
            "char_length(btrim(filename)) BETWEEN 1 AND 120", name="ck_import_batch_filename"
        ),
        schema=SCHEMA,
        comment="Committed CSV/XLSX imports, append-only (RLS protected).",
    )
    op.create_index(
        "ix_import_batch_company_created",
        "import_batch",
        ["company_id", "created_at"],
        schema=SCHEMA,
    )

    predicate = f"company_id = {SCHEMA}.current_company_id()"
    qualified = f"{SCHEMA}.import_batch"
    op.execute(f"ALTER TABLE {qualified} ENABLE ROW LEVEL SECURITY")
    op.execute(f"CREATE POLICY import_batch_tenant_select ON {qualified} FOR SELECT USING ({predicate})")
    op.execute(
        f"CREATE POLICY import_batch_tenant_insert ON {qualified} FOR INSERT WITH CHECK ({predicate})"
    )
    role = _app_role()
    op.execute(f"REVOKE ALL ON {_quote(SCHEMA)}.import_batch FROM {role}")
    op.execute(f"GRANT SELECT, INSERT ON {_quote(SCHEMA)}.import_batch TO {role}")
    _set_audit_actions(_ALL_ACTIONS)


def downgrade() -> None:
    # An audit row written with the new action would violate the previous CHECK; refuse
    # rather than delete an append-only trail.
    op.execute(
        f"DO $$ BEGIN IF EXISTS (SELECT 1 FROM {SCHEMA}.audit_record WHERE action = 'import.committed') "
        "THEN RAISE EXCEPTION 'import.committed audit rows exist; the audit trail is append-only.'; "
        "END IF; END $$"
    )
    _set_audit_actions(_PREVIOUS_ACTIONS)
    op.drop_table("import_batch", schema=SCHEMA)

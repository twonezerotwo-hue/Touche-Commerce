"""Stage 7C2: append-only tenant-scoped communications suppression.

Revision ID: 0011_communication_suppression
Revises: 0010_ai_office
No consent grant, provider credential, delivery queue or outbound send path.
"""

from __future__ import annotations

import os
from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision: str = "0011_communication_suppression"
down_revision: str | None = "0010_ai_office"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

SCHEMA = "touche"
_AUDIT_ACTIONS = ("'auth.login.success', 'auth.login.failure', 'auth.logout', 'session.company.switch', 'session.revoked', 'membership.changed', 'access.denied', 'identity.bootstrap', 'counterparty.created', 'counterparty.updated', 'product.created', 'product.updated', 'deal.created', 'deal.updated', 'deal.transitioned', 'rfq.created', 'rfq.updated', 'rfq.prepared', 'rfq.sent', 'rfq.cancelled', 'rfq.closed', 'supplier_quote.recorded', 'supplier_quote.revised', 'supplier_quote.withdrawn', 'fx_rate.recorded', 'pricing_scenario.created', 'pricing_scenario.updated', 'sales_quote.created', 'sales_quote.submitted', 'sales_quote.approved', 'sales_quote.rejected', 'sales_quote.withdrawn', 'deal.won', 'customer_acceptance.recorded', 'sales_order.created', 'sales_order.transitioned', 'sales_order.amended', 'purchase_order.created', 'purchase_order.transitioned', 'shipment.created', 'shipment.updated', 'shipment.transitioned', 'shipment.cost_recorded', 'document.uploaded', 'document.downloaded', 'document.archived', 'document.verified', 'finance.mapping.configured', 'finance.mapping.disabled', 'finance.read', 'finance.reconciliation_run.created', 'finance.evidence.linked', 'finance.discrepancy.resolved', 'finance.reconciliation.reviewed', 'ai.conversation.created', 'ai.run.completed', 'ai.run.failed', 'ai.run.cancelled', 'ai.tool.executed', 'ai.tool.denied', 'ai.action.blocked', 'ai.proposal.created', 'ai.proposal.edited', 'ai.proposal.approved', 'ai.proposal.rejected', 'communications.suppression.recorded'")
_PREVIOUS_ACTIONS = ("'auth.login.success', 'auth.login.failure', 'auth.logout', 'session.company.switch', 'session.revoked', 'membership.changed', 'access.denied', 'identity.bootstrap', 'counterparty.created', 'counterparty.updated', 'product.created', 'product.updated', 'deal.created', 'deal.updated', 'deal.transitioned', 'rfq.created', 'rfq.updated', 'rfq.prepared', 'rfq.sent', 'rfq.cancelled', 'rfq.closed', 'supplier_quote.recorded', 'supplier_quote.revised', 'supplier_quote.withdrawn', 'fx_rate.recorded', 'pricing_scenario.created', 'pricing_scenario.updated', 'sales_quote.created', 'sales_quote.submitted', 'sales_quote.approved', 'sales_quote.rejected', 'sales_quote.withdrawn', 'deal.won', 'customer_acceptance.recorded', 'sales_order.created', 'sales_order.transitioned', 'sales_order.amended', 'purchase_order.created', 'purchase_order.transitioned', 'shipment.created', 'shipment.updated', 'shipment.transitioned', 'shipment.cost_recorded', 'document.uploaded', 'document.downloaded', 'document.archived', 'document.verified', 'finance.mapping.configured', 'finance.mapping.disabled', 'finance.read', 'finance.reconciliation_run.created', 'finance.evidence.linked', 'finance.discrepancy.resolved', 'finance.reconciliation.reviewed', 'ai.conversation.created', 'ai.run.completed', 'ai.run.failed', 'ai.run.cancelled', 'ai.tool.executed', 'ai.tool.denied', 'ai.action.blocked', 'ai.proposal.created', 'ai.proposal.edited', 'ai.proposal.approved', 'ai.proposal.rejected'")


def _app_role() -> str:
    role = os.environ.get("TOUCHE_DB_APP_USER", "touche_app").strip()
    if not role:
        raise RuntimeError("TOUCHE_DB_APP_USER must not be empty")
    return postgresql.dialect().identifier_preparer.quote(role)


def upgrade() -> None:
    uuid = postgresql.UUID(as_uuid=True)
    op.create_table(
        "communication_suppression",
        sa.Column("id", uuid, primary_key=True, server_default=sa.text("gen_random_uuid()")),
        sa.Column("company_id", uuid, nullable=False),
        sa.Column("counterparty_id", uuid, nullable=False),
        sa.Column("channel", sa.String(24), nullable=False),
        sa.Column("reason", sa.String(24), nullable=False),
        sa.Column("recorded_by", uuid, nullable=False),
        sa.Column(
            "created_at", sa.DateTime(timezone=True),
            nullable=False, server_default=sa.text("now()"),
        ),
        sa.ForeignKeyConstraint(
            ["company_id"], ["touche.company.id"],
            name="fk_communication_suppression_company_id_company",
        ),
        sa.ForeignKeyConstraint(
            ["counterparty_id", "company_id"],
            ["touche.counterparty.id", "touche.counterparty.company_id"],
            name="fk_communication_suppression_counterparty_company",
            ondelete="RESTRICT",
        ),
        sa.ForeignKeyConstraint(
            ["recorded_by"], ["touche.app_user.id"],
            name="fk_communication_suppression_recorded_by_user",
        ),
        sa.UniqueConstraint(
            "company_id", "counterparty_id", "channel",
            name="uq_communication_suppression_company_contact_channel",
        ),
        sa.CheckConstraint(
            "channel IN ('EMAIL', 'WHATSAPP_BUSINESS')",
            name="ck_communication_suppression_channel",
        ),
        sa.CheckConstraint(
            "reason IN ('CONTACT_REQUEST', 'COMPLIANCE_REVIEW', 'IMPORTED_BLOCK')",
            name="ck_communication_suppression_reason",
        ),
        schema=SCHEMA,
        comment="Immutable tenant-scoped outbound contact blocks.",
    )
    op.create_index(
        "ix_communication_suppression_company_created",
        "communication_suppression", ["company_id", "created_at"], schema=SCHEMA,
    )
    table = f"{SCHEMA}.communication_suppression"
    predicate = f"company_id = {SCHEMA}.current_company_id()"
    op.execute(f"ALTER TABLE {table} ENABLE ROW LEVEL SECURITY")
    op.execute(
        f"CREATE POLICY communication_suppression_tenant_select ON {table} "
        f"FOR SELECT USING ({predicate})"
    )
    op.execute(
        f"CREATE POLICY communication_suppression_tenant_insert ON {table} "
        f"FOR INSERT WITH CHECK ({predicate})"
    )
    role = _app_role()
    op.execute(f"REVOKE ALL ON {table} FROM {role}")
    op.execute(f"GRANT SELECT, INSERT ON {table} TO {role}")
    op.drop_constraint("ck_audit_action", "audit_record", schema=SCHEMA, type_="check")
    op.create_check_constraint(
        "ck_audit_action", "audit_record",
        f"action IN ({_AUDIT_ACTIONS})", schema=SCHEMA,
    )


def downgrade() -> None:
    # Never delete a suppression or an audit assertion. Any recorded event blocks
    # downgrade until an explicit, separately approved data migration exists.
    op.execute(
        "DO $$ BEGIN IF EXISTS (SELECT 1 FROM touche.communication_suppression) "
        "OR EXISTS (SELECT 1 FROM touche.audit_record "
        "WHERE action = 'communications.suppression.recorded') "
        "THEN RAISE EXCEPTION 'Stage 7C2 records exist; downgrade would erase evidence.'; "
        "END IF; END $$"
    )
    op.drop_constraint("ck_audit_action", "audit_record", schema=SCHEMA, type_="check")
    op.create_check_constraint(
        "ck_audit_action", "audit_record",
        f"action IN ({_PREVIOUS_ACTIONS})", schema=SCHEMA,
    )
    op.drop_table("communication_suppression", schema=SCHEMA)

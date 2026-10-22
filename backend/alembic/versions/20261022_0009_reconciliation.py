"""Stage 5D: evidence-based financial reconciliation.

Creates five tenant-scoped tables. Runtime grants are deliberately narrow:

* run: SELECT, INSERT, UPDATE (lifecycle only);
* source reference: SELECT, INSERT;
* evidence: SELECT, INSERT and UPDATE only of reviewer verification columns;
* discrepancy: SELECT, INSERT, UPDATE (resolution only);
* review: SELECT, INSERT.

No table accepts DELETE for the runtime role and no Finance object is touched.
RLS uses ``touche.current_company_id()`` on every table.

Revision ID: 0009_reconciliation
Revises: 0008_finance_mapping
Create Date: 2026-10-22
"""

from __future__ import annotations

import os
from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision: str = "0009_reconciliation"
down_revision: str | None = "0008_finance_mapping"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

SCHEMA = "touche"
_APP_ROLE_ENV = "TOUCHE_DB_APP_USER"
_DEFAULT_APP_ROLE = "touche_app"
_UUID = postgresql.UUID(as_uuid=True)
_JSONB = postgresql.JSONB(astext_type=sa.Text())

_STATUSES = (
    "'INCOMPLETE', 'UNMATCHED', 'POTENTIAL_MATCH', 'MATCHED_EVIDENCE', 'VERIFIED', 'DISPUTED'"
)
_SOURCE_ENTITY_TYPES = "'SALES_ORDER', 'PURCHASE_ORDER', 'SHIPMENT', 'SHIPMENT_COST'"
_FINANCE_SOURCE_TYPES = "'AGING_RECEIVABLE', 'AGING_PAYABLE', 'ACCOUNT', 'SUMMARY'"
_EVIDENCE_STATUSES = "'UNVERIFIED', 'VERIFIED', 'REJECTED'"
_DISCREPANCY_CODES = (
    "'MISSING_EVIDENCE', 'MISSING_FINANCE_REFERENCE', 'AMOUNT_MISMATCH', "
    "'CURRENCY_MISMATCH', 'DUPLICATE_REFERENCE', 'INCOMPLETE_COSTS', "
    "'UNMATCHED_FINANCE_ITEM', 'SOURCE_STALE', 'COMPANY_MAPPING_INVALID', "
    "'MANUAL_REVIEW_REQUIRED'"
)
_SEVERITIES = "'INFO', 'WARNING', 'ERROR', 'BLOCKING'"
_DISCREPANCY_STATUSES = "'OPEN', 'RESOLVED', 'DISMISSED'"
_DECISIONS = "'CONFIRM', 'DISPUTE', 'REQUEST_CHANGES'"

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
_STAGE_5C_ACTIONS = "'finance.mapping.configured', 'finance.mapping.disabled', 'finance.read'"
_STAGE_5D_ACTIONS = (
    "'finance.reconciliation_run.created', 'finance.evidence.linked', "
    "'finance.discrepancy.resolved', 'finance.reconciliation.reviewed'"
)
_ALL_ACTIONS = (
    f"{_STAGE_1A_ACTIONS}, {_STAGE_1B_ACTIONS}, {_STAGE_3_ACTIONS}, "
    f"{_STAGE_4_ACTIONS}, {_STAGE_5C_ACTIONS}, {_STAGE_5D_ACTIONS}"
)
_PREVIOUS_ACTIONS = (
    f"{_STAGE_1A_ACTIONS}, {_STAGE_1B_ACTIONS}, {_STAGE_3_ACTIONS}, "
    f"{_STAGE_4_ACTIONS}, {_STAGE_5C_ACTIONS}"
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


def _company() -> sa.Column:
    return sa.Column("company_id", _UUID, nullable=False)


def _created() -> sa.Column:
    return sa.Column(
        "created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.text("now()")
    )


def _updated() -> sa.Column:
    return sa.Column(
        "updated_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.text("now()")
    )


def _version() -> sa.Column:
    return sa.Column("version", sa.Integer(), nullable=False, server_default=sa.text("1"))


def _create_run() -> None:
    op.create_table(
        "finance_reconciliation_run",
        _pk(),
        _company(),
        sa.Column("sales_order_id", _UUID, nullable=False),
        sa.Column("finance_company_id", sa.String(64), nullable=False),
        sa.Column("currency", sa.String(3), nullable=False),
        sa.Column("finance_currency", sa.String(3), nullable=False),
        sa.Column("as_of", sa.Date(), nullable=False),
        sa.Column("data_through", sa.Date(), nullable=True),
        sa.Column("status", sa.String(24), nullable=False),
        sa.Column("calculation_version", sa.String(40), nullable=False),
        sa.Column("source_snapshot", _JSONB, nullable=False),
        sa.Column("created_by", _UUID, nullable=False),
        _created(),
        _updated(),
        _version(),
        sa.ForeignKeyConstraint(
            ["sales_order_id", "company_id"],
            [f"{SCHEMA}.sales_order.id", f"{SCHEMA}.sales_order.company_id"],
            name="fk_finance_reconciliation_run_sales_order_company",
            ondelete="RESTRICT",
        ),
        sa.ForeignKeyConstraint(
            ["created_by"],
            [f"{SCHEMA}.app_user.id"],
            name="fk_finance_reconciliation_run_created_by_app_user",
        ),
        sa.UniqueConstraint("id", "company_id", name="uq_finance_reconciliation_run_id_company_id"),
        sa.CheckConstraint(f"status IN ({_STATUSES})", name="ck_finance_reconciliation_run_status"),
        sa.CheckConstraint(
            "currency ~ '^[A-Z]{2,3}$'", name="ck_finance_reconciliation_run_currency"
        ),
        sa.CheckConstraint(
            "finance_currency ~ '^[A-Z]{2,3}$'",
            name="ck_finance_reconciliation_run_finance_currency",
        ),
        sa.CheckConstraint(
            "finance_company_id ~ '^[a-z][a-z0-9_]{1,63}$'",
            name="ck_finance_reconciliation_run_finance_company",
        ),
        sa.CheckConstraint(
            "char_length(btrim(calculation_version)) BETWEEN 3 AND 40",
            name="ck_finance_reconciliation_run_calculation_version",
        ),
        sa.CheckConstraint("version >= 1", name="ck_finance_reconciliation_run_version"),
        sa.CheckConstraint(
            "jsonb_typeof(source_snapshot) = 'object'",
            name="ck_finance_reconciliation_run_snapshot_object",
        ),
        schema=SCHEMA,
        comment="Tenant-scoped reconciliation snapshots (RLS protected).",
    )
    op.create_index(
        "ix_finance_reconciliation_run_company_order",
        "finance_reconciliation_run",
        ["company_id", "sales_order_id", "created_at"],
        schema=SCHEMA,
    )
    op.create_index(
        "ix_finance_reconciliation_run_company_currency_status",
        "finance_reconciliation_run",
        ["company_id", "currency", "status"],
        schema=SCHEMA,
    )


def _create_source_reference() -> None:
    op.create_table(
        "finance_source_reference",
        _pk(),
        _company(),
        sa.Column("run_id", _UUID, nullable=False),
        sa.Column("source_type", sa.String(24), nullable=False),
        sa.Column("source_reference", sa.String(200), nullable=False),
        sa.Column("is_transaction_level", sa.Boolean(), nullable=False),
        sa.Column("currency", sa.String(3), nullable=False),
        sa.Column("observed_amount", sa.Numeric(18, 2), nullable=True),
        sa.Column("as_of", sa.Date(), nullable=False),
        sa.Column("data_through", sa.Date(), nullable=True),
        sa.Column("payload", _JSONB, nullable=False),
        sa.Column("content_hash", sa.String(64), nullable=False),
        _created(),
        sa.ForeignKeyConstraint(
            ["run_id", "company_id"],
            [
                f"{SCHEMA}.finance_reconciliation_run.id",
                f"{SCHEMA}.finance_reconciliation_run.company_id",
            ],
            name="fk_finance_source_reference_run_company",
            ondelete="CASCADE",
        ),
        sa.UniqueConstraint(
            "id",
            "company_id",
            "run_id",
            name="uq_finance_source_reference_id_company_run",
        ),
        sa.UniqueConstraint(
            "run_id",
            "company_id",
            "source_type",
            "source_reference",
            name="uq_finance_source_reference_run_type_reference",
        ),
        sa.CheckConstraint(
            f"source_type IN ({_FINANCE_SOURCE_TYPES})",
            name="ck_finance_source_reference_type",
        ),
        sa.CheckConstraint(
            "char_length(btrim(source_reference)) BETWEEN 1 AND 200",
            name="ck_finance_source_reference_reference",
        ),
        sa.CheckConstraint(
            "currency ~ '^[A-Z]{2,3}$'", name="ck_finance_source_reference_currency"
        ),
        sa.CheckConstraint(
            "content_hash ~ '^[0-9a-f]{64}$'", name="ck_finance_source_reference_hash"
        ),
        sa.CheckConstraint(
            "jsonb_typeof(payload) = 'object'",
            name="ck_finance_source_reference_payload_object",
        ),
        sa.CheckConstraint(
            "(source_type IN ('AGING_RECEIVABLE', 'AGING_PAYABLE')) = is_transaction_level",
            name="ck_finance_source_reference_transaction_level",
        ),
        schema=SCHEMA,
        comment="Finance source snapshot; names are never matching keys (RLS protected).",
    )
    op.create_index(
        "ix_finance_source_reference_company_run",
        "finance_source_reference",
        ["company_id", "run_id", "source_type"],
        schema=SCHEMA,
    )


def _create_evidence() -> None:
    op.create_table(
        "finance_reconciliation_evidence",
        _pk(),
        _company(),
        sa.Column("run_id", _UUID, nullable=False),
        sa.Column("finance_source_reference_id", _UUID, nullable=False),
        sa.Column("source_entity_type", sa.String(24), nullable=False),
        sa.Column("source_entity_id", _UUID, nullable=False),
        sa.Column("currency", sa.String(3), nullable=False),
        sa.Column("amount", sa.Numeric(18, 2), nullable=False),
        sa.Column("as_of", sa.Date(), nullable=False),
        sa.Column("data_through", sa.Date(), nullable=True),
        sa.Column("provenance", _JSONB, nullable=False),
        sa.Column(
            "verification_status",
            sa.String(16),
            nullable=False,
            server_default=sa.text("'UNVERIFIED'"),
        ),
        sa.Column("notes", sa.Text(), nullable=True),
        sa.Column("created_by", _UUID, nullable=False),
        _created(),
        sa.Column("verified_by", _UUID, nullable=True),
        sa.Column("verified_at", sa.DateTime(timezone=True), nullable=True),
        sa.ForeignKeyConstraint(
            ["run_id", "company_id"],
            [
                f"{SCHEMA}.finance_reconciliation_run.id",
                f"{SCHEMA}.finance_reconciliation_run.company_id",
            ],
            name="fk_finance_reconciliation_evidence_run_company",
            ondelete="CASCADE",
        ),
        sa.ForeignKeyConstraint(
            ["finance_source_reference_id", "company_id", "run_id"],
            [
                f"{SCHEMA}.finance_source_reference.id",
                f"{SCHEMA}.finance_source_reference.company_id",
                f"{SCHEMA}.finance_source_reference.run_id",
            ],
            name="fk_finance_reconciliation_evidence_source_run",
            ondelete="RESTRICT",
        ),
        sa.ForeignKeyConstraint(
            ["created_by"],
            [f"{SCHEMA}.app_user.id"],
            name="fk_finance_reconciliation_evidence_created_by_app_user",
        ),
        sa.ForeignKeyConstraint(
            ["verified_by"],
            [f"{SCHEMA}.app_user.id"],
            name="fk_finance_reconciliation_evidence_verified_by_app_user",
        ),
        sa.UniqueConstraint(
            "run_id",
            "company_id",
            "finance_source_reference_id",
            name="uq_finance_reconciliation_evidence_run_source",
        ),
        sa.CheckConstraint(
            f"source_entity_type IN ({_SOURCE_ENTITY_TYPES})",
            name="ck_finance_reconciliation_evidence_entity_type",
        ),
        sa.CheckConstraint(
            f"verification_status IN ({_EVIDENCE_STATUSES})",
            name="ck_finance_reconciliation_evidence_verification",
        ),
        sa.CheckConstraint(
            "currency ~ '^[A-Z]{2,3}$'", name="ck_finance_reconciliation_evidence_currency"
        ),
        sa.CheckConstraint("amount >= 0", name="ck_finance_reconciliation_evidence_amount"),
        sa.CheckConstraint(
            "jsonb_typeof(provenance) = 'object'",
            name="ck_finance_reconciliation_evidence_provenance_object",
        ),
        sa.CheckConstraint(
            "notes IS NULL OR char_length(notes) <= 2000",
            name="ck_finance_reconciliation_evidence_notes",
        ),
        sa.CheckConstraint(
            "(verification_status = 'VERIFIED') = "
            "(verified_by IS NOT NULL AND verified_at IS NOT NULL)",
            name="ck_finance_reconciliation_evidence_verified_pair",
        ),
        schema=SCHEMA,
        comment="Explicit evidence links; append-only for runtime (RLS protected).",
    )
    op.create_index(
        "ix_finance_reconciliation_evidence_company_run",
        "finance_reconciliation_evidence",
        ["company_id", "run_id", "source_entity_type"],
        schema=SCHEMA,
    )
    op.create_index(
        "ix_finance_reconciliation_evidence_company_entity",
        "finance_reconciliation_evidence",
        ["company_id", "source_entity_type", "source_entity_id"],
        schema=SCHEMA,
    )


def _create_discrepancy() -> None:
    op.create_table(
        "finance_discrepancy",
        _pk(),
        _company(),
        sa.Column("run_id", _UUID, nullable=False),
        sa.Column("finance_source_reference_id", _UUID, nullable=True),
        sa.Column("source_entity_type", sa.String(24), nullable=True),
        sa.Column("source_entity_id", _UUID, nullable=True),
        sa.Column("code", sa.String(32), nullable=False),
        sa.Column("severity", sa.String(16), nullable=False),
        sa.Column("status", sa.String(16), nullable=False, server_default=sa.text("'OPEN'")),
        sa.Column("fingerprint", sa.String(64), nullable=False),
        sa.Column("title", sa.String(160), nullable=False),
        sa.Column("detail", sa.Text(), nullable=False),
        sa.Column("expected", _JSONB, nullable=False, server_default=sa.text("'{}'::jsonb")),
        sa.Column("observed", _JSONB, nullable=False, server_default=sa.text("'{}'::jsonb")),
        sa.Column("assigned_to", _UUID, nullable=True),
        sa.Column("resolution_notes", sa.Text(), nullable=True),
        sa.Column("resolved_by", _UUID, nullable=True),
        sa.Column("resolved_at", sa.DateTime(timezone=True), nullable=True),
        _created(),
        _updated(),
        _version(),
        sa.ForeignKeyConstraint(
            ["run_id", "company_id"],
            [
                f"{SCHEMA}.finance_reconciliation_run.id",
                f"{SCHEMA}.finance_reconciliation_run.company_id",
            ],
            name="fk_finance_discrepancy_run_company",
            ondelete="CASCADE",
        ),
        sa.ForeignKeyConstraint(
            ["finance_source_reference_id", "company_id", "run_id"],
            [
                f"{SCHEMA}.finance_source_reference.id",
                f"{SCHEMA}.finance_source_reference.company_id",
                f"{SCHEMA}.finance_source_reference.run_id",
            ],
            name="fk_finance_discrepancy_source_run",
            ondelete="RESTRICT",
        ),
        sa.ForeignKeyConstraint(
            ["assigned_to"],
            [f"{SCHEMA}.app_user.id"],
            name="fk_finance_discrepancy_assigned_to_app_user",
        ),
        sa.ForeignKeyConstraint(
            ["resolved_by"],
            [f"{SCHEMA}.app_user.id"],
            name="fk_finance_discrepancy_resolved_by_app_user",
        ),
        sa.UniqueConstraint("run_id", "fingerprint", name="uq_finance_discrepancy_run_fingerprint"),
        sa.UniqueConstraint("id", "company_id", name="uq_finance_discrepancy_id_company_id"),
        sa.CheckConstraint(f"code IN ({_DISCREPANCY_CODES})", name="ck_finance_discrepancy_code"),
        sa.CheckConstraint(f"severity IN ({_SEVERITIES})", name="ck_finance_discrepancy_severity"),
        sa.CheckConstraint(
            f"status IN ({_DISCREPANCY_STATUSES})", name="ck_finance_discrepancy_status"
        ),
        sa.CheckConstraint(
            f"source_entity_type IS NULL OR source_entity_type IN ({_SOURCE_ENTITY_TYPES})",
            name="ck_finance_discrepancy_entity_type",
        ),
        sa.CheckConstraint(
            "char_length(btrim(fingerprint)) = 64",
            name="ck_finance_discrepancy_fingerprint",
        ),
        sa.CheckConstraint(
            "char_length(btrim(title)) BETWEEN 3 AND 160",
            name="ck_finance_discrepancy_title",
        ),
        sa.CheckConstraint(
            "resolution_notes IS NULL OR char_length(resolution_notes) <= 2000",
            name="ck_finance_discrepancy_resolution_notes",
        ),
        sa.CheckConstraint("version >= 1", name="ck_finance_discrepancy_version"),
        sa.CheckConstraint(
            "(status = 'OPEN') = (resolved_by IS NULL AND resolved_at IS NULL)",
            name="ck_finance_discrepancy_resolution_pair",
        ),
        schema=SCHEMA,
        comment="Deterministic reconciliation discrepancies (RLS protected).",
    )
    op.create_index(
        "ix_finance_discrepancy_company_run_status",
        "finance_discrepancy",
        ["company_id", "run_id", "status", "severity"],
        schema=SCHEMA,
    )


def _create_review() -> None:
    op.create_table(
        "finance_reconciliation_review",
        _pk(),
        _company(),
        sa.Column("run_id", _UUID, nullable=False),
        sa.Column("reviewer_id", _UUID, nullable=False),
        sa.Column("decision", sa.String(24), nullable=False),
        sa.Column("previous_status", sa.String(24), nullable=False),
        sa.Column("new_status", sa.String(24), nullable=False),
        sa.Column("notes", sa.Text(), nullable=False),
        _created(),
        sa.ForeignKeyConstraint(
            ["run_id", "company_id"],
            [
                f"{SCHEMA}.finance_reconciliation_run.id",
                f"{SCHEMA}.finance_reconciliation_run.company_id",
            ],
            name="fk_finance_reconciliation_review_run_company",
            ondelete="CASCADE",
        ),
        sa.ForeignKeyConstraint(
            ["reviewer_id"],
            [f"{SCHEMA}.app_user.id"],
            name="fk_finance_reconciliation_review_reviewer_app_user",
        ),
        sa.UniqueConstraint(
            "id", "company_id", name="uq_finance_reconciliation_review_id_company_id"
        ),
        sa.CheckConstraint(
            f"decision IN ({_DECISIONS})", name="ck_finance_reconciliation_review_decision"
        ),
        sa.CheckConstraint(
            f"previous_status IN ({_STATUSES})",
            name="ck_finance_reconciliation_review_previous_status",
        ),
        sa.CheckConstraint(
            f"new_status IN ({_STATUSES})",
            name="ck_finance_reconciliation_review_new_status",
        ),
        sa.CheckConstraint(
            "char_length(btrim(notes)) BETWEEN 3 AND 2000",
            name="ck_finance_reconciliation_review_notes",
        ),
        schema=SCHEMA,
        comment="Append-only financial review decisions (RLS protected).",
    )
    op.create_index(
        "ix_finance_reconciliation_review_company_run",
        "finance_reconciliation_review",
        ["company_id", "run_id", "created_at"],
        schema=SCHEMA,
    )


def _apply_rls() -> None:
    predicate = f"company_id = {SCHEMA}.current_company_id()"
    tables = (
        ("finance_reconciliation_run", ("SELECT", "INSERT", "UPDATE")),
        ("finance_source_reference", ("SELECT", "INSERT")),
        # Evidence is append-only except the reviewer-owned verification columns.
        ("finance_reconciliation_evidence", ("SELECT", "INSERT", "UPDATE")),
        ("finance_discrepancy", ("SELECT", "INSERT", "UPDATE")),
        ("finance_reconciliation_review", ("SELECT", "INSERT")),
    )
    for table, operations in tables:
        qualified = f"{SCHEMA}.{table}"
        op.execute(f"ALTER TABLE {qualified} ENABLE ROW LEVEL SECURITY")
        for operation in operations:
            policy_operation = "INSERT" if operation == "INSERT" else operation
            using = f" USING ({predicate})" if operation != "INSERT" else ""
            check = f" WITH CHECK ({predicate})" if operation in {"INSERT", "UPDATE"} else ""
            op.execute(
                f"CREATE POLICY {table}_tenant_{operation.lower()} ON {qualified} "
                f"FOR {policy_operation}{using}{check}"
            )


def _grant_runtime() -> None:
    role = _app_role()
    grants = {
        "finance_reconciliation_run": "SELECT, INSERT, UPDATE",
        "finance_source_reference": "SELECT, INSERT",
        "finance_reconciliation_evidence": (
            "SELECT, INSERT, UPDATE (verification_status, verified_by, verified_at)"
        ),
        "finance_discrepancy": "SELECT, INSERT, UPDATE",
        "finance_reconciliation_review": "SELECT, INSERT",
    }
    for table, privileges in grants.items():
        qualified = f"{_quote(SCHEMA)}.{table}"
        # The database may carry broad ALTER DEFAULT PRIVILEGES. Revoke them for
        # these append-only tables before granting the exact least privilege set.
        op.execute(f"REVOKE ALL ON {qualified} FROM {role}")
        op.execute(f"GRANT {privileges} ON {qualified} TO {role}")


def _set_audit_actions(actions: str) -> None:
    op.drop_constraint("ck_audit_action", "audit_record", schema=SCHEMA, type_="check")
    op.create_check_constraint(
        "ck_audit_action", "audit_record", f"action IN ({actions})", schema=SCHEMA
    )


def upgrade() -> None:
    _create_run()
    _create_source_reference()
    _create_evidence()
    _create_discrepancy()
    _create_review()
    _apply_rls()
    _grant_runtime()
    _set_audit_actions(_ALL_ACTIONS)


def downgrade() -> None:
    _set_audit_actions(_PREVIOUS_ACTIONS)
    for table in (
        "finance_reconciliation_review",
        "finance_discrepancy",
        "finance_reconciliation_evidence",
        "finance_source_reference",
        "finance_reconciliation_run",
    ):
        op.drop_table(table, schema=SCHEMA)

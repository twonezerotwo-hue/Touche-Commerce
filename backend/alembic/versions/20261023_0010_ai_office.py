"""Stage 6: AI Trade Director persistence.

Creates five tenant-scoped tables (conversation, run, message, tool call, proposal)
and extends the audit action CHECK. Runtime grants are deliberately narrow:

* conversation, run, proposal: SELECT, INSERT, UPDATE;
* message, tool call: SELECT, INSERT (append-only).

No table accepts DELETE for the runtime role. Nothing here stores a prompt, a
credential or a raw tool result. RLS uses ``touche.current_company_id()`` on every
table.

Revision ID: 0010_ai_office
Revises: 0009_reconciliation
Create Date: 2026-10-23
"""

from __future__ import annotations

import os
from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision: str = "0010_ai_office"
down_revision: str | None = "0009_reconciliation"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

SCHEMA = "touche"
_APP_ROLE_ENV = "TOUCHE_DB_APP_USER"
_DEFAULT_APP_ROLE = "touche_app"
_UUID = postgresql.UUID(as_uuid=True)
_JSONB = postgresql.JSONB(astext_type=sa.Text())

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
_STAGE_6_ACTIONS = (
    "'ai.conversation.created', 'ai.run.completed', 'ai.run.failed', 'ai.run.cancelled', "
    "'ai.tool.executed', 'ai.tool.denied', 'ai.action.blocked', 'ai.proposal.created', "
    "'ai.proposal.edited', 'ai.proposal.approved', 'ai.proposal.rejected'"
)
_PREVIOUS_ACTIONS = (
    f"{_STAGE_1A_ACTIONS}, {_STAGE_1B_ACTIONS}, {_STAGE_3_ACTIONS}, "
    f"{_STAGE_4_ACTIONS}, {_STAGE_5C_ACTIONS}, {_STAGE_5D_ACTIONS}"
)
_ALL_ACTIONS = f"{_PREVIOUS_ACTIONS}, {_STAGE_6_ACTIONS}"

_TOOL_CLASSES = "'READ_ONLY', 'DRAFT_PROPOSAL', 'REQUIRES_HUMAN_APPROVAL', 'BLOCKED'"


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


def _create_conversation() -> None:
    op.create_table(
        "ai_conversation",
        _pk(),
        _company(),
        sa.Column("user_id", _UUID, nullable=False),
        sa.Column("title", sa.String(160), nullable=False),
        sa.Column("status", sa.String(16), nullable=False, server_default=sa.text("'ACTIVE'")),
        sa.Column("prompt_version", sa.String(40), nullable=False),
        _created(),
        _updated(),
        _version(),
        sa.ForeignKeyConstraint(
            ["company_id"],
            [f"{SCHEMA}.company.id"],
            name="fk_ai_conversation_company_id_company",
        ),
        sa.ForeignKeyConstraint(
            ["user_id"], [f"{SCHEMA}.app_user.id"], name="fk_ai_conversation_user_id_app_user"
        ),
        sa.UniqueConstraint("id", "company_id", name="uq_ai_conversation_id_company_id"),
        sa.CheckConstraint(
            "status IN ('ACTIVE', 'ARCHIVED')", name="ck_ai_conversation_status"
        ),
        sa.CheckConstraint(
            "char_length(btrim(title)) BETWEEN 1 AND 160", name="ck_ai_conversation_title"
        ),
        sa.CheckConstraint("version >= 1", name="ck_ai_conversation_version"),
        schema=SCHEMA,
        comment="AI Office conversations (RLS protected).",
    )
    op.create_index(
        "ix_ai_conversation_company_user_updated",
        "ai_conversation",
        ["company_id", "user_id", "updated_at"],
        schema=SCHEMA,
    )


def _create_run() -> None:
    op.create_table(
        "ai_run",
        _pk(),
        _company(),
        sa.Column("conversation_id", _UUID, nullable=False),
        sa.Column("user_id", _UUID, nullable=False),
        sa.Column("status", sa.String(16), nullable=False),
        sa.Column("provider", sa.String(32), nullable=False),
        sa.Column("model", sa.String(120), nullable=False),
        sa.Column("prompt_version", sa.String(40), nullable=False),
        sa.Column("is_external", sa.Boolean(), nullable=False),
        sa.Column("input_tokens", sa.Integer(), nullable=False, server_default=sa.text("0")),
        sa.Column("output_tokens", sa.Integer(), nullable=False, server_default=sa.text("0")),
        sa.Column("estimated_usage", sa.Boolean(), nullable=False, server_default=sa.text("false")),
        sa.Column("cost_usd", sa.Numeric(12, 6), nullable=False, server_default=sa.text("0")),
        sa.Column("model_steps", sa.Integer(), nullable=False, server_default=sa.text("0")),
        sa.Column("tool_call_count", sa.Integer(), nullable=False, server_default=sa.text("0")),
        sa.Column("provider_calls", sa.Integer(), nullable=False, server_default=sa.text("0")),
        sa.Column("error_code", sa.String(64), nullable=True),
        sa.Column(
            "validation_warnings", _JSONB, nullable=False, server_default=sa.text("'[]'::jsonb")
        ),
        sa.Column("safety_flags", _JSONB, nullable=False, server_default=sa.text("'[]'::jsonb")),
        sa.Column("request_id", sa.String(128), nullable=True),
        sa.Column(
            "started_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.text("now()")
        ),
        sa.Column("finished_at", sa.DateTime(timezone=True), nullable=True),
        sa.ForeignKeyConstraint(
            ["conversation_id", "company_id"],
            [f"{SCHEMA}.ai_conversation.id", f"{SCHEMA}.ai_conversation.company_id"],
            name="fk_ai_run_conversation_company",
            ondelete="RESTRICT",
        ),
        sa.ForeignKeyConstraint(
            ["user_id"], [f"{SCHEMA}.app_user.id"], name="fk_ai_run_user_id_app_user"
        ),
        sa.UniqueConstraint("id", "company_id", name="uq_ai_run_id_company_id"),
        sa.CheckConstraint(
            "status IN ('RUNNING', 'COMPLETED', 'FAILED', 'CANCELLED')", name="ck_ai_run_status"
        ),
        sa.CheckConstraint(
            "input_tokens >= 0 AND output_tokens >= 0 AND model_steps >= 0 "
            "AND tool_call_count >= 0 AND provider_calls >= 0",
            name="ck_ai_run_counters",
        ),
        sa.CheckConstraint("cost_usd >= 0", name="ck_ai_run_cost"),
        sa.CheckConstraint(
            "jsonb_typeof(validation_warnings) = 'array' AND jsonb_typeof(safety_flags) = 'array'",
            name="ck_ai_run_flags_array",
        ),
        sa.CheckConstraint(
            "(status = 'RUNNING') = (finished_at IS NULL)", name="ck_ai_run_finished_pair"
        ),
        schema=SCHEMA,
        comment="AI run metadata, usage and cost (RLS protected).",
    )
    op.create_index("ix_ai_run_company_started", "ai_run", ["company_id", "started_at"], schema=SCHEMA)
    op.create_index(
        "ix_ai_run_company_user_started",
        "ai_run",
        ["company_id", "user_id", "started_at"],
        schema=SCHEMA,
    )
    op.create_index(
        "ix_ai_run_conversation",
        "ai_run",
        ["company_id", "conversation_id", "started_at"],
        schema=SCHEMA,
    )


def _create_message() -> None:
    op.create_table(
        "ai_message",
        _pk(),
        _company(),
        sa.Column("conversation_id", _UUID, nullable=False),
        sa.Column("run_id", _UUID, nullable=True),
        sa.Column("role", sa.String(12), nullable=False),
        sa.Column("content", sa.Text(), nullable=False),
        sa.Column("structured", _JSONB, nullable=True),
        sa.Column("evidence", _JSONB, nullable=False, server_default=sa.text("'[]'::jsonb")),
        _created(),
        sa.ForeignKeyConstraint(
            ["conversation_id", "company_id"],
            [f"{SCHEMA}.ai_conversation.id", f"{SCHEMA}.ai_conversation.company_id"],
            name="fk_ai_message_conversation_company",
            ondelete="RESTRICT",
        ),
        sa.ForeignKeyConstraint(
            ["run_id", "company_id"],
            [f"{SCHEMA}.ai_run.id", f"{SCHEMA}.ai_run.company_id"],
            name="fk_ai_message_run_company",
            ondelete="RESTRICT",
        ),
        sa.UniqueConstraint("id", "company_id", name="uq_ai_message_id_company_id"),
        sa.CheckConstraint("role IN ('USER', 'ASSISTANT')", name="ck_ai_message_role"),
        sa.CheckConstraint("char_length(content) BETWEEN 1 AND 20000", name="ck_ai_message_content"),
        sa.CheckConstraint("jsonb_typeof(evidence) = 'array'", name="ck_ai_message_evidence_array"),
        sa.CheckConstraint(
            "structured IS NULL OR jsonb_typeof(structured) = 'object'",
            name="ck_ai_message_structured_object",
        ),
        schema=SCHEMA,
        comment="AI conversation messages, append-only (RLS protected).",
    )
    op.create_index(
        "ix_ai_message_conversation",
        "ai_message",
        ["company_id", "conversation_id", "created_at"],
        schema=SCHEMA,
    )


def _create_tool_call() -> None:
    op.create_table(
        "ai_tool_call",
        _pk(),
        _company(),
        sa.Column("run_id", _UUID, nullable=False),
        sa.Column("ordinal", sa.Integer(), nullable=False),
        sa.Column("tool_name", sa.String(64), nullable=False),
        sa.Column("tool_class", sa.String(32), nullable=False),
        sa.Column("status", sa.String(12), nullable=False),
        sa.Column("arguments", _JSONB, nullable=False),
        sa.Column("result_meta", _JSONB, nullable=False, server_default=sa.text("'{}'::jsonb")),
        sa.Column("result_chars", sa.Integer(), nullable=False, server_default=sa.text("0")),
        sa.Column("duration_ms", sa.Integer(), nullable=False, server_default=sa.text("0")),
        sa.Column("error_code", sa.String(64), nullable=True),
        _created(),
        sa.ForeignKeyConstraint(
            ["run_id", "company_id"],
            [f"{SCHEMA}.ai_run.id", f"{SCHEMA}.ai_run.company_id"],
            name="fk_ai_tool_call_run_company",
            ondelete="RESTRICT",
        ),
        sa.UniqueConstraint("run_id", "ordinal", name="uq_ai_tool_call_run_ordinal"),
        sa.CheckConstraint(
            "status IN ('OK', 'DENIED', 'INVALID', 'ERROR', 'LIMITED')",
            name="ck_ai_tool_call_status",
        ),
        sa.CheckConstraint(f"tool_class IN ({_TOOL_CLASSES})", name="ck_ai_tool_call_class"),
        sa.CheckConstraint(
            "jsonb_typeof(arguments) = 'object' AND jsonb_typeof(result_meta) = 'object'",
            name="ck_ai_tool_call_json_object",
        ),
        sa.CheckConstraint("result_chars >= 0 AND duration_ms >= 0", name="ck_ai_tool_call_counters"),
        schema=SCHEMA,
        comment="AI tool-call log, append-only (RLS protected).",
    )
    op.create_index(
        "ix_ai_tool_call_company_run",
        "ai_tool_call",
        ["company_id", "run_id", "ordinal"],
        schema=SCHEMA,
    )


def _create_proposal() -> None:
    op.create_table(
        "ai_proposal",
        _pk(),
        _company(),
        sa.Column("conversation_id", _UUID, nullable=False),
        sa.Column("run_id", _UUID, nullable=False),
        sa.Column("created_by", _UUID, nullable=False),
        sa.Column("kind", sa.String(8), nullable=False),
        sa.Column("action_type", sa.String(24), nullable=False),
        sa.Column("action_class", sa.String(32), nullable=False),
        sa.Column("title", sa.String(200), nullable=False),
        sa.Column("payload", _JSONB, nullable=False),
        sa.Column("edited_payload", _JSONB, nullable=True),
        sa.Column("evidence", _JSONB, nullable=False, server_default=sa.text("'[]'::jsonb")),
        sa.Column("warnings", _JSONB, nullable=False, server_default=sa.text("'[]'::jsonb")),
        sa.Column("status", sa.String(12), nullable=False, server_default=sa.text("'PROPOSED'")),
        sa.Column("decided_by", _UUID, nullable=True),
        sa.Column("decided_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("decision_notes", sa.Text(), nullable=True),
        sa.Column("execution_result", _JSONB, nullable=True),
        _created(),
        _updated(),
        _version(),
        sa.ForeignKeyConstraint(
            ["conversation_id", "company_id"],
            [f"{SCHEMA}.ai_conversation.id", f"{SCHEMA}.ai_conversation.company_id"],
            name="fk_ai_proposal_conversation_company",
            ondelete="RESTRICT",
        ),
        sa.ForeignKeyConstraint(
            ["run_id", "company_id"],
            [f"{SCHEMA}.ai_run.id", f"{SCHEMA}.ai_run.company_id"],
            name="fk_ai_proposal_run_company",
            ondelete="RESTRICT",
        ),
        sa.ForeignKeyConstraint(
            ["created_by"], [f"{SCHEMA}.app_user.id"], name="fk_ai_proposal_created_by_app_user"
        ),
        sa.ForeignKeyConstraint(
            ["decided_by"], [f"{SCHEMA}.app_user.id"], name="fk_ai_proposal_decided_by_app_user"
        ),
        sa.UniqueConstraint("id", "company_id", name="uq_ai_proposal_id_company_id"),
        sa.CheckConstraint("kind IN ('DRAFT', 'TASK')", name="ck_ai_proposal_kind"),
        sa.CheckConstraint(
            "action_type IN ('DRAFT_REVIEW', 'OPERATOR_TASK')", name="ck_ai_proposal_action_type"
        ),
        sa.CheckConstraint(
            "action_class IN ('DRAFT_PROPOSAL', 'REQUIRES_HUMAN_APPROVAL')",
            name="ck_ai_proposal_action_class",
        ),
        sa.CheckConstraint(
            "status IN ('PROPOSED', 'APPROVED', 'REJECTED')", name="ck_ai_proposal_status"
        ),
        sa.CheckConstraint(
            "char_length(btrim(title)) BETWEEN 1 AND 200", name="ck_ai_proposal_title"
        ),
        sa.CheckConstraint(
            "jsonb_typeof(payload) = 'object' AND jsonb_typeof(evidence) = 'array' "
            "AND jsonb_typeof(warnings) = 'array'",
            name="ck_ai_proposal_json_shapes",
        ),
        sa.CheckConstraint(
            "edited_payload IS NULL OR jsonb_typeof(edited_payload) = 'object'",
            name="ck_ai_proposal_edited_object",
        ),
        sa.CheckConstraint(
            "(status = 'PROPOSED') = (decided_by IS NULL AND decided_at IS NULL)",
            name="ck_ai_proposal_decision_pair",
        ),
        sa.CheckConstraint(
            "decision_notes IS NULL OR char_length(decision_notes) <= 2000",
            name="ck_ai_proposal_decision_notes",
        ),
        sa.CheckConstraint("version >= 1", name="ck_ai_proposal_version"),
        schema=SCHEMA,
        comment="Human-approval proposals from the AI (RLS protected).",
    )
    op.create_index(
        "ix_ai_proposal_company_status",
        "ai_proposal",
        ["company_id", "status", "created_at"],
        schema=SCHEMA,
    )
    op.create_index(
        "ix_ai_proposal_conversation",
        "ai_proposal",
        ["company_id", "conversation_id", "created_at"],
        schema=SCHEMA,
    )


_TABLES = {
    "ai_conversation": ("SELECT", "INSERT", "UPDATE"),
    "ai_run": ("SELECT", "INSERT", "UPDATE"),
    "ai_message": ("SELECT", "INSERT"),
    "ai_tool_call": ("SELECT", "INSERT"),
    "ai_proposal": ("SELECT", "INSERT", "UPDATE"),
}


def _apply_rls() -> None:
    predicate = f"company_id = {SCHEMA}.current_company_id()"
    for table, operations in _TABLES.items():
        qualified = f"{SCHEMA}.{table}"
        op.execute(f"ALTER TABLE {qualified} ENABLE ROW LEVEL SECURITY")
        for operation in operations:
            using = f" USING ({predicate})" if operation != "INSERT" else ""
            check = f" WITH CHECK ({predicate})" if operation in {"INSERT", "UPDATE"} else ""
            op.execute(
                f"CREATE POLICY {table}_tenant_{operation.lower()} ON {qualified} "
                f"FOR {operation}{using}{check}"
            )


def _grant_runtime() -> None:
    role = _app_role()
    grants = {
        "ai_conversation": "SELECT, INSERT, UPDATE (title, status, updated_at, version)",
        "ai_run": "SELECT, INSERT, UPDATE",
        "ai_message": "SELECT, INSERT",
        "ai_tool_call": "SELECT, INSERT",
        "ai_proposal": (
            "SELECT, INSERT, UPDATE (title, edited_payload, warnings, status, decided_by, "
            "decided_at, decision_notes, execution_result, updated_at, version)"
        ),
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
    _create_conversation()
    _create_run()
    _create_message()
    _create_tool_call()
    _create_proposal()
    _apply_rls()
    _grant_runtime()
    _set_audit_actions(_ALL_ACTIONS)


def downgrade() -> None:
    # Audit rows written with a Stage 6 action would violate the previous CHECK, so
    # the downgrade refuses rather than deleting an append-only audit trail.
    op.execute(
        f"DO $$ BEGIN IF EXISTS (SELECT 1 FROM {SCHEMA}.audit_record WHERE action LIKE 'ai.%') "
        "THEN RAISE EXCEPTION 'Stage 6 audit rows exist; the audit trail is append-only.'; "
        "END IF; END $$"
    )
    _set_audit_actions(_PREVIOUS_ACTIONS)
    for table in ("ai_proposal", "ai_tool_call", "ai_message", "ai_run", "ai_conversation"):
        op.drop_table(table, schema=SCHEMA)

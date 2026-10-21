"""stage 1a identity: users, companies, memberships, sessions, audit, RLS

Creates the security core of TOUCHE COMMERCE:

* ``app_user``     — global identities, Argon2id password hashes
* ``company``      — tenant roots
* ``membership``   — per-company role (viewer/trader/approver/admin)
* ``auth_session`` — server-side sessions; only SHA-256 token digests
* ``login_attempt``— rate limiting / forensics
* ``audit_record`` — append-only audit trail (trigger + grants)
* ``company_settings`` / ``company_setting_entry`` — real tenant-owned tables
  used to prove RLS isolation, including the composite-FK child rule
* ``idempotency_record`` — durable storage for the replay contract

Row level security is enabled on every tenant-owned table. Policies read
transaction-scoped settings (``touche.company_id`` / ``touche.actor_id``) written
by ``SET LOCAL``, so a pooled connection can never leak a tenant to the next
request.

Revision ID: 0002_identity
Revises: 0001_foundation
Create Date: 2026-10-22
"""

from __future__ import annotations

import os
from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision: str = "0002_identity"
down_revision: str | None = "0001_foundation"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

SCHEMA = "touche"
_APP_ROLE_ENV = "TOUCHE_DB_APP_USER"
_DEFAULT_APP_ROLE = "touche_app"
_UUID = postgresql.UUID(as_uuid=True)
_TS = sa.DateTime(timezone=True)
_JSONB = postgresql.JSONB(astext_type=sa.Text())


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


def _create_identity_tables() -> None:
    op.create_table(
        "app_user",
        _pk(),
        sa.Column("email", sa.Text(), nullable=False),
        sa.Column("display_name", sa.Text(), nullable=False),
        sa.Column("password_hash", sa.Text(), nullable=False),
        sa.Column("status", sa.String(length=16), nullable=False, server_default=sa.text("'active'")),
        sa.Column("last_login_at", _TS, nullable=True),
        _created_at(),
        _updated_at(),
        sa.CheckConstraint("email = lower(email)", name="ck_app_user_email_normalised"),
        sa.CheckConstraint("char_length(email) BETWEEN 3 AND 320", name="ck_app_user_email_length"),
        sa.CheckConstraint(
            "char_length(display_name) BETWEEN 1 AND 120", name="ck_app_user_name_length"
        ),
        sa.CheckConstraint("status IN ('active', 'disabled')", name="ck_app_user_status"),
        sa.UniqueConstraint("email", name="uq_app_user_email"),
        schema=SCHEMA,
        comment="Application users (global identity).",
    )

    op.create_table(
        "company",
        _pk(),
        sa.Column("name", sa.Text(), nullable=False),
        sa.Column("country", sa.String(length=2), nullable=False),
        sa.Column("default_currency", sa.String(length=3), nullable=False),
        sa.Column("status", sa.String(length=16), nullable=False, server_default=sa.text("'active'")),
        _created_at(),
        _updated_at(),
        sa.CheckConstraint("char_length(name) BETWEEN 1 AND 160", name="ck_company_name_length"),
        sa.CheckConstraint("country ~ '^[A-Z]{2}$'", name="ck_company_country_iso"),
        sa.CheckConstraint("default_currency ~ '^[A-Z]{3}$'", name="ck_company_currency_iso"),
        sa.CheckConstraint(
            "status IN ('active', 'suspended', 'archived')", name="ck_company_status"
        ),
        schema=SCHEMA,
        comment="Tenant roots (trading companies).",
    )

    op.create_table(
        "membership",
        _pk(),
        sa.Column("user_id", _UUID, nullable=False),
        sa.Column("company_id", _UUID, nullable=False),
        sa.Column("role", sa.String(length=16), nullable=False),
        sa.Column("status", sa.String(length=16), nullable=False, server_default=sa.text("'active'")),
        _created_at(),
        _updated_at(),
        sa.Column("revoked_at", _TS, nullable=True),
        sa.ForeignKeyConstraint(
            ["user_id"],
            [f"{SCHEMA}.app_user.id"],
            name="fk_membership_user_id_app_user",
            ondelete="CASCADE",
        ),
        sa.ForeignKeyConstraint(
            ["company_id"],
            [f"{SCHEMA}.company.id"],
            name="fk_membership_company_id_company",
            ondelete="CASCADE",
        ),
        sa.CheckConstraint(
            "role IN ('viewer', 'trader', 'approver', 'admin')", name="ck_membership_role"
        ),
        sa.CheckConstraint("status IN ('active', 'revoked')", name="ck_membership_status"),
        sa.CheckConstraint(
            "(status = 'revoked') = (revoked_at IS NOT NULL)", name="ck_membership_revoked_at"
        ),
        sa.UniqueConstraint("user_id", "company_id", name="uq_membership_user_id_company_id"),
        sa.UniqueConstraint("id", "company_id", name="uq_membership_id_company_id"),
        schema=SCHEMA,
        comment="Per-company membership and role.",
    )
    op.create_index(
        "ix_membership_company_id_status", "membership", ["company_id", "status"], schema=SCHEMA
    )
    op.create_index(
        "ix_membership_user_id_status", "membership", ["user_id", "status"], schema=SCHEMA
    )

    op.create_table(
        "auth_session",
        _pk(),
        sa.Column("token_hash", sa.String(length=64), nullable=False),
        sa.Column("csrf_token", sa.String(length=64), nullable=False),
        sa.Column("user_id", _UUID, nullable=False),
        sa.Column("company_id", _UUID, nullable=True),
        sa.Column("created_at", _TS, nullable=False, server_default=sa.text("now()")),
        sa.Column("last_activity_at", _TS, nullable=False, server_default=sa.text("now()")),
        sa.Column("expires_at", _TS, nullable=False),
        sa.Column("revoked_at", _TS, nullable=True),
        sa.Column("revoked_reason", sa.String(length=64), nullable=True),
        sa.Column("ip_address", postgresql.INET(), nullable=True),
        sa.Column("user_agent", sa.Text(), nullable=True),
        sa.ForeignKeyConstraint(
            ["user_id"],
            [f"{SCHEMA}.app_user.id"],
            name="fk_auth_session_user_id_app_user",
            ondelete="CASCADE",
        ),
        sa.ForeignKeyConstraint(
            ["company_id"],
            [f"{SCHEMA}.company.id"],
            name="fk_auth_session_company_id_company",
            ondelete="CASCADE",
        ),
        sa.CheckConstraint("expires_at > created_at", name="ck_auth_session_expiry_order"),
        sa.CheckConstraint(
            "(revoked_at IS NULL) OR (revoked_at >= created_at)",
            name="ck_auth_session_revoked_order",
        ),
        sa.CheckConstraint(
            "char_length(token_hash) = 64", name="ck_auth_session_token_hash_sha256"
        ),
        sa.CheckConstraint("char_length(csrf_token) BETWEEN 32 AND 64", name="ck_auth_session_csrf"),
        sa.UniqueConstraint("token_hash", name="uq_auth_session_token_hash"),
        schema=SCHEMA,
        comment="Server-side sessions with hashed tokens.",
    )
    op.create_index("ix_auth_session_user_id", "auth_session", ["user_id"], schema=SCHEMA)
    op.create_index("ix_auth_session_company_id", "auth_session", ["company_id"], schema=SCHEMA)
    op.create_index("ix_auth_session_expires_at", "auth_session", ["expires_at"], schema=SCHEMA)

    op.create_table(
        "login_attempt",
        _pk(),
        sa.Column("email_normalized", sa.Text(), nullable=False),
        sa.Column("ip_address", postgresql.INET(), nullable=True),
        sa.Column("succeeded", sa.Boolean(), nullable=False),
        sa.Column("reason", sa.String(length=64), nullable=True),
        sa.Column("attempted_at", _TS, nullable=False, server_default=sa.text("now()")),
        sa.CheckConstraint(
            "char_length(email_normalized) BETWEEN 3 AND 320", name="ck_login_email"
        ),
        schema=SCHEMA,
        comment="Login attempts for rate limiting and forensics.",
    )
    op.create_index(
        "ix_login_attempt_email_attempted_at",
        "login_attempt",
        ["email_normalized", "attempted_at"],
        schema=SCHEMA,
    )
    op.create_index(
        "ix_login_attempt_ip_attempted_at",
        "login_attempt",
        ["ip_address", "attempted_at"],
        schema=SCHEMA,
    )
    op.create_index(
        "ix_login_attempt_attempted_at", "login_attempt", ["attempted_at"], schema=SCHEMA
    )

    op.create_table(
        "audit_record",
        _pk(),
        sa.Column(
            "actor_type", sa.String(length=16), nullable=False, server_default=sa.text("'user'")
        ),
        sa.Column("actor_id", _UUID, nullable=True),
        sa.Column("company_id", _UUID, nullable=True),
        sa.Column("action", sa.String(length=80), nullable=False),
        sa.Column("outcome", sa.String(length=16), nullable=False),
        sa.Column("request_id", sa.String(length=128), nullable=True),
        sa.Column("occurred_at", _TS, nullable=False, server_default=sa.text("now()")),
        sa.Column("ip_address", postgresql.INET(), nullable=True),
        sa.Column("user_agent", sa.Text(), nullable=True),
        sa.Column("resource_type", sa.String(length=64), nullable=True),
        sa.Column("resource_id", sa.String(length=64), nullable=True),
        sa.Column("details", _JSONB, nullable=False, server_default=sa.text("'{}'::jsonb")),
        sa.ForeignKeyConstraint(
            ["company_id"],
            [f"{SCHEMA}.company.id"],
            name="fk_audit_record_company_id_company",
            ondelete="RESTRICT",
        ),
        sa.CheckConstraint("actor_type IN ('user', 'system', 'agent')", name="ck_audit_actor_type"),
        sa.CheckConstraint(
            "outcome IN ('success', 'failure', 'denied')", name="ck_audit_outcome"
        ),
        sa.CheckConstraint(
            "action IN ('auth.login.success', 'auth.login.failure', 'auth.logout', "
            "'session.company.switch', 'session.revoked', 'membership.changed', "
            "'access.denied', 'identity.bootstrap')",
            name="ck_audit_action",
        ),
        sa.CheckConstraint("char_length(action) BETWEEN 3 AND 80", name="ck_audit_action_length"),
        sa.CheckConstraint("jsonb_typeof(details) = 'object'", name="ck_audit_details_object"),
        schema=SCHEMA,
        comment="Append-only security audit trail.",
    )
    op.create_index("ix_audit_record_occurred_at", "audit_record", ["occurred_at"], schema=SCHEMA)
    op.create_index(
        "ix_audit_record_company_occurred_at",
        "audit_record",
        ["company_id", "occurred_at"],
        schema=SCHEMA,
    )
    op.create_index(
        "ix_audit_record_actor_occurred_at",
        "audit_record",
        ["actor_id", "occurred_at"],
        schema=SCHEMA,
    )
    op.create_index(
        "ix_audit_record_action_occurred_at",
        "audit_record",
        ["action", "occurred_at"],
        schema=SCHEMA,
    )


def _create_tenant_tables() -> None:
    op.create_table(
        "company_settings",
        _pk(),
        sa.Column("company_id", _UUID, nullable=False),
        sa.Column("timezone", sa.Text(), nullable=False, server_default=sa.text("'UTC'")),
        sa.Column("locale", sa.String(length=16), nullable=False, server_default=sa.text("'en'")),
        sa.Column("version", sa.Integer(), nullable=False, server_default=sa.text("1")),
        _created_at(),
        _updated_at(),
        sa.ForeignKeyConstraint(
            ["company_id"],
            [f"{SCHEMA}.company.id"],
            name="fk_company_settings_company_id_company",
            ondelete="CASCADE",
        ),
        sa.CheckConstraint("version >= 1", name="ck_company_settings_version"),
        sa.CheckConstraint("char_length(timezone) BETWEEN 1 AND 64", name="ck_company_settings_tz"),
        sa.CheckConstraint(
            "char_length(locale) BETWEEN 2 AND 16", name="ck_company_settings_locale"
        ),
        sa.UniqueConstraint("company_id", name="uq_company_settings_company_id"),
        sa.UniqueConstraint("id", "company_id", name="uq_company_settings_id_company_id"),
        schema=SCHEMA,
        comment="Tenant-scoped company settings (RLS protected).",
    )

    op.create_table(
        "company_setting_entry",
        _pk(),
        sa.Column("company_id", _UUID, nullable=False),
        sa.Column("settings_id", _UUID, nullable=False),
        sa.Column("key", sa.String(length=80), nullable=False),
        sa.Column("value", _JSONB, nullable=False),
        _created_at(),
        _updated_at(),
        sa.ForeignKeyConstraint(
            ["settings_id", "company_id"],
            [f"{SCHEMA}.company_settings.id", f"{SCHEMA}.company_settings.company_id"],
            name="fk_company_setting_entry_settings",
            ondelete="CASCADE",
        ),
        sa.CheckConstraint(
            "char_length(key) BETWEEN 1 AND 80", name="ck_company_setting_entry_key"
        ),
        sa.CheckConstraint(
            "jsonb_typeof(value) IN ('object', 'array', 'string', 'number', 'boolean')",
            name="ck_company_setting_entry_value",
        ),
        sa.UniqueConstraint("settings_id", "key", name="uq_company_setting_entry_settings_id_key"),
        schema=SCHEMA,
        comment="Tenant-scoped settings entries (RLS protected).",
    )
    op.create_index(
        "ix_company_setting_entry_company_id",
        "company_setting_entry",
        ["company_id"],
        schema=SCHEMA,
    )

    op.create_table(
        "idempotency_record",
        _pk(),
        sa.Column("actor_id", _UUID, nullable=True),
        sa.Column("company_id", _UUID, nullable=True),
        sa.Column("key", sa.String(length=200), nullable=False),
        sa.Column("request_fingerprint", sa.String(length=64), nullable=False),
        sa.Column(
            "status", sa.String(length=16), nullable=False, server_default=sa.text("'in_flight'")
        ),
        sa.Column("response_status", sa.Integer(), nullable=True),
        sa.Column("response_body", _JSONB, nullable=True),
        _created_at(),
        sa.Column("expires_at", _TS, nullable=False),
        sa.ForeignKeyConstraint(
            ["company_id"],
            [f"{SCHEMA}.company.id"],
            name="fk_idempotency_record_company_id_company",
            ondelete="CASCADE",
        ),
        sa.CheckConstraint(
            "status IN ('in_flight', 'completed', 'failed')", name="ck_idempotency_status"
        ),
        sa.CheckConstraint("char_length(key) BETWEEN 1 AND 200", name="ck_idempotency_key_length"),
        sa.CheckConstraint(
            "char_length(request_fingerprint) = 64", name="ck_idempotency_fingerprint"
        ),
        sa.UniqueConstraint(
            "actor_id", "company_id", "key", name="uq_idempotency_record_actor_company_key"
        ),
        schema=SCHEMA,
        comment="Idempotency records (RLS protected per company).",
    )
    op.create_index(
        "ix_idempotency_record_expires_at",
        "idempotency_record",
        ["expires_at"],
        schema=SCHEMA,
    )


def _create_tenant_helpers() -> None:
    """Transaction-scoped membership functions used by every RLS policy.

    ``current_setting(..., true)`` returns NULL when the setting was never set in
    this transaction, so a request without tenant context matches no rows
    instead of matching everything (fail closed).
    """
    op.execute(
        f"""
        CREATE OR REPLACE FUNCTION {SCHEMA}.current_company_id()
        RETURNS uuid
        LANGUAGE sql
        STABLE
        PARALLEL SAFE
        AS $$
            SELECT NULLIF(current_setting('touche.company_id', true), '')::uuid
        $$
        """
    )
    op.execute(
        f"""
        CREATE OR REPLACE FUNCTION {SCHEMA}.current_actor_id()
        RETURNS uuid
        LANGUAGE sql
        STABLE
        PARALLEL SAFE
        AS $$
            SELECT NULLIF(current_setting('touche.actor_id', true), '')::uuid
        $$
        """
    )
    op.execute(
        f"COMMENT ON FUNCTION {SCHEMA}.current_company_id() IS "
        "'Active tenant for RLS; set with SET LOCAL touche.company_id.'"
    )
    op.execute(
        f"COMMENT ON FUNCTION {SCHEMA}.current_actor_id() IS "
        "'Authenticated user for RLS; set with SET LOCAL touche.actor_id.'"
    )


def _tenant_policies(table: str) -> None:
    """Four explicit policies per tenant table (no implicit ALL policy)."""
    qualified = f"{SCHEMA}.{table}"
    predicate = "company_id = touche.current_company_id()"
    op.execute(f"ALTER TABLE {qualified} ENABLE ROW LEVEL SECURITY")
    op.execute(f"COMMENT ON TABLE {qualified} IS "
               f"'Tenant-owned table; RLS enforces company_id isolation.'")
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
    op.execute(f"CREATE POLICY {table}_tenant_delete ON {qualified} FOR DELETE USING ({predicate})")


def _apply_tenant_rls() -> None:
    for table in ("company_settings", "company_setting_entry", "idempotency_record"):
        _tenant_policies(table)

    # Companies are only visible to a user who holds a membership in them.
    op.execute(f"ALTER TABLE {SCHEMA}.company ENABLE ROW LEVEL SECURITY")
    op.execute(
        f"CREATE POLICY company_tenant_select ON {SCHEMA}.company FOR SELECT "
        f"USING (EXISTS (SELECT 1 FROM {SCHEMA}.membership m "
        "WHERE m.company_id = company.id AND m.user_id = touche.current_actor_id()))"
    )

    # Membership: a user always sees their own rows; company context unlocks the
    # whole roster (admin workflows will use it from Stage 1B).
    op.execute(f"ALTER TABLE {SCHEMA}.membership ENABLE ROW LEVEL SECURITY")
    read_predicate = (
        "user_id = touche.current_actor_id() OR company_id = touche.current_company_id()"
    )
    write_predicate = "company_id = touche.current_company_id()"
    op.execute(
        f"CREATE POLICY membership_tenant_select ON {SCHEMA}.membership "
        f"FOR SELECT USING ({read_predicate})"
    )
    op.execute(
        f"CREATE POLICY membership_tenant_insert ON {SCHEMA}.membership "
        f"FOR INSERT WITH CHECK ({write_predicate})"
    )
    op.execute(
        f"CREATE POLICY membership_tenant_update ON {SCHEMA}.membership "
        f"FOR UPDATE USING ({write_predicate}) WITH CHECK ({write_predicate})"
    )
    op.execute(
        f"CREATE POLICY membership_tenant_delete ON {SCHEMA}.membership "
        f"FOR DELETE USING ({write_predicate})"
    )

    # Audit: readable per tenant; system-level rows (company_id IS NULL, e.g. a
    # failed login before any company is known) are writable but not readable.
    op.execute(f"ALTER TABLE {SCHEMA}.audit_record ENABLE ROW LEVEL SECURITY")
    op.execute(
        f"CREATE POLICY audit_record_tenant_select ON {SCHEMA}.audit_record FOR SELECT "
        "USING (company_id IS NOT NULL AND company_id = touche.current_company_id())"
    )
    op.execute(
        f"CREATE POLICY audit_record_tenant_insert ON {SCHEMA}.audit_record FOR INSERT "
        "WITH CHECK (company_id IS NULL OR company_id = touche.current_company_id())"
    )


def _protect_audit_log() -> None:
    """Make ``audit_record`` append-only for every role, including the owner.

    The grant change below stops the runtime role; the trigger stops an
    accidental UPDATE/DELETE from any privileged maintenance script. Retention
    (ADR-016) must therefore run as the owner with the trigger explicitly
    disabled, which is an auditable, deliberate operation.
    """
    op.execute(
        f"""
        CREATE OR REPLACE FUNCTION {SCHEMA}.reject_audit_mutation()
        RETURNS trigger
        LANGUAGE plpgsql
        AS $$
        BEGIN
            RAISE EXCEPTION 'touche.audit_record is append-only; % is not permitted', TG_OP
                USING ERRCODE = 'insufficient_privilege';
        END;
        $$
        """
    )
    op.execute(
        f"CREATE TRIGGER audit_record_append_only BEFORE UPDATE OR DELETE "
        f"ON {SCHEMA}.audit_record FOR EACH ROW "
        f"EXECUTE FUNCTION {SCHEMA}.reject_audit_mutation()"
    )
    op.execute(
        f"CREATE TRIGGER audit_record_no_truncate BEFORE TRUNCATE "
        f"ON {SCHEMA}.audit_record FOR EACH STATEMENT "
        f"EXECUTE FUNCTION {SCHEMA}.reject_audit_mutation()"
    )


def _apply_grants() -> None:
    role = _app_role()
    schema = _quote(SCHEMA)
    op.execute(f"REVOKE ALL ON ALL TABLES IN SCHEMA {schema} FROM PUBLIC")
    op.execute(f"GRANT USAGE ON SCHEMA {schema} TO {role}")
    op.execute(f"REVOKE CREATE ON SCHEMA {schema} FROM {role}")
    op.execute(f"GRANT SELECT, INSERT, UPDATE, DELETE ON ALL TABLES IN SCHEMA {schema} TO {role}")
    op.execute(f"REVOKE TRUNCATE ON ALL TABLES IN SCHEMA {schema} FROM {role}")
    # The audit trail is insert-only for the runtime role.
    op.execute(f"REVOKE UPDATE, DELETE ON {schema}.audit_record FROM {role}")


def upgrade() -> None:
    _create_identity_tables()
    _create_tenant_tables()
    _create_tenant_helpers()
    _apply_tenant_rls()
    _protect_audit_log()
    _apply_grants()


def downgrade() -> None:
    for table in (
        "company_setting_entry",
        "company_settings",
        "idempotency_record",
        "audit_record",
        "login_attempt",
        "auth_session",
        "membership",
        "company",
        "app_user",
    ):
        op.drop_table(table, schema=SCHEMA)
    op.execute(f"DROP FUNCTION IF EXISTS {SCHEMA}.reject_audit_mutation()")
    op.execute(f"DROP FUNCTION IF EXISTS {SCHEMA}.current_actor_id()")
    op.execute(f"DROP FUNCTION IF EXISTS {SCHEMA}.current_company_id()")





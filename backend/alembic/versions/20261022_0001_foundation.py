"""stage 0 foundation: touche schema, outbox table, runtime role grants

Creates the minimum durable foundation for the platform:

* the ``touche`` schema that will own all application tables;
* ``touche.outbox_event`` — the transactional outbox table used by future
  E-YAY / Touche Finance integrations (docs/DECISIONS.md #17);
* least-privilege grants for the runtime role (no DDL, no BYPASSRLS).

Row level security policies, companies, memberships, sessions, idempotency
records and audit tables are added in Stage 1A.

Revision ID: 0001_foundation
Revises:
Create Date: 2026-10-22
"""

from __future__ import annotations

import os
from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision: str = "0001_foundation"
down_revision: str | None = None
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

SCHEMA = "touche"
_APP_ROLE_ENV = "TOUCHE_DB_APP_USER"
_DEFAULT_APP_ROLE = "touche_app"
_APP_PRIVILEGES = "SELECT, INSERT, UPDATE, DELETE"


def _quote(value: str) -> str:
    """Quote an SQL identifier using the PostgreSQL dialect rules."""
    return postgresql.dialect().identifier_preparer.quote(value)


def _app_role() -> str:
    role = os.environ.get(_APP_ROLE_ENV, _DEFAULT_APP_ROLE).strip()
    if not role:
        raise RuntimeError(f"{_APP_ROLE_ENV} must not be empty")
    return role


def upgrade() -> None:
    schema = _quote(SCHEMA)
    op.execute(f"CREATE SCHEMA IF NOT EXISTS {schema}")
    op.execute(
        f"COMMENT ON SCHEMA {schema} IS "
        "'TOUCHE COMMERCE application schema (owned by the migration role).'"
    )

    op.create_table(
        "outbox_event",
        sa.Column(
            "id",
            postgresql.UUID(as_uuid=True),
            primary_key=True,
            server_default=sa.text("gen_random_uuid()"),
        ),
        sa.Column("company_id", postgresql.UUID(as_uuid=True), nullable=True),
        sa.Column("event_type", sa.String(length=120), nullable=False),
        sa.Column("aggregate_type", sa.String(length=64), nullable=False),
        sa.Column("aggregate_id", sa.String(length=64), nullable=False),
        sa.Column("payload", postgresql.JSONB(astext_type=sa.Text()), nullable=False),
        sa.Column(
            "occurred_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.text("now()"),
        ),
        sa.Column(
            "available_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.text("now()"),
        ),
        sa.Column("attempts", sa.Integer(), nullable=False, server_default=sa.text("0")),
        sa.Column("last_error", sa.Text(), nullable=True),
        sa.Column("processed_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.text("now()"),
        ),
        schema=SCHEMA,
        comment="Transactional outbox for future E-YAY / Touche Finance integrations.",
    )
    op.create_index(
        "ix_outbox_event_pending",
        "outbox_event",
        ["available_at"],
        schema=SCHEMA,
        postgresql_where=sa.text("processed_at IS NULL"),
    )
    op.create_index(
        "ix_outbox_event_company_occurred_at",
        "outbox_event",
        ["company_id", "occurred_at"],
        schema=SCHEMA,
    )

    # Least privilege for the runtime role. DDL stays with the migration role.
    role = _quote(_app_role())
    op.execute(f"GRANT USAGE ON SCHEMA {schema} TO {role}")
    op.execute(f"GRANT {_APP_PRIVILEGES} ON ALL TABLES IN SCHEMA {schema} TO {role}")
    op.execute(f"GRANT USAGE, SELECT ON ALL SEQUENCES IN SCHEMA {schema} TO {role}")
    op.execute(
        f"ALTER DEFAULT PRIVILEGES IN SCHEMA {schema} "
        f"GRANT {_APP_PRIVILEGES} ON TABLES TO {role}"
    )
    op.execute(
        f"ALTER DEFAULT PRIVILEGES IN SCHEMA {schema} "
        f"GRANT USAGE, SELECT ON SEQUENCES TO {role}"
    )
    # The runtime role must never be able to create objects in this schema.
    op.execute(f"REVOKE CREATE ON SCHEMA {schema} FROM {role}")


def downgrade() -> None:
    op.drop_index(
        "ix_outbox_event_company_occurred_at", table_name="outbox_event", schema=SCHEMA
    )
    op.drop_index("ix_outbox_event_pending", table_name="outbox_event", schema=SCHEMA)
    op.drop_table("outbox_event", schema=SCHEMA)
    op.execute(f"DROP SCHEMA IF EXISTS {_quote(SCHEMA)} CASCADE")

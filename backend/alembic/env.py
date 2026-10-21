"""Alembic environment for TOUCHE COMMERCE.

Migrations run with the *migration* role (TOUCHE_DATABASE_MIGRATION_URL), which
owns the schema and can run DDL.  The runtime role (TOUCHE_DATABASE_URL) never
executes migrations and has no DDL rights (docs/DECISIONS.md #4).
"""

from __future__ import annotations

import sys
from logging.config import fileConfig
from pathlib import Path

from alembic import context
from sqlalchemy import engine_from_config, pool

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from app.core.config import get_settings
from app.db.models import Base

config = context.config

if config.config_file_name is not None:
    fileConfig(config.config_file_name, disable_existing_loggers=False)

settings = get_settings()
# Escape '%' so ConfigParser interpolation does not mangle password characters.
config.set_main_option("sqlalchemy.url", settings.migration_dsn.replace("%", "%%"))

target_metadata = Base.metadata

_VERSION_TABLE_SCHEMA = "public"


def _configure_kwargs() -> dict[str, object]:
    return {
        "target_metadata": target_metadata,
        "compare_type": True,
        "compare_server_default": True,
        "include_schemas": True,
        "version_table_schema": _VERSION_TABLE_SCHEMA,
    }


def run_migrations_offline() -> None:
    """Emit SQL without a DBAPI connection (``alembic upgrade head --sql``)."""
    context.configure(
        url=config.get_main_option("sqlalchemy.url"),
        literal_binds=True,
        dialect_opts={"paramstyle": "named"},
        **_configure_kwargs(),
    )
    with context.begin_transaction():
        context.run_migrations()


def run_migrations_online() -> None:
    """Run migrations against the database."""
    section = config.get_section(config.config_ini_section, {})
    connectable = engine_from_config(section, prefix="sqlalchemy.", poolclass=pool.NullPool)
    with connectable.connect() as connection:
        context.configure(connection=connection, **_configure_kwargs())
        with context.begin_transaction():
            context.run_migrations()


if context.is_offline_mode():
    run_migrations_offline()
else:
    run_migrations_online()

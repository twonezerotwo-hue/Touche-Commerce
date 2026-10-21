"""Declarative base and shared naming conventions for ORM models."""

from __future__ import annotations

from sqlalchemy import MetaData
from sqlalchemy.orm import DeclarativeBase

# Deterministic constraint names keep Alembic autogenerate diffs meaningful.
NAMING_CONVENTION = {
    "ix": "ix_%(table_name)s_%(column_0_name)s",
    "uq": "uq_%(table_name)s_%(column_0_name)s",
    "ck": "ck_%(table_name)s_%(constraint_name)s",
    "fk": "fk_%(table_name)s_%(column_0_name)s_%(referred_table_name)s",
    "pk": "pk_%(table_name)s",
}

SCHEMA = "touche"


class Base(DeclarativeBase):
    """Base class for all TOUCHE COMMERCE ORM models."""

    metadata = MetaData(naming_convention=NAMING_CONVENTION, schema=SCHEMA)

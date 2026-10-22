"""Shared write metadata and small helpers for the trade services."""

from __future__ import annotations

from dataclasses import dataclass
from uuid import UUID


@dataclass(frozen=True)
class WriteMeta:
    """Values every audited write needs, captured once by the route."""

    company_id: UUID
    actor_id: UUID
    request_id: str | None = None
    ip_address: str | None = None
    user_agent: str | None = None


def escape_like(value: str) -> str:
    """Escape SQL ``LIKE`` wildcards so a search term is never a pattern."""
    return value.replace("\\", "\\\\").replace("%", "\\%").replace("_", "\\_")


def clean_optional(value: str | None) -> str | None:
    """Trim optional text and collapse an empty string to ``None``."""
    if value is None:
        return None
    cleaned = value.strip()
    return cleaned or None


__all__ = ["WriteMeta", "clean_optional", "escape_like"]

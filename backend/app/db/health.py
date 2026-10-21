"""Database readiness result types (transport agnostic)."""

from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True, slots=True)
class DatabaseReadiness:
    """Outcome of a database readiness probe."""

    ok: bool
    latency_ms: float
    server_version: str | None = None
    role: str | None = None
    error_code: str | None = None
    error_message: str | None = None

    @property
    def detail(self) -> str:
        """Human readable detail, safe to expose (never contains credentials)."""
        if self.ok:
            version = self.server_version or "unknown"
            role = self.role or "unknown"
            return f"PostgreSQL {version} reachable as role '{role}'."
        return self.error_message or "Database is unavailable."

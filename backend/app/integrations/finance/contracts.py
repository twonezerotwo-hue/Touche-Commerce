"""Stable contracts for the Finance integration boundary.

The dataclass is intentionally small: Stage 5A can prove that Finance is
reachable and reports a consistent ledger, but it cannot read commercial
balances or post accounting entries.  A future read-only adapter must implement
:class:`FinanceHealthProbe` (or a successor protocol) only after Finance exposes
a versioned, authenticated integration endpoint.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from enum import StrEnum
from typing import Any, Protocol


class FinanceLinkState(StrEnum):
    """Outcome of one read-only Finance health probe."""

    DISABLED = "disabled"
    HEALTHY = "healthy"
    DEGRADED = "degraded"
    UNREACHABLE = "unreachable"
    INCOMPATIBLE = "incompatible"


@dataclass(frozen=True, slots=True)
class FinanceHealth:
    """Result of probing Finance's public, read-only ``GET /api/health``.

    ``reports_local_admin_session`` mirrors Finance's ``yerel`` flag.  It is
    diagnostic only: Commerce never relies on being treated as a local admin,
    because that would be network-position authorisation rather than a service
    credential.
    """

    state: FinanceLinkState
    finance_status: str | None
    latency_ms: float
    detail: str
    checked_at: datetime
    reports_local_admin_session: bool | None = None


class FinanceHealthProbe(Protocol):
    """Minimal protocol so service tests never need a real socket."""

    def probe(self) -> FinanceHealth:
        """Return one health observation without mutating Finance."""
        ...


@dataclass(frozen=True, slots=True)
class FinanceApiResponse:
    """One authenticated Finance v1 response plus its server metadata."""

    data: dict[str, Any]
    request_id: str | None
    generated_at: str | None

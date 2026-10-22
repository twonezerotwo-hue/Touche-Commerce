"""Response schema for the Stage 5A Finance integration status endpoint."""

from __future__ import annotations

from datetime import datetime
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field

from app.integrations.finance.contracts import FinanceLinkState


class FinanceLinkStatusResponse(BaseModel):
    """One read-only observation of the local Finance link.

    The two literal fields are part of the contract, not documentation: a client
    can assert that Stage 5A never claims an accounting capability.
    """

    model_config = ConfigDict(
        json_schema_extra={
            "example": {
                "state": "healthy",
                "finance_status": "ok",
                "latency_ms": 4.12,
                "detail": "Finance reports a consistent ledger.",
                "checked_at": "2026-10-22T09:30:00+00:00",
                "scope": "health_only",
                "accounting_writes_enabled": False,
            }
        }
    )

    state: FinanceLinkState = Field(description="Observed link state.")
    finance_status: str | None = Field(
        default=None,
        description="Raw Finance health value ('ok' or 'degraded') when one was returned.",
    )
    latency_ms: float = Field(ge=0, description="Probe duration in milliseconds.")
    detail: str = Field(description="Credential-free diagnostic text.")
    checked_at: datetime = Field(description="Server-side UTC timestamp of the probe.")
    scope: Literal["health_only"] = Field(
        default="health_only",
        description="Stage 5A is restricted to the public Finance health endpoint.",
    )
    accounting_writes_enabled: Literal[False] = Field(
        default=False,
        description="Always false: Commerce never posts invoices, payments or ledger entries.",
    )

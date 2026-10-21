"""Response schemas for health endpoints (also the OpenAPI source of truth)."""

from __future__ import annotations

from datetime import datetime
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field

HealthStatus = Literal["ok", "error"]


class HealthLiveResponse(BaseModel):
    """Liveness result: proves the process is running and serving HTTP."""

    model_config = ConfigDict(
        json_schema_extra={
            "example": {
                "status": "ok",
                "service": "touche-commerce-api",
                "version": "0.1.0",
                "environment": "local",
                "checked_at": "2026-10-22T09:30:00+00:00",
            }
        }
    )

    status: Literal["ok"] = "ok"
    service: str = Field(description="Service identifier.")
    version: str = Field(description="Deployed application version.")
    environment: str = Field(description="Deployment environment name.")
    checked_at: datetime = Field(description="Server-side UTC timestamp of the probe.")


class HealthCheckResult(BaseModel):
    """Outcome of a single dependency check."""

    name: str = Field(description="Dependency name, e.g. 'database'.")
    status: HealthStatus
    latency_ms: float = Field(ge=0, description="Probe duration in milliseconds.")
    detail: str = Field(description="Human readable, credential-free detail.")
    error_code: str | None = Field(
        default=None, description="Machine readable failure reason when status is 'error'."
    )


class ReadinessResponse(BaseModel):
    """Readiness result: proves required dependencies are usable."""

    model_config = ConfigDict(
        json_schema_extra={
            "example": {
                "status": "ready",
                "service": "touche-commerce-api",
                "version": "0.1.0",
                "environment": "local",
                "checked_at": "2026-10-22T09:30:00+00:00",
                "checks": [
                    {
                        "name": "database",
                        "status": "ok",
                        "latency_ms": 4.12,
                        "detail": "PostgreSQL 17.6 reachable as role 'touche_app'.",
                        "error_code": None,
                    }
                ],
            }
        }
    )

    status: Literal["ready"] = "ready"
    service: str
    version: str
    environment: str
    checked_at: datetime
    checks: list[HealthCheckResult]

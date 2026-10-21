"""Health endpoints.

* ``/health/live``  — liveness; must never touch PostgreSQL.
* ``/health/ready`` — readiness; verifies required dependencies (database).
"""

from __future__ import annotations

from datetime import UTC, datetime

from fastapi import APIRouter, Depends, status

from app.api.deps import app_settings, get_database
from app.api.v1.schemas.errors import ErrorEnvelope
from app.api.v1.schemas.health import (
    HealthCheckResult,
    HealthLiveResponse,
    ReadinessResponse,
)
from app.core.config import Settings
from app.core.errors import NotReadyError
from app.db.engine import Database

router = APIRouter(tags=["health"])


@router.get(
    "/health/live",
    response_model=HealthLiveResponse,
    summary="Liveness probe",
    description=(
        "Returns 200 as soon as the API process can serve HTTP. "
        "It deliberately performs no database, cache or network I/O so a "
        "dependency outage cannot cause the orchestrator to kill a healthy process."
    ),
    responses={
        200: {"description": "The service process is alive."},
    },
)
def health_live(settings: Settings = Depends(app_settings)) -> HealthLiveResponse:
    return HealthLiveResponse(
        service=settings.service_name,
        version=settings.app_version,
        environment=settings.environment,
        checked_at=datetime.now(tz=UTC),
    )


@router.get(
    "/health/ready",
    response_model=ReadinessResponse,
    summary="Readiness probe",
    description=(
        "Verifies that required dependencies are usable. Currently checks the "
        "PostgreSQL connection using the runtime role. Returns 503 with the "
        "standard error envelope when a dependency is unavailable."
    ),
    responses={
        200: {"description": "All required dependencies are reachable."},
        503: {"model": ErrorEnvelope, "description": "A required dependency is unavailable."},
    },
    status_code=status.HTTP_200_OK,
)
def health_ready(
    settings: Settings = Depends(app_settings),
    database: Database = Depends(get_database),
) -> ReadinessResponse:
    readiness = database.check_readiness()
    database_check = HealthCheckResult(
        name="database",
        status="ok" if readiness.ok else "error",
        latency_ms=readiness.latency_ms,
        detail=readiness.detail,
        error_code=readiness.error_code,
    )
    checked_at = datetime.now(tz=UTC)

    if not readiness.ok:
        raise NotReadyError(
            details={
                "status": "not_ready",
                "checks": [database_check.model_dump(mode="json")],
            }
        )

    return ReadinessResponse(
        service=settings.service_name,
        version=settings.app_version,
        environment=settings.environment,
        checked_at=checked_at,
        checks=[database_check],
    )

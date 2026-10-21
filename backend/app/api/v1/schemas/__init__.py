"""API schemas (Pydantic models) — the source of the generated TypeScript types."""

from app.api.v1.schemas.errors import ErrorDetail, ErrorEnvelope
from app.api.v1.schemas.health import (
    HealthCheckResult,
    HealthLiveResponse,
    ReadinessResponse,
)

__all__ = [
    "ErrorDetail",
    "ErrorEnvelope",
    "HealthCheckResult",
    "HealthLiveResponse",
    "ReadinessResponse",
]

"""Error envelope schemas used for OpenAPI documentation."""

from __future__ import annotations

from datetime import datetime
from typing import Any

from pydantic import BaseModel, ConfigDict, Field


class ErrorDetail(BaseModel):
    """Machine readable error description."""

    code: str = Field(description="Stable error code, e.g. NOT_READY.")
    message: str = Field(description="Human readable message (safe to display).")
    request_id: str | None = Field(default=None, description="Correlation id for support.")
    timestamp: datetime = Field(description="UTC timestamp of the error.")
    details: Any | None = Field(default=None, description="Optional structured context.")


class ErrorEnvelope(BaseModel):
    """Every non-2xx response uses this envelope."""

    model_config = ConfigDict(
        json_schema_extra={
            "example": {
                "error": {
                    "code": "NOT_READY",
                    "message": "The service is not ready to handle requests.",
                    "request_id": "9f1c2b7d4a8e4c1b9d0e5f6a7b8c9d0e",
                    "timestamp": "2026-10-22T09:30:00+00:00",
                    "details": None,
                }
            }
        }
    )

    error: ErrorDetail

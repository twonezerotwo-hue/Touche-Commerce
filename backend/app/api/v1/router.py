"""Versioned API router aggregation (mounted at /api/v1)."""

from fastapi import APIRouter

from app.api.v1.routes import health

api_router = APIRouter()
api_router.include_router(health.router)

__all__ = ["api_router"]

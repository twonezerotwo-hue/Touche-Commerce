"""Versioned API router aggregation (mounted at /api/v1)."""

from fastapi import APIRouter

from app.api.v1.routes import auth, companies, health

api_router = APIRouter()
api_router.include_router(health.router)
api_router.include_router(auth.router)
api_router.include_router(companies.router)

__all__ = ["api_router"]


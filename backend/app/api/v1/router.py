"""Versioned API router aggregation (mounted at /api/v1)."""

from fastapi import APIRouter

from app.api.v1.routes import (
    auth,
    companies,
    counterparties,
    dashboard,
    deals,
    fx_rates,
    health,
    pricing_scenarios,
    products,
    rfqs,
    sales_quotes,
    supplier_quotes,
)

api_router = APIRouter()
api_router.include_router(health.router)
api_router.include_router(auth.router)
api_router.include_router(companies.router)
api_router.include_router(counterparties.router)
api_router.include_router(products.router)
api_router.include_router(deals.router)
api_router.include_router(dashboard.router)
api_router.include_router(fx_rates.router)
api_router.include_router(rfqs.router)
api_router.include_router(supplier_quotes.router)
api_router.include_router(pricing_scenarios.router)
api_router.include_router(sales_quotes.router)

__all__ = ["api_router"]


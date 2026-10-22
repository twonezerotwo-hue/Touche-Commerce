"""Versioned API router aggregation (mounted at /api/v1)."""

from fastapi import APIRouter

from app.api.v1.routes import (
    auth,
    companies,
    counterparties,
    dashboard,
    deals,
    documents,
    finance,
    fx_rates,
    health,
    integrations,
    orders,
    pricing_scenarios,
    products,
    purchase_orders,
    reconciliation,
    rfqs,
    sales_quotes,
    shipments,
    supplier_quotes,
)

api_router = APIRouter()
api_router.include_router(health.router)
api_router.include_router(integrations.router)
api_router.include_router(finance.router)
api_router.include_router(reconciliation.router)
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
# Stage 4: sales orders must be registered before the generic document routes so
# ``/sales-orders/{id}/documents/preview`` is matched by its own handler.
api_router.include_router(orders.router)
api_router.include_router(purchase_orders.router)
api_router.include_router(shipments.router)
api_router.include_router(documents.router)

__all__ = ["api_router"]

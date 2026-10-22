"""FastAPI application factory for the TOUCHE COMMERCE API.

Stage 0 scope: configuration, observability, error contract, database
foundation and health endpoints.  Authentication, sessions, multi-company
scoping and business modules are explicitly Stage 1A+ work.
"""

from __future__ import annotations

from collections.abc import AsyncIterator
from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from app.api.v1.router import api_router
from app.core.config import Settings, get_settings
from app.core.errors import register_exception_handlers
from app.core.logging import configure_logging, get_logger
from app.core.middleware import OriginValidationMiddleware, RequestContextMiddleware
from app.db.engine import Database

logger = get_logger("app.main")

_ALLOWED_HEADERS = [
    "Accept",
    "Content-Type",
    "X-Request-ID",
    "X-CSRF-Token",
    "Idempotency-Key",
    "If-Match",
]
_EXPOSED_HEADERS = ["X-Request-ID", "ETag", "Retry-After"]
_ALLOWED_METHODS = ["GET", "POST", "PUT", "PATCH", "DELETE", "OPTIONS"]


def create_app(settings: Settings | None = None) -> FastAPI:
    """Build the ASGI application (explicit settings make testing trivial)."""
    resolved = settings or get_settings()
    configure_logging(resolved)
    database = Database(resolved)

    @asynccontextmanager
    async def lifespan(_app: FastAPI) -> AsyncIterator[None]:
        logger.info(
            "service.started",
            extra={
                "deployment_environment": resolved.environment,
                "app_version": resolved.app_version,
                "api_prefix": resolved.api_prefix,
                "database_configured": database.is_configured,
            },
        )
        try:
            yield
        finally:
            database.dispose()
            logger.info("service.stopped")

    app = FastAPI(
        title=resolved.app_name,
        version=resolved.app_version,
        description=(
            "TOUCHE COMMERCE trade management API. Stage 1A exposes identity "
            "(server-side sessions), multi-company membership and tenant isolation "
            "on top of the Stage 0 foundation."
        ),
        lifespan=lifespan,
        openapi_url=resolved.api_openapi_url,
        docs_url="/docs" if resolved.docs_enabled else None,
        redoc_url=None,
        openapi_tags=[
            {
                "name": "health",
                "description": "Liveness and readiness probes used by the UI and orchestrators.",
            },
            {
                "name": "auth",
                "description": (
                    "Sign-in, sign-out and the current session profile. Sessions are "
                    "server-side rows; the browser holds only an HttpOnly cookie."
                ),
            },
            {
                "name": "companies",
                "description": (
                    "Company discovery and active-company selection. Access is always "
                    "derived from verified memberships, never from a client-supplied id."
                ),
            },
            {
                "name": "meta",
                "description": "Service identity and discovery endpoints.",
            },
            {
                "name": "counterparties",
                "description": (
                    "Tenant-scoped customers and suppliers. Reads need company.view; "
                    "writes need trade.write and support Idempotency-Key and If-Match."
                ),
            },
            {
                "name": "products",
                "description": (
                    "Tenant-scoped product catalogue with SKU, unit, currency and price."
                ),
            },
            {
                "name": "deals",
                "description": (
                    "Trade deals with a validated state machine. Status only changes "
                    "through POST /deals/{id}/transitions; WON is disabled until sales "
                    "orders exist."
                ),
            },
            {
                "name": "dashboard",
                "description": "Aggregates for the command center, scoped to the active company.",
            },
        ],
    )

    app.state.settings = resolved
    app.state.database = database

    register_exception_handlers(app)

    # Order (outermost first): CORS → request correlation → origin validation →
    # routes, so rejected origins still carry an X-Request-ID.
    app.add_middleware(OriginValidationMiddleware, allowed_origins=resolved.trusted_origins)
    app.add_middleware(RequestContextMiddleware)
    app.add_middleware(
        CORSMiddleware,
        allow_origins=resolved.cors_allowed_origins,
        allow_credentials=resolved.cors_allow_credentials,
        allow_methods=_ALLOWED_METHODS,
        allow_headers=_ALLOWED_HEADERS,
        expose_headers=_EXPOSED_HEADERS,
        max_age=600,
    )

    app.include_router(api_router, prefix=resolved.api_prefix)

    @app.get("/", tags=["meta"], summary="Service descriptor")
    def service_descriptor() -> dict[str, str]:
        return {
            "service": resolved.service_name,
            "version": resolved.app_version,
            "environment": resolved.environment,
            "api": resolved.api_prefix,
            "docs": "/docs" if resolved.docs_enabled else "disabled",
            "liveness": f"{resolved.api_prefix}/health/live",
            "readiness": f"{resolved.api_prefix}/health/ready",
        }

    return app

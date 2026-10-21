"""Shared FastAPI dependencies."""

from __future__ import annotations

from typing import cast

from fastapi import Request

from app.core.config import Settings
from app.db.engine import Database


def app_settings(request: Request) -> Settings:
    """Return the settings instance bound to the running application."""
    return cast(Settings, request.app.state.settings)


def get_database(request: Request) -> Database:
    """Return the application-scoped database handle."""
    return cast(Database, request.app.state.database)

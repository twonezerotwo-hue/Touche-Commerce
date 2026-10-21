"""Session cookie helpers.

The cookie is ``HttpOnly`` (JavaScript cannot read it), ``SameSite=Lax`` and
``Secure`` outside local development, where it also receives the ``__Host-``
prefix. The CSRF token is delivered in the response body instead of a readable
cookie, so an XSS payload gains nothing it could not already do same-origin.
"""

from __future__ import annotations

from fastapi import Response

from app.core.config import Settings


def set_session_cookie(response: Response, settings: Settings, *, token: str) -> None:
    response.set_cookie(
        key=settings.effective_session_cookie_name,
        value=token,
        max_age=settings.session_cookie_max_age,
        path=settings.session_cookie_path,
        domain=settings.session_cookie_domain,
        secure=settings.secure_cookies,
        httponly=True,
        samesite=settings.session_cookie_samesite,
    )


def clear_session_cookie(response: Response, settings: Settings) -> None:
    response.delete_cookie(
        key=settings.effective_session_cookie_name,
        path=settings.session_cookie_path,
        domain=settings.session_cookie_domain,
        secure=settings.secure_cookies,
        httponly=True,
        samesite=settings.session_cookie_samesite,
    )


def mark_no_store(response: Response) -> None:
    """Session-bearing responses must never be cached by a proxy or browser."""
    response.headers["Cache-Control"] = "no-store"
    response.headers["Vary"] = "Cookie"

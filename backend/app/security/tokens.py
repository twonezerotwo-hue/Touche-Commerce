"""Opaque session and CSRF tokens.

Session tokens are 256 bits of entropy, URL-safe. Only their SHA-256 digest is
persisted, so a database leak does not yield usable cookies (docs/DECISIONS.md
#2). SHA-256 is sufficient here because the input is already high entropy —
there is nothing to brute force, unlike a user-chosen password.
"""

from __future__ import annotations

import hashlib
import hmac
import secrets

SESSION_TOKEN_BYTES = 32
CSRF_TOKEN_BYTES = 32
_MAX_TOKEN_LENGTH = 256


def generate_session_token() -> str:
    """Return a fresh, unguessable session token (never stored in plaintext)."""
    return secrets.token_urlsafe(SESSION_TOKEN_BYTES)


def generate_csrf_token() -> str:
    """Return a fresh CSRF token bound to a single session."""
    return secrets.token_urlsafe(CSRF_TOKEN_BYTES)


def hash_token(token: str) -> str:
    """Return the hex SHA-256 digest used for storage and lookup."""
    if len(token) > _MAX_TOKEN_LENGTH:
        raise ValueError("Token is longer than any token this service issues.")
    return hashlib.sha256(token.encode("utf-8")).hexdigest()


def constant_time_equals(left: str, right: str) -> bool:
    """Compare two secrets without leaking their common prefix length."""
    return hmac.compare_digest(left.encode("utf-8"), right.encode("utf-8"))

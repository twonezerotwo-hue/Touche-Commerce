"""Security primitives: password hashing, opaque tokens and authorization.

Nothing in this package touches the database or the HTTP layer, which keeps it
trivially unit testable and safe to reuse from the CLI, the API and (later) AI
tool adapters.
"""

from app.security.passwords import (
    PasswordPolicyError,
    PasswordService,
    validate_password_strength,
)
from app.security.permissions import (
    ROLE_PERMISSIONS,
    Permission,
    Role,
    has_permission,
    permissions_for,
)
from app.security.tokens import (
    constant_time_equals,
    generate_csrf_token,
    generate_session_token,
    hash_token,
)

__all__ = [
    "ROLE_PERMISSIONS",
    "PasswordPolicyError",
    "PasswordService",
    "Permission",
    "Role",
    "constant_time_equals",
    "generate_csrf_token",
    "generate_session_token",
    "has_permission",
    "hash_token",
    "permissions_for",
    "validate_password_strength",
]

"""Argon2id password hashing.

Argon2id is the only accepted algorithm (docs/DECISIONS.md #20). Parameters are
configuration, not constants, so tests can use a cheap profile and production
can raise the cost without a code change. Only the encoded hash is ever stored;
plaintext passwords never leave the request that carried them.
"""

from __future__ import annotations

import secrets

from argon2 import PasswordHasher
from argon2.exceptions import InvalidHashError, VerificationError

from app.core.config import Settings

# Argon2 itself is fast on short inputs; the cap protects against a caller
# sending a multi-megabyte "password" to burn CPU.
MAX_PASSWORD_LENGTH = 512

_DUMMY_PASSWORD = secrets.token_urlsafe(32)


class PasswordPolicyError(ValueError):
    """Raised when a candidate password does not satisfy the policy."""


def validate_password_strength(password: str, *, min_length: int = 12) -> None:
    """Enforce the documented policy; raise :class:`PasswordPolicyError`."""
    if len(password) < min_length:
        raise PasswordPolicyError(f"Password must be at least {min_length} characters long.")
    if len(password) > MAX_PASSWORD_LENGTH:
        raise PasswordPolicyError(
            f"Password must be at most {MAX_PASSWORD_LENGTH} characters long."
        )
    if password.strip() != password:
        raise PasswordPolicyError("Password must not start or end with whitespace.")
    classes = sum(
        (
            any(character.islower() for character in password),
            any(character.isupper() for character in password),
            any(character.isdigit() for character in password),
            any(not character.isalnum() for character in password),
        )
    )
    if classes < 3:
        raise PasswordPolicyError(
            "Password must combine at least three of: lower case, upper case, digits, symbols."
        )


class PasswordService:
    """Thin, deterministic wrapper around :class:`argon2.PasswordHasher`."""

    def __init__(self, settings: Settings) -> None:
        self._hasher = PasswordHasher(
            time_cost=settings.argon2_time_cost,
            memory_cost=settings.argon2_memory_cost_kib,
            parallelism=settings.argon2_parallelism,
            hash_len=32,
            salt_len=16,
        )
        self._dummy_hash: str | None = None

    def hash(self, password: str) -> str:
        """Return an Argon2id encoded hash (algorithm and salt embedded)."""
        if len(password) > MAX_PASSWORD_LENGTH:
            raise PasswordPolicyError("Password is too long.")
        return self._hasher.hash(password)

    def verify(self, password_hash: str, password: str) -> bool:
        """Verify a candidate password without leaking *why* it failed."""
        if len(password) > MAX_PASSWORD_LENGTH:
            return False
        try:
            return self._hasher.verify(password_hash, password)
        except (VerificationError, InvalidHashError):
            return False

    def needs_rehash(self, password_hash: str) -> bool:
        """True when the stored hash predates the current cost parameters."""
        try:
            return self._hasher.check_needs_rehash(password_hash)
        except InvalidHashError:
            return True

    def verify_dummy(self, password: str) -> None:
        """Burn the same work for unknown accounts to reduce timing leakage."""
        if self._dummy_hash is None:
            self._dummy_hash = self._hasher.hash(_DUMMY_PASSWORD)
        self.verify(self._dummy_hash, password)

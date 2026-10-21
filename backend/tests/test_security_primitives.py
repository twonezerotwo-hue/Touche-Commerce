"""Unit tests for the Stage 1A security primitives (no database required)."""

from __future__ import annotations

from datetime import UTC, datetime, timedelta
from uuid import uuid4

import pytest
from pydantic import SecretStr

from app.core.config import Settings
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
    sorted_permission_values,
)
from app.security.tokens import (
    constant_time_equals,
    generate_csrf_token,
    generate_session_token,
    hash_token,
)
from app.services.audit import REDACTED, is_sensitive_key, normalise_ip, redact_details
from app.services.auth import ActorSummary, SessionContext, normalize_email

TEST_PASSWORD = "Correct-Horse-Battery-9"


@pytest.fixture()
def password_service(settings: Settings) -> PasswordService:
    return PasswordService(settings)


class TestPasswordHashing:
    def test_hash_is_argon2id_and_never_contains_the_password(
        self, password_service: PasswordService
    ) -> None:
        encoded = password_service.hash(TEST_PASSWORD)
        assert encoded.startswith("$argon2id$")
        assert TEST_PASSWORD not in encoded
        assert password_service.verify(encoded, TEST_PASSWORD) is True

    def test_wrong_password_is_rejected(self, password_service: PasswordService) -> None:
        encoded = password_service.hash(TEST_PASSWORD)
        assert password_service.verify(encoded, "Correct-Horse-Battery-0") is False
        assert password_service.verify(encoded, "") is False

    def test_garbage_hash_is_rejected_without_raising(
        self, password_service: PasswordService
    ) -> None:
        assert password_service.verify("not-a-hash", TEST_PASSWORD) is False
        assert password_service.needs_rehash("not-a-hash") is True

    def test_same_password_produces_different_hashes(
        self, password_service: PasswordService
    ) -> None:
        assert password_service.hash(TEST_PASSWORD) != password_service.hash(TEST_PASSWORD)

    def test_dummy_verification_accepts_any_input(self, password_service: PasswordService) -> None:
        password_service.verify_dummy("anything")
        password_service.verify_dummy("")

    @pytest.mark.parametrize(
        "password",
        [
            "short",
            "alllowercaseletters",
            " leading-space-9A",
            "trailing-space-9A ",
            "A1" + "x" * 600,
        ],
    )
    def test_policy_rejects_weak_input(self, password: str) -> None:
        with pytest.raises(PasswordPolicyError):
            validate_password_strength(password, min_length=12)

    def test_policy_accepts_three_character_classes(self) -> None:
        validate_password_strength("correct-Horse-9", min_length=12)


class TestTokens:
    def test_session_tokens_are_long_unique_and_url_safe(self) -> None:
        first = generate_session_token()
        second = generate_session_token()
        assert first != second
        assert len(first) >= 43
        assert all(character.isalnum() or character in "-_" for character in first)

    def test_hash_is_stable_sha256_hex(self) -> None:
        token = generate_session_token()
        digest = hash_token(token)
        assert len(digest) == 64
        assert digest == hash_token(token)
        assert digest != hash_token(generate_session_token())

    def test_constant_time_compare(self) -> None:
        assert constant_time_equals("abc", "abc") is True
        assert constant_time_equals("abc", "abd") is False
        assert constant_time_equals("", "a") is False

    def test_oversized_token_is_refused(self) -> None:
        with pytest.raises(ValueError):
            hash_token("x" * 300)

    def test_csrf_tokens_are_unique(self) -> None:
        assert generate_csrf_token() != generate_csrf_token()


class TestPermissionMatrix:
    def test_admin_never_holds_financial_approval(self) -> None:
        assert Permission.FINANCE_APPROVE not in permissions_for(Role.ADMIN)
        assert has_permission(Role.ADMIN, Permission.FINANCE_APPROVE) is False
        assert has_permission("admin", "finance.approve") is False

    def test_approver_can_approve_but_cannot_manage_memberships(self) -> None:
        assert has_permission(Role.APPROVER, Permission.FINANCE_APPROVE) is True
        assert has_permission(Role.APPROVER, Permission.MEMBERSHIP_MANAGE) is False
        assert has_permission(Role.APPROVER, Permission.SETTINGS_MANAGE) is False

    def test_viewer_is_read_only(self) -> None:
        assert permissions_for(Role.VIEWER) == {
            Permission.COMPANY_VIEW,
            Permission.SETTINGS_VIEW,
        }
        assert has_permission(Role.VIEWER, Permission.TRADE_WRITE) is False

    def test_trader_can_write_trade_data_but_not_approve(self) -> None:
        assert has_permission(Role.TRADER, Permission.TRADE_WRITE) is True
        assert has_permission(Role.TRADER, Permission.FINANCE_APPROVE) is False

    def test_admin_manages_memberships_and_audit(self) -> None:
        assert has_permission(Role.ADMIN, Permission.MEMBERSHIP_MANAGE) is True
        assert has_permission(Role.ADMIN, Permission.AUDIT_VIEW) is True

    def test_unknown_roles_and_permissions_are_denied(self) -> None:
        assert permissions_for("superuser") == frozenset()
        assert has_permission(Role.ADMIN, "finance.transfer") is False

    def test_every_role_declares_company_view(self) -> None:
        for role in Role:
            assert Permission.COMPANY_VIEW in ROLE_PERMISSIONS[role]

    def test_permission_listing_is_sorted(self) -> None:
        values = sorted_permission_values(Role.ADMIN)
        assert values == sorted(values)


class TestAuditRedaction:
    def test_sensitive_keys_are_redacted_recursively(self) -> None:
        redacted = redact_details(
            {
                "password": "hunter2",
                "nested": {"session_token": "abc", "csrf": "xyz", "safe": "visible"},
                "items": [{"api_key": "k"}],
                "authorization": "Bearer abc",
            }
        )
        assert redacted["password"] == REDACTED
        assert redacted["nested"]["session_token"] == REDACTED
        assert redacted["nested"]["csrf"] == REDACTED
        assert redacted["nested"]["safe"] == "visible"
        assert redacted["items"][0]["api_key"] == REDACTED
        assert redacted["authorization"] == REDACTED
        assert "hunter2" not in str(redacted)
        assert "abc" not in str(redacted)

    def test_long_strings_are_bounded(self) -> None:
        redacted = redact_details({"note": "x" * 2000})
        assert isinstance(redacted["note"], str)
        assert len(redacted["note"]) == 512

    def test_non_json_values_are_stringified(self) -> None:
        moment = datetime(2026, 10, 22, 12, 0, tzinfo=UTC)
        identifier = uuid4()
        redacted = redact_details({"at": moment, "id": identifier, "count": 2, "flag": True})
        assert redacted["at"].startswith("2026-10-22")
        assert redacted["id"] == str(identifier)
        assert redacted["count"] == 2
        assert redacted["flag"] is True

    def test_sensitive_key_detection(self) -> None:
        assert is_sensitive_key("password") is True
        assert is_sensitive_key("X-CSRF-Token") is True
        assert is_sensitive_key("display_name") is False

    def test_ip_normalisation_rejects_garbage(self) -> None:
        assert normalise_ip("127.0.0.1") == "127.0.0.1"
        assert normalise_ip("::1") == "::1"
        assert normalise_ip("testclient") is None
        assert normalise_ip(None) is None


class TestSessionContextCsrf:
    def _context(self, *, csrf_token: str) -> SessionContext:
        now = datetime.now(tz=UTC)
        return SessionContext(
            session_id=uuid4(),
            csrf_token=csrf_token,
            user=ActorSummary(
                user_id=uuid4(),
                email="a@b.example",
                display_name="A",
                status="active",
            ),
            company_id=None,
            created_at=now,
            last_activity_at=now,
            expires_at=now + timedelta(hours=12),
            ip_address=None,
            user_agent=None,
            memberships=(),
        )

    def test_csrf_is_compared_exactly(self) -> None:
        token = generate_csrf_token()
        context = self._context(csrf_token=token)
        assert context.verify_csrf(token) is True
        assert context.verify_csrf(token + "x") is False
        assert context.verify_csrf("") is False
        assert context.verify_csrf(None) is False

    def test_permissions_follow_the_active_membership(self) -> None:
        assert self._context(csrf_token="x").permissions == frozenset()
        assert self._context(csrf_token="x").role is None

    def test_csrf_token_is_never_derived_from_the_session_token(self) -> None:
        session_token = generate_session_token()
        csrf_token = generate_csrf_token()
        assert csrf_token != session_token
        assert hash_token(session_token) != csrf_token


class TestEmailNormalisation:
    def test_email_is_trimmed_and_lowercased(self) -> None:
        assert normalize_email("  Amina@Touche.Example ") == "amina@touche.example"


class TestStage1aConfiguration:
    def test_local_cookies_are_not_secure_but_dev_friendly(self, settings: Settings) -> None:
        assert settings.effective_session_cookie_name == "touche_session"
        assert settings.secure_cookies is False
        assert settings.session_cookie_max_age == settings.session_idle_timeout_seconds

    def test_production_cookies_require_https_and_the_host_prefix(self) -> None:
        production = Settings(
            environment="production",
            database_url=SecretStr("postgresql+psycopg://u:p@db:5432/touche"),
            session_cookie_secure=True,
            cors_allowed_origins=["https://app.touche.example"],
        )
        assert production.effective_session_cookie_name == "__Host-touche_session"
        assert production.secure_cookies is True

    def test_production_rejects_insecure_cookie_configuration(self) -> None:
        with pytest.raises(ValueError):
            Settings(
                environment="production",
                database_url=SecretStr("postgresql+psycopg://u:p@db:5432/touche"),
                session_cookie_secure=False,
                cors_allowed_origins=["https://app.touche.example"],
            )

    def test_production_rejects_a_cookie_domain(self) -> None:
        with pytest.raises(ValueError):
            Settings(
                environment="production",
                database_url=SecretStr("postgresql+psycopg://u:p@db:5432/touche"),
                session_cookie_secure=True,
                session_cookie_domain=".touche.example",
                cors_allowed_origins=["https://app.touche.example"],
            )

    def test_test_database_dsn_swaps_only_the_database_name(self, settings: Settings) -> None:
        dsn = settings.test_database_dsn
        assert dsn is not None
        assert dsn.endswith("/touche_commerce_test")
        assert "127.0.0.1:59999" in dsn


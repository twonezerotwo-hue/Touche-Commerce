"""Stage 1A authentication, session and company-selection integration tests.

These run against the isolated ``touche_commerce_test`` database with the real
runtime role, so RLS, hashing, cookies, CSRF and audit behaviour are exercised
exactly as in production code paths.
"""

from __future__ import annotations

from datetime import UTC, datetime, timedelta
from typing import Any
from uuid import UUID

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import text

from app.db.engine import Database
from app.db.models import AuditAction, Membership
from app.services import admin
from app.services.admin import RevocationResult
from tests.conftest import IdentityWorld
from tests.support import TEST_PASSWORD, csrf_from, csrf_headers, login

pytestmark = pytest.mark.integration

LOGIN = "/api/v1/auth/login"
LOGOUT = "/api/v1/auth/logout"
ME = "/api/v1/auth/me"
COMPANIES = "/api/v1/companies"
SWITCH = "/api/v1/session/company"


def error_code(response: Any) -> str:
    return str(response.json()["error"]["code"])


def audit_actions(migration_database: Database) -> list[str]:
    with migration_database.session() as session:
        return list(
            session.execute(
                text("SELECT action FROM touche.audit_record ORDER BY occurred_at")
            ).scalars()
        )


def audit_details_text(migration_database: Database) -> str:
    with migration_database.session() as session:
        return str(
            session.execute(text("SELECT details::text FROM touche.audit_record")).scalars().all()
        )


def session_rows(migration_database: Database) -> list[dict[str, Any]]:
    with migration_database.session() as session:
        return [
            dict(row)
            for row in session.execute(
                text(
                    "SELECT id, user_id, company_id, token_hash, csrf_token, revoked_at, "
                    "revoked_reason, last_activity_at, expires_at FROM touche.auth_session"
                )
            ).mappings()
        ]


def age_session(
    migration_database: Database,
    *,
    last_activity_at: datetime | None = None,
    expires_at: datetime | None = None,
    created_at: datetime | None = None,
) -> None:
    with migration_database.transaction() as session:
        if created_at is not None:
            session.execute(
                text("UPDATE touche.auth_session SET created_at = :value"),
                {"value": created_at},
            )
        if last_activity_at is not None:
            session.execute(
                text("UPDATE touche.auth_session SET last_activity_at = :value"),
                {"value": last_activity_at},
            )
        if expires_at is not None:
            session.execute(
                text("UPDATE touche.auth_session SET expires_at = :value"),
                {"value": expires_at},
            )


class TestLogin:
    def test_login_returns_profile_and_hardened_cookie(
        self, identity_world: IdentityWorld, api_client: TestClient
    ) -> None:
        response = login(api_client, identity_world.email_a)

        assert response.status_code == 200, response.text
        payload = response.json()
        assert payload["user"]["email"] == identity_world.email_a
        assert payload["user"]["display_name"] == "Amina Haddad"
        assert payload["session"]["company"] is None  # two memberships -> explicit choice
        assert {company["name"] for company in payload["memberships"]} == {
            "TOUCHE Trading",
            "Meridian Commodities",
        }
        assert payload["session"]["csrf_token"]
        assert "token" not in payload["session"]
        assert "password" not in response.text.lower()

        cookie = response.headers["set-cookie"]
        assert "touche_session=" in cookie
        assert "HttpOnly" in cookie
        assert "SameSite=lax" in cookie
        assert "Path=/" in cookie
        assert "Secure" not in cookie  # local/test HTTP development
        raw_token = cookie.split("touche_session=")[1].split(";")[0]
        assert raw_token not in response.text

    def test_single_membership_is_auto_selected(
        self, identity_world: IdentityWorld, api_client: TestClient
    ) -> None:
        response = login(api_client, identity_world.email_b)

        assert response.status_code == 200
        session = response.json()["session"]
        assert session["company"]["name"] == "Meridian Commodities"
        assert session["company"]["role"] == "trader"
        assert session["company"]["permissions"] == [
            "company.view",
            "settings.view",
            "trade.write",
        ]

    def test_unknown_email_and_wrong_password_are_indistinguishable(
        self, identity_world: IdentityWorld, client_factory: Any
    ) -> None:
        unknown = client_factory().post(
            LOGIN, json={"email": "nobody@touche.example", "password": TEST_PASSWORD}
        )
        wrong = client_factory().post(
            LOGIN, json={"email": identity_world.email_a, "password": "just-wrong-password"}
        )

        assert unknown.status_code == wrong.status_code == 401
        assert error_code(unknown) == error_code(wrong) == "UNAUTHORIZED"
        assert unknown.json()["error"]["message"] == wrong.json()["error"]["message"]
        assert identity_world.email_a not in wrong.text
        assert identity_world.email_a not in unknown.text
        assert "nobody@touche.example" not in wrong.text

    def test_disabled_account_is_rejected_with_the_same_message(
        self, identity_world: IdentityWorld, api_client: TestClient, migration_database: Database
    ) -> None:
        with migration_database.transaction() as session:
            session.execute(
                text("UPDATE touche.app_user SET status = 'disabled' WHERE id = :id"),
                {"id": identity_world.user_a},
            )

        response = login(api_client, identity_world.email_a)

        assert response.status_code == 401
        assert error_code(response) == "UNAUTHORIZED"
        assert response.json()["error"]["message"] == "Email or password is incorrect."

    def test_login_is_rate_limited_per_account(
        self, identity_world: IdentityWorld, api_client: TestClient, migration_database: Database
    ) -> None:
        for _ in range(10):
            attempt = login(api_client, identity_world.email_a, "wrong-password-1")
            assert attempt.status_code == 401

        blocked = login(api_client, identity_world.email_a)
        assert blocked.status_code == 429
        assert error_code(blocked) == "RATE_LIMITED"
        assert int(blocked.headers["Retry-After"]) >= 1

        # Even a correct password is refused while the window is saturated.
        assert audit_actions(migration_database).count(str(AuditAction.ACCESS_DENIED)) >= 1

    def test_validation_errors_are_field_level(
        self, identity_world: IdentityWorld, api_client: TestClient
    ) -> None:
        response = api_client.post(LOGIN, json={"email": "not-an-email", "password": ""})

        assert response.status_code == 422
        assert error_code(response) == "VALIDATION_ERROR"
        fields = {detail["field"] for detail in response.json()["error"]["details"]}
        assert any("email" in field for field in fields)
        assert any("password" in field for field in fields)



class TestSessionLifecycle:
    def test_me_requires_a_session(self, api_client: TestClient) -> None:
        response = api_client.get(ME)

        assert response.status_code == 401
        assert error_code(response) == "UNAUTHORIZED"
        assert response.headers["cache-control"] == "no-store"

    def test_me_returns_identity_company_and_csrf(
        self, identity_world: IdentityWorld, api_client: TestClient
    ) -> None:
        issued = login(api_client, identity_world.email_b)
        response = api_client.get(ME)

        assert response.status_code == 200
        payload = response.json()
        assert payload["user"]["email"] == identity_world.email_b
        assert payload["session"]["company"]["name"] == "Meridian Commodities"
        assert payload["session"]["csrf_token"] == csrf_from(issued)
        assert payload["session"]["expires_at"] > payload["session"]["created_at"]
        assert payload["session"]["idle_expires_at"] > payload["session"]["last_activity_at"]

    def test_idle_timeout_revokes_the_session(
        self,
        identity_world: IdentityWorld,
        api_client: TestClient,
        migration_database: Database,
    ) -> None:
        login(api_client, identity_world.email_b)
        age_session(
            migration_database,
            last_activity_at=datetime.now(tz=UTC) - timedelta(minutes=31),
        )

        response = api_client.get(ME)

        assert response.status_code == 401
        assert error_code(response) == "SESSION_EXPIRED"
        rows = session_rows(migration_database)
        assert len(rows) == 1
        assert rows[0]["revoked_at"] is not None
        assert rows[0]["revoked_reason"] == "idle_timeout"
        assert str(AuditAction.SESSION_REVOKED) in audit_actions(migration_database)

    def test_absolute_timeout_revokes_the_session(
        self,
        identity_world: IdentityWorld,
        api_client: TestClient,
        migration_database: Database,
    ) -> None:
        login(api_client, identity_world.email_b)
        now = datetime.now(tz=UTC)
        age_session(
            migration_database,
            created_at=now - timedelta(hours=13),
            expires_at=now - timedelta(hours=1),
        )

        response = api_client.get(ME)

        assert response.status_code == 401
        assert error_code(response) == "SESSION_EXPIRED"
        assert session_rows(migration_database)[0]["revoked_reason"] == "absolute_timeout"

    def test_logout_revokes_the_session_and_clears_the_cookie(
        self,
        identity_world: IdentityWorld,
        api_client: TestClient,
        migration_database: Database,
    ) -> None:
        issued = login(api_client, identity_world.email_b)

        response = api_client.post(LOGOUT, headers=csrf_headers(csrf_from(issued)))

        assert response.status_code == 200, response.text
        assert response.json() == {"status": "signed_out"}
        assert "touche_session=" in response.headers["set-cookie"]
        assert "Max-Age=0" in response.headers["set-cookie"]
        assert api_client.get(ME).status_code == 401
        assert session_rows(migration_database)[0]["revoked_reason"] == "logout"
        assert str(AuditAction.LOGOUT) in audit_actions(migration_database)

    def test_logout_without_csrf_is_rejected_and_keeps_the_session(
        self, identity_world: IdentityWorld, api_client: TestClient
    ) -> None:
        login(api_client, identity_world.email_b)

        response = api_client.post(LOGOUT)

        assert response.status_code == 403
        assert error_code(response) == "CSRF_REJECTED"
        assert api_client.get(ME).status_code == 200

    def test_csrf_token_must_belong_to_the_presented_session(
        self, identity_world: IdentityWorld, client_factory: Any
    ) -> None:
        first = client_factory()
        second = client_factory()
        login(first, identity_world.email_a)
        foreign_csrf = csrf_from(login(second, identity_world.email_a))

        response = first.post(LOGOUT, headers=csrf_headers(foreign_csrf))

        assert response.status_code == 403
        assert error_code(response) == "CSRF_REJECTED"

    def test_company_switch_rotates_the_session_token(
        self, identity_world: IdentityWorld, client_factory: Any
    ) -> None:
        client = client_factory()
        issued = login(client, identity_world.email_a)
        stale_token = client.cookies.get("touche_session")
        assert stale_token is not None

        switched = client.post(
            SWITCH,
            json={"company_id": str(identity_world.company_a)},
            headers=csrf_headers(csrf_from(issued)),
        )

        assert switched.status_code == 200, switched.text
        rotated_token = client.cookies.get("touche_session")
        assert rotated_token is not None
        assert rotated_token != stale_token
        assert switched.json()["session"]["company"]["name"] == "TOUCHE Trading"

        replay = client_factory().get(ME, headers={"Cookie": f"touche_session={stale_token}"})
        assert replay.status_code == 401
        assert error_code(replay) == "UNAUTHORIZED"

    def test_switch_requires_csrf(
        self, identity_world: IdentityWorld, api_client: TestClient
    ) -> None:
        login(api_client, identity_world.email_a)

        response = api_client.post(SWITCH, json={"company_id": str(identity_world.company_a)})

        assert response.status_code == 403
        assert error_code(response) == "CSRF_REJECTED"



class TestOriginValidation:
    def test_mutating_request_without_origin_is_rejected(
        self, identity_world: IdentityWorld, client_factory: Any
    ) -> None:
        response = client_factory(origin=None).post(
            LOGIN, json={"email": identity_world.email_a, "password": TEST_PASSWORD}
        )

        assert response.status_code == 403
        assert error_code(response) == "ORIGIN_REJECTED"

    def test_foreign_origin_is_rejected(
        self, identity_world: IdentityWorld, client_factory: Any, migration_database: Database
    ) -> None:
        response = client_factory(origin="https://evil.example").post(
            LOGIN, json={"email": identity_world.email_a, "password": TEST_PASSWORD}
        )

        assert response.status_code == 403
        assert error_code(response) == "ORIGIN_REJECTED"
        assert session_rows(migration_database) == []

    def test_safe_methods_do_not_require_an_origin(
        self, identity_world: IdentityWorld, client_factory: Any
    ) -> None:
        response = client_factory(origin=None).get("/api/v1/health/live")
        assert response.status_code == 200


class TestCompanySelection:
    def test_companies_list_only_verified_memberships(
        self, identity_world: IdentityWorld, api_client: TestClient
    ) -> None:
        login(api_client, identity_world.email_a)

        response = api_client.get(COMPANIES)

        assert response.status_code == 200
        payload = response.json()
        names = {company["name"] for company in payload["companies"]}
        assert names == {"TOUCHE Trading", "Meridian Commodities"}
        assert "Northwind Metals" not in names
        roles = {company["name"]: company["role"] for company in payload["companies"]}
        assert roles == {"TOUCHE Trading": "admin", "Meridian Commodities": "viewer"}
        assert payload["active_company_id"] is None

    def test_switch_to_a_company_without_membership_is_forbidden(
        self, identity_world: IdentityWorld, api_client: TestClient, migration_database: Database
    ) -> None:
        issued = login(api_client, identity_world.email_a)

        response = api_client.post(
            SWITCH,
            json={"company_id": str(identity_world.company_c)},
            headers=csrf_headers(csrf_from(issued)),
        )

        assert response.status_code == 403
        assert error_code(response) == "FORBIDDEN"
        assert api_client.get(ME).json()["session"]["company"] is None

        with migration_database.session() as session:
            details = session.execute(
                text(
                    "SELECT details FROM touche.audit_record WHERE action = 'access.denied' "
                    "ORDER BY occurred_at DESC LIMIT 1"
                )
            ).scalar_one()
        assert details["reason"] == "company_switch_without_membership"
        assert details["requested_company_id"] == str(identity_world.company_c)

    def test_switch_to_a_member_company_updates_the_session(
        self, identity_world: IdentityWorld, api_client: TestClient
    ) -> None:
        issued = login(api_client, identity_world.email_a)

        response = api_client.post(
            SWITCH,
            json={"company_id": str(identity_world.company_b)},
            headers=csrf_headers(csrf_from(issued)),
        )

        assert response.status_code == 200
        company = response.json()["session"]["company"]
        assert company["name"] == "Meridian Commodities"
        assert company["role"] == "viewer"
        assert company["permissions"] == ["company.view", "settings.view"]
        assert api_client.get(COMPANIES).json()["active_company_id"] == str(
            identity_world.company_b
        )

    def test_switch_requires_a_uuid(
        self, identity_world: IdentityWorld, api_client: TestClient
    ) -> None:
        issued = login(api_client, identity_world.email_a)

        response = api_client.post(
            SWITCH, json={"company_id": "not-a-uuid"}, headers=csrf_headers(csrf_from(issued))
        )

        assert response.status_code == 422
        assert error_code(response) == "VALIDATION_ERROR"



class TestMembershipRevocation:
    def _revoke(
        self, migration_database: Database, *, membership_id: UUID
    ) -> RevocationResult:
        with migration_database.transaction() as session:
            membership = session.get(Membership, membership_id)
            assert membership is not None
            return admin.revoke_membership(session, membership, reason="test_revocation")

    def test_revocation_kills_only_the_affected_company_sessions(
        self,
        identity_world: IdentityWorld,
        client_factory: Any,
        migration_database: Database,
    ) -> None:
        victim = client_factory()
        login(victim, identity_world.email_b)  # auto-selected company B
        assert victim.get(ME).status_code == 200

        colleague = client_factory()
        issued = login(colleague, identity_world.email_a)
        colleague.post(
            SWITCH,
            json={"company_id": str(identity_world.company_b)},
            headers=csrf_headers(csrf_from(issued)),
        )
        assert colleague.get(ME).status_code == 200

        result = self._revoke(
            migration_database, membership_id=identity_world.membership_b_trader
        )
        assert result.revoked_sessions == 1

        # The revoked user loses the session immediately.
        blocked = victim.get(ME)
        assert blocked.status_code == 401

        # The colleague keeps their unrelated (company B) membership.
        still_valid = colleague.get(ME)
        assert still_valid.status_code == 200
        assert still_valid.json()["session"]["company"]["name"] == "Meridian Commodities"
        assert "Meridian Commodities" in {
            company["name"] for company in colleague.get(COMPANIES).json()["companies"]
        }

        # Re-authentication is possible, but the revoked company is gone.
        reauth = login(client_factory(), identity_world.email_b)
        assert reauth.status_code == 200
        assert reauth.json()["memberships"] == []
        assert reauth.json()["session"]["company"] is None

    def test_revocation_is_idempotent(
        self, identity_world: IdentityWorld, migration_database: Database
    ) -> None:
        first = self._revoke(migration_database, membership_id=identity_world.membership_b_trader)
        second = self._revoke(migration_database, membership_id=identity_world.membership_b_trader)

        assert first.already_revoked is False
        assert second.already_revoked is True
        assert second.revoked_sessions == 0

    def test_revocation_writes_membership_and_session_audit_records(
        self,
        identity_world: IdentityWorld,
        api_client: TestClient,
        migration_database: Database,
    ) -> None:
        login(api_client, identity_world.email_b)
        self._revoke(migration_database, membership_id=identity_world.membership_b_trader)

        actions = audit_actions(migration_database)
        assert str(AuditAction.MEMBERSHIP_CHANGED) in actions
        assert str(AuditAction.SESSION_REVOKED) in actions

        with migration_database.session() as session:
            changed = session.execute(
                text(
                    "SELECT details FROM touche.audit_record "
                    "WHERE action = 'membership.changed' ORDER BY occurred_at DESC LIMIT 1"
                )
            ).scalar_one()
        assert changed["status"] == "revoked"
        assert changed["reason"] == "test_revocation"
        assert changed["revoked_sessions"] == 1


class TestAuditTrail:
    def test_security_actions_are_recorded_with_request_correlation(
        self, identity_world: IdentityWorld, api_client: TestClient, migration_database: Database
    ) -> None:
        issued = login(api_client, identity_world.email_a)
        switched = api_client.post(
            SWITCH,
            json={"company_id": str(identity_world.company_a)},
            headers=csrf_headers(csrf_from(issued)),
        )
        request_id = switched.headers["x-request-id"]
        logged_out = api_client.post(
            LOGOUT, headers=csrf_headers(csrf_from(switched))
        )
        assert logged_out.status_code == 200

        actions = audit_actions(migration_database)
        assert str(AuditAction.LOGIN_SUCCESS) in actions
        assert str(AuditAction.COMPANY_SWITCH) in actions
        assert str(AuditAction.LOGOUT) in actions

        with migration_database.session() as session:
            stored_request_id = session.execute(
                text(
                    "SELECT request_id FROM touche.audit_record "
                    "WHERE action = 'session.company.switch'"
                )
            ).scalar_one()
        assert stored_request_id == request_id

        details = audit_details_text(migration_database)
        assert TEST_PASSWORD not in details
        assert "token" not in details.lower()

    def test_failed_login_is_audited_without_credentials(
        self, identity_world: IdentityWorld, api_client: TestClient, migration_database: Database
    ) -> None:
        login(api_client, identity_world.email_a, "definitely-wrong-pass")

        with migration_database.session() as session:
            row = session.execute(
                text(
                    "SELECT outcome, details, actor_id FROM touche.audit_record "
                    "WHERE action = 'auth.login.failure'"
                )
            ).mappings().one()

        assert row["outcome"] == "failure"
        assert row["details"]["reason"] == "invalid_password"
        assert row["actor_id"] == identity_world.user_a
        assert "definitely-wrong-pass" not in str(row["details"])
        assert identity_world.email_a not in str(row["details"])


"""Seed the ISOLATED acceptance database with synthetic companies and users.

Never touches the development or production database: it only works on the test database
(``touche_commerce_test`` derived from the configured DSNs) and refuses anything else. It
resets that database's identity tables (the same reset the integration tests use), applies
migrations, and creates:

* company A "Touche Acceptance Trading" (a clearly synthetic name; the real company's legal
  title, tax number and address are unverified and are never invented here), with a user for
  each role in the owner's list — owner (admin), sales, purchasing and operations (trader),
  finance (approver) and a read-only viewer — plus
* company B "Acceptance Other Co" with its own admin, to prove tenant isolation.

Passwords are random per run and are written to ``backend/var/acceptance/credentials.json``
(git-ignored). They are never printed.

Usage (from ``backend``): ``python -m scripts.seed_acceptance``
"""

from __future__ import annotations

import json
import os
import secrets
import subprocess
import sys
from pathlib import Path
from typing import Any

BACKEND_ROOT = Path(__file__).resolve().parents[1]
if str(BACKEND_ROOT) not in sys.path:
    sys.path.insert(0, str(BACKEND_ROOT))

from sqlalchemy import text  # noqa: E402

from app.core.config import Settings  # noqa: E402
from app.db.engine import Database  # noqa: E402
from app.security.passwords import PasswordService  # noqa: E402
from app.security.permissions import Role  # noqa: E402
from app.services import admin  # noqa: E402

CREDENTIALS = BACKEND_ROOT / "var" / "acceptance" / "credentials.json"
DOMAIN = "acceptance.touche.example"  # the validator rejects reserved ".test" addresses

USERS_A: tuple[tuple[str, str, Role], ...] = (
    ("owner", "Acceptance Owner", Role.ADMIN),
    ("sales", "Acceptance Sales", Role.TRADER),
    ("purchasing", "Acceptance Purchasing", Role.TRADER),
    ("operations", "Acceptance Operations", Role.TRADER),
    ("finance", "Acceptance Finance", Role.APPROVER),
    ("viewer", "Acceptance Viewer", Role.VIEWER),
)


def _reset(database: Database) -> None:
    with database.transaction() as session:
        # The audit trigger blocks TRUNCATE by design; the owner disables it for this
        # explicit, test-database-only reset (the runtime role cannot do this).
        session.execute(text("ALTER TABLE touche.audit_record DISABLE TRIGGER USER"))
        session.execute(
            text(
                "TRUNCATE TABLE touche.company_setting_entry, touche.company_settings, "
                "touche.idempotency_record, touche.audit_record, touche.login_attempt, "
                "touche.auth_session, touche.membership, touche.company, touche.app_user "
                "RESTART IDENTITY CASCADE"
            )
        )
        session.execute(text("ALTER TABLE touche.audit_record ENABLE TRIGGER USER"))


def seed() -> dict[str, Any]:
    loaded = Settings()
    migration_dsn = loaded.test_migration_dsn
    if migration_dsn is None:
        raise SystemExit("The isolated test database DSN is not configured; nothing was changed.")
    if not migration_dsn.rsplit("/", 1)[-1].split("?")[0].endswith("_test"):
        raise SystemExit("Refusing to seed: the target is not a *_test database.")

    env = {
        **os.environ,
        "TOUCHE_ENVIRONMENT": "test",
        "TOUCHE_DATABASE_MIGRATION_URL": migration_dsn,
    }
    subprocess.run(
        [sys.executable, "-m", "alembic", "upgrade", "head"],
        cwd=BACKEND_ROOT,
        env=env,
        check=True,
        capture_output=True,
    )

    database = Database(loaded, dsn_override=migration_dsn)
    hasher = PasswordService(loaded)
    credentials: dict[str, Any] = {"companies": {}, "users": {}}
    try:
        _reset(database)
        with database.transaction() as session:
            company_a = admin.create_company(
                session,
                name="Touche Acceptance Trading",
                country="TR",
                default_currency="TRY",
                timezone="Europe/Istanbul",
                locale="tr",
            )
            company_b = admin.create_company(
                session, name="Acceptance Other Co", country="DE", default_currency="EUR"
            )
            credentials["companies"] = {
                "A": {"id": str(company_a.id), "name": company_a.name},
                "B": {"id": str(company_b.id), "name": company_b.name},
            }
            for slug, display, role in USERS_A:
                password = secrets.token_urlsafe(18)
                user = admin.create_user(
                    session,
                    email=f"{slug}@{DOMAIN}",
                    display_name=display,
                    password_hash=hasher.hash(password),
                )
                admin.grant_membership(session, user_id=user.id, company_id=company_a.id, role=role)
                credentials["users"][slug] = {
                    "email": user.email,
                    "password": password,
                    "role": role.value,
                    "company": "A",
                }
            password = secrets.token_urlsafe(18)
            outsider = admin.create_user(
                session,
                email=f"outsider@{DOMAIN}",
                display_name="Acceptance Outsider",
                password_hash=hasher.hash(password),
            )
            admin.grant_membership(
                session, user_id=outsider.id, company_id=company_b.id, role=Role.ADMIN
            )
            credentials["users"]["outsider"] = {
                "email": outsider.email,
                "password": password,
                "role": Role.ADMIN.value,
                "company": "B",
            }
    finally:
        database.dispose()

    CREDENTIALS.parent.mkdir(parents=True, exist_ok=True)
    CREDENTIALS.write_text(json.dumps(credentials, indent=2), encoding="utf-8")
    return credentials


def main() -> int:
    credentials = seed()
    users = ", ".join(sorted(credentials["users"]))
    print(f"Seeded the isolated acceptance database: users {users}.")
    print(f"Credentials were written to {CREDENTIALS} (git-ignored); they are not printed.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

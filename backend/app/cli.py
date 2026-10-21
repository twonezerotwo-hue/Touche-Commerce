"""TOUCHE COMMERCE administration CLI.

The CLI is the only supported way to create the first administrator, add
companies and manage memberships. It never accepts a password on the command
line (shell history / process list leak) and never prints one:

* interactive prompt (default) — hidden input, confirmation, policy check;
* ``--password-stdin`` — one line from standard input, for automation.

Example::

    python -m app.cli bootstrap
    python -m app.cli list companies
    python -m app.cli membership grant --email a@b.c --company "TOUCHE Trading" --role approver
    python -m app.cli membership revoke --email a@b.c --company "TOUCHE Trading"

Commands run with the migration role because they may create rows before any
tenant context exists.
"""

from __future__ import annotations

import argparse
import getpass
import sys
from collections.abc import Sequence
from typing import NoReturn

from email_validator import EmailNotValidError, validate_email
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.core.config import ConfigurationError, Settings, get_settings
from app.db.engine import Database
from app.db.models import (
    AuditAction,
    AuditActorType,
    AuditOutcome,
    Company,
    Membership,
    User,
)
from app.security.passwords import PasswordPolicyError, PasswordService, validate_password_strength
from app.security.permissions import Role
from app.services import admin
from app.services.audit import record_audit

EXIT_OK = 0
EXIT_USAGE = 2
EXIT_CONFLICT = 3


class CliError(RuntimeError):
    """A user-facing failure; the message is safe to print."""


def _fail(message: str, code: int = EXIT_USAGE) -> NoReturn:
    print(f"error: {message}", file=sys.stderr)
    raise SystemExit(code)


def _privileged_database(settings: Settings) -> Database:
    try:
        dsn = settings.migration_dsn
    except ConfigurationError as exc:
        _fail(str(exc))
    return Database(settings, dsn_override=dsn)


def _prompt(label: str, *, default: str | None = None, secret: bool = False) -> str:
    if not sys.stdin.isatty():
        _fail(f"{label} is required when running non-interactively (pass the matching flag).")
    suffix = f" [{default}]" if default else ""
    prompt = f"{label}{suffix}: "
    value = getpass.getpass(prompt) if secret else input(prompt)
    value = value.strip()
    return value or (default or "")


def _read_password(settings: Settings, *, password_stdin: bool) -> str:
    """Return a password from a hidden prompt or from stdin; never from argv."""
    if password_stdin:
        line = sys.stdin.readline()
        if not line:
            _fail("--password-stdin was given but standard input was empty.")
        password = line.rstrip("\r\n")
    else:
        password = _prompt("Password", secret=True)
        confirmation = _prompt("Confirm password", secret=True)
        if password != confirmation:
            _fail("Passwords do not match.")
    try:
        validate_password_strength(password, min_length=settings.password_min_length)
    except PasswordPolicyError as exc:
        _fail(str(exc))
    return password


def _validate_email(value: str) -> str:
    try:
        result = validate_email(value, check_deliverability=False)
    except EmailNotValidError as exc:
        _fail(f"invalid email address: {exc}")
    return result.normalized.lower()


def _validate_country(value: str) -> str:
    country = value.strip().upper()
    if len(country) != 2 or not country.isalpha():
        _fail("country must be a two-letter ISO 3166-1 code (for example GB).")
    return country


def _validate_currency(value: str) -> str:
    currency = value.strip().upper()
    if len(currency) != 3 or not currency.isalpha():
        _fail("currency must be a three-letter ISO 4217 code (for example USD).")
    return currency


def _resolve_membership(
    session: Session, *, email: str, company_name: str
) -> tuple[User, Company, Membership]:
    user = admin.find_user(session, email)
    if user is None:
        _fail(f"no user with email {email!r}.", EXIT_CONFLICT)
    company = admin.find_company_by_name(session, company_name)
    if company is None:
        _fail(f"no company named {company_name!r}.", EXIT_CONFLICT)
    membership = admin.membership_for_user(session, user_id=user.id, company_id=company.id)
    if membership is None:
        _fail(f"{email} has no membership in {company_name!r}.", EXIT_CONFLICT)
    return user, company, membership

def _print_summary(label: str, lines: Sequence[tuple[str, str]]) -> None:
    print(f"\n{label}")
    width = max(len(name) for name, _ in lines)
    for name, value in lines:
        print(f"  {name.ljust(width)}  {value}")
    print()


def cmd_bootstrap(args: argparse.Namespace, settings: Settings) -> int:
    """Create the first company and its administrator (interactive by default)."""
    email = _validate_email(args.email or _prompt("Administrator email"))
    display_name = (args.name or _prompt("Administrator display name")).strip()
    company_name = (args.company or _prompt("Company name")).strip()
    country = _validate_country(
        args.country or _prompt("Company country (ISO alpha-2)", default="GB")
    )
    currency = _validate_currency(
        args.currency or _prompt("Default currency (ISO 4217)", default="USD")
    )
    password = _read_password(settings, password_stdin=args.password_stdin)

    if not display_name:
        _fail("display name must not be empty.")
    if not company_name:
        _fail("company name must not be empty.")

    database = _privileged_database(settings)
    password_hash = PasswordService(settings).hash(password)
    try:
        with database.transaction() as session:
            if admin.find_user(session, email) is not None:
                raise CliError(f"a user with email {email!r} already exists.")
            if admin.find_company_by_name(session, company_name) is not None:
                raise CliError(f"a company named {company_name!r} already exists.")
            company = admin.create_company(
                session,
                name=company_name,
                country=country,
                default_currency=currency,
            )
            user = admin.create_user(
                session,
                email=email,
                display_name=display_name,
                password_hash=password_hash,
            )
            admin.grant_membership(
                session, user_id=user.id, company_id=company.id, role=Role.ADMIN
            )
            record_audit(
                session,
                action=AuditAction.IDENTITY_BOOTSTRAPPED,
                outcome=AuditOutcome.SUCCESS,
                actor_type=AuditActorType.SYSTEM,
                company_id=company.id,
                resource_type="company",
                resource_id=str(company.id),
                details={
                    "administrator_email": user.email,
                    "country": company.country,
                    "default_currency": company.default_currency,
                    "role": str(Role.ADMIN),
                },
            )
            summary = [
                ("Administrator", user.email),
                ("Display name", user.display_name),
                ("Company", company.name),
                ("Country", company.country),
                ("Currency", company.default_currency),
                ("Role", str(Role.ADMIN)),
            ]
    except CliError as exc:
        _fail(str(exc), EXIT_CONFLICT)
    finally:
        database.dispose()

    _print_summary("Bootstrap complete", summary)
    print("Sign in at http://localhost:3000/login with the password you just entered.")
    print("Administrators do not automatically hold finance.approve (ADR-003).")
    return EXIT_OK


def cmd_create_user(args: argparse.Namespace, settings: Settings) -> int:
    email = _validate_email(args.email)
    display_name = (args.name or _prompt("Display name")).strip()
    password = _read_password(settings, password_stdin=args.password_stdin)
    database = _privileged_database(settings)
    password_hash = PasswordService(settings).hash(password)
    try:
        with database.transaction() as session:
            if admin.find_user(session, email) is not None:
                raise CliError(f"a user with email {email!r} already exists.")
            user = admin.create_user(
                session,
                email=email,
                display_name=display_name,
                password_hash=password_hash,
            )
            summary = [("User", user.email), ("Display name", user.display_name)]
    except CliError as exc:
        _fail(str(exc), EXIT_CONFLICT)
    finally:
        database.dispose()
    _print_summary("User created", summary)
    print("Grant access with: python -m app.cli membership grant --email ... --company ...")
    return EXIT_OK



def cmd_create_company(args: argparse.Namespace, settings: Settings) -> int:
    name = (args.name or _prompt("Company name")).strip()
    country = _validate_country(args.country or _prompt("Country (ISO alpha-2)", default="GB"))
    currency = _validate_currency(
        args.currency or _prompt("Default currency (ISO 4217)", default="USD")
    )
    database = _privileged_database(settings)
    try:
        with database.transaction() as session:
            if admin.find_company_by_name(session, name) is not None:
                raise CliError(f"a company named {name!r} already exists.")
            company = admin.create_company(
                session,
                name=name,
                country=country,
                default_currency=currency,
                timezone=args.timezone,
            )
            summary = [
                ("Company", company.name),
                ("Country", company.country),
                ("Currency", company.default_currency),
            ]
    except CliError as exc:
        _fail(str(exc), EXIT_CONFLICT)
    finally:
        database.dispose()
    _print_summary("Company created", summary)
    return EXIT_OK


def cmd_grant_membership(args: argparse.Namespace, settings: Settings) -> int:
    email = _validate_email(args.email)
    role = str(Role(args.role))
    database = _privileged_database(settings)
    try:
        with database.transaction() as session:
            user = admin.find_user(session, email)
            if user is None:
                raise CliError(f"no user with email {email!r}.")
            company = admin.find_company_by_name(session, args.company)
            if company is None:
                raise CliError(f"no company named {args.company!r}.")
            membership = admin.grant_membership(
                session, user_id=user.id, company_id=company.id, role=role
            )
            summary = [
                ("User", user.email),
                ("Company", company.name),
                ("Role", membership.role),
                ("Membership", str(membership.id)),
            ]
    except CliError as exc:
        _fail(str(exc), EXIT_CONFLICT)
    finally:
        database.dispose()
    _print_summary("Membership granted", summary)
    return EXIT_OK


def cmd_revoke_membership(args: argparse.Namespace, settings: Settings) -> int:
    email = _validate_email(args.email)
    database = _privileged_database(settings)
    try:
        with database.transaction() as session:
            user, company, membership = _resolve_membership(
                session, email=email, company_name=args.company
            )
            result = admin.revoke_membership(session, membership, reason="cli_revocation")
            summary = [
                ("User", user.email),
                ("Company", company.name),
                ("Membership", str(result.membership_id)),
                ("Already revoked", "yes" if result.already_revoked else "no"),
                ("Sessions revoked", str(result.revoked_sessions)),
            ]
    finally:
        database.dispose()
    _print_summary("Membership revoked", summary)
    return EXIT_OK



def cmd_set_password(args: argparse.Namespace, settings: Settings) -> int:
    email = _validate_email(args.email)
    password = _read_password(settings, password_stdin=args.password_stdin)
    database = _privileged_database(settings)
    password_hash = PasswordService(settings).hash(password)
    try:
        with database.transaction() as session:
            user = admin.find_user(session, email)
            if user is None:
                raise CliError(f"no user with email {email!r}.")
            user.password_hash = password_hash
            summary = [("User", user.email)]
    except CliError as exc:
        _fail(str(exc), EXIT_CONFLICT)
    finally:
        database.dispose()
    _print_summary("Password updated", summary)
    print("Existing sessions are unaffected; revoke the membership to end them.")
    return EXIT_OK


def cmd_list(args: argparse.Namespace, settings: Settings) -> int:
    database = _privileged_database(settings)
    try:
        with database.transaction() as session:
            if args.what == "companies":
                companies = list(session.scalars(select(Company).order_by(Company.name)))
                if not companies:
                    print("No companies.")
                for company in companies:
                    print(
                        f"{company.name}  |  {company.country}  |  "
                        f"{company.default_currency}  |  {company.status}"
                    )
            elif args.what == "users":
                users = list(session.scalars(select(User).order_by(User.email)))
                if not users:
                    print("No users.")
                for user in users:
                    print(f"{user.email}  |  {user.display_name}  |  {user.status}")
            else:
                if not args.company:
                    _fail("--company is required for 'list memberships'.")
                target = admin.find_company_by_name(session, args.company)
                if target is None:
                    _fail(f"no company named {args.company!r}.", EXIT_CONFLICT)
                rows = admin.list_memberships(session, target.id)
                if not rows:
                    print("No memberships.")
                for membership, user in rows:
                    print(f"{user.email}  |  {membership.role}  |  {membership.status}")
    finally:
        database.dispose()
    return EXIT_OK



def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="python -m app.cli",
        description="TOUCHE COMMERCE administration CLI (privileged, server-side only).",
    )
    subparsers = parser.add_subparsers(dest="command", required=True)

    bootstrap = subparsers.add_parser(
        "bootstrap", help="Create the first company and its administrator."
    )
    bootstrap.add_argument("--email", help="Administrator email (prompted when omitted).")
    bootstrap.add_argument("--name", help="Administrator display name.")
    bootstrap.add_argument("--company", help="Company name.")
    bootstrap.add_argument("--country", help="ISO 3166-1 alpha-2 country code.")
    bootstrap.add_argument("--currency", help="ISO 4217 default currency code.")
    bootstrap.add_argument(
        "--password-stdin", action="store_true", help="Read the password from stdin (automation)."
    )
    bootstrap.set_defaults(handler=cmd_bootstrap)

    create_user = subparsers.add_parser("create-user", help="Create a user account.")
    create_user.add_argument("--email", required=True)
    create_user.add_argument("--name", help="Display name (prompted when omitted).")
    create_user.add_argument("--password-stdin", action="store_true")
    create_user.set_defaults(handler=cmd_create_user)

    create_company = subparsers.add_parser("create-company", help="Create a company.")
    create_company.add_argument("--name")
    create_company.add_argument("--country")
    create_company.add_argument("--currency")
    create_company.add_argument("--timezone", default="UTC")
    create_company.set_defaults(handler=cmd_create_company)

    membership = subparsers.add_parser("membership", help="Grant or revoke memberships.")
    membership_sub = membership.add_subparsers(dest="membership_command", required=True)

    grant = membership_sub.add_parser("grant", help="Grant or re-activate a membership.")
    grant.add_argument("--email", required=True)
    grant.add_argument("--company", required=True)
    grant.add_argument(
        "--role",
        required=True,
        choices=[str(role) for role in Role],
        help="viewer, trader, approver or admin.",
    )
    grant.set_defaults(handler=cmd_grant_membership)

    revoke = membership_sub.add_parser("revoke", help="Revoke a membership and its sessions.")
    revoke.add_argument("--email", required=True)
    revoke.add_argument("--company", required=True)
    revoke.set_defaults(handler=cmd_revoke_membership)

    set_password = subparsers.add_parser("set-password", help="Rotate a user password.")
    set_password.add_argument("--email", required=True)
    set_password.add_argument("--password-stdin", action="store_true")
    set_password.set_defaults(handler=cmd_set_password)

    list_parser = subparsers.add_parser("list", help="List companies, users or memberships.")
    list_parser.add_argument("what", choices=["companies", "users", "memberships"])
    list_parser.add_argument("--company", help="Company name (memberships only).")
    list_parser.set_defaults(handler=cmd_list)

    return parser


def main(argv: Sequence[str] | None = None) -> int:
    parser = build_parser()
    args = parser.parse_args(argv)
    settings = get_settings()
    handler = args.handler
    return int(handler(args, settings))


if __name__ == "__main__":  # pragma: no cover - entry point
    raise SystemExit(main())


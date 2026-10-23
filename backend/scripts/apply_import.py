"""Stage 13B controlled local import — atomic, never an anonymous bulk upload.

Default behavior is a read-only preview. The database commit path is disabled
outside local/test/ci; it requires a TRADE_WRITE membership, a verified backup
restore statement and an exact file-hash confirmation. No existing trade row
is updated and no external message is sent. Reruns refuse duplicates.
"""

from __future__ import annotations

import argparse
import hashlib
import json
from datetime import date
from pathlib import Path
from uuid import UUID

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.core.config import Settings
from app.db.engine import Database
from app.db.models import (
    Company,
    CompanyStatus,
    Counterparty,
    Membership,
    MembershipStatus,
    Product,
    User,
    UserStatus,
)
from app.security.permissions import Permission, permissions_for
from app.services.catalog import ProductService
from app.services.crm import CounterpartyService
from app.services.import_preview import (
    MAX_BYTES,
    ImportPreview,
    ImportPreviewError,
    preview_import,
)
from app.services.trade_meta import WriteMeta

LOCAL_ONLY = frozenset({"local", "test", "ci"})


class ImportCommitBlocked(ValueError):
    """Operator has not proved the prerequisites for an atomic import."""


def _source_keys(kind: str, preview: ImportPreview) -> set[str]:
    if kind == "products":
        return {row.values["sku"].strip().upper() for row in preview.rows}
    return {" ".join(row.values["name"].split()).casefold() for row in preview.rows}


def _live_existing(session: Session, kind: str, company_id: UUID) -> set[str]:
    if kind == "products":
        # The caller holds a privileged import transaction. Restrict by company
        # explicitly; a missing tenant predicate is an error, never a default.
        rows = session.scalars(select(Product.sku).where(Product.company_id == company_id))
        return {row.upper() for row in rows}
    rows = session.scalars(
        select(Counterparty.name).where(Counterparty.company_id == company_id)
    )
    return {" ".join(row.split()).casefold() for row in rows}


def commit_preview(
    database: Database,
    *,
    preview: ImportPreview,
    company_name: str,
    actor_email: str,
    source_sha256: str,
) -> int:
    """Apply every validated row in one transaction, all-or-nothing.

    The same source file can be retried safely: existing rows block the
    transaction before any new row is created. The operator must review the
    company and signed-in trade-writer identity locally.
    """

    if (
        not preview.rows
        or preview.rejected > 0
        or preview.accepted != preview.total_rows
        or len(source_sha256) != 64
    ):
        raise ImportCommitBlocked("Only fully validated, nonempty files can be committed")
    with database.transaction() as session:
        company = session.scalar(select(Company).where(Company.name == company_name.strip()))
        actor = session.scalar(select(User).where(User.email == actor_email.strip().lower()))
        if company is None or actor is None:
            raise ImportCommitBlocked("Unknown company or operator")
        if (
            company.status != CompanyStatus.ACTIVE.value
            or actor.status != UserStatus.ACTIVE.value
        ):
            raise ImportCommitBlocked("Company and operator must both be active")
        membership = session.scalar(
            select(Membership).where(
                Membership.company_id == company.id,
                Membership.user_id == actor.id,
                Membership.status == MembershipStatus.ACTIVE.value,
            )
        )
        if membership is None or Permission.TRADE_WRITE not in permissions_for(membership.role):
            raise ImportCommitBlocked("Operator lacks trade.write for this company")
        incoming = _source_keys(preview.kind, preview)
        existing = _live_existing(session, preview.kind, company.id)
        if incoming & existing:
            raise ImportCommitBlocked(
                "At least one record already exists; no records were written"
            )
        meta = WriteMeta(
            company_id=company.id,
            actor_id=actor.id,
            request_id=f"local-import:{source_sha256[:32]}",
        )
        for row in preview.rows:
            if preview.kind == "products":
                ProductService(database).create(session, meta=meta, data=row.values)
            else:
                CounterpartyService(database).create(session, meta=meta, data=row.values)
        return preview.accepted


def apply_if_authorized(
    *,
    settings: Settings,
    filename: Path,
    kind: str,
    company_name: str,
    actor_email: str,
    confirmed_phrase: str,
    restore_tested: date | None,
    database: Database | None = None,
) -> dict[str, str | int | bool]:
    """Do not even connect to a DB until explicit local-only operator gates pass."""

    if settings.environment not in LOCAL_ONLY:
        raise ImportCommitBlocked("Bulk import CLI is disabled outside local/test/ci")
    if not 1 <= filename.stat().st_size <= MAX_BYTES:
        raise ImportCommitBlocked("Import must be nonempty and at most 2 MB")
    source = filename.read_bytes()
    preview = preview_import(filename.name, source, kind=kind)
    digest = hashlib.sha256(source).hexdigest()
    phrase = f"IMPORT {digest[:12].upper()}"
    if confirmed_phrase != phrase:
        raise ImportCommitBlocked(f"Explicit review required; confirmation phrase: {phrase}")
    if restore_tested is None or restore_tested > date.today():
        raise ImportCommitBlocked("A dated operator-confirmed backup restore test is required")
    if (date.today() - restore_tested).days > 7:
        raise ImportCommitBlocked("The backup restore evidence must be from the last seven days")
    if preview.rejected:
        raise ImportCommitBlocked("File has invalid or duplicate rows; commit blocked")
    if not preview.rows:
        raise ImportCommitBlocked("Cannot commit an empty file")
    owned = database is None
    db = database if database is not None else Database(
        settings, dsn_override=settings.migration_dsn
    )
    try:
        written = commit_preview(
            db,
            preview=preview,
            company_name=company_name,
            actor_email=actor_email,
            source_sha256=digest,
        )
    finally:
        if owned:
            db.dispose()
    return {
        "status": "COMMITTED",
        "rows": written,
        "company": company_name,
        "source_sha256": digest,
        "existing_records_updated": False,
        "messages_sent": False,
    }


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--file", type=Path, required=True)
    parser.add_argument("--kind", choices=("products", "counterparties"), required=True)
    parser.add_argument("--company", required=True)
    parser.add_argument("--actor", required=True, help="Existing active trade writer email")
    parser.add_argument("--commit", action="store_true")
    parser.add_argument("--confirm", default="")
    parser.add_argument("--restore-tested", type=date.fromisoformat)
    args = parser.parse_args()

    try:
        if not 1 <= args.file.stat().st_size <= MAX_BYTES:
            raise ImportCommitBlocked("Import must be nonempty and at most 2 MB")
        content = args.file.read_bytes()
        preview = preview_import(args.file.name, content, kind=args.kind)
        digest = hashlib.sha256(content).hexdigest()
        summary = {
            "status": "PREVIEW_ONLY",
            "valid_rows": preview.accepted,
            "rejected_rows": preview.rejected,
            "commit_phrase": f"IMPORT {digest[:12].upper()}",
            "committed": False,
        }
        if args.commit:
            result = apply_if_authorized(
                settings=Settings(),
                filename=args.file,
                kind=args.kind,
                company_name=args.company,
                actor_email=args.actor,
                confirmed_phrase=args.confirm,
                restore_tested=args.restore_tested,
            )
            summary = result
        print(json.dumps(summary, ensure_ascii=False, indent=2))
        return 0 if (args.commit or preview.rejected == 0) else 2
    except (ImportPreviewError, ImportCommitBlocked, OSError, ValueError) as exc:
        print(json.dumps({"status": "BLOCKED", "reason": str(exc)}, ensure_ascii=False))
        return 1


if __name__ == "__main__":
    raise SystemExit(main())

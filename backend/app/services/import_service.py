"""Stage 13C: authenticated, company-scoped CSV/XLSX import (inspect, preview, commit).

The parser is the Stage 13A :func:`~app.services.import_preview.preview_import`; nothing
here evaluates a formula or trusts a file name. A preview compares every valid row with the
live records of the *active company* and reports it as ``NEW``, ``EXISTS`` (already in the
company) or ``INVALID``. A commit:

* needs the SHA-256 of exactly the file that was previewed (so a swapped file is refused);
* refuses any invalid row and — unless ``skip_existing`` is set — any existing record;
* never updates an existing record: existing keys are skipped, never overwritten;
* writes every new row, the ledger row and the audit row in one transaction;
* is idempotent by file hash: the same file for the same company and kind is recorded once
  and a repeat returns the recorded result without writing.
"""

from __future__ import annotations

import hashlib
from dataclasses import dataclass
from pathlib import Path
from typing import Literal
from uuid import UUID

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.core.errors import BadRequestError, ConflictError
from app.db.engine import Database
from app.db.models import AuditAction, AuditOutcome, Counterparty, ImportBatch, Product
from app.db.tenant import apply_company_context
from app.services.audit import record_audit
from app.services.catalog import ProductService
from app.services.crm import CounterpartyService
from app.services.import_preview import (
    ALIASES,
    FIELDS,
    REQUIRED,
    ImportKind,
    ImportPreview,
    ImportPreviewError,
    PreviewRow,
    header_row,
    preview_import,
)
from app.services.trade_meta import WriteMeta

RowStatus = Literal["NEW", "EXISTS", "INVALID"]


@dataclass(frozen=True)
class HeaderGuess:
    """One column heading of the uploaded file and the field it maps to (or ``None``)."""

    heading: str
    field: str | None


@dataclass(frozen=True)
class InspectReport:
    kind: ImportKind
    source_sha256: str
    headers: tuple[HeaderGuess, ...]
    fields: tuple[str, ...]
    required: tuple[str, ...]


@dataclass(frozen=True)
class ReportRow:
    row: int
    status: RowStatus
    values: dict[str, str]
    errors: tuple[str, ...]


@dataclass(frozen=True)
class ImportReport:
    kind: ImportKind
    filename: str
    source_sha256: str
    total_rows: int
    new_rows: int
    existing_rows: int
    invalid_rows: int
    rows: tuple[ReportRow, ...]
    already_imported: bool

    @property
    def can_commit(self) -> bool:
        return self.invalid_rows == 0 and self.new_rows > 0 and not self.already_imported


@dataclass(frozen=True)
class ImportOutcome:
    batch_id: UUID
    kind: ImportKind
    source_sha256: str
    total_rows: int
    created_rows: int
    skipped_rows: int
    replayed: bool


def sanitise_filename(value: str) -> str:
    """Display-only name: the base name, no path, bounded, no control characters."""
    name = Path(value.replace("\\", "/")).name
    cleaned = "".join(ch for ch in name if ch.isprintable() and ch not in '<>:"|?*')
    return (cleaned.strip() or "import")[:120]


def sha256_of(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def inspect_headers(filename: str, data: bytes, *, kind: ImportKind) -> InspectReport:
    """Read only the header row and show how each heading would be mapped."""
    try:
        headings = header_row(filename, data)
    except ImportPreviewError as exc:
        raise BadRequestError(str(exc)) from exc
    guesses: list[HeaderGuess] = []
    for heading in headings:
        normalised = heading.strip().casefold().replace(" ", "_").replace("-", "_")
        field = ALIASES.get(normalised, normalised)
        guesses.append(HeaderGuess(heading, field if field in FIELDS[kind] else None))
    return InspectReport(
        kind=kind,
        source_sha256=sha256_of(data),
        headers=tuple(guesses),
        fields=tuple(sorted(FIELDS[kind])),
        required=tuple(sorted(REQUIRED[kind])),
    )


def _product_key(values: dict[str, str]) -> str:
    return values.get("sku", "").strip().upper()


def _counterparty_key(values: dict[str, str]) -> str:
    return " ".join(values.get("name", "").split()).casefold()


def _key_of(kind: ImportKind, values: dict[str, str]) -> str:
    return _product_key(values) if kind == "products" else _counterparty_key(values)


def _existing_keys(session: Session, kind: ImportKind, company_id: UUID) -> set[str]:
    if kind == "products":
        rows = session.scalars(select(Product.sku).where(Product.company_id == company_id))
        return {row.strip().upper() for row in rows}
    rows = session.scalars(select(Counterparty.name).where(Counterparty.company_id == company_id))
    return {" ".join(row.split()).casefold() for row in rows}


def _parse(
    filename: str, data: bytes, kind: ImportKind, mapping: dict[str, str] | None
) -> ImportPreview:
    try:
        return preview_import(filename, data, kind=kind, mapping=mapping)
    except ImportPreviewError as exc:
        raise BadRequestError(str(exc)) from exc


def _report(
    session: Session,
    *,
    company_id: UUID,
    filename: str,
    data: bytes,
    kind: ImportKind,
    mapping: dict[str, str] | None,
) -> tuple[ImportReport, ImportPreview]:
    preview = _parse(filename, data, kind, mapping)
    existing = _existing_keys(session, kind, company_id)
    digest = sha256_of(data)
    rows: list[ReportRow] = []
    for item in preview.rows:
        status: RowStatus
        errors = item.errors
        if not item.valid:
            status = "INVALID"
        elif _key_of(kind, item.values) in existing:
            status = "EXISTS"
            errors = ("Already exists in this company; it will not be changed.",)
        else:
            status = "NEW"
        rows.append(ReportRow(item.row, status, item.values, errors))
    already = (
        session.scalar(
            select(ImportBatch.id).where(
                ImportBatch.company_id == company_id,
                ImportBatch.kind == kind,
                ImportBatch.source_sha256 == digest,
            )
        )
        is not None
    )
    report = ImportReport(
        kind=kind,
        filename=sanitise_filename(filename),
        source_sha256=digest,
        total_rows=len(rows),
        new_rows=sum(r.status == "NEW" for r in rows),
        existing_rows=sum(r.status == "EXISTS" for r in rows),
        invalid_rows=sum(r.status == "INVALID" for r in rows),
        rows=tuple(rows),
        already_imported=already,
    )
    return report, preview


def preview(
    database: Database,
    *,
    company_id: UUID,
    filename: str,
    data: bytes,
    kind: ImportKind,
    mapping: dict[str, str] | None = None,
) -> ImportReport:
    """Dry run against the live records of one company. Writes nothing."""
    with database.transaction() as session:
        apply_company_context(session, company_id)
        report, _ = _report(
            session,
            company_id=company_id,
            filename=filename,
            data=data,
            kind=kind,
            mapping=mapping,
        )
        return report


def commit(
    database: Database,
    *,
    meta: WriteMeta,
    filename: str,
    data: bytes,
    kind: ImportKind,
    mapping: dict[str, str] | None,
    expected_sha256: str,
    skip_existing: bool,
) -> ImportOutcome:
    """Create the new rows atomically; see the module docstring for the rules."""
    digest = sha256_of(data)
    if expected_sha256.lower() != digest:
        raise ConflictError(
            "The file differs from the one that was previewed. Preview it again before importing."
        )
    with database.transaction() as session:
        apply_company_context(session, meta.company_id)
        report, _ = _report(
            session,
            company_id=meta.company_id,
            filename=filename,
            data=data,
            kind=kind,
            mapping=mapping,
        )
        if report.already_imported:
            batch = session.scalars(
                select(ImportBatch).where(
                    ImportBatch.company_id == meta.company_id,
                    ImportBatch.kind == kind,
                    ImportBatch.source_sha256 == digest,
                )
            ).one()
            return ImportOutcome(
                batch.id,
                kind,
                digest,
                batch.total_rows,
                batch.created_rows,
                batch.skipped_rows,
                replayed=True,
            )
        if report.invalid_rows:
            raise BadRequestError("The file has invalid rows. Fix them and upload it again.")
        if report.existing_rows and not skip_existing:
            raise ConflictError(
                "Some records already exist in this company. Choose to skip them, or remove them "
                "from the file. Nothing was imported."
            )
        if report.new_rows == 0:
            raise ConflictError("The file contains no new records to import.")

        products = ProductService(database)
        counterparties = CounterpartyService(database)
        created = 0
        for item in report.rows:
            if item.status != "NEW":
                continue
            if kind == "products":
                products.create(session, meta=meta, data=item.values)
            else:
                counterparties.create(session, meta=meta, data=item.values)
            created += 1
        batch = ImportBatch(
            company_id=meta.company_id,
            kind=kind,
            source_sha256=digest,
            filename=report.filename,
            total_rows=report.total_rows,
            created_rows=created,
            skipped_rows=report.total_rows - created,
            created_by=meta.actor_id,
        )
        session.add(batch)
        session.flush()
        record_audit(
            session,
            action=AuditAction.IMPORT_COMMITTED,
            outcome=AuditOutcome.SUCCESS,
            actor_id=meta.actor_id,
            company_id=meta.company_id,
            request_id=meta.request_id,
            ip_address=meta.ip_address,
            user_agent=meta.user_agent,
            resource_type="import_batch",
            resource_id=str(batch.id),
            details={
                "kind": kind,
                "total_rows": report.total_rows,
                "created_rows": created,
                "skipped_rows": report.total_rows - created,
                "source_sha256": digest[:16],
            },
        )
        return ImportOutcome(
            batch.id,
            kind,
            digest,
            report.total_rows,
            created,
            report.total_rows - created,
            replayed=False,
        )


def list_batches(
    database: Database, *, company_id: UUID, limit: int = 25
) -> tuple[ImportBatch, ...]:
    with database.transaction() as session:
        apply_company_context(session, company_id)
        rows = session.scalars(
            select(ImportBatch)
            .where(ImportBatch.company_id == company_id)
            .order_by(ImportBatch.created_at.desc(), ImportBatch.id.desc())
            .limit(limit)
        ).all()
        session.expunge_all()
        return tuple(rows)


__all__ = [
    "HeaderGuess",
    "ImportOutcome",
    "ImportReport",
    "InspectReport",
    "PreviewRow",
    "ReportRow",
    "commit",
    "inspect_headers",
    "list_batches",
    "preview",
    "sanitise_filename",
    "sha256_of",
]

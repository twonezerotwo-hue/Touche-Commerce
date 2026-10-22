"""Private document storage and the trade document service.

Files are written to a directory outside every served path. The client never
supplies a path: the server generates ``company_id/document_id/v{n}-{sha}{ext}``,
recomputes the SHA-256 while streaming, enforces a hard size limit during the
write and verifies the digest again before a download is served.

Authorization is two-layered: PostgreSQL RLS scopes every row to the active
company, and :func:`_assert_entity` proves that the linked entity exists in that
same company. ``linked_entity_type`` is an allow-listed enum, so a client cannot
attach a file to an arbitrary table.

Malware scanning is **not** implemented; it is documented as a remaining control
in docs/PROGRESS.md.
"""

from __future__ import annotations

import hashlib
import os
import re
from collections.abc import Iterable
from dataclasses import dataclass
from datetime import UTC, date, datetime
from decimal import Decimal
from pathlib import Path
from typing import Any
from uuid import UUID, uuid4

from sqlalchemy import and_, func, select
from sqlalchemy.orm import Session

from app.core.config import Settings
from app.core.errors import (
    BadRequestError,
    ConflictError,
    NotFoundError,
    PayloadTooLargeError,
)
from app.db.engine import Database
from app.db.models import (
    AuditAction,
    AuditOutcome,
    Company,
    Counterparty,
    CustomerAcceptanceEvidence,
    Deal,
    DocumentStatus,
    DocumentVerificationStatus,
    LinkedEntityType,
    PurchaseOrder,
    SalesOrder,
    SalesOrderItem,
    Shipment,
    ShipmentItem,
    TradeDocument,
    TradeDocumentType,
)
from app.db.tenant import apply_actor_context, apply_company_context
from app.services.audit import record_audit
from app.services.trade_meta import WriteMeta, clean_optional

_MIME_SUFFIXES: dict[str, str] = {
    "application/pdf": ".pdf",
    "image/png": ".png",
    "image/jpeg": ".jpg",
    "text/csv": ".csv",
    "text/plain": ".txt",
    "application/vnd.openxmlformats-officedocument.wordprocessingml.document": ".docx",
    "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet": ".xlsx",
}
_MAGIC_PREFIXES: dict[str, tuple[bytes, ...]] = {
    "application/pdf": (b"%PDF-",),
    "image/png": (b"\x89PNG\r\n\x1a\n",),
    "image/jpeg": (b"\xff\xd8\xff",),
    "application/vnd.openxmlformats-officedocument.wordprocessingml.document": (
        b"PK\x03\x04",
    ),
    "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet": (b"PK\x03\x04",),
}
_STORAGE_KEY_PATTERN = re.compile(
    r"^[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}/"
    r"[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}/"
    r"v[1-9][0-9]{0,5}-[0-9a-f]{16}\.[a-z0-9]{1,8}$"
)
_FILENAME_SAFE = re.compile(r"[^A-Za-z0-9._ ()-]+")
_MAX_FILENAME = 255


def sanitise_filename(value: str) -> str:
    """Strip directories, control characters and over-long names."""
    base = os.path.basename(value.replace("\\", "/")).strip()
    cleaned = _FILENAME_SAFE.sub("_", base).strip(" .")
    if not cleaned:
        return "document"
    stem, dot, suffix = cleaned.rpartition(".")
    if dot and len(suffix) <= 8:
        cleaned = f"{stem[: _MAX_FILENAME - len(suffix) - 1]}.{suffix}"
    return cleaned[:_MAX_FILENAME] or "document"


def validate_mime(mime_type: str) -> str:
    normalised = (mime_type or "").split(";")[0].strip().lower()
    if normalised not in _MIME_SUFFIXES:
        raise BadRequestError(
            "This file type is not accepted.",
            details={
                "allowed": sorted(_MIME_SUFFIXES),
                "reason": "UNSUPPORTED_CONTENT_TYPE",
            },
        )
    return normalised


def _check_content(mime_type: str, first_chunk: bytes) -> None:
    prefixes = _MAGIC_PREFIXES.get(mime_type)
    if prefixes is not None:
        if not any(first_chunk.startswith(prefix) for prefix in prefixes):
            raise BadRequestError(
                "The file content does not match its declared type.",
                details={"reason": "CONTENT_TYPE_MISMATCH", "mime_type": mime_type},
            )
        return
    if b"\x00" in first_chunk[:4096]:
        raise BadRequestError(
            "A text document cannot contain binary control bytes.",
            details={"reason": "CONTENT_TYPE_MISMATCH"},
        )


@dataclass(frozen=True, slots=True)
class StoredFile:
    storage_key: str
    sha256: str
    size_bytes: int


class DocumentStorage:
    """Local private storage adapter (the only place that touches the filesystem)."""

    def __init__(self, settings: Settings) -> None:
        self._root = Path(settings.document_storage_path).resolve()
        self._max_bytes = settings.document_max_bytes

    @property
    def max_bytes(self) -> int:
        return self._max_bytes

    def path_for(self, storage_key: str) -> Path:
        """Resolve a server-generated key, refusing traversal or absolute paths."""
        if not _STORAGE_KEY_PATTERN.fullmatch(storage_key or ""):
            raise ValueError("Invalid storage key.")
        candidate = (self._root / storage_key).resolve()
        if not candidate.is_relative_to(self._root):
            raise ValueError("Storage key escapes the document root.")
        return candidate

    def save(
        self,
        *,
        company_id: UUID,
        document_id: UUID,
        version: int,
        mime_type: str,
        chunks: Iterable[bytes],
    ) -> StoredFile:
        self._root.mkdir(parents=True, exist_ok=True)
        directory = (self._root / str(company_id) / str(document_id)).resolve()
        if not directory.is_relative_to(self._root):
            raise ValueError("Storage directory escapes the document root.")
        directory.mkdir(parents=True, exist_ok=True)

        digest = hashlib.sha256()
        size = 0
        first_chunk = b""
        temporary = directory / f"v{version}.part"
        try:
            with temporary.open("wb") as handle:
                for chunk in chunks:
                    if not chunk:
                        continue
                    if not first_chunk:
                        first_chunk = chunk[:4096]
                        _check_content(mime_type, first_chunk)
                    size += len(chunk)
                    if size > self._max_bytes:
                        raise PayloadTooLargeError(
                            f"The file exceeds the {self._max_bytes} byte limit."
                        )
                    digest.update(chunk)
                    handle.write(chunk)
            if size == 0:
                raise BadRequestError("An empty file cannot be stored.")
            sha256 = digest.hexdigest()
            storage_key = (
                f"{company_id}/{document_id}/v{version}-{sha256[:16]}"
                f"{_MIME_SUFFIXES[mime_type]}"
            )
            temporary.replace(self.path_for(storage_key))
            return StoredFile(storage_key=storage_key, sha256=sha256, size_bytes=size)
        except Exception:
            temporary.unlink(missing_ok=True)
            raise

    def read_verified(self, storage_key: str, *, expected_sha256: str) -> bytes:
        path = self.path_for(storage_key)
        if not path.is_file():
            raise ConflictError(
                "The stored file is missing.",
                details={"reason": "DOCUMENT_FILE_MISSING"},
            )
        content = path.read_bytes()
        if hashlib.sha256(content).hexdigest() != expected_sha256:
            raise ConflictError(
                "The stored file does not match its recorded checksum.",
                details={"reason": "DOCUMENT_CHECKSUM_MISMATCH"},
            )
        return content

    def remove(self, storage_key: str) -> None:
        """Best-effort cleanup used only before a row is committed."""
        try:
            self.path_for(storage_key).unlink(missing_ok=True)
        except ValueError:  # pragma: no cover - defensive
            return


@dataclass(frozen=True, slots=True)
class DocumentRecord:
    id: UUID
    company_id: UUID
    document_type: str
    linked_entity_type: str
    linked_entity_id: UUID
    title: str
    original_filename: str
    storage_key: str
    mime_type: str
    size_bytes: int
    sha256: str
    version: int
    supersedes_document_id: UUID | None
    status: str
    verification_status: str
    is_draft: bool
    uploaded_by: UUID
    uploaded_at: datetime
    archived_at: datetime | None


@dataclass(frozen=True, slots=True)
class DocumentPage:
    items: tuple[DocumentRecord, ...]
    next_cursor: str | None


@dataclass(frozen=True, slots=True)
class UploadData:
    document_type: str
    linked_entity_type: str
    linked_entity_id: UUID
    title: str
    filename: str
    mime_type: str
    supersedes_document_id: UUID | None = None
    is_draft: bool = False


@dataclass(frozen=True, slots=True)
class DocumentDownload:
    record: DocumentRecord
    content: bytes


def _record(row: TradeDocument) -> DocumentRecord:
    return DocumentRecord(
        id=row.id,
        company_id=row.company_id,
        document_type=row.document_type,
        linked_entity_type=row.linked_entity_type,
        linked_entity_id=row.linked_entity_id,
        title=row.title,
        original_filename=row.original_filename,
        storage_key=row.storage_key,
        mime_type=row.mime_type,
        size_bytes=row.size_bytes,
        sha256=row.sha256,
        version=row.version,
        supersedes_document_id=row.supersedes_document_id,
        status=row.status,
        verification_status=row.verification_status,
        is_draft=row.is_draft,
        uploaded_by=row.uploaded_by,
        uploaded_at=row.uploaded_at,
        archived_at=row.archived_at,
    )


_ENTITY_MODELS: dict[LinkedEntityType, Any] = {
    LinkedEntityType.DEAL: Deal,
    LinkedEntityType.SALES_ORDER: SalesOrder,
    LinkedEntityType.PURCHASE_ORDER: PurchaseOrder,
    LinkedEntityType.SHIPMENT: Shipment,
    LinkedEntityType.CUSTOMER_ACCEPTANCE: CustomerAcceptanceEvidence,
}


def _assert_entity(
    session: Session, *, company_id: UUID, entity_type: str, entity_id: UUID
) -> None:
    """Prove the linked entity exists in this company before accepting a link."""
    try:
        model = _ENTITY_MODELS[LinkedEntityType(entity_type)]
    except ValueError as exc:
        raise BadRequestError(
            "Documents cannot be linked to that entity type.",
            details={
                "reason": "UNSUPPORTED_ENTITY_TYPE",
                "allowed": [entity.value for entity in _ENTITY_MODELS],
            },
        ) from exc
    found = session.execute(
        select(model.id).where(model.id == entity_id, model.company_id == company_id)
    ).scalar_one_or_none()
    if found is None:
        raise NotFoundError("The linked business record does not exist in this company.")


class DocumentService:
    """Metadata, private file storage and authorised retrieval."""

    def __init__(self, database: Database, settings: Settings) -> None:
        self._database = database
        self.storage = DocumentStorage(settings)

    # ------------------------------------------------------------------ reads
    def list(
        self,
        *,
        company_id: UUID,
        document_type: str | None,
        linked_entity_type: str | None,
        linked_entity_id: UUID | None,
        status: str | None,
        search: str | None,
        limit: int,
    ) -> tuple[DocumentRecord, ...]:
        with self._database.transaction() as session:
            apply_company_context(session, company_id)
            query = select(TradeDocument).where(TradeDocument.company_id == company_id)
            if document_type:
                query = query.where(TradeDocument.document_type == document_type)
            if linked_entity_type:
                query = query.where(
                    TradeDocument.linked_entity_type == linked_entity_type
                )
            if linked_entity_id:
                query = query.where(TradeDocument.linked_entity_id == linked_entity_id)
            if status:
                query = query.where(TradeDocument.status == status)
            if search:
                term = f"%{search.lower()}%"
                query = query.where(
                    TradeDocument.title.ilike(term)
                    | TradeDocument.original_filename.ilike(term)
                )
            rows = session.execute(
                query.order_by(
                    TradeDocument.uploaded_at.desc(), TradeDocument.id.desc()
                ).limit(limit)
            ).scalars()
            return tuple(_record(row) for row in rows)

    def get(self, *, company_id: UUID, document_id: UUID) -> DocumentRecord:
        with self._database.transaction() as session:
            apply_company_context(session, company_id)
            row = session.execute(
                select(TradeDocument).where(
                    TradeDocument.id == document_id,
                    TradeDocument.company_id == company_id,
                )
            ).scalar_one_or_none()
            if row is None:
                raise NotFoundError("The document does not exist.")
            return _record(row)

    def history(
        self, *, company_id: UUID, document_id: UUID
    ) -> tuple[DocumentRecord, ...]:
        with self._database.transaction() as session:
            apply_company_context(session, company_id)
            row = session.execute(
                select(TradeDocument).where(
                    TradeDocument.id == document_id,
                    TradeDocument.company_id == company_id,
                )
            ).scalar_one_or_none()
            if row is None:
                raise NotFoundError("The document does not exist.")
            rows = session.execute(
                select(TradeDocument)
                .where(
                    TradeDocument.company_id == company_id,
                    TradeDocument.linked_entity_type == row.linked_entity_type,
                    TradeDocument.linked_entity_id == row.linked_entity_id,
                    TradeDocument.document_type == row.document_type,
                )
                .order_by(TradeDocument.version)
            ).scalars()
            return tuple(_record(item) for item in rows)

    # ----------------------------------------------------------------- writes
    def upload(
        self,
        session: Session,
        *,
        meta: WriteMeta,
        data: UploadData,
        chunks: Iterable[bytes],
    ) -> DocumentRecord:
        try:
            document_type = TradeDocumentType(data.document_type).value
        except ValueError as exc:
            raise BadRequestError(
                "Unknown document type.",
                details={"allowed": [value.value for value in TradeDocumentType]},
            ) from exc
        try:
            entity_type = LinkedEntityType(data.linked_entity_type)
        except ValueError as exc:
            raise BadRequestError(
                "Documents cannot be linked to that entity type.",
                details={"allowed": [value.value for value in LinkedEntityType]},
            ) from exc
        _assert_entity(
            session,
            company_id=meta.company_id,
            entity_type=entity_type.value,
            entity_id=data.linked_entity_id,
        )

        filename = sanitise_filename(data.filename)
        mime_type = validate_mime(data.mime_type)
        title = " ".join((data.title or filename).split())[:200] or filename

        previous: TradeDocument | None = None
        if data.supersedes_document_id is not None:
            previous = session.execute(
                select(TradeDocument).where(
                    TradeDocument.id == data.supersedes_document_id,
                    TradeDocument.company_id == meta.company_id,
                )
            ).scalar_one_or_none()
            if previous is None:
                raise BadRequestError("The document being superseded does not exist.")
            if (
                previous.document_type != document_type
                or previous.linked_entity_type != entity_type.value
                or previous.linked_entity_id != data.linked_entity_id
            ):
                raise ConflictError(
                    "A new version must describe the same entity and document type.",
                    details={"reason": "VERSION_TARGET_MISMATCH"},
                )

        highest = session.execute(
            select(func.max(TradeDocument.version)).where(
                TradeDocument.company_id == meta.company_id,
                TradeDocument.linked_entity_type == entity_type.value,
                TradeDocument.linked_entity_id == data.linked_entity_id,
                TradeDocument.document_type == document_type,
            )
        ).scalar_one()
        version = int(highest or 0) + 1
        document_id = uuid4()
        stored = self.storage.save(
            company_id=meta.company_id,
            document_id=document_id,
            version=version,
            mime_type=mime_type,
            chunks=chunks,
        )
        now = datetime.now(tz=UTC)
        row = TradeDocument(
            id=document_id,
            company_id=meta.company_id,
            document_type=document_type,
            linked_entity_type=entity_type.value,
            linked_entity_id=data.linked_entity_id,
            title=title,
            original_filename=filename,
            storage_key=stored.storage_key,
            mime_type=mime_type,
            size_bytes=stored.size_bytes,
            sha256=stored.sha256,
            version=version,
            supersedes_document_id=previous.id if previous else None,
            status=DocumentStatus.ACTIVE.value,
            verification_status=DocumentVerificationStatus.UNVERIFIED.value,
            is_draft=data.is_draft,
            uploaded_by=meta.actor_id,
            uploaded_at=now,
        )
        try:
            session.add(row)
            if previous is not None:
                previous.status = DocumentStatus.ARCHIVED.value
                previous.archived_at = now
                previous.archived_by = meta.actor_id
            session.flush()
            record_audit(
                session,
                action=AuditAction.DOCUMENT_UPLOADED,
                outcome=AuditOutcome.SUCCESS,
                actor_id=meta.actor_id,
                company_id=meta.company_id,
                request_id=meta.request_id,
                ip_address=meta.ip_address,
                user_agent=meta.user_agent,
                resource_type="trade_document",
                resource_id=str(row.id),
                details={
                    "document_type": document_type,
                    "linked_entity_type": entity_type.value,
                    "linked_entity_id": str(data.linked_entity_id),
                    "version": version,
                    "sha256": stored.sha256,
                    "size_bytes": stored.size_bytes,
                    "is_draft": data.is_draft,
                },
            )
        except Exception:
            self.storage.remove(stored.storage_key)
            raise
        return _record(row)

    def download(
        self, session: Session, *, meta: WriteMeta, document_id: UUID
    ) -> DocumentDownload:
        apply_company_context(session, meta.company_id)
        row = session.execute(
            select(TradeDocument).where(
                TradeDocument.id == document_id,
                TradeDocument.company_id == meta.company_id,
            )
        ).scalar_one_or_none()
        if row is None:
            raise NotFoundError("The document does not exist.")
        if row.status == DocumentStatus.ARCHIVED.value:
            raise ConflictError(
                "This document version has been archived.",
                details={"reason": "DOCUMENT_ARCHIVED"},
            )
        _assert_entity(
            session,
            company_id=meta.company_id,
            entity_type=row.linked_entity_type,
            entity_id=row.linked_entity_id,
        )
        content = self.storage.read_verified(row.storage_key, expected_sha256=row.sha256)
        record_audit(
            session,
            action=AuditAction.DOCUMENT_DOWNLOADED,
            outcome=AuditOutcome.SUCCESS,
            actor_id=meta.actor_id,
            company_id=meta.company_id,
            request_id=meta.request_id,
            ip_address=meta.ip_address,
            user_agent=meta.user_agent,
            resource_type="trade_document",
            resource_id=str(row.id),
            details={
                "document_type": row.document_type,
                "linked_entity_type": row.linked_entity_type,
                "linked_entity_id": str(row.linked_entity_id),
                "version": row.version,
            },
        )
        return DocumentDownload(record=_record(row), content=content)

    def archive(
        self,
        session: Session,
        *,
        meta: WriteMeta,
        document_id: UUID,
        reason: str | None,
    ) -> DocumentRecord:
        apply_company_context(session, meta.company_id)
        row = session.execute(
            select(TradeDocument)
            .where(
                TradeDocument.id == document_id,
                TradeDocument.company_id == meta.company_id,
            )
            .with_for_update()
        ).scalar_one_or_none()
        if row is None:
            raise NotFoundError("The document does not exist.")
        if row.status == DocumentStatus.ARCHIVED.value:
            raise ConflictError(
                "The document is already archived.",
                details={"reason": "ALREADY_ARCHIVED"},
            )
        now = datetime.now(tz=UTC)
        row.status = DocumentStatus.ARCHIVED.value
        row.archived_at = now
        row.archived_by = meta.actor_id
        session.flush()
        record_audit(
            session,
            action=AuditAction.DOCUMENT_ARCHIVED,
            outcome=AuditOutcome.SUCCESS,
            actor_id=meta.actor_id,
            company_id=meta.company_id,
            request_id=meta.request_id,
            ip_address=meta.ip_address,
            user_agent=meta.user_agent,
            resource_type="trade_document",
            resource_id=str(row.id),
            details={
                "document_type": row.document_type,
                "version": row.version,
                "reason": clean_optional(reason),
            },
        )
        return _record(row)

    def set_verification(
        self,
        session: Session,
        *,
        meta: WriteMeta,
        document_id: UUID,
        verification_status: str,
        note: str | None,
    ) -> DocumentRecord:
        apply_company_context(session, meta.company_id)
        try:
            status = DocumentVerificationStatus(verification_status).value
        except ValueError as exc:
            raise BadRequestError(
                "Unknown verification status.",
                details={"allowed": ["VERIFIED", "REJECTED"]},
            ) from exc
        if status == DocumentVerificationStatus.UNVERIFIED.value:
            raise BadRequestError(
                "Use VERIFIED or REJECTED; a document cannot be un-verified."
            )
        row = session.execute(
            select(TradeDocument)
            .where(
                TradeDocument.id == document_id,
                TradeDocument.company_id == meta.company_id,
            )
            .with_for_update()
        ).scalar_one_or_none()
        if row is None:
            raise NotFoundError("The document does not exist.")
        row.verification_status = status
        session.flush()
        record_audit(
            session,
            action=AuditAction.DOCUMENT_VERIFIED,
            outcome=AuditOutcome.SUCCESS,
            actor_id=meta.actor_id,
            company_id=meta.company_id,
            request_id=meta.request_id,
            ip_address=meta.ip_address,
            user_agent=meta.user_agent,
            resource_type="trade_document",
            resource_id=str(row.id),
            details={
                "document_type": row.document_type,
                "version": row.version,
                "verification_status": status,
                "note": clean_optional(note),
            },
        )
        return _record(row)

    # --------------------------------------------------------------- previews
    def preview(
        self,
        *,
        company_id: UUID,
        actor_id: UUID,
        sales_order_id: UUID,
        kind: str,
        shipment_id: UUID | None = None,
    ) -> dict[str, Any]:
        """Build an honest DRAFT preview; never a legally issued document."""
        if kind not in ("commercial_invoice", "packing_list"):
            raise BadRequestError("Unknown preview kind.")
        with self._database.transaction() as session:
            apply_company_context(session, company_id)
            # The seller row is protected by a membership policy, so the actor
            # must be bound too or the join would silently hide the company.
            apply_actor_context(session, actor_id)
            row = session.execute(
                select(
                    SalesOrder,
                    Company.name.label("seller_name"),
                    Company.country.label("seller_country"),
                    Counterparty.name.label("buyer_name"),
                    Counterparty.country.label("buyer_country"),
                )
                .join(Company, Company.id == SalesOrder.company_id)
                .join(
                    Counterparty,
                    and_(
                        Counterparty.id == SalesOrder.customer_id,
                        Counterparty.company_id == SalesOrder.company_id,
                    ),
                )
                .where(
                    SalesOrder.id == sales_order_id,
                    SalesOrder.company_id == company_id,
                )
            ).one_or_none()
            if row is None:
                raise NotFoundError("The sales order does not exist.")
            order, seller_name, seller_country, buyer_name, buyer_country = row

            items = list(
                session.execute(
                    select(SalesOrderItem)
                    .where(
                        SalesOrderItem.company_id == company_id,
                        SalesOrderItem.sales_order_id == order.id,
                    )
                    .order_by(SalesOrderItem.sku)
                ).scalars()
            )
            shipped: dict[UUID, Decimal] = {}
            shipment_number: str | None = None
            if kind == "packing_list" and shipment_id is not None:
                shipment_row = session.execute(
                    select(Shipment).where(
                        Shipment.id == shipment_id,
                        Shipment.company_id == company_id,
                        Shipment.sales_order_id == order.id,
                    )
                ).scalar_one_or_none()
                if shipment_row is None:
                    raise NotFoundError(
                        "The shipment does not belong to this sales order."
                    )
                shipment_number = shipment_row.shipment_number
                if shipment_row.status != "CANCELLED":
                    for item_id, quantity in session.execute(
                        select(
                            ShipmentItem.sales_order_item_id,
                            ShipmentItem.quantity,
                        ).where(
                            ShipmentItem.company_id == company_id,
                            ShipmentItem.shipment_id == shipment_row.id,
                        )
                    ).all():
                        shipped[item_id] = quantity

            lines = [
                {
                    "sku": item.sku,
                    "description": item.description,
                    "quantity": str(item.quantity),
                    "unit": item.unit,
                    "unit_price": str(item.unit_price),
                    "line_total": str(item.line_total),
                    "shipment_quantity": (
                        str(shipped.get(item.id, Decimal("0")))
                        if kind == "packing_list"
                        else None
                    ),
                }
                for item in items
            ]
            header = {
                "kind": kind,
                "is_draft": True,
                "legal_notice": (
                    "DRAFT preview generated from accepted order data. This is not a "
                    "legally issued commercial invoice, customs declaration, "
                    "certificate of origin or carrier document."
                ),
                "document_label": (
                    "Commercial invoice (draft)"
                    if kind == "commercial_invoice"
                    else "Packing list (draft)"
                ),
                "document_number": f"DRAFT-{order.order_number}",
                "document_date": date.today().isoformat(),
                "sales_order_id": str(order.id),
                "order_number": order.order_number,
                "sales_quote_revision": order.sales_quote_revision,
                "seller": {"name": seller_name, "country": seller_country},
                "buyer": {"name": buyer_name, "country": buyer_country},
                "currency": order.currency,
                "incoterm": order.incoterm,
                "named_delivery_place": order.named_delivery_place,
                "payment_terms": order.payment_terms_snapshot,
                "order_total": str(order.order_total),
                "shipment_id": str(shipment_id) if shipment_id else None,
                "shipment_number": shipment_number,
                "generated_at": datetime.now(tz=UTC).isoformat(),
            }
            return {"header": header, "lines": lines}


__all__ = [
    "DocumentDownload",
    "DocumentPage",
    "DocumentRecord",
    "DocumentService",
    "DocumentStorage",
    "StoredFile",
    "UploadData",
    "sanitise_filename",
    "validate_mime",
]

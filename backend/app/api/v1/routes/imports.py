"""CSV / XLSX import wizard endpoints (Stage 13C).

``inspect`` shows how the file's headings map, ``preview`` compares every row with the
active company's live records, and ``commit`` creates the new rows atomically. All three
need ``trade.write`` in the active company; the company is the session's, never a request
field. A commit carries the SHA-256 of the previewed file and is idempotent by that hash.
"""

from __future__ import annotations

import json
from typing import Annotated, Any

from fastapi import APIRouter, Depends, File, Form, Request, Response, UploadFile, status

from app.api.deps import get_database
from app.api.security import active_company_id, require_company_permission
from app.api.v1.schemas.errors import ErrorEnvelope
from app.api.v1.schemas.imports import (
    HeaderGuessResponse,
    ImportBatchListResponse,
    ImportBatchResponse,
    ImportCommitResponse,
    ImportKindValue,
    ImportReportResponse,
    ImportRowResponse,
    InspectResponse,
)
from app.api.v1.trade_helpers import write_meta
from app.core.errors import BadRequestError, PayloadTooLargeError
from app.db.engine import Database
from app.security.permissions import Permission
from app.services import import_service
from app.services.auth import SessionContext
from app.services.import_preview import MAX_BYTES, MAX_COLS

router = APIRouter(prefix="/imports", tags=["imports"])

WriteContext = Annotated[
    SessionContext, Depends(require_company_permission(Permission.TRADE_WRITE))
]
ViewContext = Annotated[
    SessionContext, Depends(require_company_permission(Permission.COMPANY_VIEW))
]
Db = Annotated[Database, Depends(get_database)]


def _no_store(response: Response) -> None:
    response.headers["Cache-Control"] = "no-store"
    response.headers["Vary"] = "Cookie"


def _read_upload(upload: UploadFile) -> bytes:
    """Read at most the allowed size; a bigger body is refused, never buffered fully."""
    data = upload.file.read(MAX_BYTES + 1)
    if len(data) > MAX_BYTES:
        raise PayloadTooLargeError("The import file is larger than 2 MB.")
    if not data:
        raise BadRequestError("The import file is empty.")
    return data


def _parse_mapping(raw: str | None) -> dict[str, str] | None:
    if raw is None or not raw.strip():
        return None
    try:
        value: Any = json.loads(raw)
    except json.JSONDecodeError as exc:
        raise BadRequestError("The column mapping is not valid JSON.") from exc
    if (
        not isinstance(value, dict)
        or len(value) > MAX_COLS
        or not all(isinstance(k, str) and isinstance(v, str) for k, v in value.items())
    ):
        raise BadRequestError("The column mapping must be an object of heading to field.")
    return {k: v for k, v in value.items() if v}


def _report_response(report: import_service.ImportReport) -> ImportReportResponse:
    return ImportReportResponse(
        kind=report.kind,
        filename=report.filename,
        source_sha256=report.source_sha256,
        total_rows=report.total_rows,
        new_rows=report.new_rows,
        existing_rows=report.existing_rows,
        invalid_rows=report.invalid_rows,
        rows=[
            ImportRowResponse(row=r.row, status=r.status, values=r.values, errors=list(r.errors))
            for r in report.rows
        ],
        already_imported=report.already_imported,
        can_commit=report.can_commit,
    )


@router.post(
    "/inspect",
    response_model=InspectResponse,
    summary="Read the file's headings and show how they map",
    responses={
        400: {"model": ErrorEnvelope, "description": "Unsupported or unsafe file."},
        413: {"model": ErrorEnvelope, "description": "File larger than 2 MB."},
    },
)
def inspect_import(
    response: Response,
    context: WriteContext,
    kind: Annotated[ImportKindValue, Form()],
    file: Annotated[UploadFile, File()],
) -> InspectResponse:
    _no_store(response)
    data = _read_upload(file)
    report = import_service.inspect_headers(file.filename or "import", data, kind=kind)
    return InspectResponse(
        kind=report.kind,
        source_sha256=report.source_sha256,
        headers=[HeaderGuessResponse(heading=h.heading, field=h.field) for h in report.headers],
        fields=list(report.fields),
        required=list(report.required),
    )


@router.post(
    "/preview",
    response_model=ImportReportResponse,
    summary="Dry run: validate every row and compare it with the company's records",
    description="Writes nothing. Rows are NEW, EXISTS (will be skipped, never changed) or INVALID.",
    responses={
        400: {"model": ErrorEnvelope, "description": "Unsupported, unsafe or unmappable file."},
        413: {"model": ErrorEnvelope, "description": "File larger than 2 MB."},
    },
)
def preview_import(
    response: Response,
    context: WriteContext,
    database: Db,
    kind: Annotated[ImportKindValue, Form()],
    file: Annotated[UploadFile, File()],
    mapping: Annotated[str | None, Form()] = None,
) -> ImportReportResponse:
    _no_store(response)
    data = _read_upload(file)
    report = import_service.preview(
        database,
        company_id=active_company_id(context),
        filename=file.filename or "import",
        data=data,
        kind=kind,
        mapping=_parse_mapping(mapping),
    )
    return _report_response(report)


@router.post(
    "/commit",
    response_model=ImportCommitResponse,
    status_code=status.HTTP_201_CREATED,
    summary="Create the new rows atomically (idempotent by file hash)",
    description=(
        "Needs the SHA-256 of the previewed file. Invalid rows block the import; existing "
        "records are never updated and need skip_existing. The same file is recorded once: a "
        "repeat returns the recorded result with replayed=true and writes nothing."
    ),
    responses={
        400: {"model": ErrorEnvelope, "description": "Invalid rows or an unsafe file."},
        409: {
            "model": ErrorEnvelope,
            "description": "Changed file, existing records or nothing new.",
        },
        413: {"model": ErrorEnvelope, "description": "File larger than 2 MB."},
    },
)
def commit_import(
    request: Request,
    response: Response,
    context: WriteContext,
    database: Db,
    kind: Annotated[ImportKindValue, Form()],
    file: Annotated[UploadFile, File()],
    expected_sha256: Annotated[str, Form(min_length=64, max_length=64)],
    skip_existing: Annotated[bool, Form()] = False,
    mapping: Annotated[str | None, Form()] = None,
) -> ImportCommitResponse:
    _no_store(response)
    data = _read_upload(file)
    outcome = import_service.commit(
        database,
        meta=write_meta(context, request),
        filename=file.filename or "import",
        data=data,
        kind=kind,
        mapping=_parse_mapping(mapping),
        expected_sha256=expected_sha256,
        skip_existing=skip_existing,
    )
    if outcome.replayed:
        response.status_code = status.HTTP_200_OK
    return ImportCommitResponse(
        batch_id=outcome.batch_id,
        kind=outcome.kind,
        source_sha256=outcome.source_sha256,
        total_rows=outcome.total_rows,
        created_rows=outcome.created_rows,
        skipped_rows=outcome.skipped_rows,
        replayed=outcome.replayed,
    )


@router.get(
    "",
    response_model=ImportBatchListResponse,
    summary="Recent imports of the active company",
)
def list_imports(response: Response, context: ViewContext, database: Db) -> ImportBatchListResponse:
    _no_store(response)
    batches = import_service.list_batches(database, company_id=active_company_id(context))
    return ImportBatchListResponse(
        items=[
            ImportBatchResponse(
                id=b.id,
                kind=b.kind,
                source_sha256=b.source_sha256,
                filename=b.filename,
                total_rows=b.total_rows,
                created_rows=b.created_rows,
                skipped_rows=b.skipped_rows,
                created_by=b.created_by,
                created_at=b.created_at,
            )
            for b in batches
        ]
    )

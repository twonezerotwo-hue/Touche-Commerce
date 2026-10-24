"""Stage 13C CSV/XLSX import API schemas (counts and row values for the uploader only)."""

from __future__ import annotations

from datetime import datetime
from typing import Literal
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field

ImportKindValue = Literal["products", "counterparties"]
RowStatusValue = Literal["NEW", "EXISTS", "INVALID"]


class ImportModel(BaseModel):
    model_config = ConfigDict(extra="ignore", json_schema_serialization_defaults_required=True)


class HeaderGuessResponse(ImportModel):
    heading: str
    field: str | None = Field(
        description="Field this column maps to automatically, or null when it needs a choice."
    )


class InspectResponse(ImportModel):
    kind: ImportKindValue
    source_sha256: str
    headers: list[HeaderGuessResponse]
    fields: list[str] = Field(description="Every field this kind accepts.")
    required: list[str] = Field(description="Fields every file must provide.")


class ImportRowResponse(ImportModel):
    row: int
    status: RowStatusValue
    values: dict[str, str]
    errors: list[str]


class ImportReportResponse(ImportModel):
    kind: ImportKindValue
    filename: str
    source_sha256: str
    total_rows: int
    new_rows: int
    existing_rows: int
    invalid_rows: int
    rows: list[ImportRowResponse]
    already_imported: bool
    can_commit: bool = Field(
        description="True when nothing is invalid, at least one row is new and the file was "
        "not imported before. Existing rows additionally need skip_existing."
    )


class ImportCommitResponse(ImportModel):
    batch_id: UUID
    kind: ImportKindValue
    source_sha256: str
    total_rows: int
    created_rows: int
    skipped_rows: int
    replayed: bool = Field(
        description="True when this exact file had already been imported; nothing was written now."
    )


class ImportBatchResponse(ImportModel):
    id: UUID
    kind: ImportKindValue
    source_sha256: str
    filename: str
    total_rows: int
    created_rows: int
    skipped_rows: int
    created_by: UUID
    created_at: datetime


class ImportBatchListResponse(ImportModel):
    items: list[ImportBatchResponse]

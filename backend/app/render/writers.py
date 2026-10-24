"""Single entry point: spec + format -> (bytes, media type, file extension)."""

from __future__ import annotations

from typing import Literal

from app.render.csv_writer import render_csv
from app.render.docx_writer import render_docx
from app.render.pdf_writer import render_pdf
from app.render.spec import DocumentSpec
from app.render.xlsx_writer import render_xlsx

OutputFormat = Literal["pdf", "docx", "xlsx", "csv"]

MEDIA_TYPES: dict[str, str] = {
    "pdf": "application/pdf",
    "docx": "application/vnd.openxmlformats-officedocument.wordprocessingml.document",
    "xlsx": "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
    "csv": "text/csv; charset=utf-8",
}


def render(spec: DocumentSpec, output: OutputFormat) -> bytes:
    if output == "pdf":
        return render_pdf(spec)
    if output == "docx":
        return render_docx(spec)
    if output == "xlsx":
        return render_xlsx(spec)
    return render_csv(spec)

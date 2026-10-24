"""CSV output: the document's table, UTF-8 with a BOM so Excel reads Turkish letters.

Raw numbers use a dot decimal and no thousands separator (machine-friendly). Text that a
spreadsheet could read as a formula is prefixed with an apostrophe (CSV injection).
"""

from __future__ import annotations

import csv
import io
from datetime import date, datetime
from decimal import Decimal

from app.render.formatting import clean_text
from app.render.spec import DocumentSpec

_FORMULA_LEAD = ("=", "+", "-", "@", "\t", "\r")


def _safe(value: object, kind: str) -> str:
    if value is None:
        return ""
    if isinstance(value, Decimal):
        return f"{value:f}"
    if isinstance(value, (date, datetime)):
        return value.date().isoformat() if isinstance(value, datetime) else value.isoformat()
    text = clean_text(value)
    if kind == "text" and text.startswith(_FORMULA_LEAD):
        return f"'{text}"
    return text


def render_csv(spec: DocumentSpec) -> bytes:
    buffer = io.StringIO(newline="")
    writer = csv.writer(buffer, lineterminator="\r\n")
    writer.writerow([clean_text(column.label) for column in spec.columns])
    for row in spec.rows:
        writer.writerow([_safe(row.get(column.key), column.kind) for column in spec.columns])
    return ("﻿" + buffer.getvalue()).encode("utf-8")

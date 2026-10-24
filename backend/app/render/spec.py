"""Format-neutral description of a trade document.

A builder (``app.services.document_builders``) turns stored records into a
:class:`DocumentSpec`; the writers (PDF, DOCX, XLSX, CSV) only draw it. Nothing in this
package touches the database, so every writer can be tested with a hand-made spec.

Raw values (``Decimal``, ``date``) stay raw in ``rows``; each writer formats them for its
medium and the document's locale, so the XLSX keeps real numbers and the PDF shows
``1.234,50`` or ``1,234.50`` as the locale requires.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import date
from decimal import Decimal
from typing import Literal

Locale = Literal["en", "tr"]
ColumnKind = Literal["text", "qty", "money", "date"]


@dataclass(frozen=True)
class Party:
    """A named party with only the lines that are actually on record (never invented)."""

    name: str
    lines: tuple[str, ...] = ()


@dataclass(frozen=True)
class Column:
    key: str
    label: str
    kind: ColumnKind = "text"


@dataclass(frozen=True)
class DocumentSpec:
    kind: str
    locale: Locale
    title: str
    number: str
    issue_date: date
    #: True for anything Commerce has not finalised. Drawn as a watermark and a banner.
    draft: bool
    #: Extra regulatory line, e.g. "not a tax invoice". Shown under the title.
    notice: str | None
    issuer: Party
    #: (label, party) blocks drawn side by side: buyer, supplier, ship-to ...
    parties: tuple[tuple[str, Party], ...]
    #: (label, already formatted value) pairs: incoterm, payment terms, validity ...
    facts: tuple[tuple[str, str], ...]
    columns: tuple[Column, ...]
    rows: tuple[dict[str, object], ...]
    currency: str | None
    #: (label, amount) lines shown under the table, in ``currency``.
    totals: tuple[tuple[str, Decimal], ...]
    notes: str | None
    #: Things the reader should know are missing, e.g. "seller tax number not configured".
    warnings: tuple[str, ...]
    footer: str
    filename: str

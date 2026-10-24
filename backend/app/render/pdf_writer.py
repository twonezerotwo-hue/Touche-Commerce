"""PDF output (ReportLab). A4, Bitstream Vera (bundled with ReportLab, covers Turkish).

Drafts carry a diagonal watermark on every page and a banner under the title, so a draft
can never be mistaken for a final or tax document. Output is deterministic (``invariant``):
the same spec always produces the same bytes.
"""

from __future__ import annotations

import io
from pathlib import Path
from xml.sax.saxutils import escape

import reportlab
from reportlab.lib import colors
from reportlab.lib.enums import TA_RIGHT
from reportlab.lib.pagesizes import A4
from reportlab.lib.styles import ParagraphStyle
from reportlab.lib.units import mm
from reportlab.pdfbase import pdfmetrics
from reportlab.pdfbase.ttfonts import TTFont
from reportlab.platypus import (
    KeepTogether,
    Paragraph,
    SimpleDocTemplate,
    Spacer,
    Table,
    TableStyle,
)

from app.render.formatting import clean_text, format_cell, format_date, format_money
from app.render.labels import label
from app.render.spec import Column, DocumentSpec

_FONT_DIR = Path(reportlab.__file__).resolve().parent / "fonts"
_FAMILY = "TrBody"
_registered = False

INK = colors.HexColor("#14213d")
MUTED = colors.HexColor("#5b6478")
RULE = colors.HexColor("#c9d0de")
BAND = colors.HexColor("#eef1f7")
WARN = colors.HexColor("#8a5a00")


def _register_fonts() -> None:
    global _registered
    if _registered:
        return
    files = {
        _FAMILY: "Vera.ttf",
        f"{_FAMILY}-Bold": "VeraBd.ttf",
        f"{_FAMILY}-Italic": "VeraIt.ttf",
        f"{_FAMILY}-BoldItalic": "VeraBI.ttf",
    }
    for name, filename in files.items():
        pdfmetrics.registerFont(TTFont(name, str(_FONT_DIR / filename)))
    pdfmetrics.registerFontFamily(
        _FAMILY,
        normal=_FAMILY,
        bold=f"{_FAMILY}-Bold",
        italic=f"{_FAMILY}-Italic",
        boldItalic=f"{_FAMILY}-BoldItalic",
    )
    _registered = True


def _style(name: str, **kwargs: object) -> ParagraphStyle:
    base: dict[str, object] = {"fontName": _FAMILY, "fontSize": 9, "leading": 12, "textColor": INK}
    base.update(kwargs)
    return ParagraphStyle(name, **base)


def _column_weight(column: Column) -> float:
    """Relative width: wide descriptions, roomy amounts, a sliver for the line number."""
    if column.key == "line":
        return 0.45
    if column.key == "description":
        return 3.0
    if column.kind == "money":
        return 1.6
    if column.kind == "qty":
        return 1.1
    return 1.3


def _p(text: object, style: ParagraphStyle) -> Paragraph:
    return Paragraph(escape(clean_text(text)).replace("\n", "<br/>"), style)


def render_pdf(spec: DocumentSpec) -> bytes:
    _register_fonts()
    locale = spec.locale
    body = _style("body")
    small = _style("small", fontSize=8, leading=10.5, textColor=MUTED)
    bold = _style("bold", fontName=f"{_FAMILY}-Bold")
    title_style = _style("title", fontName=f"{_FAMILY}-Bold", fontSize=20, leading=24)
    right = _style("right", alignment=TA_RIGHT)
    right_bold = _style("rightb", alignment=TA_RIGHT, fontName=f"{_FAMILY}-Bold")
    head = _style("head", fontName=f"{_FAMILY}-Bold", fontSize=8, textColor=colors.white)
    head_right = _style(
        "headr", fontName=f"{_FAMILY}-Bold", fontSize=8, textColor=colors.white, alignment=TA_RIGHT
    )

    buffer = io.BytesIO()
    document = SimpleDocTemplate(
        buffer,
        pagesize=A4,
        leftMargin=16 * mm,
        rightMargin=16 * mm,
        topMargin=16 * mm,
        bottomMargin=18 * mm,
        title=clean_text(f"{spec.title} {spec.number}"),
        author="TOUCHE COMMERCE",
        invariant=True,
    )
    width = A4[0] - 32 * mm
    story: list[object] = []

    # Header: issuer on the left, title / number / date on the right.
    issuer_lines = [
        Paragraph(
            f"<b>{escape(clean_text(spec.issuer.name))}</b>", _style("iss", fontSize=12, leading=15)
        )
    ]
    issuer_lines += [_p(line, small) for line in spec.issuer.lines]
    meta = [
        _p(spec.title, title_style),
        _p(f"{label(locale, 'number')}: {spec.number}", bold),
        _p(f"{label(locale, 'date')}: {format_date(spec.issue_date, locale)}", body),
    ]
    header = Table([[issuer_lines, meta]], colWidths=[width * 0.5, width * 0.5])
    header.setStyle(
        TableStyle(
            [
                ("VALIGN", (0, 0), (-1, -1), "TOP"),
                ("LINEBELOW", (0, 0), (-1, 0), 1, INK),
                ("BOTTOMPADDING", (0, 0), (-1, -1), 8),
                ("LEFTPADDING", (0, 0), (-1, -1), 0),
                ("RIGHTPADDING", (0, 0), (-1, -1), 0),
            ]
        )
    )
    story += [header, Spacer(1, 5 * mm)]

    if spec.draft:
        banner = Table(
            [
                [
                    _p(
                        f"{label(locale, 'draft')} - "
                        f"{spec.notice or label(locale, 'notice.draft_unapproved')}",
                        _style("ban", fontName=f"{_FAMILY}-Bold", textColor=WARN),
                    )
                ]
            ],
            colWidths=[width],
        )
        banner.setStyle(
            TableStyle(
                [
                    ("BACKGROUND", (0, 0), (-1, -1), colors.HexColor("#fff4d6")),
                    ("BOX", (0, 0), (-1, -1), 0.6, WARN),
                    ("TOPPADDING", (0, 0), (-1, -1), 4),
                    ("BOTTOMPADDING", (0, 0), (-1, -1), 4),
                ]
            )
        )
        story += [banner, Spacer(1, 4 * mm)]
    elif spec.notice:
        story += [_p(spec.notice, small), Spacer(1, 3 * mm)]

    # Parties.
    if spec.parties:
        cells = []
        for caption, party in spec.parties:
            block: list[object] = [
                _p(
                    caption.upper(),
                    _style("cap", fontSize=7, textColor=MUTED, fontName=f"{_FAMILY}-Bold"),
                ),
                _p(party.name, bold),
            ]
            block += [_p(line, body) for line in party.lines]
            cells.append(block)
        columns = len(cells)
        parties = Table([cells], colWidths=[width / columns] * columns)
        parties.setStyle(
            TableStyle([("VALIGN", (0, 0), (-1, -1), "TOP"), ("LEFTPADDING", (0, 0), (-1, -1), 0)])
        )
        story += [parties, Spacer(1, 4 * mm)]

    # Facts in two columns.
    if spec.facts:
        rows = []
        pairs = list(spec.facts)
        for index in range(0, len(pairs), 2):
            left = pairs[index]
            right_pair = pairs[index + 1] if index + 1 < len(pairs) else ("", "")
            rows.append(
                [
                    _p(left[0], small),
                    _p(left[1], body),
                    _p(right_pair[0], small),
                    _p(right_pair[1], body),
                ]
            )
        facts = Table(rows, colWidths=[width * 0.18, width * 0.32, width * 0.18, width * 0.32])
        facts.setStyle(
            TableStyle(
                [
                    ("BACKGROUND", (0, 0), (-1, -1), BAND),
                    ("VALIGN", (0, 0), (-1, -1), "TOP"),
                    ("TOPPADDING", (0, 0), (-1, -1), 3),
                    ("BOTTOMPADDING", (0, 0), (-1, -1), 3),
                ]
            )
        )
        story += [facts, Spacer(1, 5 * mm)]

    # Main table.
    if spec.columns:
        numeric = {"qty", "money"}
        data = [
            [
                _p(column.label, head_right if column.kind in numeric else head)
                for column in spec.columns
            ]
        ]
        for row in spec.rows:
            data.append(
                [
                    _p(
                        format_cell(column.kind, row.get(column.key), locale),
                        right if column.kind in numeric else body,
                    )
                    for column in spec.columns
                ]
            )
        weights = [_column_weight(column) for column in spec.columns]
        total = sum(weights)
        table = Table(data, colWidths=[width * weight / total for weight in weights], repeatRows=1)
        style = [
            ("BACKGROUND", (0, 0), (-1, 0), INK),
            ("VALIGN", (0, 0), (-1, -1), "TOP"),
            ("LINEBELOW", (0, 0), (-1, -1), 0.25, RULE),
            ("TOPPADDING", (0, 0), (-1, -1), 4),
            ("BOTTOMPADDING", (0, 0), (-1, -1), 4),
        ]
        for index in range(2, len(data), 2):
            style.append(("BACKGROUND", (0, index), (-1, index), BAND))
        table.setStyle(TableStyle(style))
        story.append(table)

    if spec.totals:
        story.append(Spacer(1, 3 * mm))
        totals_rows = [
            [
                _p(caption, right_bold if index == len(spec.totals) - 1 else right),
                _p(
                    format_money(amount, spec.currency, locale),
                    right_bold if index == len(spec.totals) - 1 else right,
                ),
            ]
            for index, (caption, amount) in enumerate(spec.totals)
        ]
        totals = Table(totals_rows, colWidths=[width * 0.7, width * 0.3])
        totals.setStyle(
            TableStyle(
                [("LINEABOVE", (0, len(totals_rows) - 1), (-1, len(totals_rows) - 1), 0.8, INK)]
            )
        )
        story.append(KeepTogether(totals))

    if spec.notes:
        story += [Spacer(1, 5 * mm), _p(label(locale, "notes"), bold), _p(spec.notes, body)]
    if spec.warnings:
        story += [
            Spacer(1, 5 * mm),
            _p(label(locale, "warnings"), _style("w", fontName=f"{_FAMILY}-Bold", textColor=WARN)),
        ]
        story += [
            _p(f"- {warning}", _style("wl", textColor=WARN, fontSize=8))
            for warning in spec.warnings
        ]

    def decorate(canvas: object, doc: SimpleDocTemplate) -> None:
        canvas.saveState()  # type: ignore[attr-defined]
        if spec.draft:
            canvas.setFillColor(colors.Color(0.55, 0.55, 0.62))  # type: ignore[attr-defined]
            canvas.setFillAlpha(0.13)  # type: ignore[attr-defined]
            canvas.setFont(f"{_FAMILY}-Bold", 110)  # type: ignore[attr-defined]
            canvas.translate(A4[0] / 2, A4[1] / 2)  # type: ignore[attr-defined]
            canvas.rotate(45)  # type: ignore[attr-defined]
            canvas.drawCentredString(0, 0, label(locale, "draft"))  # type: ignore[attr-defined]
        canvas.restoreState()  # type: ignore[attr-defined]
        canvas.saveState()  # type: ignore[attr-defined]
        canvas.setFont(_FAMILY, 7.5)  # type: ignore[attr-defined]
        canvas.setFillColor(MUTED)  # type: ignore[attr-defined]
        canvas.drawString(16 * mm, 10 * mm, clean_text(spec.footer))  # type: ignore[attr-defined]
        canvas.drawRightString(  # type: ignore[attr-defined]
            A4[0] - 16 * mm, 10 * mm, f"{label(locale, 'page')} {doc.page}"
        )
        canvas.restoreState()  # type: ignore[attr-defined]

    document.build(story, onFirstPage=decorate, onLaterPages=decorate)
    return buffer.getvalue()

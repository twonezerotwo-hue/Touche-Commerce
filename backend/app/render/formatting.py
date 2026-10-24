"""Locale-aware formatting of amounts, quantities and dates for documents.

Plain functions on purpose: the process locale of a server must never decide how a
customer sees a price. Turkish uses ``1.234,50`` and ``24.10.2026``; English uses
``1,234.50`` and ``24 Oct 2026``.
"""

from __future__ import annotations

from datetime import date, datetime
from decimal import ROUND_HALF_UP, Decimal

from app.render.spec import Locale

_MONTHS = ("Jan", "Feb", "Mar", "Apr", "May", "Jun", "Jul", "Aug", "Sep", "Oct", "Nov", "Dec")

# Characters the bundled font lacks but trade documents legitimately contain.
_SUBSTITUTIONS = {
    "\u20ba": "TRY",  # Turkish lira sign: the bundled font has no glyph for it
    "\u2013": "-",  # en dash
    "\u2014": "-",  # em dash
    "\u00a0": " ",  # no-break space
}


def _group(integer: str, separator: str) -> str:
    groups: list[str] = []
    while len(integer) > 3:
        groups.insert(0, integer[-3:])
        integer = integer[:-3]
    groups.insert(0, integer)
    return separator.join(groups)


def format_decimal(value: Decimal, locale: Locale, *, places: int = 2) -> str:
    quantum = Decimal(1).scaleb(-places)
    rounded = value.quantize(quantum, rounding=ROUND_HALF_UP)
    sign = "-" if rounded < 0 else ""
    integer, _, fraction = f"{abs(rounded):f}".partition(".")
    thousands, point = (".", ",") if locale == "tr" else (",", ".")
    body = _group(integer, thousands)
    return f"{sign}{body}{point}{fraction}" if places else f"{sign}{body}"


def format_money(value: Decimal, currency: str | None, locale: Locale) -> str:
    amount = format_decimal(value, locale)
    return f"{amount} {currency}" if currency else amount


def format_quantity(value: Decimal, locale: Locale) -> str:
    """Up to four decimals, trailing zeros removed (``5.0000`` -> ``5``)."""
    text = format_decimal(value, locale, places=4)
    point = "," if locale == "tr" else "."
    if point in text:
        text = text.rstrip("0").rstrip(point)
    return text


def format_date(value: date | datetime | None, locale: Locale) -> str:
    if value is None:
        return "-"
    if isinstance(value, datetime):
        value = value.date()
    if locale == "tr":
        return f"{value.day:02d}.{value.month:02d}.{value.year}"
    return f"{value.day:02d} {_MONTHS[value.month - 1]} {value.year}"


def clean_text(value: object) -> str:
    """Text safe for the bundled font: control characters dropped, known glyphs replaced."""
    text = "" if value is None else str(value)
    for source, target in _SUBSTITUTIONS.items():
        text = text.replace(source, target)
    return "".join(ch for ch in text if ch == "\n" or ch >= " ")


def format_cell(kind: str, value: object, locale: Locale) -> str:
    """Human text for one table cell according to the column kind."""
    if value is None or value == "":
        return "-" if kind in ("date", "money", "qty") else ""
    if kind == "money" and isinstance(value, Decimal):
        return format_decimal(value, locale)
    if kind == "qty" and isinstance(value, Decimal):
        return format_quantity(value, locale)
    if kind == "date" and isinstance(value, (date, datetime)):
        return format_date(value, locale)
    return clean_text(value)

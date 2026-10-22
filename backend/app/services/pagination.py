"""Opaque, filter-bound pagination cursors (API contract §3).

Offset pagination is not used: trade data mutates while a user browses, so a
page number silently skips or repeats rows. A cursor carries the sort key of the
last row (``created_at`` plus ``id`` as a tiebreaker) and a fingerprint of the
active filters. A cursor presented with a different filter set is rejected with
``422 VALIDATION_ERROR`` instead of returning a misleading page.

Cursors are base64url-encoded JSON, deliberately opaque to clients but not
encrypted: they contain no secret, only a timestamp, a UUID and a hash.
"""

from __future__ import annotations

import base64
import binascii
import hashlib
import json
from collections.abc import Mapping
from dataclasses import dataclass
from datetime import UTC, datetime
from uuid import UUID

from app.core.errors import InvalidCursorError

_CURSOR_VERSION = 1
_MAX_CURSOR_LENGTH = 512


@dataclass(frozen=True)
class PageCursor:
    """Position of the last row of a page."""

    created_at: datetime
    row_id: UUID
    filter_fingerprint: str


def filter_fingerprint(filters: Mapping[str, str | None]) -> str:
    """Stable hash of the normalised filter set (order independent)."""
    canonical = json.dumps(
        {key: (value or "").strip().lower() for key, value in sorted(filters.items())},
        separators=(",", ":"),
        sort_keys=True,
    )
    return hashlib.sha256(canonical.encode("utf-8")).hexdigest()[:16]


def encode_cursor(*, created_at: datetime, row_id: UUID, filters: Mapping[str, str | None]) -> str:
    payload = {
        "v": _CURSOR_VERSION,
        "t": created_at.astimezone(UTC).isoformat(),
        "id": str(row_id),
        "f": filter_fingerprint(filters),
    }
    raw = json.dumps(payload, separators=(",", ":")).encode("utf-8")
    return base64.urlsafe_b64encode(raw).decode("ascii").rstrip("=")


def decode_cursor(cursor: str, *, filters: Mapping[str, str | None]) -> PageCursor:
    if not cursor or len(cursor) > _MAX_CURSOR_LENGTH:
        raise InvalidCursorError()
    padded = cursor + "=" * (-len(cursor) % 4)
    try:
        raw = base64.urlsafe_b64decode(padded.encode("ascii"))
        payload = json.loads(raw.decode("utf-8"))
    except (binascii.Error, UnicodeDecodeError, ValueError) as exc:
        raise InvalidCursorError("The pagination cursor could not be decoded.") from exc

    if not isinstance(payload, dict) or payload.get("v") != _CURSOR_VERSION:
        raise InvalidCursorError("The pagination cursor version is not supported.")

    expected_fingerprint = filter_fingerprint(filters)
    if payload.get("f") != expected_fingerprint:
        raise InvalidCursorError(
            "The pagination cursor was issued for a different filter combination."
        )

    try:
        created_at = datetime.fromisoformat(str(payload["t"]))
        row_id = UUID(str(payload["id"]))
    except (KeyError, ValueError) as exc:
        raise InvalidCursorError("The pagination cursor is incomplete.") from exc

    if created_at.tzinfo is None:
        created_at = created_at.replace(tzinfo=UTC)
    return PageCursor(
        created_at=created_at, row_id=row_id, filter_fingerprint=expected_fingerprint
    )


__all__ = ["PageCursor", "decode_cursor", "encode_cursor", "filter_fingerprint"]

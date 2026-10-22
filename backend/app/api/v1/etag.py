"""ETag / If-Match helpers (ADR-013).

Versioned resources answer with ``ETag: "v{version}"``. A ``PATCH`` must send the
same value back in ``If-Match``: a missing header is ``428
PRECONDITION_REQUIRED`` and a stale value is ``409 VERSION_CONFLICT`` (never
``412``) so clients can branch on a stable code.
"""

from __future__ import annotations

import re

from app.core.errors import BadRequestError, PreconditionRequiredError

_IF_MATCH_PATTERN = re.compile(r'^"?v(?P<version>[0-9]{1,9})"?$')


def etag_for(version: int) -> str:
    """Render the strong ETag for a resource version."""
    return f'"v{version}"'


def parse_if_match(header: str | None, *, required: bool) -> int | None:
    """Return the requested version, or ``None`` when absent and optional."""
    if header is None or not header.strip():
        if required:
            raise PreconditionRequiredError()
        return None
    match = _IF_MATCH_PATTERN.fullmatch(header.strip())
    if match is None:
        raise BadRequestError(
            'If-Match must be the ETag returned by the API, for example "v7".',
            details=[
                {
                    "field": "header.If-Match",
                    "message": "Unrecognised If-Match value.",
                    "type": "invalid_if_match",
                }
            ],
        )
    return int(match.group("version"))


def require_if_match(header: str | None) -> int:
    """Return the version from a mandatory ``If-Match`` header."""
    version = parse_if_match(header, required=True)
    if version is None:  # pragma: no cover - required=True cannot return None
        raise PreconditionRequiredError()
    return version


__all__ = ["etag_for", "parse_if_match", "require_if_match"]

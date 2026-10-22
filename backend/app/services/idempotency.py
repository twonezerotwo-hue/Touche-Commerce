"""Transactional idempotency for mutating endpoints (ADR-012).

The whole contract lives in **one** database transaction:

1. insert the idempotency row (``in_flight``) — the unique constraint serialises
   concurrent duplicates;
2. run the business change **in the same transaction**;
3. stamp the row ``completed`` with the serialised response;
4. commit.

That ordering is what makes a replay trustworthy: a response can only have been
recorded if the business change committed alongside it, and a failed request
rolls the row back, so the client may safely retry. Replays are scoped by
``(company, actor, endpoint, key)``; the stored fingerprint covers the method,
path and canonical JSON body, so the same key with a different payload is
rejected with ``409 IDEMPOTENCY_CONFLICT``.

The helper is a context manager rather than middleware because it needs the
verified session context (company + actor) and the parsed body, i.e. exactly the
values a starlette middleware does not have.
"""

from __future__ import annotations

import hashlib
import json
import re
from collections.abc import Iterator, Mapping
from contextlib import contextmanager
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
from typing import Any
from uuid import UUID, uuid4

from sqlalchemy import select, update
from sqlalchemy.dialects.postgresql import insert as pg_insert
from sqlalchemy.orm import Session

from app.core.errors import (
    BadRequestError,
    IdempotencyConflictError,
    IdempotencyInProgressError,
    IdempotencyKeyRequiredError,
)
from app.db.engine import Database
from app.db.models import IdempotencyRecord
from app.db.tenant import apply_actor_context, apply_company_context

KEY_MIN_LENGTH = 8
KEY_MAX_LENGTH = 128
_KEY_PATTERN = re.compile(rf"^[A-Za-z0-9._:-]{{{KEY_MIN_LENGTH},{KEY_MAX_LENGTH}}}$")

_UNIQUE_COLUMNS = ("actor_id", "company_id", "endpoint", "key")


@dataclass(frozen=True)
class Replay:
    """A previously committed response for the same key and fingerprint."""

    status_code: int
    body: dict[str, Any]


@dataclass
class IdempotentCall:
    """Handle yielded to the route: the session plus zero-or-one replay."""

    session: Session
    replay: Replay | None
    _record_id: UUID | None = None

    def complete(self, *, status_code: int, body: Mapping[str, Any]) -> None:
        """Record the response before the surrounding transaction commits."""
        if self._record_id is None:
            return
        self.session.execute(
            update(IdempotencyRecord)
            .where(IdempotencyRecord.id == self._record_id)
            .values(
                status="completed",
                response_status=status_code,
                response_body=dict(body),
            )
        )


def read_idempotency_key(value: str | None, *, required: bool) -> str | None:
    """Validate the header value; ``required`` endpoints reject a missing key."""
    if value is None or not value.strip():
        if required:
            raise IdempotencyKeyRequiredError()
        return None
    key = value.strip()
    if not _KEY_PATTERN.fullmatch(key):
        raise BadRequestError(
            "The Idempotency-Key header must be 8-128 characters from "
            "A-Z a-z 0-9 . _ : -",
            details=[
                {
                    "field": "header.Idempotency-Key",
                    "message": "Invalid idempotency key format.",
                    "type": "invalid_idempotency_key",
                }
            ],
        )
    return key


def canonical_payload(payload: Any | None) -> str:
    """Deterministic JSON for fingerprinting (key order and formatting ignored)."""
    if payload is None:
        return "null"
    return json.dumps(payload, sort_keys=True, separators=(",", ":"), default=str)


def request_fingerprint(*, method: str, path: str, payload: Any | None) -> str:
    material = f"{method.upper()} {path}\n{canonical_payload(payload)}"
    return hashlib.sha256(material.encode("utf-8")).hexdigest()


@contextmanager
def idempotent_transaction(
    database: Database,
    *,
    company_id: UUID,
    actor_id: UUID,
    endpoint: str,
    key: str | None,
    fingerprint: str,
    ttl_hours: int,
) -> Iterator[IdempotentCall]:
    """Open the transaction that owns both the idempotency row and the change."""
    now = datetime.now(tz=UTC)

    with database.transaction() as session:
        apply_company_context(session, company_id)
        apply_actor_context(session, actor_id)

        if key is None:
            yield IdempotentCall(session=session, replay=None)
            return

        inserted = session.execute(
            pg_insert(IdempotencyRecord)
            .values(
                id=uuid4(),
                actor_id=actor_id,
                company_id=company_id,
                endpoint=endpoint,
                key=key,
                request_fingerprint=fingerprint,
                status="in_flight",
                created_at=now,
                expires_at=now + timedelta(hours=ttl_hours),
            )
            .on_conflict_do_nothing(index_elements=list(_UNIQUE_COLUMNS))
            .returning(IdempotencyRecord.id)
        ).scalar_one_or_none()

        if inserted is not None:
            yield IdempotentCall(session=session, replay=None, _record_id=inserted)
            return

        existing = (
            session.execute(
                select(
                    IdempotencyRecord.id,
                    IdempotencyRecord.request_fingerprint,
                    IdempotencyRecord.status,
                    IdempotencyRecord.response_status,
                    IdempotencyRecord.response_body,
                    IdempotencyRecord.expires_at,
                ).where(
                    IdempotencyRecord.actor_id == actor_id,
                    IdempotencyRecord.company_id == company_id,
                    IdempotencyRecord.endpoint == endpoint,
                    IdempotencyRecord.key == key,
                )
            )
            .mappings()
            .one_or_none()
        )

        if existing is None:  # pragma: no cover - RLS/sequence anomaly, fail closed
            raise IdempotencyConflictError(
                "The idempotency record could not be resolved for this company."
            )

        if existing["request_fingerprint"] != fingerprint:
            raise IdempotencyConflictError(
                details={
                    "key": key,
                    "reason": "fingerprint_mismatch",
                    "hint": "Use a new Idempotency-Key for a different request body.",
                }
            )

        expired = existing["expires_at"] <= now
        if expired:
            session.execute(
                update(IdempotencyRecord)
                .where(IdempotencyRecord.id == existing["id"])
                .values(
                    status="in_flight",
                    response_status=None,
                    response_body=None,
                    created_at=now,
                    expires_at=now + timedelta(hours=ttl_hours),
                )
            )
            yield IdempotentCall(session=session, replay=None, _record_id=existing["id"])
            return

        if existing["status"] == "in_flight":
            raise IdempotencyInProgressError(headers={"Retry-After": "1"})

        if existing["status"] == "completed" and existing["response_status"] is not None:
            body = existing["response_body"] or {}
            yield IdempotentCall(
                session=session,
                replay=Replay(status_code=int(existing["response_status"]), body=dict(body)),
            )
            return

        # A previously failed attempt: take ownership and run it again.
        session.execute(
            update(IdempotencyRecord)
            .where(IdempotencyRecord.id == existing["id"])
            .values(
                status="in_flight",
                response_status=None,
                response_body=None,
                created_at=now,
                expires_at=now + timedelta(hours=ttl_hours),
            )
        )
        yield IdempotentCall(session=session, replay=None, _record_id=existing["id"])


__all__ = [
    "IdempotentCall",
    "Replay",
    "canonical_payload",
    "idempotent_transaction",
    "read_idempotency_key",
    "request_fingerprint",
]


"""Unit tests for pagination cursors and idempotency primitives."""

from __future__ import annotations

import hashlib
from datetime import UTC, datetime, timedelta
from uuid import uuid4

import pytest

from app.core.errors import (
    BadRequestError,
    IdempotencyKeyRequiredError,
    InvalidCursorError,
)
from app.services.idempotency import (
    canonical_payload,
    read_idempotency_key,
    request_fingerprint,
)
from app.services.pagination import decode_cursor, encode_cursor, filter_fingerprint


class TestCursors:
    def test_roundtrip_preserves_position_and_filters(self) -> None:
        created_at = datetime.now(tz=UTC) - timedelta(minutes=5)
        row_id = uuid4()
        filters = {"search": "acme", "status": "active", "type": None}
        cursor = encode_cursor(created_at=created_at, row_id=row_id, filters=filters)

        decoded = decode_cursor(cursor, filters=filters)

        assert decoded.row_id == row_id
        assert decoded.created_at == created_at
        assert decoded.filter_fingerprint == filter_fingerprint(filters)

    def test_cursor_is_bound_to_the_filter_set(self) -> None:
        cursor = encode_cursor(
            created_at=datetime.now(tz=UTC), row_id=uuid4(), filters={"search": "acme"}
        )
        with pytest.raises(InvalidCursorError):
            decode_cursor(cursor, filters={"search": "other"})

    def test_filter_fingerprint_is_order_independent(self) -> None:
        assert filter_fingerprint({"a": "1", "b": "2"}) == filter_fingerprint(
            {"b": "2", "a": "1"}
        )
        assert filter_fingerprint({"a": "1"}) != filter_fingerprint({"a": "2"})

    @pytest.mark.parametrize("cursor", ["", "%%%not-base64%%%", "e30", "x" * 600])
    def test_malformed_cursors_are_rejected(self, cursor: str) -> None:
        with pytest.raises(InvalidCursorError):
            decode_cursor(cursor, filters={})


class TestIdempotencyPrimitives:
    def test_key_is_required_when_the_endpoint_says_so(self) -> None:
        with pytest.raises(IdempotencyKeyRequiredError):
            read_idempotency_key(None, required=True)
        with pytest.raises(IdempotencyKeyRequiredError):
            read_idempotency_key("   ", required=True)

    def test_key_is_optional_for_non_critical_writes(self) -> None:
        assert read_idempotency_key(None, required=False) is None
        assert read_idempotency_key("abc-DEF_123.4:5", required=False) == "abc-DEF_123.4:5"

    @pytest.mark.parametrize("key", ["short", "has space", "x" * 129, "semi;colon"])
    def test_invalid_keys_are_rejected(self, key: str) -> None:
        with pytest.raises(BadRequestError):
            read_idempotency_key(key, required=False)

    def test_fingerprint_is_stable_and_body_sensitive(self) -> None:
        payload = {"title": "Deal", "quantity": "10.000"}
        first = request_fingerprint(method="post", path="/api/v1/deals", payload=payload)
        second = request_fingerprint(
            method="POST",
            path="/api/v1/deals",
            payload={"quantity": "10.000", "title": "Deal"},
        )
        assert first == second
        assert first == hashlib.sha256(
            b'POST /api/v1/deals\n{"quantity":"10.000","title":"Deal"}'
        ).hexdigest()
        assert first != request_fingerprint(
            method="POST", path="/api/v1/deals", payload={**payload, "title": "Other"}
        )
        assert first != request_fingerprint(
            method="PATCH", path="/api/v1/deals", payload=payload
        )

    def test_canonical_payload_handles_none(self) -> None:
        assert canonical_payload(None) == "null"
        assert canonical_payload({"b": 1, "a": 2}) == '{"a":2,"b":1}'

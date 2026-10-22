"""Read-only HTTP probe for the locally running TOUCHE FINANCE server.

Verified Finance contract (see ``docs/STAGE5_FINANCE_DISCOVERY.md``):

* ``GET /api/health`` is the only endpoint served without a session;
* it performs a read-only SQLite query and never initialises the schema;
* it returns ``{"durum": "ok" | "degraded", "yerel": <bool>}``.

This client deliberately does **not** send cookies, bearer tokens or Tailscale
identity headers, and it never calls a business endpoint.  The base URL is
restricted to literal loopback addresses because Finance has no service-to-
service credential yet; relying on Finance's ``127.0.0.1`` -> ``OWNER`` shortcut
would be network-position authorisation, not an integration contract.
"""

from __future__ import annotations

import http.client
import json
import time
from datetime import UTC, datetime
from typing import Any
from urllib.parse import urlsplit

from app.integrations.finance.contracts import FinanceHealth, FinanceLinkState

_HEALTH_PATH = "/api/health"
_MAX_RESPONSE_BYTES = 8_192
_LOOPBACK_HOSTS = frozenset({"127.0.0.1", "::1"})


class FinanceEndpointError(ValueError):
    """Raised when a configured Finance URL is not a safe loopback endpoint."""


def parse_loopback_base_url(value: str) -> tuple[str, int]:
    """Validate ``http://<loopback>:<port>`` and return ``(host, port)``.

    HTTPS, DNS names, credentials, paths, queries and fragments are rejected:
    each would either imply a trust relationship Finance does not expose or make
    the destination ambiguous.
    """

    parsed = urlsplit(value.strip())
    if parsed.scheme != "http":
        raise FinanceEndpointError("Finance base URL must use http on a loopback address.")
    if parsed.username is not None or parsed.password is not None:
        raise FinanceEndpointError("Finance base URL must not contain credentials.")
    host = parsed.hostname
    if host is None or host not in _LOOPBACK_HOSTS:
        raise FinanceEndpointError("Finance base URL must point at 127.0.0.1 or ::1.")
    if parsed.path not in {"", "/"} or parsed.query or parsed.fragment:
        raise FinanceEndpointError(
            "Finance base URL must not contain a path, query string or fragment."
        )
    try:
        port = parsed.port
    except ValueError as exc:
        raise FinanceEndpointError("Finance base URL contains an invalid port.") from exc
    return host, port or 80


class FinanceHealthClient:
    """One-shot, non-authenticated probe of Finance's public health endpoint."""

    def __init__(self, base_url: str, timeout_seconds: float = 2.0) -> None:
        if timeout_seconds <= 0:
            raise ValueError("timeout_seconds must be positive")
        self._host, self._port = parse_loopback_base_url(base_url)
        self._timeout_seconds = timeout_seconds

    def probe(self) -> FinanceHealth:
        """Return the observed state; network failures become data, not crashes."""

        started = time.perf_counter()
        connection = http.client.HTTPConnection(
            self._host,
            self._port,
            timeout=self._timeout_seconds,
        )
        try:
            connection.request(
                "GET",
                _HEALTH_PATH,
                headers={
                    "Accept": "application/json",
                    "User-Agent": "touche-commerce-finance-link/0.1",
                },
            )
            response = connection.getresponse()
            status = response.status
            server_header = response.getheader("Server") or ""
            content_type = response.getheader("Content-Type") or ""
            body = response.read(_MAX_RESPONSE_BYTES + 1)
        except TimeoutError:
            return self._failure(
                FinanceLinkState.UNREACHABLE,
                "Finance health probe timed out.",
                started,
            )
        except (OSError, http.client.HTTPException) as exc:
            return self._failure(
                FinanceLinkState.UNREACHABLE,
                f"Finance is unreachable ({type(exc).__name__}).",
                started,
            )
        finally:
            connection.close()

        if status != 200:
            return self._failure(
                FinanceLinkState.INCOMPATIBLE,
                f"Finance health endpoint returned HTTP {status}.",
                started,
            )
        if not server_header.startswith("ToucheFinans/"):
            return self._failure(
                FinanceLinkState.INCOMPATIBLE,
                "The endpoint did not identify itself as TOUCHE FINANCE.",
                started,
            )
        if not content_type.casefold().startswith("application/json"):
            return self._failure(
                FinanceLinkState.INCOMPATIBLE,
                "Finance health endpoint did not return JSON.",
                started,
            )
        if len(body) > _MAX_RESPONSE_BYTES:
            return self._failure(
                FinanceLinkState.INCOMPATIBLE,
                "Finance health response exceeded the accepted size.",
                started,
            )

        payload = _decode_object(body)
        if payload is None:
            return self._failure(
                FinanceLinkState.INCOMPATIBLE,
                "Finance health response was not a JSON object.",
                started,
            )

        durum = payload.get("durum")
        if durum not in {"ok", "degraded"}:
            return self._failure(
                FinanceLinkState.INCOMPATIBLE,
                "Finance health response did not contain a recognised 'durum'.",
                started,
            )

        local = payload.get("yerel")
        local_session: bool | None
        if local is None:
            local_session = None
        elif isinstance(local, bool):
            local_session = local
        else:
            return self._failure(
                FinanceLinkState.INCOMPATIBLE,
                "Finance health response contained a non-boolean 'yerel'.",
                started,
            )

        state = FinanceLinkState.HEALTHY if durum == "ok" else FinanceLinkState.DEGRADED
        detail = (
            "Finance reports a consistent ledger."
            if state is FinanceLinkState.HEALTHY
            else "Finance reports degraded recovery or ledger consistency."
        )
        return FinanceHealth(
            state=state,
            finance_status=durum,
            latency_ms=_elapsed_ms(started),
            detail=detail,
            checked_at=datetime.now(tz=UTC),
            reports_local_admin_session=local_session,
        )

    @staticmethod
    def _failure(state: FinanceLinkState, detail: str, started: float) -> FinanceHealth:
        return FinanceHealth(
            state=state,
            finance_status=None,
            latency_ms=_elapsed_ms(started),
            detail=detail,
            checked_at=datetime.now(tz=UTC),
        )


def _decode_object(body: bytes) -> dict[str, Any] | None:
    try:
        decoded = json.loads(body.decode("utf-8"))
    except (UnicodeDecodeError, json.JSONDecodeError):
        return None
    if not isinstance(decoded, dict):
        return None
    return decoded


def _elapsed_ms(started: float) -> float:
    return round((time.perf_counter() - started) * 1000, 2)


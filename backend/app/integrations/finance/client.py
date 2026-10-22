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
import re
import time
from datetime import UTC, datetime
from typing import Any
from urllib.parse import quote, urlencode, urlsplit

from app.integrations.finance.contracts import (
    FinanceApiResponse,
    FinanceHealth,
    FinanceLinkState,
)

_HEALTH_PATH = "/api/health"
_INTEGRATION_PREFIX = "/api/integration/v1"
_MAX_RESPONSE_BYTES = 8_192
_LOOPBACK_HOSTS = frozenset({"127.0.0.1", "::1"})
_FINANCE_COMPANY_RE = re.compile(r"^[a-z][a-z0-9_]{1,63}$")
_INTEGRATION_PATH_RE = re.compile(r"^/api/integration/v1/[a-z0-9_/-]+$")
_AUTH_FINANCE_CODES = frozenset(
    {"MISSING_CREDENTIALS", "INVALID_CREDENTIALS", "SCOPE_DENIED", "COMPANY_DENIED"}
)


class FinanceEndpointError(ValueError):
    """Raised when a configured Finance URL is not a safe loopback endpoint."""


class FinanceClientError(Exception):
    """A Finance call failed without exposing credentials or request headers.

    ``category`` is the Finance machine code when one was returned, otherwise a
    transport/protocol category. The connector translates it to a Commerce error
    while preserving the original category in ``details.finance_code``.
    """

    def __init__(
        self,
        category: str,
        message: str,
        *,
        status_code: int | None = None,
        request_id: str | None = None,
        details: dict[str, Any] | None = None,
    ) -> None:
        super().__init__(message)
        self.category = category
        self.status_code = status_code
        self.request_id = request_id
        self.details = details or {}



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



class FinanceIntegrationClient:
    """Authenticated, read-only client for Finance integration contract v1.

    Only the six verified endpoints are reachable. The base URL is validated as a
    literal loopback endpoint, paths are chosen internally (never accepted from an
    API request), and redirects are not followed. Responses are bounded in size.
    """

    def __init__(
        self,
        base_url: str,
        key_id: str,
        secret: str,
        timeout_seconds: float = 2.0,
        max_response_bytes: int = 1_048_576,
    ) -> None:
        if timeout_seconds <= 0:
            raise ValueError("timeout_seconds must be positive")
        if max_response_bytes < 1_024:
            raise ValueError("max_response_bytes must be at least 1024")
        if not key_id.startswith("key_") or len(key_id) != 20:
            raise ValueError("key_id is not a Finance integration key id")
        if len(secret) < 32:
            raise ValueError("secret is too short for a Finance integration secret")
        self._host, self._port = parse_loopback_base_url(base_url)
        self._key_id = key_id
        self._secret = secret
        self._timeout_seconds = timeout_seconds
        self._max_response_bytes = max_response_bytes

    def health(self) -> FinanceApiResponse:
        return self._get("/health")

    def capabilities(self) -> FinanceApiResponse:
        return self._get("/capabilities")

    def companies(self) -> FinanceApiResponse:
        return self._get("/companies")

    def summary(
        self, company_id: str, *, currency: str | None = None
    ) -> FinanceApiResponse:
        return self._get(
            f"/companies/{self._company_segment(company_id)}/summary",
            {"currency": currency} if currency else None,
        )

    def accounts(
        self,
        company_id: str,
        *,
        currency: str | None = None,
        from_date: str | None = None,
        to_date: str | None = None,
        limit: int | None = None,
        offset: int | None = None,
    ) -> FinanceApiResponse:
        return self._get(
            f"/companies/{self._company_segment(company_id)}/accounts",
            {
                "currency": currency,
                "from": from_date,
                "to": to_date,
                "limit": limit,
                "offset": offset,
            },
        )

    def aging(
        self,
        company_id: str,
        *,
        kind: str,
        currency: str | None = None,
        as_of: str | None = None,
        limit: int | None = None,
        offset: int | None = None,
    ) -> FinanceApiResponse:
        return self._get(
            f"/companies/{self._company_segment(company_id)}/aging",
            {
                "type": kind,
                "currency": currency,
                "as_of": as_of,
                "limit": limit,
                "offset": offset,
            },
        )


    @staticmethod
    def _company_segment(company_id: str) -> str:
        if not _FINANCE_COMPANY_RE.fullmatch(company_id):
            raise ValueError("Finance company id has an invalid shape")
        return quote(company_id, safe="")

    def _get(
        self,
        path: str,
        params: dict[str, Any] | None = None,
    ) -> FinanceApiResponse:
        full_path = f"{_INTEGRATION_PREFIX}{path}"
        if not _INTEGRATION_PATH_RE.fullmatch(full_path) or ".." in full_path:
            raise ValueError("Finance integration path is not allow-listed")
        query = self._query(params)
        if query:
            full_path = f"{full_path}?{query}"

        connection = http.client.HTTPConnection(
            self._host,
            self._port,
            timeout=self._timeout_seconds,
        )
        try:
            connection.request(
                "GET",
                full_path,
                headers={
                    "Accept": "application/json",
                    "User-Agent": "touche-commerce-finance-link/1.0",
                    "X-Touche-Integration-Key": self._key_id,
                    "X-Touche-Integration-Secret": self._secret,
                },
            )
            response = connection.getresponse()
            status = int(response.status)
            server_header = response.getheader("Server", "")
            content_type = response.getheader("Content-Type", "")
            declared_length = response.getheader("Content-Length")
            if declared_length:
                try:
                    if int(declared_length) > self._max_response_bytes:
                        raise FinanceClientError(
                            "RESPONSE_TOO_LARGE",
                            "Finance response exceeded the accepted size.",
                            status_code=status,
                        )
                except ValueError:
                    raise FinanceClientError(
                        "INVALID_RESPONSE",
                        "Finance returned an invalid Content-Length.",
                        status_code=status,
                    ) from None
            body = response.read(self._max_response_bytes + 1)
        except FinanceClientError:
            raise
        except TimeoutError as exc:
            raise FinanceClientError(
                "TIMEOUT", "Finance did not answer within the configured timeout."
            ) from exc
        except OSError as exc:
            raise FinanceClientError(
                "UNREACHABLE", "Finance could not be reached."
            ) from exc
        finally:
            connection.close()

        if len(body) > self._max_response_bytes:
            raise FinanceClientError(
                "RESPONSE_TOO_LARGE",
                "Finance response exceeded the accepted size.",
                status_code=status,
            )
        if not server_header.startswith("ToucheFinans/"):
            raise FinanceClientError(
                "INVALID_SERVER",
                "The endpoint did not identify itself as TOUCHE FINANCE.",
                status_code=status,
            )
        if not content_type.casefold().startswith("application/json"):
            raise FinanceClientError(
                "INVALID_CONTENT_TYPE",
                "Finance did not return JSON.",
                status_code=status,
            )

        payload = _decode_object(body)
        if payload is None:
            raise FinanceClientError(
                "INVALID_RESPONSE",
                "Finance returned a body that is not a JSON object.",
                status_code=status,
            )
        if status != 200:
            raise self._error_from_payload(payload, status)

        data = payload.get("data")
        meta = payload.get("meta")
        if not isinstance(data, dict) or not isinstance(meta, dict):
            raise FinanceClientError(
                "INVALID_RESPONSE",
                "Finance response did not contain the v1 data/meta envelope.",
                status_code=status,
            )
        if str(meta.get("contract_version")) != "1" or meta.get("read_only") is not True:
            raise FinanceClientError(
                "UNSUPPORTED_CONTRACT",
                "Finance did not confirm integration contract version 1 as read-only.",
                status_code=status,
                request_id=str(meta.get("request_id") or "") or None,
            )
        return FinanceApiResponse(
            data=data,
            request_id=str(meta.get("request_id") or "") or None,
            generated_at=str(meta.get("generated_at") or "") or None,
        )


    @staticmethod
    def _query(params: dict[str, Any] | None) -> str:
        if not params:
            return ""
        clean = {
            key: str(value)
            for key, value in params.items()
            if value is not None and str(value) != ""
        }
        return urlencode(clean, doseq=False)

    @staticmethod
    def _error_from_payload(
        payload: dict[str, Any], status_code: int
    ) -> FinanceClientError:
        error = payload.get("error")
        if not isinstance(error, dict):
            return FinanceClientError(
                "UPSTREAM_HTTP_ERROR",
                f"Finance returned HTTP {status_code}.",
                status_code=status_code,
            )
        code = str(error.get("code") or "UPSTREAM_HTTP_ERROR")[:64]
        message = " ".join(str(error.get("message") or "Finance request failed.").split())[:300]
        request_id = str(error.get("request_id") or "")[:128] or None
        details_raw = error.get("details")
        details = details_raw if isinstance(details_raw, dict) else {}
        return FinanceClientError(
            code,
            message,
            status_code=status_code,
            request_id=request_id,
            details=details,
        )


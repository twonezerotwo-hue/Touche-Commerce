"""Provider protocol and the shared, hardened HTTP call.

The call uses only the standard library (no new runtime dependency), never follows
a redirect (a redirect could carry the credential to another host), bounds the size
of the response and maps every failure onto the provider error types without ever
including the response body or the credential in a message.
"""

from __future__ import annotations

import json
import socket
import urllib.error
import urllib.request
from typing import Any, Protocol

from app.ai.errors import (
    ProviderAuthError,
    ProviderBadResponseError,
    ProviderQuotaError,
    ProviderRateLimitedError,
    ProviderTimeoutError,
    ProviderUnavailableError,
)
from app.ai.types import ModelRequest, ModelResponse

MAX_RESPONSE_BYTES = 2 * 1024 * 1024


class ModelProvider(Protocol):
    """What the gateway needs from a model provider."""

    name: str
    model: str
    #: True when requests leave the host (and so carry commercial data to a third party).
    is_external: bool

    def complete(self, request: ModelRequest) -> ModelResponse: ...


class _NoRedirect(urllib.request.HTTPRedirectHandler):
    def redirect_request(self, *args: Any, **kwargs: Any) -> None:
        return None


def parse_arguments(raw: Any) -> tuple[dict[str, Any], str | None]:
    """Parse provider tool arguments; a provider may send invalid JSON (documented)."""
    if isinstance(raw, dict):
        return dict(raw), None
    if raw in (None, ""):
        return {}, None
    if not isinstance(raw, str):
        return {}, "arguments are not a JSON object"
    try:
        value = json.loads(raw)
    except json.JSONDecodeError:
        return {}, "arguments are not valid JSON"
    if not isinstance(value, dict):
        return {}, "arguments are not a JSON object"
    return value, None


def _retry_after(headers: Any) -> float | None:
    value = headers.get("Retry-After") if headers else None
    try:
        return max(0.0, float(value)) if value is not None else None
    except (TypeError, ValueError):
        return None


def post_json(
    url: str,
    *,
    headers: dict[str, str],
    payload: dict[str, Any],
    timeout: float,
) -> dict[str, Any]:
    """POST JSON and return the decoded JSON object, or raise a provider error."""
    body = json.dumps(payload).encode("utf-8")
    request = urllib.request.Request(  # noqa: S310 - scheme and host validated in Settings
        url,
        data=body,
        method="POST",
        headers={"Content-Type": "application/json", "Accept": "application/json", **headers},
    )
    opener = urllib.request.build_opener(_NoRedirect())
    try:
        with opener.open(request, timeout=timeout) as response:
            raw = response.read(MAX_RESPONSE_BYTES + 1)
    except urllib.error.HTTPError as exc:
        status = int(exc.code)
        retry_after = _retry_after(exc.headers)
        exc.close()
        if status in (401, 403):
            raise ProviderAuthError() from None
        if status == 402:
            raise ProviderQuotaError() from None
        if status == 429:
            raise ProviderRateLimitedError(retry_after=retry_after) from None
        if status == 408:
            raise ProviderTimeoutError() from None
        if status >= 500:
            raise ProviderUnavailableError() from None
        raise ProviderBadResponseError() from None
    except TimeoutError:
        raise ProviderTimeoutError() from None
    except urllib.error.URLError as exc:
        if isinstance(exc.reason, (TimeoutError, socket.timeout)):
            raise ProviderTimeoutError() from None
        raise ProviderUnavailableError() from None
    except OSError:
        raise ProviderUnavailableError() from None

    if len(raw) > MAX_RESPONSE_BYTES:
        raise ProviderBadResponseError("The AI provider response was too large.")
    try:
        decoded = json.loads(raw.decode("utf-8"))
    except (UnicodeDecodeError, json.JSONDecodeError):
        raise ProviderBadResponseError() from None
    if not isinstance(decoded, dict):
        raise ProviderBadResponseError()
    return decoded

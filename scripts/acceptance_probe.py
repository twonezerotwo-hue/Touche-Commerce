#!/usr/bin/env python3
"""Non-invasive Stage 11 runtime preflight for Windows and macOS operators.

Only unauthenticated, read-only endpoints are probed. There is no login,
session creation, database operation, migration, message delivery, or command
execution. Successful probes do NOT prove local acceptance or production
readiness; interactive acceptance and a restored backup are separate evidence.
"""

from __future__ import annotations

import argparse
import ipaddress
import json
from collections.abc import Callable
from dataclasses import asdict, dataclass
from typing import Literal
from urllib.error import HTTPError, URLError
from urllib.parse import urlsplit
from urllib.request import HTTPRedirectHandler, ProxyHandler, Request, build_opener

Mode = Literal["local", "lan"]

LOCAL_FRONTEND = "http://localhost:3000"
LOCAL_BACKEND = "http://127.0.0.1:8000"


class TargetRejected(ValueError):
    """A probe URL would cross an unapproved network boundary."""


@dataclass(frozen=True)
class Check:
    name: str
    status: str
    http_status: int | None = None


class NoRedirect(HTTPRedirectHandler):
    """Never follow an external or authenticated redirect."""

    def redirect_request(self, req, fp, code, msg, headers, newurl):
        return None


def validated_base_url(url: str, *, mode: Mode) -> str:
    """Validate exactly one root origin, not an arbitrary fetch destination.

    LAN probes must use HTTPS to a literal private IPv4/IPv6 address.
    We intentionally disallow DNS, URL credentials, public addresses and
    plaintext LAN auth endpoints until a separate TLS/network acceptance.
    """

    parsed = urlsplit(url)
    if parsed.scheme not in {"http", "https"}:
        raise TargetRejected("Only http(s) URL schemes are supported")
    if parsed.username is not None or parsed.password is not None:
        raise TargetRejected("Credentials are not permitted in probe URLs")
    if not parsed.hostname or parsed.path not in {"", "/"} or parsed.query or parsed.fragment:
        raise TargetRejected("Expected an origin URL without path, query or fragment")
    try:
        port = parsed.port
    except ValueError as exc:
        raise TargetRejected("Invalid port") from exc
    if port is not None and not 1 <= port <= 65535:
        raise TargetRejected("Invalid port")

    host = parsed.hostname
    if mode == "local":
        if host not in {"localhost", "127.0.0.1", "::1"}:
            raise TargetRejected("Local mode accepts loopback only")
    elif mode == "lan":
        if parsed.scheme != "https":
            raise TargetRejected("LAN mode requires verified TLS (https)")
        try:
            ip = ipaddress.ip_address(host)
        except ValueError as exc:
            raise TargetRejected("LAN mode requires a literal private IP address") from exc
        if not ip.is_private or ip.is_loopback or ip.is_reserved or ip.is_multicast:
            raise TargetRejected("LAN mode rejects public, loopback or special-use addresses")
    else:
        raise TargetRejected("Unsupported mode")

    return f"{parsed.scheme}://{parsed.netloc}"


def read_status(url: str, timeout: float) -> int:
    """Make a bounded GET, without redirects, credentials or response logging."""

    request = Request(url, headers={"Cache-Control": "no-store", "Accept": "text/html, application/json"})
    opener = build_opener(ProxyHandler({}), NoRedirect)
    try:
        with opener.open(request, timeout=timeout) as response:
            return response.status
    except HTTPError as exc:
        return exc.code


def run_probes(
    frontend: str,
    backend: str | None,
    *,
    mode: Mode,
    timeout: float = 3.0,
    transport: Callable[[str, float], int] = read_status,
) -> dict[str, object]:
    """Return safe, bounded observations. No result grants launch approval."""

    front = validated_base_url(frontend, mode=mode)
    back = validated_base_url(backend, mode=mode) if backend else None
    if not 0.2 <= timeout <= 15:
        raise TargetRejected("Timeout must be between 0.2 and 15 seconds")

    targets = [
        ("frontend_login", f"{front}/login"),
        ("frontend_status", f"{front}/status"),
    ]
    if back:
        targets.extend(
            [
                ("backend_live", f"{back}/api/v1/health/live"),
                ("backend_ready", f"{back}/api/v1/health/ready"),
            ]
        )

    checks: list[Check] = []
    for name, url in targets:
        try:
            status = transport(url, timeout)
            checks.append(Check(name, "PASS" if status == 200 else "HTTP_NOT_OK", status))
        except (URLError, OSError, TimeoutError, ValueError):
            # Do not leak source addresses, URLs or response bodies in output.
            checks.append(Check(name, "UNREACHABLE"))
    all_passed = all(item.status == "PASS" for item in checks)
    return {
        "mode": mode,
        "status": "PROBES_PASS" if all_passed else "BLOCKED",
        "checks": [asdict(item) for item in checks],
        "evidence": "UNAUTHENTICATED_READ_ONLY_HTTP",
        "local_accepted": False,
        "production_approved": False,
        "warning": (
            "Green probes do not prove login, tenant isolation, trade workflows, "
            "data backup/restore, cross-device access or production security."
        ),
    }


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--mode", choices=["local", "lan"], default="local")
    parser.add_argument("--frontend", default=LOCAL_FRONTEND, help="Browser-facing frontend origin")
    parser.add_argument("--backend", default=None, help="Optional backend origin; local mode defaults to 127.0.0.1:8000")
    parser.add_argument("--timeout", type=float, default=3.0)
    args = parser.parse_args()

    backend = args.backend
    if backend is None and args.mode == "local":
        backend = LOCAL_BACKEND
    try:
        result = run_probes(args.frontend, backend, mode=args.mode, timeout=args.timeout)
    except TargetRejected as exc:
        result = {
            "status": "BLOCKED",
            "reason": "INVALID_PROBE_TARGET",
            "detail": str(exc),
            "local_accepted": False,
            "production_approved": False,
        }
    print(json.dumps(result, ensure_ascii=False, indent=2))
    return 0 if result["status"] == "PROBES_PASS" else 1


if __name__ == "__main__":
    raise SystemExit(main())

"""Stage 11: no-send, no-login and no-public-fetch operator probes."""

from __future__ import annotations

import importlib.util
import sys
from pathlib import Path
from urllib.error import URLError

import pytest

SCRIPT = Path(__file__).resolve().parents[2] / "scripts" / "acceptance_probe.py"
SPEC = importlib.util.spec_from_file_location("touche_acceptance_probe", SCRIPT)
assert SPEC is not None and SPEC.loader is not None
probe = importlib.util.module_from_spec(SPEC)
sys.modules[SPEC.name] = probe
SPEC.loader.exec_module(probe)


@pytest.mark.parametrize(
    "url",
    [
        "http://google.com",
        "https://192.168.10.5",
        "ftp://localhost:3000",
        "http://localhost:3000/steal",
        "http://localhost:3000?token=secret",
        "http://user:pass@localhost:3000",
        "http://localhost:99999",
        "http://localhost:0",
        "http://0.0.0.0:8000",
        "http://[::2]:8000",
    ],
)
def test_local_probe_refuses_unapproved_targets(url: str) -> None:
    with pytest.raises(probe.TargetRejected):
        probe.validated_base_url(url, mode="local")


@pytest.mark.parametrize(
    "url",
    [
        "http://192.168.1.23:3000",
        "https://1.1.1.1:443",
        "https://127.0.0.1:443",
        "https://localhost:443",
        "https://my-lan-host.local:443",
        "https://10.0.0.1:443/redirect",
    ],
)
def test_lan_mode_requires_literal_private_address_and_tls(url: str) -> None:
    with pytest.raises(probe.TargetRejected):
        probe.validated_base_url(url, mode="lan")


def test_lan_mode_can_probe_private_https_ip() -> None:
    assert (
        probe.validated_base_url("https://192.168.1.23:8443/", mode="lan")
        == "https://192.168.1.23:8443"
    )


def test_local_probes_do_not_assert_local_or_production_acceptance() -> None:
    seen: list[str] = []

    def fake_fetch(url: str, timeout: float) -> int:
        seen.append(url)
        assert timeout == 3.0
        return 200

    result = probe.run_probes(
        "http://localhost:3000",
        "http://127.0.0.1:8000",
        mode="local",
        transport=fake_fetch,
    )
    assert result["status"] == "PROBES_PASS"
    assert result["local_accepted"] is False
    assert result["production_approved"] is False
    assert seen == [
        "http://localhost:3000/login",
        "http://localhost:3000/status",
        "http://127.0.0.1:8000/api/v1/health/live",
        "http://127.0.0.1:8000/api/v1/health/ready",
    ]


def test_macbook_lan_browser_probe_does_not_claim_backend_health() -> None:
    seen: list[str] = []
    result = probe.run_probes(
        "https://192.168.1.20",
        None,
        mode="lan",
        transport=lambda url, _: (seen.append(url), 200)[1],
    )
    assert result["status"] == "PROBES_PASS"
    assert len(result["checks"]) == 2
    assert all("/api/v1/health" not in url for url in seen)
    assert result["local_accepted"] is False


def test_not_ready_and_http_redirect_fail_closed() -> None:
    def response(url: str, _: float) -> int:
        return 503 if url.endswith("/ready") else 302 if url.endswith("/login") else 200

    result = probe.run_probes(
        "http://localhost:3000", "http://127.0.0.1:8000", mode="local", transport=response
    )
    assert result["status"] == "BLOCKED"
    assert [check["status"] for check in result["checks"]] == [
        "HTTP_NOT_OK",
        "PASS",
        "PASS",
        "HTTP_NOT_OK",
    ]


def test_network_failures_do_not_echo_urls_or_sensitive_messages() -> None:
    def broken(_: str, __: float) -> int:
        raise URLError("secret-in-error-message")

    result = probe.run_probes(
        "http://127.0.0.1:3000", None, mode="local", transport=broken
    )
    assert result["status"] == "BLOCKED"
    assert all(check["status"] == "UNREACHABLE" for check in result["checks"])
    assert "secret" not in str(result)


def test_timeout_bounds_reject_invalid_configuration() -> None:
    with pytest.raises(probe.TargetRejected):
        probe.run_probes("http://localhost:3000", None, mode="local", timeout=200)


def test_backend_target_is_separately_validated() -> None:
    with pytest.raises(probe.TargetRejected):
        probe.run_probes(
            "http://localhost:3000", "https://example.com", mode="local"
        )

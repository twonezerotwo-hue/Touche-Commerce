"""E-YAY market adapter never executes orders or exposes paper portfolio data."""

from __future__ import annotations

from datetime import UTC, datetime, timedelta

import pytest

from app.integrations import eyay
from app.integrations.eyay import market_preview, parse_eyay_address


def _health() -> dict[str, object]:
    return {"api_status": "ok", "paper_safe": True, "no_execution": True, "workers": {}}


def _regime(*, age_seconds: float = 5.0) -> dict[str, object]:
    return {
        "meta": {
            "snapshot_id": "snapshot-r1",
            "generated_at": (datetime.now(UTC) - timedelta(seconds=age_seconds)).isoformat(),
        },
        "regime_label": "NEUTRAL",
        "assets": [
            {"symbol": "XAUUSD", "direction": "neutral", "status": "PENDING", "score": 50.0},
            {"symbol": "<script>", "direction": "bullish", "status": "CONFIRMED", "score": 90.0},
        ],
        "paper_state": {"open_positions": [{"size_usd": 999_999}]},
    }


def test_disabled_by_default_is_completely_offline(monkeypatch: pytest.MonkeyPatch) -> None:
    def forbid(*args: object, **kwargs: object) -> None:
        raise AssertionError("Cannot perform network IO when integration is disabled")
    monkeypatch.setattr(eyay, "_source_get", forbid)
    result = market_preview(enabled=False, base_url="http://127.0.0.1:9000")
    assert result.integration_state == "DISABLED"
    assert result.assets == []
    assert result.automatic_execution_enabled is False
    assert result.finance_writes_enabled is False
    assert result.trade_actions_enabled is False


@pytest.mark.parametrize("url", [
    "https://127.0.0.1:9000",
    "http://localhost:9000",
    "http://8.8.8.8:9000",
    "http://127.0.0.1:9000/other",
    "http://user:secret@127.0.0.1:9000",
    "http://127.0.0.1:9000?path=/api",
    "http://127.0.0.1",
    "file:///etc/passwd",
])
def test_rejects_ssrf_and_unsafe_base_urls(url: str) -> None:
    with pytest.raises(ValueError):
        parse_eyay_address(url)


def test_healthy_e_yay_yields_bounded_provenance_not_positions(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    calls: list[str] = []
    def fake(host: str, port: int, *, path: str, timeout: float, max_bytes: int) -> dict:
        assert host == "127.0.0.1" and port == 9000
        calls.append(path)
        return _health() if path == "/api/v1/system/health" else _regime()
    monkeypatch.setattr(eyay, "_source_get", fake)
    result = market_preview(enabled=True, base_url="http://127.0.0.1:9000")
    assert calls == ["/api/v1/system/health", "/api/v1/regime-report/current"]
    assert result.integration_state == "ISOLATED_HTTP_READ_ONLY"
    assert result.regime == "NEUTRAL"
    assert result.source_snapshot_id == "snapshot-r1"
    assert [a.symbol for a in result.assets] == ["XAUUSD"]
    assert "paper_state" not in result.model_dump_json()
    assert result.automatic_execution_enabled is False


def test_unsafe_or_stale_e_yay_never_produces_market_signals(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(
        eyay, "_source_get",
        lambda *args, **kwargs: {
            **_health(), "paper_safe": False,
        } if kwargs["path"].endswith("health") else _regime(),
    )
    assert market_preview(
        enabled=True, base_url="http://127.0.0.1:9000"
    ).integration_state == "UNSAFE_SOURCE"

    monkeypatch.setattr(
        eyay, "_source_get",
        lambda *args, **kwargs: (
            _health() if kwargs["path"].endswith("health")
            else _regime(age_seconds=3600)
        ),
    )
    stale = market_preview(enabled=True, base_url="http://127.0.0.1:9000")
    assert stale.integration_state == "STALE"
    assert stale.assets == []


def test_invalid_payload_or_unavailable_e_yay_fails_closed(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(eyay, "_source_get", lambda *a, **k: {"paper_safe": True, "no_execution": True} if k["path"].endswith("health") else {"regime_label": "HACK"})
    unavailable = market_preview(enabled=True, base_url="http://127.0.0.1:9000")
    assert unavailable.integration_state == "UNAVAILABLE"
    assert unavailable.assets == []

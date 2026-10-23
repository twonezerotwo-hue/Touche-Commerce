"""E-YAY read-only market context: narrow, loopback-only, no execution.

Only the published E-YAY OpenAPI contract's system health and regime report are
accessed. Commerce never retrieves paper positions, authorises a trading order,
creates commercial orders or uses E-YAY's untrusted output as instructions.
"""

from __future__ import annotations

import http.client
import json
import re
from datetime import UTC, datetime
from urllib.parse import urlsplit
from typing import Any

from pydantic import BaseModel, ConfigDict, Field


class EyayMarketSignal(BaseModel):
    model_config = ConfigDict(extra="forbid")
    symbol: str = Field(max_length=32)
    direction: str
    status: str
    score: float = Field(ge=0, le=100)


class EyayMarketPreview(BaseModel):
    model_config = ConfigDict(extra="forbid")
    source: str = "CLEAN_E_YAY"
    mode: str = "READ_ONLY"
    integration_state: str = "DISABLED"
    automatic_execution_enabled: bool = False
    finance_writes_enabled: bool = False
    trade_actions_enabled: bool = False
    source_snapshot_id: str | None = None
    source_generated_at: datetime | None = None
    regime: str | None = None
    assets: list[EyayMarketSignal] = Field(default_factory=list)
    warning: str | None = None


_SYMBOL = re.compile(r"^[A-Za-z0-9._:/-]{1,32}$")
_LOOPBACK = frozenset({"127.0.0.1", "::1"})
_REGIMES = frozenset({"OFFENSIVE", "NEUTRAL", "DEFENSIVE", "CRISIS"})
_DIRECTIONS = frozenset({"bullish", "bearish", "neutral"})
_STATUSES = frozenset({"BLOCKING", "PENDING", "CONFIRMED"})


def parse_eyay_address(base_url: str) -> tuple[str, int]:
    """Reject DNS, credentials, SSRF targets, path tricks and remote endpoints."""
    try:
        parts = urlsplit(base_url)
        port = parts.port
    except ValueError as exc:
        raise ValueError("Invalid E-YAY address") from exc
    if (
        parts.scheme != "http"
        or parts.hostname not in _LOOPBACK
        or parts.username is not None
        or parts.password is not None
        or parts.path not in ("", "/")
        or parts.query
        or parts.fragment
        or not port
    ):
        raise ValueError("E-YAY must use http://127.0.0.1:<port> or IPv6 loopback")
    return parts.hostname, port


def _source_get(host: str, port: int, *, path: str, timeout: float, max_bytes: int) -> dict[str, Any]:
    client = http.client.HTTPConnection(host, port, timeout=timeout)
    try:
        client.request(
            "GET", path,
            headers={"Accept": "application/json", "Connection": "close"},
        )
        response = client.getresponse()
        if response.status != 200:
            raise ValueError("E-YAY did not return a verified success response")
        if response.getheader("Content-Type", "").split(";")[0].strip() != "application/json":
            raise ValueError("E-YAY returned an unexpected content type")
        length = response.getheader("Content-Length")
        if length:
            try:
                if int(length) > max_bytes:
                    raise ValueError("E-YAY response too large")
            except ValueError as exc:
                raise ValueError("Invalid E-YAY response length") from exc
        raw = response.read(max_bytes + 1)
        if len(raw) > max_bytes:
            raise ValueError("E-YAY response too large")
        payload = json.loads(raw)
        if not isinstance(payload, dict):
            raise ValueError("E-YAY response is not a JSON object")
        return payload
    finally:
        client.close()


def market_preview(
    *, enabled: bool, base_url: str,
    timeout: float = 2.0, max_response_bytes: int = 131072,
) -> EyayMarketPreview:
    """A degraded result is not an opportunity recommendation."""
    if not enabled:
        return EyayMarketPreview(warning="E-YAY integration disabled by default")
    try:
        host, port = parse_eyay_address(base_url)
        health = _source_get(
            host, port, path="/api/v1/system/health",
            timeout=timeout, max_bytes=max_response_bytes,
        )
        if health.get("paper_safe") is not True or health.get("no_execution") is not True:
            return EyayMarketPreview(
                integration_state="UNSAFE_SOURCE",
                warning="E-YAY paper-only/no-execution safety gates are not verified",
            )
        report = _source_get(
            host, port, path="/api/v1/regime-report/current",
            timeout=timeout, max_bytes=max_response_bytes,
        )
        regime = report.get("regime_label")
        meta = report.get("meta")
        assets = report.get("assets")
        if regime not in _REGIMES or not isinstance(meta, dict) or not isinstance(assets, list):
            raise ValueError("Regime-report contract mismatch")
        source_id = meta.get("snapshot_id")
        generated = meta.get("generated_at")
        if not isinstance(source_id, str) or not (1 <= len(source_id) <= 128):
            raise ValueError("Missing source snapshot provenance")
        if not isinstance(generated, str):
            raise ValueError("Missing snapshot timestamp")
        parsed = datetime.fromisoformat(generated.replace("Z", "+00:00"))
        if parsed.tzinfo is None or parsed.astimezone(UTC) > datetime.now(UTC):
            raise ValueError("Invalid snapshot timestamp")
        clean = []
        for asset in assets[:20]:
            if not isinstance(asset, dict):
                continue
            name = asset.get("symbol")
            score = asset.get("score")
            direction = asset.get("direction")
            status = asset.get("status")
            if (
                isinstance(name, str) and _SYMBOL.fullmatch(name)
                and isinstance(score, (int, float)) and not isinstance(score, bool)
                and direction in _DIRECTIONS and status in _STATUSES
            ):
                clean.append(
                    EyayMarketSignal(
                        symbol=name, score=float(score),
                        direction=direction, status=status,
                    )
                )
        age_seconds = (datetime.now(UTC) - parsed.astimezone(UTC)).total_seconds()
        if age_seconds > 900:
            return EyayMarketPreview(
                integration_state="STALE",
                source_snapshot_id=source_id,
                source_generated_at=parsed,
                warning="Snapshot older than 15 minutes; source signals withheld",
            )
        return EyayMarketPreview(
            integration_state="ISOLATED_HTTP_READ_ONLY",
            source_snapshot_id=source_id,
            source_generated_at=parsed,
            regime=regime,
            assets=clean,
        )
    except (OSError, TimeoutError, ValueError, json.JSONDecodeError, TypeError, OverflowError):
        return EyayMarketPreview(
            integration_state="UNAVAILABLE",
            warning="E-YAY endpoint is unavailable or has an invalid source contract",
        )

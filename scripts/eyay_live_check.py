"""Live check of the E-YAY market-context integration (read-only, loopback).

Runs Commerce's real adapter (``app.integrations.eyay.market_preview``) against an E-YAY API and
checks the contract and the safety gates. Only the two documented GET endpoints are touched
(``/api/v1/system/health`` and ``/api/v1/regime-report/current``); no paper-trading, portfolio,
decision or order endpoint is ever called. It prints states, counts and the regime label, never
prices or positions.

    backend\\.venv\\Scripts\\python.exe scripts\\eyay_live_check.py [--base-url http://127.0.0.1:9000]
        [--expect-down]

``--expect-down`` instead proves the outage behaviour: with E-YAY stopped, Commerce must report
UNAVAILABLE (never an error, never stale data).

Exit 0 = EYAY_LIVE_VERIFIED (or EYAY_OUTAGE_HANDLED); 1 = a check failed.
"""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "backend"))

from app.integrations.eyay import market_preview


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--base-url", default="http://127.0.0.1:9000")
    parser.add_argument("--expect-down", action="store_true")
    args = parser.parse_args()

    failures: list[str] = []

    def check(condition: bool, label: str) -> None:
        print(f"  [{'ok' if condition else 'FAIL'}] {label}")
        if not condition:
            failures.append(label)

    disabled = market_preview(enabled=False, base_url=args.base_url)
    check(disabled.integration_state == "DISABLED", "disabled by default: no network, no data")

    for bad in ("http://example.com:9000", "http://user:pw@127.0.0.1:9000", "http://127.0.0.1"):
        refused = market_preview(enabled=True, base_url=bad)
        check(
            refused.integration_state == "UNAVAILABLE",
            f"refuses a non-loopback or odd address ({bad})",
        )

    preview = market_preview(enabled=True, base_url=args.base_url)
    print(
        f"  state={preview.integration_state} regime={preview.regime} assets={len(preview.assets)}"
    )

    if args.expect_down:
        check(preview.integration_state == "UNAVAILABLE", "E-YAY stopped -> UNAVAILABLE")
        check(not preview.assets and preview.regime is None, "no stale signals are shown")
        check(
            not (preview.trade_actions_enabled or preview.automatic_execution_enabled),
            "trading and execution stay disabled",
        )
        verdict = "EYAY_OUTAGE_HANDLED: Commerce degrades to UNAVAILABLE without data or errors."
    else:
        check(preview.integration_state == "ISOLATED_HTTP_READ_ONLY", "contract verified over HTTP")
        check(preview.mode == "READ_ONLY", "mode is READ_ONLY")
        check(preview.trade_actions_enabled is False, "trade actions disabled")
        check(preview.automatic_execution_enabled is False, "automatic execution disabled")
        check(preview.finance_writes_enabled is False, "finance writes disabled")
        check(
            preview.regime in {"OFFENSIVE", "NEUTRAL", "DEFENSIVE", "CRISIS"}, "valid regime label"
        )
        check(len(preview.assets) > 0, "asset signals parsed and validated")
        check(
            preview.source_snapshot_id is not None and preview.source_generated_at is not None,
            "snapshot provenance present",
        )
        verdict = "EYAY_LIVE_VERIFIED: the real E-YAY API answered read-only and paper-safe."

    if failures:
        print(f"EYAY_LIVE_FAILED: {len(failures)} check(s) failed.")
        return 1
    print(verdict)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

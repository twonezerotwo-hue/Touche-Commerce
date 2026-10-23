#!/usr/bin/env python3
"""Fail-closed release readiness checks for TOUCHE COMMERCE.

CI verifies repository-side release prerequisites. Runtime prerequisites
(Windows, PostgreSQL, live providers, backups) are never inferred from CI.
No secrets, network calls, DB mutations or provider requests.
"""

from __future__ import annotations

import argparse
import json
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[1]

REQUIRED_PATHS = (
    "backend/alembic/versions/20261023_0011_communication_suppression.py",
    "backend/app/api/v1/routes/communications.py",
    "backend/app/integrations/eyay.py",
    "scripts/start-local.ps1",
    "scripts/verify.ps1",
    "docs/FINANCE_INTEGRATION_CONTRACT.md",
    "docs/ARCHITECTURE.md",
    "docs/PROGRESS.md",
    "docs/ROADMAP.md",
    "frontend/package.json",
    "frontend/openapi/openapi.json",
)

BLOCKED_EXTERNAL = (
    "GMAIL_OAUTH_AND_PROVIDER_ACCEPTANCE",
    "WHATSAPP_CLOUD_API_CONNECTION_AND_WEBHOOK_VERIFICATION",
    "RECIPIENT_OPT_IN_AND_SEND_APPROVAL",
    "LIVE_FINANCE_READ_ONLY_VERIFICATION",
    "LIVE_EYAY_SOURCE_CONTRACT_VERIFICATION",
    "EXTERNAL_AI_PROVIDER_CREDENTIAL_AND_DATA_PROCESSING_REVIEW",
)
BLOCKED_DEPLOYMENT = (
    "WINDOWS_LOCAL_INTERACTIVE_SMOKE_TEST",
    "POSTGRES_BACKUP_RESTORE_DRILL",
    "TLS_ACL_AND_KEY_MANAGEMENT_REVIEW",
    "PRODUCTION_MONITORING_AND_RECOVERY_DRILL",
    "ACCESSIBILITY_AND_BROWSER_ACCEPTANCE",
)


def evaluate(root: Path = ROOT, *, target: str = "ci") -> dict[str, Any]:
    """Return evidence limitations without interpreting env flags as proof."""
    if target not in {"ci", "local", "production"}:
        raise ValueError("unsupported target")
    missing = [str(path) for path in REQUIRED_PATHS if not (root / path).is_file()]
    claims = {
        "ci_artifacts_present": not missing,
        "real_email_send_available": False,
        "real_whatsapp_send_available": False,
        "accounting_write_available": False,
        "autonomous_trade_execution_available": False,
        "production_ready": False,
    }
    blockers = [f"REQUIRED_FILE_MISSING:{path}" for path in missing]
    if target in {"local", "production"}:
        blockers.append("LOCAL_RUNTIME_NOT_VERIFIED_BY_STATIC_CHECK")
    if target == "production":
        blockers.extend(BLOCKED_EXTERNAL)
        blockers.extend(BLOCKED_DEPLOYMENT)
    return {
        "target": target,
        "status": "PASS" if not blockers else "BLOCKED",
        "checks": claims,
        "blockers": blockers,
        "verification": "STATIC_REPOSITORY_ONLY",
        "summary": (
            "Repository-side CI prerequisite files exist"
            if not missing
            else "Missing repository-side release prerequisites"
        ),
        "disclaimer": (
            "This check does not start Commerce, read Finance or E-YAY, "
            "connect Gmail/WhatsApp, prove backups or authorize production."
        ),
    }


def main() -> int:
    parser = argparse.ArgumentParser(description="Non-invasive release prerequisite gate")
    parser.add_argument("--target", choices=["ci", "local", "production"], default="ci")
    parser.add_argument("--root", type=Path, default=ROOT, help="Repository root for fixture tests")
    args = parser.parse_args()
    result = evaluate(args.root, target=args.target)
    print(json.dumps(result, sort_keys=True, indent=2))
    return 0 if result["status"] == "PASS" else 1


if __name__ == "__main__":
    raise SystemExit(main())

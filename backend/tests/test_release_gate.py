"""Static Stage 10 release gate. Must not touch live databases or the network."""

from __future__ import annotations

import importlib.util
from pathlib import Path
from types import ModuleType

import pytest

SCRIPT = Path(__file__).resolve().parents[2] / "scripts" / "release-gate.py"


def module() -> ModuleType:
    spec = importlib.util.spec_from_file_location("commerce_release_gate", SCRIPT)
    assert spec is not None and spec.loader is not None
    loaded = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(loaded)
    return loaded


def test_ci_gate_reports_repo_files_but_no_production_entitlement() -> None:
    m = module()
    result = m.evaluate()
    assert result["status"] == "PASS"
    assert result["verification"] == "STATIC_REPOSITORY_ONLY"
    assert result["checks"]["ci_artifacts_present"] is True
    assert result["checks"]["production_ready"] is False
    for feature in (
        "real_email_send_available",
        "real_whatsapp_send_available",
        "accounting_write_available",
        "autonomous_trade_execution_available",
    ):
        assert result["checks"][feature] is False


def test_missing_requirement_fails_closed(tmp_path: Path) -> None:
    m = module()
    result = m.evaluate(tmp_path, target="ci")
    assert result["status"] == "BLOCKED"
    assert any(s.startswith("REQUIRED_FILE_MISSING:") for s in result["blockers"])


def test_local_gate_does_not_infer_running_service_from_source_files() -> None:
    m = module()
    result = m.evaluate(target="local")
    assert result["status"] == "BLOCKED"
    assert "LOCAL_RUNTIME_NOT_VERIFIED_BY_STATIC_CHECK" in result["blockers"]


def test_production_gate_requires_external_evidence() -> None:
    m = module()
    result = m.evaluate(target="production")
    assert result["status"] == "BLOCKED"
    assert "POSTGRES_BACKUP_RESTORE_DRILL" in result["blockers"]
    assert "LIVE_FINANCE_READ_ONLY_VERIFICATION" in result["blockers"]
    assert "GMAIL_OAUTH_AND_PROVIDER_ACCEPTANCE" in result["blockers"]
    assert "WINDOWS_LOCAL_INTERACTIVE_SMOKE_TEST" in result["blockers"]


def test_invalid_target_is_rejected() -> None:
    m = module()
    with pytest.raises(ValueError):
        m.evaluate(target="unknown")

"""Stage 9 local operation safety contracts; no live host or DB required."""

from __future__ import annotations

from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]


def test_local_launcher_rejects_collision_and_does_not_reset_databases() -> None:
    source = (ROOT / "scripts" / "start-local.ps1").read_text(encoding="utf-8")
    assert "Test-LocalTcp -Port" in source
    assert "Port $port is occupied" in source
    assert "Start-Process" in source
    assert "NoReload" in source
    assert "-ApplyMigrations" not in source  # switch is named ApplyMigrations
    assert "$ApplyMigrations" in source
    assert "Remove-Item" not in source
    assert "bootstrap-local-postgres" not in source
    assert "127.0.0.1:8000/api/v1/health/live" in source
    assert "localhost:3000/login" in source


def test_verify_script_fails_without_frontend_and_checks_runtime_mypy() -> None:
    source = (ROOT / "scripts" / "verify.ps1").read_text(encoding="utf-8")
    assert "@('-m', 'mypy', 'app')" in source
    assert "$failures.Add('frontend: dependencies missing')" in source
    assert "if ($failures.Count -gt 0)" in source

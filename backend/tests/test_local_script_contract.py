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
    assert "if ($ApplyMigrations) {" in source
    assert "$ApplyMigrations" in source
    assert "Remove-Item" not in source
    assert "bootstrap-local-postgres" not in source
    assert "127.0.0.1:$BackendPort/api/v1/health/live" in source
    assert "localhost:$FrontendPort/login" in source
    assert "$BackendPort = 8000" in source and "$FrontendPort = 3000" in source


def test_launcher_can_move_ports_without_widening_exposure_or_editing_env() -> None:
    source = (ROOT / "scripts" / "start-local.ps1").read_text(encoding="utf-8")
    assert "-AutoPorts" in source or "$AutoPorts" in source
    assert "TOUCHE_CORS_ALLOWED_ORIGINS" in source
    # Only loopback origins are ever trusted for a moved port.
    assert "http://localhost:$FrontendPort" in source and "http://127.0.0.1:$FrontendPort" in source
    assert "0.0.0.0" not in source
    assert "Set-Content" not in source and "Out-File" not in source  # .env is never edited
    common = (ROOT / "scripts" / "lib" / "common.ps1").read_text(encoding="utf-8")
    assert "-not $Force" in common  # an already-set variable wins over .env


def test_verify_script_fails_without_frontend_and_checks_runtime_mypy() -> None:
    source = (ROOT / "scripts" / "verify.ps1").read_text(encoding="utf-8")
    assert "@('-m', 'mypy', 'app')" in source
    assert "$failures.Add('frontend: dependencies missing')" in source
    assert "if ($failures.Count -gt 0)" in source

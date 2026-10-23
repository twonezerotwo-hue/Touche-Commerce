"""Stage 18A fail-closed backup copy-integrity evidence tests."""

from __future__ import annotations

import hashlib
import importlib.util
import os
import sys
from datetime import UTC, datetime, timedelta
from pathlib import Path

import pytest

SCRIPT = Path(__file__).resolve().parents[2] / "scripts" / "backup_copy_evidence.py"
SPEC = importlib.util.spec_from_file_location("touche_backup_copy_evidence", SCRIPT)
assert SPEC is not None and SPEC.loader is not None
evidence = importlib.util.module_from_spec(SPEC)
sys.modules[SPEC.name] = evidence
SPEC.loader.exec_module(evidence)


@pytest.fixture()
def pair(tmp_path: Path) -> tuple[Path, dict[str, object]]:
    local = tmp_path / "local"
    secondary = tmp_path / "secondary"
    local.mkdir()
    secondary.mkdir()
    data = b"encrypted-test-fixture-not-a-real-backup"
    (local / "db.age").write_bytes(data)
    (secondary / "db.age").write_bytes(data)
    manifest: dict[str, object] = {
        "version": 1,
        "created_at": "2026-10-24T00:00:00Z",
        "sha256": hashlib.sha256(data).hexdigest(),
        "bytes": len(data),
        "copies": {"local": "local/db.age", "secondary": "secondary/db.age"},
    }
    return tmp_path, manifest


def check(root: Path, manifest: dict[str, object]) -> dict[str, object]:
    return evidence.verify_manifest(
        manifest, root=root, now=datetime(2026, 10, 24, 1, tzinfo=UTC)
    )


def test_hashes_match_without_claiming_restore_or_production(
    pair: tuple[Path, dict[str, object]],
) -> None:
    root, manifest = pair
    result = check(root, manifest)
    assert result["status"] == "COPY_HASH_VERIFIED"
    assert result["backup_restore_tested"] is False
    assert result["encryption_verified"] is False
    assert result["production_approved"] is False
    assert result["independent_failure_domains_verified"] is False
    assert [x["label"] for x in result["files"]] == ["local", "secondary"]


def test_tampering_with_second_copy_is_refused(
    pair: tuple[Path, dict[str, object]],
) -> None:
    root, manifest = pair
    (root / "secondary" / "db.age").write_bytes(b"x" * manifest["bytes"])
    with pytest.raises(evidence.EvidenceError, match="digest mismatch"):
        check(root, manifest)


@pytest.mark.parametrize(
    ("field", "bad"),
    [
        ("sha256", "0" * 64),
        ("bytes", -1),
        ("bytes", True),
        ("created_at", "2026-01-01T00:00:00Z"),
        ("created_at", "2026-10-24T00:00:00"),
        ("version", 2),
    ],
)
def test_invalid_or_stale_manifest_is_rejected(
    pair: tuple[Path, dict[str, object]], field: str, bad: object
) -> None:
    root, manifest = pair
    manifest[field] = bad
    with pytest.raises(evidence.EvidenceError):
        check(root, manifest)


def test_samefile_alias_rejected(pair: tuple[Path, dict[str, object]]) -> None:
    root, manifest = pair
    original = root / "local" / "db.age"
    secondary = root / "secondary" / "db.age"
    secondary.unlink()
    try:
        os.link(original, secondary)
    except OSError:
        pytest.skip("Hard links unavailable on current filesystem")
    with pytest.raises(evidence.EvidenceError, match="same physical file"):
        check(root, manifest)


def test_path_escape_is_rejected(pair: tuple[Path, dict[str, object]]) -> None:
    root, manifest = pair
    manifest["copies"] = {"local": "../outside", "secondary": "secondary/db.age"}
    with pytest.raises(evidence.EvidenceError, match="paths must be within"):
        check(root, manifest)


def test_missing_copy_cannot_pass(pair: tuple[Path, dict[str, object]]) -> None:
    root, manifest = pair
    (root / "local" / "db.age").unlink()
    with pytest.raises(OSError):
        check(root, manifest)


def test_recent_age_bound(pair: tuple[Path, dict[str, object]]) -> None:
    root, manifest = pair
    with pytest.raises(evidence.EvidenceError, match="stale"):
        evidence.verify_manifest(
            manifest,
            root=root,
            now=datetime(2026, 10, 30, tzinfo=UTC),
            max_age_hours=12,
        )


def test_no_symlink_final_file_accepted(pair: tuple[Path, dict[str, object]]) -> None:
    root, manifest = pair
    source = root / "secondary" / "db.age"
    source.unlink()
    try:
        source.symlink_to(root / "local" / "db.age")
    except (NotImplementedError, OSError):
        pytest.skip("Symlinks unavailable")
    with pytest.raises(evidence.EvidenceError):
        check(root, manifest)

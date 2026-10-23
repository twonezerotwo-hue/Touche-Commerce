#!/usr/bin/env python3
"""Read-only evidence check for two Commerce database backup file copies.

Verifies cryptographic byte equality to an operator-approved manifest.
No file or database is written. This does not prove offsite independence,
encryption, recoverability or release readiness.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import os
import stat
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
from pathlib import Path
from typing import Any

CHUNK_SIZE = 1024 * 1024
MAX_BYTES = 80 * 1024 * 1024 * 1024


class EvidenceError(ValueError):
    """Manifest or local file evidence cannot be trusted as a matching copy."""


@dataclass(frozen=True)
class FileEvidence:
    label: str
    bytes_checked: int
    sha256: str


def _regular_no_symlink(path: Path) -> os.stat_result:
    try:
        detail = path.lstat()
    except OSError as exc:
        raise EvidenceError("Backup copy is not available") from exc
    if stat.S_ISLNK(detail.st_mode) or not stat.S_ISREG(detail.st_mode):
        raise EvidenceError("Backup evidence must be a regular, non-symlink file")
    if not 1 <= detail.st_size <= MAX_BYTES:
        raise EvidenceError("Backup evidence size is outside the supported range")
    return detail


def _digest(path: Path, expected_size: int, *, label: str) -> FileEvidence:
    stat_before = _regular_no_symlink(path)
    if stat_before.st_size != expected_size:
        raise EvidenceError("Backup copy length does not match manifest")
    digest = hashlib.sha256()
    bytes_read = 0
    try:
        with path.open("rb") as stream:
            while chunk := stream.read(CHUNK_SIZE):
                bytes_read += len(chunk)
                if bytes_read > expected_size:
                    raise EvidenceError("Backup grew during verification")
                digest.update(chunk)
    except OSError as exc:
        raise EvidenceError("Backup cannot be read") from exc
    stat_after = _regular_no_symlink(path)
    if (
        stat_before.st_size != stat_after.st_size
        or stat_before.st_mtime_ns != stat_after.st_mtime_ns
        or bytes_read != expected_size
    ):
        raise EvidenceError("Backup changed during verification")
    return FileEvidence(label, bytes_read, digest.hexdigest())


def _date_utc(value: str, *, now: datetime, max_age_hours: int) -> None:
    try:
        created = datetime.fromisoformat(value.replace("Z", "+00:00"))
    except ValueError as exc:
        raise EvidenceError("created_at must be an ISO-8601 UTC timestamp") from exc
    if created.tzinfo is None or created.utcoffset() != timedelta(0):
        raise EvidenceError("created_at must use UTC timezone")
    if created > now + timedelta(minutes=5):
        raise EvidenceError("Backup timestamp is in the future")
    if now - created > timedelta(hours=max_age_hours):
        raise EvidenceError("Backup manifest is stale")


def verify_manifest(
    manifest: dict[str, Any],
    *,
    root: Path,
    now: datetime | None = None,
    max_age_hours: int = 48,
) -> dict[str, Any]:
    """Validate bytes, not the operator's storage/encryption/recovery assertions."""

    if max_age_hours < 1 or max_age_hours > 24 * 31:
        raise EvidenceError("max_age_hours is outside supported range")
    if now is None:
        now = datetime.now(UTC)
    if (
        not isinstance(manifest, dict)
        or set(manifest) != {"version", "created_at", "sha256", "bytes", "copies"}
        or manifest["version"] != 1
        or not isinstance(manifest["created_at"], str)
    ):
        raise EvidenceError("Manifest schema or version is invalid")
    _date_utc(manifest["created_at"], now=now, max_age_hours=max_age_hours)
    expected = manifest["sha256"]
    count = manifest["bytes"]
    if (
        not isinstance(expected, str)
        or len(expected) != 64
        or any(c not in "0123456789abcdef" for c in expected)
        or type(count) is not int
        or not 1 <= count <= MAX_BYTES
    ):
        raise EvidenceError("Manifest digest or byte length is invalid")
    copies = manifest["copies"]
    if (
        not isinstance(copies, dict)
        or set(copies) != {"local", "secondary"}
        or any(not isinstance(p, str) or not p for p in copies.values())
    ):
        raise EvidenceError("Manifest requires local and secondary copy paths")
    resolved_root = root.resolve(strict=True)
    found: list[FileEvidence] = []
    originals: list[Path] = []
    for label in ("local", "secondary"):
        relative = Path(copies[label])
        if relative.is_absolute() or ".." in relative.parts:
            raise EvidenceError("Backup paths must be within the specified evidence root")
        source = (resolved_root / relative).resolve(strict=True)
        if not source.is_relative_to(resolved_root):
            raise EvidenceError("Backup paths escape the evidence root")
        info = _digest(source, count, label=label)
        if info.sha256 != expected:
            raise EvidenceError("Backup digest mismatch")
        found.append(info)
        originals.append(source)
    try:
        if os.path.samefile(originals[0], originals[1]):
            raise EvidenceError("Both backup paths refer to the same physical file")
    except OSError as exc:
        raise EvidenceError("Could not verify that backup copies are distinct") from exc
    return {
        "status": "COPY_HASH_VERIFIED",
        "files": [{"label": f.label, "bytes_checked": f.bytes_checked} for f in found],
        "backup_restore_tested": False,
        "independent_failure_domains_verified": False,
        "encryption_verified": False,
        "production_approved": False,
        "notice": (
            "Matching copy hashes do not verify decryption, successful PostgreSQL "
            "restore, offsite separation, file ownership or production readiness."
        ),
    }


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--manifest", required=True, type=Path)
    parser.add_argument("--root", required=True, type=Path)
    parser.add_argument("--max-age-hours", type=int, default=48)
    args = parser.parse_args()
    try:
        if args.manifest.stat().st_size > 16_384:
            raise EvidenceError("Manifest exceeds 16 KiB")
        parsed = json.loads(args.manifest.read_text(encoding="utf-8"))
        result = verify_manifest(
            parsed, root=args.root, max_age_hours=args.max_age_hours
        )
    except (EvidenceError, OSError, json.JSONDecodeError, TypeError) as exc:
        result = {
            "status": "BLOCKED",
            "error_type": type(exc).__name__,
            "production_approved": False,
        }
    print(json.dumps(result, ensure_ascii=False, indent=2))
    return 0 if result["status"] == "COPY_HASH_VERIFIED" else 1


if __name__ == "__main__":
    raise SystemExit(main())

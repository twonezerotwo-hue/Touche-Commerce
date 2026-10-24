"""Stage 18 encrypted backups: round trip and every way a damaged file must be refused."""

from __future__ import annotations

import os
from pathlib import Path

import pytest

from app.ops import backup_crypt
from app.ops.backup_crypt import BackupCryptError, decrypt_file, encrypt_file, main

PASSPHRASE = "correct horse battery staple 2026"
MARKER = b"CUSTOMER-IBAN-GB82WEST12345698765432"


def make(path: Path, size: int) -> Path:
    block = MARKER + os.urandom(64)
    data = (block * (size // len(block) + 1))[:size]
    path.write_bytes(data)
    return path


@pytest.mark.parametrize(
    "size",
    [0, 1, 4096, backup_crypt.CHUNK_BYTES, backup_crypt.CHUNK_BYTES + 1, 2_600_000],
)
def test_round_trip_at_chunk_boundaries(tmp_path: Path, size: int) -> None:
    source = make(tmp_path / "db.dump", size)
    sealed = tmp_path / "db.dump.enc"
    encrypt_file(source, sealed, PASSPHRASE)
    restored = tmp_path / "restored.dump"
    assert decrypt_file(sealed, restored, PASSPHRASE) == size
    assert restored.read_bytes() == source.read_bytes()


def test_ciphertext_hides_content_and_is_different_each_time(tmp_path: Path) -> None:
    source = make(tmp_path / "db.dump", 50_000)
    one, two = tmp_path / "one.enc", tmp_path / "two.enc"
    encrypt_file(source, one, PASSPHRASE)
    encrypt_file(source, two, PASSPHRASE)
    assert MARKER not in one.read_bytes()
    assert one.read_bytes() != two.read_bytes()  # random salt and nonce prefix


def test_wrong_passphrase_is_refused_and_leaves_no_plaintext(tmp_path: Path) -> None:
    sealed = tmp_path / "db.enc"
    encrypt_file(make(tmp_path / "db.dump", 10_000), sealed, PASSPHRASE)
    target = tmp_path / "out.dump"
    with pytest.raises(BackupCryptError, match="Wrong passphrase"):
        decrypt_file(sealed, target, "another passphrase that is long")
    assert not target.exists()


def tampered(sealed: Path, edit: str, tmp_path: Path) -> Path:
    data = bytearray(sealed.read_bytes())
    if edit == "flip":
        data[len(data) // 2] ^= 0x01
    elif edit == "append":
        data += b"extra"
    elif edit == "cut-tail":
        del data[-9:]
    elif edit == "header":
        data[8] ^= 0x01  # inside the salt: a different key, and a different header (AAD)
    damaged = tmp_path / f"damaged-{edit}.enc"
    damaged.write_bytes(bytes(data))
    return damaged


@pytest.mark.parametrize("edit", ["flip", "append", "cut-tail", "header"])
def test_any_damage_is_detected_before_plaintext_is_kept(tmp_path: Path, edit: str) -> None:
    sealed = tmp_path / "db.enc"
    encrypt_file(make(tmp_path / "db.dump", 2_300_000), sealed, PASSPHRASE)
    out = tmp_path / "out.dump"
    with pytest.raises(BackupCryptError):
        decrypt_file(tampered(sealed, edit, tmp_path), out, PASSPHRASE)
    assert not out.exists()


def test_dropping_whole_trailing_chunks_is_detected(tmp_path: Path) -> None:
    sealed = tmp_path / "db.enc"
    encrypt_file(make(tmp_path / "db.dump", 2_300_000), sealed, PASSPHRASE)  # three chunks
    data = sealed.read_bytes()
    # Walk the chunk list and keep only the first two: a valid-looking but cut-short file.
    position = backup_crypt.HEADER_BYTES
    for _ in range(2):
        position += 4 + int.from_bytes(data[position : position + 4], "big")
    cut = tmp_path / "cut.enc"
    cut.write_bytes(data[:position])
    with pytest.raises(BackupCryptError):
        decrypt_file(cut, tmp_path / "out.dump", PASSPHRASE)


def test_never_overwrites_and_rejects_weak_or_foreign_input(tmp_path: Path) -> None:
    source = make(tmp_path / "db.dump", 100)
    existing = tmp_path / "keep.enc"
    existing.write_bytes(b"precious")
    with pytest.raises(BackupCryptError, match="never overwritten"):
        encrypt_file(source, existing, PASSPHRASE)
    assert existing.read_bytes() == b"precious"
    with pytest.raises(BackupCryptError, match="at least"):
        encrypt_file(source, tmp_path / "x.enc", "short")
    not_a_backup = tmp_path / "plain.txt"
    not_a_backup.write_bytes(b"just a text file, definitely not encrypted data")
    with pytest.raises(BackupCryptError, match="not a Touche encrypted backup"):
        decrypt_file(not_a_backup, tmp_path / "out", PASSPHRASE)


def test_command_line_reads_the_passphrase_from_the_environment_only(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    source = make(tmp_path / "db.dump", 5000)
    monkeypatch.delenv(backup_crypt.PASSPHRASE_ENV, raising=False)
    assert main(["encrypt", str(source), str(tmp_path / "a.enc")]) == 1
    assert backup_crypt.PASSPHRASE_ENV in capsys.readouterr().err

    monkeypatch.setenv(backup_crypt.PASSPHRASE_ENV, PASSPHRASE)
    assert main(["encrypt", str(source), str(tmp_path / "a.enc")]) == 0
    assert main(["decrypt", str(tmp_path / "a.enc"), str(tmp_path / "a.dump")]) == 0
    assert (tmp_path / "a.dump").read_bytes() == source.read_bytes()
    assert PASSPHRASE not in capsys.readouterr().out

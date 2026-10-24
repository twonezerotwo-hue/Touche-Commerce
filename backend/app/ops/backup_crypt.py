"""Authenticated encryption of backup files (AES-256-GCM, scrypt-derived key).

A backup that leaves the machine must not be readable by whoever holds the file. The format
is chunked so a multi-gigabyte dump never has to sit in memory, and every chunk is bound to
its position and to the end of the file, so truncation, reordering, duplication and bit-flips
are all detected before a single byte of plaintext is released.

    header   : MAGIC (6) | version (1) | scrypt salt (16) | nonce prefix (4)
    chunk i  : length (4, big endian) | AES-GCM(ciphertext + tag)
               nonce = prefix || i (8 bytes);  associated data = header || final flag

The passphrase is read from an environment variable (never from a command-line argument, so it
does not appear in process listings or shell history) and is never written anywhere.

    python -m app.ops.backup_crypt encrypt <plain> <encrypted>
    python -m app.ops.backup_crypt decrypt <encrypted> <plain>
"""

from __future__ import annotations

import argparse
import hashlib
import os
import sys
from pathlib import Path
from typing import BinaryIO

from cryptography.exceptions import InvalidTag
from cryptography.hazmat.primitives.ciphers.aead import AESGCM

MAGIC = b"TCBK1\x00"
VERSION = 1
SALT_BYTES = 16
PREFIX_BYTES = 4
CHUNK_BYTES = 1024 * 1024
KEY_BYTES = 32
TAG_BYTES = 16
HEADER_BYTES = len(MAGIC) + 1 + SALT_BYTES + PREFIX_BYTES
#: scrypt cost (RFC 7914): ~64 MiB and a few hundred ms per derivation on a laptop.
SCRYPT_N = 2**16
SCRYPT_R = 8
SCRYPT_P = 1
PASSPHRASE_ENV = "TOUCHE_BACKUP_PASSPHRASE"  # noqa: S105 - the variable name, not a secret
MIN_PASSPHRASE_CHARS = 16


class BackupCryptError(Exception):
    """The file cannot be encrypted or decrypted (wrong passphrase, damaged or foreign file)."""


def _derive_key(passphrase: str, salt: bytes) -> bytes:
    return hashlib.scrypt(
        passphrase.encode("utf-8"),
        salt=salt,
        n=SCRYPT_N,
        r=SCRYPT_R,
        p=SCRYPT_P,
        maxmem=256 * 1024 * 1024,
        dklen=KEY_BYTES,
    )


def _nonce(prefix: bytes, index: int) -> bytes:
    return prefix + index.to_bytes(8, "big")


def _read_chunk(stream: BinaryIO) -> bytes:
    return stream.read(CHUNK_BYTES)


def check_passphrase(passphrase: str | None) -> str:
    if not passphrase:
        raise BackupCryptError(f"Set {PASSPHRASE_ENV} to a backup passphrase first.")
    if len(passphrase) < MIN_PASSPHRASE_CHARS:
        raise BackupCryptError(
            f"The backup passphrase must be at least {MIN_PASSPHRASE_CHARS} characters."
        )
    return passphrase


def encrypt_file(source: Path, destination: Path, passphrase: str) -> int:
    """Encrypt ``source`` into the new file ``destination``; returns the encrypted size."""
    check_passphrase(passphrase)
    if destination.exists():
        raise BackupCryptError(f"{destination.name} already exists; a backup is never overwritten.")
    salt = os.urandom(SALT_BYTES)
    prefix = os.urandom(PREFIX_BYTES)
    header = MAGIC + bytes([VERSION]) + salt + prefix
    aead = AESGCM(_derive_key(passphrase, salt))
    written = 0
    try:
        with source.open("rb") as reader, destination.open("xb") as writer:
            writer.write(header)
            written += len(header)
            index = 0
            current = _read_chunk(reader)
            while True:
                following = _read_chunk(reader) if current else b""
                final = not following
                sealed = aead.encrypt(_nonce(prefix, index), current, header + bytes([final]))
                writer.write(len(sealed).to_bytes(4, "big"))
                writer.write(sealed)
                written += 4 + len(sealed)
                if final:
                    break
                current, index = following, index + 1
    except BaseException:
        destination.unlink(missing_ok=True)  # never leave a half-written "backup"
        raise
    return written


def decrypt_file(source: Path, destination: Path, passphrase: str) -> int:
    """Decrypt ``source`` into the new file ``destination``; returns the plaintext size.

    Nothing is released unless every chunk authenticates and the final chunk is present.
    """
    check_passphrase(passphrase)
    if destination.exists():
        raise BackupCryptError(f"{destination.name} already exists; refusing to overwrite it.")
    produced = 0
    try:
        with source.open("rb") as reader, destination.open("xb") as writer:
            header = reader.read(HEADER_BYTES)
            if len(header) != HEADER_BYTES or not header.startswith(MAGIC):
                raise BackupCryptError("This is not a Touche encrypted backup.")
            if header[len(MAGIC)] != VERSION:
                raise BackupCryptError("Unsupported encrypted backup version.")
            salt = header[len(MAGIC) + 1 : len(MAGIC) + 1 + SALT_BYTES]
            prefix = header[-PREFIX_BYTES:]
            aead = AESGCM(_derive_key(passphrase, salt))
            index = 0
            seen_final = False
            while not seen_final:
                length_bytes = reader.read(4)
                if len(length_bytes) != 4:
                    raise BackupCryptError("The encrypted backup is truncated.")
                length = int.from_bytes(length_bytes, "big")
                if not TAG_BYTES <= length <= CHUNK_BYTES + TAG_BYTES:
                    raise BackupCryptError("The encrypted backup is damaged.")
                sealed = reader.read(length)
                if len(sealed) != length:
                    raise BackupCryptError("The encrypted backup is truncated.")
                # A chunk is final when nothing follows it; authenticate against that fact.
                is_last = reader.read(1) == b""
                if not is_last:
                    reader.seek(-1, os.SEEK_CUR)
                try:
                    plain = aead.decrypt(_nonce(prefix, index), sealed, header + bytes([is_last]))
                except InvalidTag:
                    raise BackupCryptError(
                        "Wrong passphrase, or the encrypted backup was changed or cut short."
                    ) from None
                writer.write(plain)
                produced += len(plain)
                seen_final = is_last
                index += 1
    except BaseException:
        destination.unlink(missing_ok=True)  # no plaintext remains from a failed decryption
        raise
    return produced


def sha256_of(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as reader:
        for block in iter(lambda: reader.read(CHUNK_BYTES), b""):
            digest.update(block)
    return digest.hexdigest()


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Encrypt or decrypt a Touche backup file.")
    parser.add_argument("mode", choices=("encrypt", "decrypt"))
    parser.add_argument("source", type=Path)
    parser.add_argument("destination", type=Path)
    args = parser.parse_args(argv)
    try:
        passphrase = check_passphrase(os.environ.get(PASSPHRASE_ENV))
        action = encrypt_file if args.mode == "encrypt" else decrypt_file
        size = action(args.source, args.destination, passphrase)
    except BackupCryptError as exc:
        print(f"ERROR: {exc}", file=sys.stderr)
        return 1
    print(f"{args.mode}ed {size} bytes -> {args.destination}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

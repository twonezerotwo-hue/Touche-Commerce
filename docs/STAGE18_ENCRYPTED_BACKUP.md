# Stage 18B — encrypted backup and encrypted restore drill

Status: **implemented and exercised locally** (Windows, PostgreSQL 17). This is one line of
evidence for Stage 18; it is not an offsite or production-readiness claim.

## What it does

`scripts\backup-local.ps1 -Encrypt` writes, next to the usual dump and manifest, an encrypted
copy `<dump>.enc` and **proves it** by decrypting it again and comparing the SHA-256 with the
dump before recording it in the manifest (`encrypted_copy.round_trip_verified`).

`scripts\restore-test.ps1 -BackupFile <dump>.enc` verifies the encrypted file against the manifest,
decrypts it to a temporary file next to it, restores into the scratch database
(`touche_restore_check*`), compares revision, every table's row count, row level security and the
audit trigger, then removes the temporary plaintext — also when anything fails.

```powershell
$env:TOUCHE_BACKUP_PASSPHRASE = '<16+ characters, kept in your password manager>'
.\scripts\backup-local.ps1 -Encrypt
.\scripts\restore-test.ps1 -BackupFile .\backups\touche_commerce-<stamp>.dump.enc
```

## Format (`app/ops/backup_crypt.py`)

AES-256-GCM, key from the passphrase with scrypt (N=2^16, r=8, p=1, random 16-byte salt), data in
1 MiB chunks. Every chunk is bound to its position (nonce) and to whether it is the last one
(associated data), so a wrong passphrase, a flipped bit, appended bytes, a cut tail, dropped
trailing chunks or a damaged header are all refused, and the partial plaintext is deleted.
15 unit tests cover each case. The passphrase is read from the environment only (never a
command-line argument) and is never written by these scripts.

## Evidence (2026-10-24)

* Encrypted backup of the development database (revision `0014_company_profile`, 55 tables):
  the encrypted copy decrypted to identical bytes.
* Restore from the `.enc` file into a scratch database: `RESTORE_VERIFIED` — 55 tables compared,
  51 with row level security, audit trigger present; the scratch database was dropped and no
  temporary plaintext remained.
* A wrong passphrase failed closed ("Wrong passphrase, or the encrypted backup was changed or cut
  short") and left no plaintext.

## Not done (needs the owner)

* **Offsite copy.** No storage account exists and none was created. Only the `.enc` file should
  ever be copied off this machine (never the plain dump); `scripts\backup_copy_evidence.py` can
  then check two copies byte for byte. This does not prove independent failure domains.
* **Key management.** The passphrase is a human secret: lose it and the encrypted copy is
  unreadable. No rotation, escrow or hardware key is implemented. The backups made during the
  drill above used throw-away passphrases and are test artefacts only.
* **Scheduling and retention.** Nothing runs automatically and nothing is deleted automatically.
  Plain dumps stay in the git-ignored `backups\` folder until the owner removes them.

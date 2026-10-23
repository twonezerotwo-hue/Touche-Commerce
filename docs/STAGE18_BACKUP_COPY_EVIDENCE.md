# Stage 18A — two-copy backup hash evidence (not a restore test)

**Stage 18 remains unaccepted.** This is a deliberately non-invasive tool to
detect missing, changed, or stale copies of an independently created database
backup. It never connects to PostgreSQL, reads customer records, decrypts files,
starts a restore or uploads an archive. Do not use it alone to approve production.

## Example manifest

Create a local manifest `db-backups.json` **without passwords or API keys**:

```json
{
  "version": 1,
  "created_at": "2026-10-24T00:00:00Z",
  "sha256": "REPLACE_WITH_64_LOWERCASE_HEX_CHARACTERS",
  "bytes": 123456,
  "copies": {
    "local": "local/commerce.dump.age",
    "secondary": "remote-mounted/commerce.dump.age"
  }
}
```

Both paths are relative to the user-supplied evidence root and must refer to
distinct regular files. The timestamp has to be UTC and recent; the SHA-256
must match both byte streams. The tool never prints file names, hashes, content,
account names, access tokens, or the physical locations of backup copies.

Run `python scripts/backup_copy_evidence.py --manifest db-backups.json --root C:\backup-evidence`
(or the equivalent Mac path). It reports `COPY_HASH_VERIFIED` only when
both backups contain exactly the expected bytes and the manifest is recent.
The manifest itself is an operator assertion, not cryptographically signed.

**Important limitations:**
- Two same-hash copies do NOT establish separate offsite failure domains.
- An `.age` / `.gpg` suffix does NOT prove the file is encrypted.
- Neither checksum nor a backup tool exit code demonstrates restore success.
- File age is based on an untrusted manifest timestamp, not a secure attestation.
- Real customer data must not be uploaded to GitHub for this test.

## Stage 18 acceptance still required

- PostgreSQL `pg_dump`/version/roles verified and an isolated restore drill
- Separate encrypted offsite and offline/local copies with independent owners
- Private object storage, key rotation and audited access
- Restore point and restoration-time targets (RPO/RTO)
- Multi-user authorization, account recovery, secure HTTPS and monitoring
- Named operational owner and written production signoff

This tool can supply one line of evidence in that review. It never returns
`PRODUCTION_APPROVED`.

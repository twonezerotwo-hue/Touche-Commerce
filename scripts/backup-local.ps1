<#
.SYNOPSIS
    Creates a verified local PostgreSQL backup of the Commerce database.

.DESCRIPTION
    Runs pg_dump (custom format) as the migration role, which owns the schema and can
    read every tenant's rows. Writes next to the dump a JSON manifest (SHA-256, size,
    UTC time, Alembic revision and per-table row counts taken before and after the
    dump) that scripts\restore-test.ps1 and scripts\backup_copy_evidence.py can check.

    A backup is only evidence once a restore into a scratch database has passed
    (scripts\restore-test.ps1). The dump is NOT encrypted by this script; encrypt it
    with scripts\backup_encrypt.py before it leaves this machine (Stage 18).

    Nothing is deleted or overwritten: every run writes a new, time-stamped pair of
    files. The output directory is git-ignored.

.PARAMETER OutputDir
    Where to write the dump and manifest (default: <repo>\backups).

.PARAMETER Database
    Database to dump (default: POSTGRES_DB from .env).

.PARAMETER Encrypt
    Also write and verify an encrypted copy (needs TOUCHE_BACKUP_PASSPHRASE, 16+ characters).
#>
[CmdletBinding()]
param(
    [string] $OutputDir,
    [string] $Database,
    [switch] $Encrypt
)

$ErrorActionPreference = 'Stop'
. "$PSScriptRoot\lib\common.ps1"

$repoRoot = Get-RepoRoot
Import-DotEnv
if (-not $OutputDir) { $OutputDir = Join-Path $repoRoot 'backups' }
if (-not $Database) { $Database = Get-RequiredEnv 'POSTGRES_DB' }
if ($Database -notmatch '^[A-Za-z0-9_]{1,63}$') { throw 'Database name contains unsupported characters.' }

if ($Encrypt -and ([string]::IsNullOrEmpty($env:TOUCHE_BACKUP_PASSPHRASE) -or $env:TOUCHE_BACKUP_PASSPHRASE.Length -lt 16)) {
    throw 'Set TOUCHE_BACKUP_PASSPHRASE (16+ characters) in this shell before using -Encrypt. It is never written to disk by these scripts.'
}

$pgBin = Get-PostgresBin
$pgHost = if ($env:POSTGRES_HOST) { $env:POSTGRES_HOST } else { '127.0.0.1' }
$pgPort = if ($env:POSTGRES_PORT) { $env:POSTGRES_PORT } else { '5432' }
$user = Get-RequiredEnv 'TOUCHE_DB_MIGRATOR_USER'
$password = Get-RequiredEnv 'TOUCHE_DB_MIGRATOR_PASSWORD'

New-Item -ItemType Directory -Force -Path $OutputDir | Out-Null
$stamp = (Get-Date).ToUniversalTime().ToString('yyyyMMdd-HHmmss')
$dumpPath = Join-Path $OutputDir "$Database-$stamp.dump"
$manifestPath = "$dumpPath.manifest.json"
if ((Test-Path $dumpPath) -or (Test-Path $manifestPath)) { throw "Refusing to overwrite $dumpPath" }

function Get-TableCounts {
    param([string] $Psql)
    $tables = & $Psql -h $pgHost -p $pgPort -U $user -d $Database -v ON_ERROR_STOP=1 -tA -c `
        "SELECT table_name FROM information_schema.tables WHERE table_schema='touche' AND table_type='BASE TABLE' ORDER BY 1"
    if ($LASTEXITCODE -ne 0) { throw 'Could not list tables.' }
    $counts = [ordered]@{}
    foreach ($table in ($tables | Where-Object { $_ -match '^[a-z0-9_]+$' })) {
        $value = & $Psql -h $pgHost -p $pgPort -U $user -d $Database -v ON_ERROR_STOP=1 -tA -c "SELECT count(*) FROM touche.$table"
        if ($LASTEXITCODE -ne 0) { throw "Could not count touche.$table." }
        $counts[$table] = [int64]$value
    }
    return $counts
}

$previousPassword = $env:PGPASSWORD
$env:PGPASSWORD = $password
try {
    $psql = Join-Path $pgBin 'psql.exe'
    $pgDump = Join-Path $pgBin 'pg_dump.exe'

    Write-Step "Reading revision and row counts of $Database"
    $revision = (& $psql -h $pgHost -p $pgPort -U $user -d $Database -tA -c 'SELECT version_num FROM alembic_version').Trim()
    if ($LASTEXITCODE -ne 0 -or -not $revision) { throw 'Could not read alembic_version; is the database migrated?' }
    $before = Get-TableCounts -Psql $psql

    Write-Step "pg_dump -> $dumpPath"
    & $pgDump -h $pgHost -p $pgPort -U $user -d $Database --format=custom --no-password --file $dumpPath
    if ($LASTEXITCODE -ne 0) { throw "pg_dump failed with exit code $LASTEXITCODE" }

    $after = Get-TableCounts -Psql $psql
}
finally {
    $env:PGPASSWORD = $previousPassword
}

$encryptedCopy = $null
if ($Encrypt) {
    Write-Step 'Encrypting the dump (AES-256-GCM) and proving it can be decrypted'
    $python = Get-BackendPython
    $encPath = "$dumpPath.enc"
    $checkPath = "$dumpPath.verify.tmp"
    Invoke-Native -FilePath $python -Arguments @('-m', 'app.ops.backup_crypt', 'encrypt', $dumpPath, $encPath) `
        -WorkingDirectory (Join-Path $repoRoot 'backend')
    try {
        Invoke-Native -FilePath $python -Arguments @('-m', 'app.ops.backup_crypt', 'decrypt', $encPath, $checkPath) `
            -WorkingDirectory (Join-Path $repoRoot 'backend')
        $plainHash = (Get-FileHash -Algorithm SHA256 -Path $dumpPath).Hash
        $roundTrip = (Get-FileHash -Algorithm SHA256 -Path $checkPath).Hash
        if ($plainHash -ne $roundTrip) { throw 'The encrypted copy does not decrypt to the dump; it must not be used.' }
    }
    finally {
        if (Test-Path $checkPath) { Remove-Item -LiteralPath $checkPath -Force }
    }
    $encItem = Get-Item $encPath
    $encryptedCopy = [ordered]@{
        file       = (Split-Path -Leaf $encPath)
        sha256     = (Get-FileHash -Algorithm SHA256 -Path $encPath).Hash.ToLowerInvariant()
        bytes      = [int64]$encItem.Length
        algorithm  = 'AES-256-GCM, scrypt (N=2^16, r=8, p=1), 1 MiB authenticated chunks'
        round_trip_verified = $true
    }
    Write-Ok "encrypted copy written and decrypts to the same bytes: $encPath"
}

$quiescent = (($before | ConvertTo-Json -Compress) -eq ($after | ConvertTo-Json -Compress))
$item = Get-Item $dumpPath
$hash = (Get-FileHash -Algorithm SHA256 -Path $dumpPath).Hash.ToLowerInvariant()
$manifest = [ordered]@{
    version        = 1
    created_at     = (Get-Date).ToUniversalTime().ToString('yyyy-MM-ddTHH:mm:ssZ')
    database       = $Database
    alembic_revision = $revision
    sha256         = $hash
    bytes          = [int64]$item.Length
    encrypted      = $false
    encrypted_copy = $encryptedCopy
    source_quiescent = $quiescent
    table_counts   = $before
    copies         = [ordered]@{ local = (Split-Path -Leaf $dumpPath) }
}
$manifest | ConvertTo-Json -Depth 5 | Set-Content -Path $manifestPath -Encoding UTF8

Write-Ok "backup written: $dumpPath ($([math]::Round($item.Length / 1KB, 1)) KiB)"
Write-Ok "revision $revision, $($before.Count) tables, sha256 $($hash.Substring(0, 12))..."
if (-not $quiescent) {
    Write-Host '    [warning] row counts changed while the dump ran; the restore test will be INCONCLUSIVE. Stop the app and repeat.' -ForegroundColor Yellow
}
Write-Host 'Next: scripts\restore-test.ps1 -BackupFile <dump or dump.enc>  (a backup is not proven until a restore passes)'

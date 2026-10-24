<#
.SYNOPSIS
    Proves a backup by restoring it into a throw-away scratch database and comparing.

.DESCRIPTION
    Verifies the dump against its manifest (SHA-256 and size), creates a scratch
    database whose name must start with 'touche_restore_check', restores the dump into
    it with pg_restore, then checks that the Alembic revision, every table's row count,
    row level security and the append-only audit trigger match what the manifest
    recorded. The scratch database is dropped afterwards unless -Keep is given.

    The live database is only ever READ (by backup-local.ps1); this script never writes
    to it and refuses to restore into any database that is not a scratch name.

.PARAMETER BackupFile
    Path of a .dump produced by scripts\backup-local.ps1 (its .manifest.json must be next to it).

.PARAMETER ScratchDatabase
    Name of the scratch database (default: touche_restore_check).

.PARAMETER Keep
    Do not drop the scratch database afterwards.
#>
[CmdletBinding()]
param(
    [Parameter(Mandatory = $true)][string] $BackupFile,
    [string] $ScratchDatabase = 'touche_restore_check',
    [switch] $Keep
)

$ErrorActionPreference = 'Stop'
. "$PSScriptRoot\lib\common.ps1"

Import-DotEnv
if ($ScratchDatabase -notmatch '^touche_restore_check[A-Za-z0-9_]{0,30}$') {
    throw "Refusing to restore into '$ScratchDatabase': a scratch database name must start with touche_restore_check."
}
if (-not (Test-Path $BackupFile)) { throw "Backup file not found: $BackupFile" }
$manifestPath = "$BackupFile.manifest.json"
if (-not (Test-Path $manifestPath)) { throw "Manifest not found next to the backup: $manifestPath" }
$manifest = Get-Content -Raw -Path $manifestPath | ConvertFrom-Json

Write-Step 'Verifying the dump against its manifest'
$hash = (Get-FileHash -Algorithm SHA256 -Path $BackupFile).Hash.ToLowerInvariant()
if ($hash -ne $manifest.sha256) { throw 'SHA-256 does not match the manifest: the backup is corrupt or was replaced.' }
if ((Get-Item $BackupFile).Length -ne $manifest.bytes) { throw 'File size does not match the manifest.' }
Write-Ok 'checksum and size match'

$pgBin = Get-PostgresBin
$pgHost = if ($env:POSTGRES_HOST) { $env:POSTGRES_HOST } else { '127.0.0.1' }
$pgPort = if ($env:POSTGRES_PORT) { $env:POSTGRES_PORT } else { '5432' }
$admin = Get-RequiredEnv 'POSTGRES_ADMIN_USER'
$adminPassword = Get-RequiredEnv 'POSTGRES_ADMIN_PASSWORD'
$migrator = Get-RequiredEnv 'TOUCHE_DB_MIGRATOR_USER'
$migratorPassword = Get-RequiredEnv 'TOUCHE_DB_MIGRATOR_PASSWORD'
$psql = Join-Path $pgBin 'psql.exe'
$pgRestore = Join-Path $pgBin 'pg_restore.exe'
$failures = [System.Collections.Generic.List[string]]::new()

function Invoke-Sql {
    param([string] $Database, [string] $UserName, [string] $Password, [string] $Sql)
    $previous = $env:PGPASSWORD
    $previousOptions = $env:PGOPTIONS
    $previousPreference = $ErrorActionPreference
    $env:PGPASSWORD = $Password
    # NOTICE messages (for example "database does not exist, skipping") go to stderr;
    # with -ErrorAction Stop Windows PowerShell would treat them as failures.
    $env:PGOPTIONS = '-c client_min_messages=warning'
    $ErrorActionPreference = 'Continue'
    try {
        $out = & $psql -h $pgHost -p $pgPort -U $UserName -d $Database -v ON_ERROR_STOP=1 -tA -c $Sql 2>$null
        if ($LASTEXITCODE -ne 0) { throw "SQL failed on ${Database}: $Sql" }
        return $out
    }
    finally {
        $ErrorActionPreference = $previousPreference
        $env:PGPASSWORD = $previous
        $env:PGOPTIONS = $previousOptions
    }
}

try {
    Write-Step "Creating scratch database $ScratchDatabase"
    Invoke-Sql 'postgres' $admin $adminPassword "DROP DATABASE IF EXISTS `"$ScratchDatabase`" WITH (FORCE)" | Out-Null
    Invoke-Sql 'postgres' $admin $adminPassword "CREATE DATABASE `"$ScratchDatabase`" OWNER `"$migrator`"" | Out-Null

    Write-Step 'pg_restore into the scratch database'
    $previous = $env:PGPASSWORD
    $previousPreference = $ErrorActionPreference
    $env:PGPASSWORD = $migratorPassword
    $ErrorActionPreference = 'Continue'
    try {
        & $pgRestore -h $pgHost -p $pgPort -U $migrator -d $ScratchDatabase --no-owner --no-password --exit-on-error $BackupFile 2>&1 |
            ForEach-Object { if ($_ -is [System.Management.Automation.ErrorRecord]) { Write-Host "    pg_restore: $($_.Exception.Message)" -ForegroundColor DarkYellow } }
        if ($LASTEXITCODE -ne 0) { throw "pg_restore failed with exit code $LASTEXITCODE" }
    }
    finally {
        $ErrorActionPreference = $previousPreference
        $env:PGPASSWORD = $previous
    }
    Write-Ok 'restore finished without errors'

    Write-Step 'Comparing the restored database with the manifest'
    $revision = (Invoke-Sql $ScratchDatabase $migrator $migratorPassword 'SELECT version_num FROM alembic_version').Trim()
    if ($revision -ne $manifest.alembic_revision) { $failures.Add("revision $revision != $($manifest.alembic_revision)") }

    $expected = $manifest.table_counts
    $tables = $expected.PSObject.Properties.Name
    $checked = 0
    foreach ($table in $tables) {
        if ($table -notmatch '^[a-z0-9_]+$') { continue }
        $count = [int64](Invoke-Sql $ScratchDatabase $migrator $migratorPassword "SELECT count(*) FROM touche.$table")
        if ($count -ne [int64]$expected.$table) { $failures.Add("touche.$table has $count rows, manifest says $($expected.$table)") }
        $checked++
    }

    $rls = [int](Invoke-Sql $ScratchDatabase $migrator $migratorPassword "SELECT count(*) FROM pg_class c JOIN pg_namespace n ON n.oid=c.relnamespace WHERE n.nspname='touche' AND c.relkind='r' AND c.relrowsecurity")
    if ($rls -lt 5) { $failures.Add("only $rls tables have row level security after the restore") }
    $trigger = [int](Invoke-Sql $ScratchDatabase $migrator $migratorPassword "SELECT count(*) FROM pg_trigger t JOIN pg_class c ON c.oid=t.tgrelid WHERE c.relname='audit_record' AND NOT t.tgisinternal")
    if ($trigger -lt 1) { $failures.Add('the append-only audit trigger is missing after the restore') }
    Write-Ok "$checked tables compared, $rls with row level security, audit trigger present"
}
finally {
    if (-not $Keep) {
        try { Invoke-Sql 'postgres' $admin $adminPassword "DROP DATABASE IF EXISTS `"$ScratchDatabase`" WITH (FORCE)" | Out-Null }
        catch { Write-Host "    [warning] could not drop $ScratchDatabase : $($_.Exception.Message)" -ForegroundColor Yellow }
    }
}

if ($failures.Count -gt 0) {
    $failures | ForEach-Object { Write-Host "    [failed] $_" -ForegroundColor Red }
    if (-not $manifest.source_quiescent) {
        Write-Host 'RESTORE_INCONCLUSIVE: the source changed while it was dumped; repeat with the app stopped.' -ForegroundColor Yellow
        exit 2
    }
    Write-Host 'RESTORE_FAILED' -ForegroundColor Red
    exit 1
}
Write-Host 'RESTORE_VERIFIED: the backup restored into a scratch database and matches its manifest.' -ForegroundColor Green

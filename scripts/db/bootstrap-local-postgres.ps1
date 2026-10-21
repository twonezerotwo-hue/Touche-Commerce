<#
.SYNOPSIS
    Provisions a local PostgreSQL cluster for TOUCHE COMMERCE without Docker.

.DESCRIPTION
    Fallback for machines without Docker Desktop/WSL. It downloads the official
    EDB PostgreSQL 17 binaries into infra/.local (git-ignored), initialises a
    cluster in infra/.local/pgdata, starts it on 127.0.0.1 and creates the two
    least-privilege roles plus the application database.

    The primary, production-shaped path remains infra/docker-compose.yml.

.PARAMETER Port
    TCP port for the local cluster (default 5432).

.PARAMETER ForceDownload
    Re-download the portable binaries even if they already exist.
#>
param(
    [int] $Port = 5432,
    [switch] $ForceDownload
)

. "$PSScriptRoot\..\lib\common.ps1"

$repoRoot = Get-RepoRoot
Import-DotEnv

$adminUser = Get-RequiredEnv 'POSTGRES_ADMIN_USER'
$adminPassword = Get-RequiredEnv 'POSTGRES_ADMIN_PASSWORD'
$database = Get-RequiredEnv 'POSTGRES_DB'
$appUser = Get-RequiredEnv 'TOUCHE_DB_APP_USER'
$appPassword = Get-RequiredEnv 'TOUCHE_DB_APP_PASSWORD'
$migratorUser = Get-RequiredEnv 'TOUCHE_DB_MIGRATOR_USER'
$migratorPassword = Get-RequiredEnv 'TOUCHE_DB_MIGRATOR_PASSWORD'

$localRoot = Join-Path $repoRoot 'infra\.local'
$pgRoot = Join-Path $localRoot 'pg17\pgsql'
$pgBin = Join-Path $pgRoot 'bin'
$dataDir = Join-Path $localRoot 'pgdata'
$logFile = Join-Path $localRoot 'postgres-server.log'
$zipPath = Join-Path $localRoot 'pg17-binaries.zip'
$postgresVersion = '17.6'

New-Item -ItemType Directory -Force -Path $localRoot | Out-Null

if ($ForceDownload -or -not (Test-Path (Join-Path $pgBin 'pg_ctl.exe'))) {
    Write-Step "Downloading PostgreSQL $postgresVersion portable binaries"
    $ProgressPreference = 'SilentlyContinue'
    $url = "https://get.enterprisedb.com/postgresql/postgresql-$postgresVersion-1-windows-x64-binaries.zip"
    Invoke-WebRequest -Uri $url -OutFile $zipPath -UseBasicParsing
    Write-Ok "downloaded $(([math]::Round((Get-Item $zipPath).Length / 1MB, 1))) MB"
    Write-Step 'Extracting PostgreSQL binaries'
    Expand-Archive -Path $zipPath -DestinationPath (Join-Path $localRoot 'pg17') -Force
    Write-Ok "extracted to $pgRoot"
}
else {
    Write-Ok "PostgreSQL binaries present at $pgRoot"
}

if (-not (Test-Path (Join-Path $dataDir 'PG_VERSION'))) {
    Write-Step 'Initialising the local cluster (initdb)'
    $pwFile = Join-Path $localRoot 'initdb.pw'
    try {
        Set-Content -NoNewline -Path $pwFile -Value $adminPassword
        & (Join-Path $pgBin 'initdb.exe') -D $dataDir -U $adminUser --pwfile=$pwFile `
            -E UTF8 --locale=C -A scram-sha-256 | Out-Null
        if ($LASTEXITCODE -ne 0) { throw 'initdb failed' }
    }
    finally {
        Remove-Item -Force -ErrorAction SilentlyContinue $pwFile
    }
    $conf = Join-Path $dataDir 'postgresql.conf'
    Add-Content -Path $conf -Value @(
        '',
        '# --- TOUCHE COMMERCE local development ---',
        "port = $Port",
        "listen_addresses = '127.0.0.1'",
        "log_timezone = 'UTC'",
        "timezone = 'UTC'"
    )
    Write-Ok 'cluster initialised'
}
else {
    Write-Ok "existing cluster found at $dataDir"
}

$ready = Wait-ForPostgres -PgBin $pgBin -Port $Port -TimeoutSeconds 2
if (-not $ready) {
    Write-Step 'Starting PostgreSQL'
    $logDir = Split-Path -Parent $logFile
    New-Item -ItemType Directory -Force -Path $logDir | Out-Null
    # Redirect pg_ctl output to files: PostgreSQL inherits those handles, so the
    # calling shell is not blocked by the long-lived server process.
    $ctlStdout = Join-Path $localRoot 'pg_ctl.out.log'
    $ctlStderr = Join-Path $localRoot 'pg_ctl.err.log'
    $process = Start-Process -FilePath (Join-Path $pgBin 'pg_ctl.exe') `
        -ArgumentList @('-D', $dataDir, '-l', $logFile, 'start') `
        -RedirectStandardOutput $ctlStdout -RedirectStandardError $ctlStderr `
        -WindowStyle Hidden -Wait -PassThru
    if ($process.ExitCode -ne 0) {
        throw "pg_ctl start failed with exit code $($process.ExitCode). See $ctlStderr and $logFile"
    }
    if (-not (Wait-ForPostgres -PgBin $pgBin -Port $Port -TimeoutSeconds 30)) {
        throw "PostgreSQL did not become ready on port $Port. See $logFile"
    }
    Write-Ok "PostgreSQL listening on 127.0.0.1:$Port"
}
else {
    Write-Ok "PostgreSQL already running on 127.0.0.1:$Port"
}

Write-Step 'Creating roles and application database'
$psql = Join-Path $pgBin 'psql.exe'
$previousPassword = $env:PGPASSWORD
try {
    $env:PGPASSWORD = $adminPassword
    & $psql -h 127.0.0.1 -p $Port -U $adminUser -d postgres -v ON_ERROR_STOP=1 `
        -v "app_user=$appUser" -v "app_password=$appPassword" `
        -v "migrator_user=$migratorUser" -v "migrator_password=$migratorPassword" `
        -v "db_name=$database" `
        -f (Join-Path $PSScriptRoot '01-roles-and-database.sql')
    if ($LASTEXITCODE -ne 0) { throw 'role/database bootstrap failed' }

    & $psql -h 127.0.0.1 -p $Port -U $adminUser -d $database -v ON_ERROR_STOP=1 `
        -v "app_user=$appUser" -v "migrator_user=$migratorUser" `
        -f (Join-Path $PSScriptRoot '02-schema-grants.sql')
    if ($LASTEXITCODE -ne 0) { throw 'schema grant bootstrap failed' }
}
finally {
    $env:PGPASSWORD = $previousPassword
}
Write-Ok 'roles, database and schema grants are in place'

Write-Host ''
Write-Host 'Local PostgreSQL is ready. Next: scripts\migrate.ps1' -ForegroundColor Green

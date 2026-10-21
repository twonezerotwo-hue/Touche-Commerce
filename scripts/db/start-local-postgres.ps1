<#
.SYNOPSIS
    Starts the local (non-Docker) PostgreSQL cluster created by
    bootstrap-local-postgres.ps1.
#>
param([int] $Port = 5432)

. "$PSScriptRoot\..\lib\common.ps1"

$repoRoot = Get-RepoRoot
$localRoot = Join-Path $repoRoot 'infra\.local'
$pgBin = Get-PostgresBin
$dataDir = Join-Path $localRoot 'pgdata'
$logFile = Join-Path $localRoot 'postgres-server.log'

if (-not (Test-Path (Join-Path $dataDir 'PG_VERSION'))) {
    throw 'No local cluster found. Run scripts\db\bootstrap-local-postgres.ps1 first.'
}

if (Wait-ForPostgres -PgBin $pgBin -Port $Port -TimeoutSeconds 2) {
    Write-Ok "PostgreSQL already running on 127.0.0.1:$Port"
    exit 0
}

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
    throw "PostgreSQL did not become ready on 127.0.0.1:$Port. See $logFile"
}
Write-Ok "PostgreSQL listening on 127.0.0.1:$Port"

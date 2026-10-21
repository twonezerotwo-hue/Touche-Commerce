<#
.SYNOPSIS
    Stops the local (non-Docker) PostgreSQL cluster.
#>
param([switch] $Fast)

. "$PSScriptRoot\..\lib\common.ps1"

$repoRoot = Get-RepoRoot
$pgBin = Get-PostgresBin
$dataDir = Join-Path $repoRoot 'infra\.local\pgdata'

if (-not (Test-Path (Join-Path $dataDir 'PG_VERSION'))) {
    throw 'No local cluster found.'
}

$mode = @('-m', 'fast')
if (-not $Fast) { $mode = @() }
& (Join-Path $pgBin 'pg_ctl.exe') -D $dataDir stop @mode
Write-Ok 'PostgreSQL stopped'

<#
.SYNOPSIS
    Applies Alembic migrations using the migration database role.

.PARAMETER Revision
    Target revision (default: head).

.PARAMETER Offline
    Emit SQL to stdout instead of executing it.
#>
param(
    [string] $Revision = 'head',
    [switch] $Offline
)

. "$PSScriptRoot\lib\common.ps1"

$repoRoot = Get-RepoRoot
Import-DotEnv
$python = Get-BackendPython

Write-Step "Alembic upgrade -> $Revision"
Push-Location (Join-Path $repoRoot 'backend')
try {
    if ($Offline) {
        & $python -m alembic upgrade $Revision --sql
    }
    else {
        & $python -m alembic upgrade $Revision
    }
    if ($LASTEXITCODE -ne 0) { throw "alembic upgrade failed with exit code $LASTEXITCODE" }
}
finally {
    Pop-Location
}
Write-Ok "database is at revision $Revision"

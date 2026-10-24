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
$alembicArgs = @('-m', 'alembic', 'upgrade', $Revision)
if ($Offline) { $alembicArgs += '--sql' }
# Invoke-Native checks the real exit code: Alembic logs progress to stderr, which Windows
# PowerShell would otherwise turn into a terminating error before the migration finishes.
Invoke-Native -FilePath $python -Arguments $alembicArgs -WorkingDirectory (Join-Path $repoRoot 'backend')
Write-Ok "database is at revision $Revision"

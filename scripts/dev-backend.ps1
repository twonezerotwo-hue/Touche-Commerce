<#
.SYNOPSIS
    Starts the FastAPI backend on http://127.0.0.1:8000 with auto-reload.

.PARAMETER Port
    TCP port to bind (default 8000).

.PARAMETER NoReload
    Disable the file watcher (use for performance checks).
#>
param(
    [int] $Port = 8000,
    [switch] $NoReload
)

. "$PSScriptRoot\lib\common.ps1"

$repoRoot = Get-RepoRoot
Import-DotEnv
$python = Get-BackendPython

$uvicornArgs = @(
    '-m', 'uvicorn', 'app.main:create_app', '--factory',
    '--host', '127.0.0.1', '--port', "$Port",
    '--proxy-headers', '--no-server-header'
)
if (-not $NoReload) { $uvicornArgs += '--reload' }

Write-Step "Starting API on http://127.0.0.1:$Port (docs: /docs)"
Push-Location (Join-Path $repoRoot 'backend')
try {
    & $python @uvicornArgs
}
finally {
    Pop-Location
}

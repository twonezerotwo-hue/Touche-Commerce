<#
.SYNOPSIS
    Starts the Next.js frontend on http://localhost:3000.

.PARAMETER Port
    TCP port to bind (default 3000).
#>
param([int] $Port = 3000)

. "$PSScriptRoot\lib\common.ps1"

$repoRoot = Get-RepoRoot
$frontend = Join-Path $repoRoot 'frontend'

if (-not (Test-Path (Join-Path $frontend 'node_modules'))) {
    throw 'Frontend dependencies are missing. Run scripts\setup.ps1 (or npm install in frontend/) first.'
}

Write-Step "Starting TOUCHE COMMERCE web shell on http://localhost:$Port"
Push-Location $frontend
try {
    & npm run dev -- --port $Port
}
finally {
    Pop-Location
}

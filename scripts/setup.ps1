<#
.SYNOPSIS
    One-time local setup: environment file, Python virtualenv + deps, npm deps.

.DESCRIPTION
    Safe to re-run. Does not start servers and does not touch the database.
#>
param([switch] $SkipFrontend)

. "$PSScriptRoot\lib\common.ps1"

$repoRoot = Get-RepoRoot

Write-Step 'Checking prerequisites'
foreach ($tool in @('python', 'node', 'npm', 'git')) {
    $command = Get-Command $tool -ErrorAction SilentlyContinue
    if (-not $command) { throw "Required tool '$tool' was not found on PATH." }
    Write-Ok "$tool found"
}

if (-not (Test-Path (Join-Path $repoRoot '.env'))) {
    Copy-Item (Join-Path $repoRoot '.env.example') (Join-Path $repoRoot '.env')
    Write-Ok 'created .env from .env.example (local development credentials only)'
}
else {
    Write-Ok '.env already exists (left untouched)'
}

Write-Step 'Creating backend virtualenv and installing dependencies'
$venvPath = Join-Path $repoRoot 'backend\.venv'
if (-not (Test-Path $venvPath)) {
    Invoke-Native -FilePath 'python' -Arguments @('-m', 'venv', $venvPath)
}
$python = Join-Path $venvPath 'Scripts\python.exe'
Invoke-Native -FilePath $python -Arguments @(
    '-m', 'pip', 'install', '--quiet', '--disable-pip-version-check',
    '-e', (Join-Path $repoRoot 'backend') + '[dev]'
)

if (-not $SkipFrontend) {
    Write-Step 'Installing frontend dependencies'
    $frontend = Join-Path $repoRoot 'frontend'
    if (-not (Test-Path $frontend)) {
        Write-Host '    frontend/ not present yet - skipping npm install' -ForegroundColor Yellow
    }
    else {
        Invoke-Native -FilePath 'npm' -Arguments @('install', '--no-audit', '--no-fund') -WorkingDirectory $frontend
    }
}

Write-Host ''
Write-Host 'Setup complete.' -ForegroundColor Green
Write-Host 'Next steps:'
Write-Host '  1. scripts\db\bootstrap-local-postgres.ps1   (or: docker compose -f infra\docker-compose.yml up -d)'
Write-Host '  2. scripts\migrate.ps1'
Write-Host '  3. scripts\dev-backend.ps1                   (terminal 1)'
Write-Host '  4. scripts\dev-frontend.ps1                  (terminal 2)'

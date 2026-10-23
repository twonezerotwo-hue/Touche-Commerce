<#
.SYNOPSIS
    Start the already-installed TOUCHE COMMERCE locally in two visible windows.
.DESCRIPTION
    Refuses occupied ports and missing prerequisites. Never silently creates a
    database, fetches secrets, overwrites a .env file, or exposes a listener
    beyond localhost. Optional -ApplyMigrations requires operator action.
    Local development only, NOT production deployment.
#>
[CmdletBinding()]
param(
    [switch] $ApplyMigrations
)

$ErrorActionPreference = 'Stop'
. "$PSScriptRoot\lib\common.ps1"

$repoRoot = Get-RepoRoot
Import-DotEnv

if (-not (Test-Path (Join-Path $repoRoot '.env'))) {
    throw 'Missing .env; run scripts\setup.ps1 and configure credentials.'
}
$python = Get-BackendPython
if (-not (Test-Path $python)) {
    throw 'Python virtual environment unavailable. Run scripts\setup.ps1.'
}
if (-not (Test-Path (Join-Path $repoRoot 'frontend\node_modules'))) {
    throw 'Frontend dependencies unavailable. Run scripts\setup.ps1.'
}
if (-not $env:TOUCHE_DATABASE_URL) {
    throw 'Database connection not configured in .env.'
}

function Test-LocalTcp {
    param([int] $Port)
    $client = [System.Net.Sockets.TcpClient]::new()
    try {
        $task = $client.ConnectAsync('127.0.0.1', $Port)
        return ($task.Wait(350) -and $client.Connected)
    }
    catch { return $false }
    finally { $client.Dispose() }
}

if (-not (Test-LocalTcp -Port 5432)) {
    throw 'PostgreSQL unavailable at 127.0.0.1:5432. Start the local cluster first.'
}
foreach ($port in @(8000, 3000)) {
    if (Test-LocalTcp -Port $port) {
        throw "Port $port is occupied. Refusing to affect existing processes."
    }
}

if ($ApplyMigrations) {
    Write-Host 'Applying migrations. A tested backup is required beforehand.'
    & (Join-Path $PSScriptRoot 'migrate.ps1')
    if ($LASTEXITCODE -ne 0) {
        throw 'Migration failed. Nothing was launched.'
    }
}

$pwsh = (Get-Command pwsh.exe, powershell.exe -ErrorAction SilentlyContinue |
    Select-Object -First 1).Source
if (-not $pwsh) { throw 'PowerShell executable is required.' }

$backend = Start-Process -FilePath $pwsh -PassThru -ArgumentList @(
    '-NoProfile', '-NoExit', '-ExecutionPolicy', 'Bypass',
    '-File', (Join-Path $PSScriptRoot 'dev-backend.ps1'), '-NoReload'
)
$frontend = Start-Process -FilePath $pwsh -PassThru -ArgumentList @(
    '-NoProfile', '-NoExit', '-ExecutionPolicy', 'Bypass',
    '-File', (Join-Path $PSScriptRoot 'dev-frontend.ps1')
)

Write-Host "Started backend terminal PID $($backend.Id) and frontend terminal PID $($frontend.Id)."
Write-Host 'Close those terminals to stop the development processes.'

$backendReady = $false
$frontendReady = $false
for ($i = 0; $i -lt 20; $i++) {
    try {
        $probe = Invoke-WebRequest -UseBasicParsing -Uri 'http://127.0.0.1:8000/api/v1/health/live' -TimeoutSec 2
        $backendReady = ($probe.StatusCode -eq 200)
    }
    catch { }
    try {
        $probe = Invoke-WebRequest -UseBasicParsing -Uri 'http://localhost:3000/login' -TimeoutSec 2
        $frontendReady = ($probe.StatusCode -eq 200)
    }
    catch { }
    if ($backendReady -and $frontendReady) { break }
    Start-Sleep -Milliseconds 1200
}
if (-not ($backendReady -and $frontendReady)) {
    throw "Local services are not both ready. Backend=$backendReady Frontend=$frontendReady. Inspect terminal output."
}

Write-Host 'TOUCHE COMMERCE development is reachable: http://localhost:3000' -ForegroundColor Green
Write-Host 'No Finance, Gmail, WhatsApp, E-YAY or payment integration was enabled.'

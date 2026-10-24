<#
.SYNOPSIS
    Start the already-installed TOUCHE COMMERCE locally in two visible windows.
.DESCRIPTION
    Refuses occupied ports and missing prerequisites. Never silently creates a
    database, fetches secrets, overwrites a .env file, or exposes a listener
    beyond localhost. Optional -ApplyMigrations requires operator action.
    Local development only, NOT production deployment.

    Ports: the defaults are 8000 (API) and 3000 (web). Another program may already use
    them; the launcher never touches an existing process. Pass -BackendPort and
    -FrontendPort to choose others, or -AutoPorts to take the next free ones. A
    non-default port also sets the browser origin the API trusts and the API address the
    web app calls, for this launch only (.env is never edited).
#>
[CmdletBinding()]
param(
    [switch] $ApplyMigrations,
    [ValidateRange(1024, 65535)][int] $BackendPort = 8000,
    [ValidateRange(1024, 65535)][int] $FrontendPort = 3000,
    [switch] $AutoPorts
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
function Find-FreePort {
    param([int] $Start, [int] $Last, [int[]] $Exclude = @())
    for ($candidate = $Start; $candidate -le $Last; $candidate++) {
        if ($Exclude -contains $candidate) { continue }
        if (-not (Test-LocalTcp -Port $candidate)) { return $candidate }
    }
    throw "No free port between $Start and $Last."
}

if ($AutoPorts) {
    if (Test-LocalTcp -Port $BackendPort) { $BackendPort = Find-FreePort -Start 8010 -Last 8099 }
    if (Test-LocalTcp -Port $FrontendPort) {
        $FrontendPort = Find-FreePort -Start 3010 -Last 3099 -Exclude @($BackendPort)
    }
}
foreach ($port in @($BackendPort, $FrontendPort)) {
    if (Test-LocalTcp -Port $port) {
        throw "Port $port is occupied. Refusing to affect existing processes. Use -AutoPorts or choose -BackendPort / -FrontendPort."
    }
}
if ($BackendPort -eq $FrontendPort) { throw 'The API and the web app need different ports.' }

if (($BackendPort -ne 8000) -or ($FrontendPort -ne 3000)) {
    # Passed to the two child terminals through the environment for this launch only.
    # Import-DotEnv never overrides a variable that is already set.
    $env:TOUCHE_CORS_ALLOWED_ORIGINS = "[`"http://localhost:$FrontendPort`",`"http://127.0.0.1:$FrontendPort`"]"
    $env:NEXT_PUBLIC_API_BASE_URL = "http://127.0.0.1:$BackendPort"
    $env:API_INTERNAL_BASE_URL = "http://127.0.0.1:$BackendPort"
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
    '-File', (Join-Path $PSScriptRoot 'dev-backend.ps1'), '-Port', $BackendPort, '-NoReload'
)
$frontend = Start-Process -FilePath $pwsh -PassThru -ArgumentList @(
    '-NoProfile', '-NoExit', '-ExecutionPolicy', 'Bypass',
    '-File', (Join-Path $PSScriptRoot 'dev-frontend.ps1'), '-Port', $FrontendPort
)

Write-Host "Started backend terminal PID $($backend.Id) and frontend terminal PID $($frontend.Id)."
Write-Host 'Close those terminals to stop the development processes.'

$backendReady = $false
$frontendReady = $false
for ($i = 0; $i -lt 20; $i++) {
    try {
        $probe = Invoke-WebRequest -UseBasicParsing -Uri "http://127.0.0.1:$BackendPort/api/v1/health/live" -TimeoutSec 2
        $backendReady = ($probe.StatusCode -eq 200)
    }
    catch { }
    try {
        $probe = Invoke-WebRequest -UseBasicParsing -Uri "http://localhost:$FrontendPort/login" -TimeoutSec 2
        $frontendReady = ($probe.StatusCode -eq 200)
    }
    catch { }
    if ($backendReady -and $frontendReady) { break }
    Start-Sleep -Milliseconds 1200
}
if (-not ($backendReady -and $frontendReady)) {
    throw "Local services are not both ready. Backend=$backendReady Frontend=$frontendReady. Inspect terminal output."
}

Write-Host "TOUCHE COMMERCE is reachable: http://localhost:$FrontendPort   (API http://127.0.0.1:$BackendPort, loopback only)" -ForegroundColor Green
Write-Host 'No Finance, Gmail, WhatsApp, E-YAY or payment integration was enabled.'

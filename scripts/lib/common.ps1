# Shared helpers for the TOUCHE COMMERCE PowerShell scripts.
# Dot-source from another script: . "$PSScriptRoot\..\lib\common.ps1"

Set-StrictMode -Version Latest
$ErrorActionPreference = 'Stop'

$script:RepoRoot = (Resolve-Path (Join-Path $PSScriptRoot '..\..')).Path

function Get-RepoRoot {
    return $script:RepoRoot
}

function Import-DotEnv {
    <#
    .SYNOPSIS
        Load KEY=VALUE pairs from .env into the current process environment.
    #>
    param(
        [string] $Path = (Join-Path $script:RepoRoot '.env')
    )

    if (-not (Test-Path $Path)) {
        throw "Environment file not found: $Path. Copy .env.example to .env first."
    }

    foreach ($rawLine in Get-Content -Path $Path) {
        $line = $rawLine.Trim()
        if (-not $line -or $line.StartsWith('#')) { continue }
        $separator = $line.IndexOf('=')
        if ($separator -lt 1) { continue }

        $name = $line.Substring(0, $separator).Trim()
        $value = $line.Substring($separator + 1).Trim()
        if ($value.Length -ge 2 -and $value.StartsWith('"') -and $value.EndsWith('"')) {
            $value = $value.Substring(1, $value.Length - 2)
        }
        [Environment]::SetEnvironmentVariable($name, $value, 'Process')
    }
}

function Get-RequiredEnv {
    param([Parameter(Mandatory = $true)][string] $Name)

    $value = [Environment]::GetEnvironmentVariable($Name, 'Process')
    if ([string]::IsNullOrWhiteSpace($value)) {
        throw "Required environment variable '$Name' is missing. Check your .env file."
    }
    return $value
}

function Get-BackendPython {
    $python = Join-Path $script:RepoRoot 'backend\.venv\Scripts\python.exe'
    if (-not (Test-Path $python)) {
        throw "Backend virtualenv not found at $python. Run scripts\setup.ps1 first."
    }
    return $python
}

function Get-PostgresBin {
    param([string] $PgRoot = (Join-Path $script:RepoRoot 'infra\.local\pg17\pgsql'))

    $bin = Join-Path $PgRoot 'bin'
    if (-not (Test-Path (Join-Path $bin 'pg_ctl.exe'))) {
        throw "PostgreSQL binaries not found in $bin. Run scripts\db\bootstrap-local-postgres.ps1 first (or use Docker Compose)."
    }
    return $bin
}

function Wait-ForPostgres {
    param(
        [Parameter(Mandatory = $true)][string] $PgBin,
        [int] $Port = 5432,
        [int] $TimeoutSeconds = 30
    )

    $deadline = (Get-Date).AddSeconds($TimeoutSeconds)
    while ((Get-Date) -lt $deadline) {
        & (Join-Path $PgBin 'pg_isready.exe') -h 127.0.0.1 -p $Port -q 2>$null
        if ($LASTEXITCODE -eq 0) { return $true }
        Start-Sleep -Milliseconds 500
    }
    return $false
}

function Write-Step {
    param([Parameter(Mandatory = $true)][string] $Message)
    Write-Host ""
    Write-Host "==> $Message" -ForegroundColor Cyan
}

function Write-Ok {
    param([Parameter(Mandatory = $true)][string] $Message)
    Write-Host "    [ok] $Message" -ForegroundColor Green
}

function Invoke-Native {
    <#
    .SYNOPSIS
        Runs a native executable, streams its output and throws on non-zero exit.
    .DESCRIPTION
        Windows PowerShell 5.1 turns native stderr into terminating errors when
        $ErrorActionPreference is 'Stop', which produces false failures for tools
        such as alembic/pytest that log to stderr. This helper contains that
        behaviour and checks the real exit code instead.
    #>
    param(
        [Parameter(Mandatory = $true)][string] $FilePath,
        [Parameter(ValueFromRemainingArguments = $true)][string[]] $Arguments = @(),
        [string] $WorkingDirectory
    )

    $previous = $ErrorActionPreference
    $ErrorActionPreference = 'Continue'
    $location = $null
    try {
        if ($WorkingDirectory) {
            $location = Push-Location $WorkingDirectory -PassThru
        }
        & $FilePath @Arguments 2>&1 | ForEach-Object { Write-Host $_ }
        $exitCode = $LASTEXITCODE
    }
    finally {
        if ($location) { Pop-Location }
        $ErrorActionPreference = $previous
    }

    if ($exitCode -ne 0) {
        throw "$FilePath exited with code $exitCode"
    }
}

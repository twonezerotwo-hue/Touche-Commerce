<#
.SYNOPSIS
    Runs every Stage 0 verification step: backend lint/typecheck/tests and
    frontend format/lint/typecheck/tests/build.

.PARAMETER SkipBuild
    Skip the production Next.js build (faster inner loop).

.PARAMETER SkipIntegration
    Exclude tests that require a live PostgreSQL instance.
#>
param(
    [switch] $SkipBuild,
    [switch] $SkipIntegration
)

. "$PSScriptRoot\lib\common.ps1"

$repoRoot = Get-RepoRoot
$backendDir = Join-Path $repoRoot 'backend'
$frontendDir = Join-Path $repoRoot 'frontend'
$python = Get-BackendPython
$failures = [System.Collections.Generic.List[string]]::new()

function Invoke-Step {
    param(
        [Parameter(Mandatory = $true)][string] $Name,
        [Parameter(Mandatory = $true)][scriptblock] $Action
    )

    Write-Step $Name
    try {
        & $Action
        Write-Ok $Name
    }
    catch {
        $failures.Add($Name)
        Write-Host "    [failed] $($_.Exception.Message)" -ForegroundColor Red
    }
}

$pytestArgs = @('-m', 'pytest', '-q')
if ($SkipIntegration) { $pytestArgs += @('-m', 'not integration') }

Invoke-Step 'backend: ruff' {
    Invoke-Native -FilePath $python -Arguments @('-m', 'ruff', 'check', '.') -WorkingDirectory $backendDir
}
Invoke-Step 'backend: mypy' {
    Invoke-Native -FilePath $python -Arguments @('-m', 'mypy', 'app') -WorkingDirectory $backendDir
}
Invoke-Step 'backend: pytest' {
    Invoke-Native -FilePath $python -Arguments $pytestArgs -WorkingDirectory $backendDir
}

if (Test-Path (Join-Path $frontendDir 'node_modules')) {
    Invoke-Step 'frontend: format check' {
        Invoke-Native -FilePath 'npm' -Arguments @('run', 'format:check') -WorkingDirectory $frontendDir
    }
    Invoke-Step 'frontend: eslint' {
        Invoke-Native -FilePath 'npm' -Arguments @('run', 'lint') -WorkingDirectory $frontendDir
    }
    Invoke-Step 'frontend: typecheck' {
        Invoke-Native -FilePath 'npm' -Arguments @('run', 'typecheck') -WorkingDirectory $frontendDir
    }
    Invoke-Step 'frontend: vitest' {
        Invoke-Native -FilePath 'npm' -Arguments @('test') -WorkingDirectory $frontendDir
    }
    if (-not $SkipBuild) {
        Invoke-Step 'frontend: production build' {
            Invoke-Native -FilePath 'npm' -Arguments @('run', 'build') -WorkingDirectory $frontendDir
        }
    }
}
else {
    Write-Host ''
    $failures.Add('frontend: dependencies missing')
    Write-Host 'frontend/node_modules missing - verification cannot pass. Run scripts\setup.ps1' -ForegroundColor Red
}

Write-Host ''
if ($failures.Count -gt 0) {
    Write-Host "VERIFICATION FAILED: $($failures -join ', ')" -ForegroundColor Red
    exit 1
}
Write-Host 'All verification steps passed.' -ForegroundColor Green

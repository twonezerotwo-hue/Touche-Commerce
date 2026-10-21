<#
.SYNOPSIS
    Regenerates the OpenAPI document and the TypeScript types derived from it.

.DESCRIPTION
    Single source of truth: backend Pydantic schemas -> OpenAPI -> TypeScript.
    With -Check the command fails when the committed artefacts are stale.

.PARAMETER Check
    Verify that regenerating produces no diff (used by CI).
#>
param([switch] $Check)

. "$PSScriptRoot\lib\common.ps1"

$repoRoot = Get-RepoRoot
Import-DotEnv
$python = Get-BackendPython

Write-Step 'Exporting OpenAPI schema from FastAPI'
Invoke-Native -FilePath $python `
    -Arguments @('scripts/export_openapi.py') `
    -WorkingDirectory (Join-Path $repoRoot 'backend')
Write-Ok 'frontend/openapi/openapi.json updated'

Write-Step 'Generating TypeScript types (openapi-typescript)'
Invoke-Native -FilePath 'npm' -Arguments @('run', 'api:types') -WorkingDirectory (Join-Path $repoRoot 'frontend')
Write-Ok 'frontend/src/lib/api/schema.d.ts updated'

if ($Check) {
    Write-Step 'Checking for contract drift'
    $location = Push-Location $repoRoot -PassThru
    try {
        Invoke-Native -FilePath 'git' -Arguments @(
            'diff', '--exit-code', '--',
            'frontend/openapi/openapi.json',
            'frontend/src/lib/api/schema.d.ts'
        )
    }
    finally {
        Pop-Location
    }
    Write-Ok 'generated API types are up to date'
}

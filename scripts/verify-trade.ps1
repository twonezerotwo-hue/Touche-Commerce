<#
.SYNOPSIS
    Runs the Stage 1B trade workflow verification against the local stack.

.DESCRIPTION
    Thin wrapper around backend/scripts/verify_trade_workflow.py. It loads the
    repository .env (so TOUCHE_DATABASE_URL etc. are the local ones) and runs the
    workflow with the backend virtualenv.

    The workflow signs in with known development accounts and needs their
    passwords in the process environment; they are never accepted as command-line
    arguments:

        $env:TOUCHE_VERIFY_TRADER_PASSWORD = '...'
        $env:TOUCHE_VERIFY_ADMIN_PASSWORD  = '...'

.PARAMETER ApiBase
    API origin to drive (default http://127.0.0.1:8000).

.PARAMETER WebBase
    Frontend origin used for the server-render check (default http://127.0.0.1:3000).
#>
param(
    [string] $ApiBase = 'http://127.0.0.1:8000',
    [string] $WebBase = 'http://127.0.0.1:3000'
)

. "$PSScriptRoot\lib\common.ps1"

$repoRoot = Get-RepoRoot
Import-DotEnv
$python = Get-BackendPython

$env:TOUCHE_VERIFY_API = $ApiBase
$env:TOUCHE_VERIFY_WEB = $WebBase

Write-Step 'Stage 1B trade workflow'
Invoke-Native -FilePath $python `
    -Arguments @('scripts/verify_trade_workflow.py') `
    -WorkingDirectory (Join-Path $repoRoot 'backend')

Write-Ok 'trade workflow passed'

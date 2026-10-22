<#
.SYNOPSIS
    Runs the Stage 3 sourcing workflow verification against the local stack.

.DESCRIPTION
    Thin wrapper around backend/scripts/verify_sourcing_workflow.py. It loads the
    repository .env (so TOUCHE_DATABASE_URL etc. are the local ones) and runs the
    workflow with the backend virtualenv.

    The workflow signs in with dedicated development accounts and needs their
    passwords in the process environment; they are never accepted as command-line
    arguments:

        $env:TOUCHE_VERIFY_STAGE3_TRADER_PASSWORD   = '...'
        $env:TOUCHE_VERIFY_STAGE3_APPROVER_PASSWORD = '...'
        $env:TOUCHE_VERIFY_STAGE3_OUTSIDER_PASSWORD = '...'

    The accounts must exist locally: stage3.trader@touche.example (trader) and
    stage3.approver@touche.example (approver) in one company, plus
    stage3.outsider@touche.example (viewer) in another company for the isolation
    check. Create them with `python -m app.cli create-user` and
    `python -m app.cli membership grant`.

.PARAMETER ApiBase
    API origin to drive (default http://127.0.0.1:8000).

.PARAMETER WebBase
    Frontend origin used for the server-render checks (default http://127.0.0.1:3000).
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

Write-Step 'Stage 3 sourcing workflow'
Invoke-Native -FilePath $python `
    -Arguments @('scripts/verify_sourcing_workflow.py') `
    -WorkingDirectory (Join-Path $repoRoot 'backend')

<#
.SYNOPSIS
    Runs the Stage 4 sales-order / procurement / logistics / document workflow.

.DESCRIPTION
    Thin wrapper around backend/scripts/verify_operations_workflow.py. It loads the
    repository .env (so TOUCHE_DATABASE_URL etc. are the local ones) and drives the
    running API and frontend with the backend virtualenv.

    The workflow needs three development accounts and their passwords in the
    process environment (never as command-line arguments):

        $env:TOUCHE_VERIFY_STAGE4_TRADER_PASSWORD   = '...'
        $env:TOUCHE_VERIFY_STAGE4_APPROVER_PASSWORD = '...'
        $env:TOUCHE_VERIFY_STAGE4_OUTSIDER_PASSWORD = '...'

    Create the accounts with `python -m app.cli create-user`, the companies with
    `python -m app.cli create-company` and the memberships with
    `python -m app.cli membership grant`:
      * stage4.trader@touche.example    trader   in "Stage 4 Trading"
      * stage4.approver@touche.example  approver in "Stage 4 Trading"
      * stage4.outsider@touche.example  viewer   in "Stage 4 Outsider"

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

Write-Step 'Stage 4 operations workflow'
Invoke-Native -FilePath $python `
    -Arguments @('scripts/verify_operations_workflow.py') `
    -WorkingDirectory (Join-Path $repoRoot 'backend')

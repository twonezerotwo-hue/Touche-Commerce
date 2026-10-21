<#
.SYNOPSIS
    Creates the first TOUCHE COMMERCE administrator and company (Stage 1A).

.DESCRIPTION
    Wrapper around `python -m app.cli bootstrap`. The password is requested with a
    hidden prompt and confirmed; it is never passed on the command line, never
    printed and never written to disk. There is no default password.

    The CLI connects with the migration role because the first company/user must
    exist before any tenant context can be established. Run it once per
    environment, then use `scripts\migrate.ps1` and the dev scripts.

.PARAMETER Email
    Administrator email. Prompted when omitted.

.PARAMETER Name
    Administrator display name.

.PARAMETER Company
    Company name.

.PARAMETER Country
    ISO 3166-1 alpha-2 country code (default prompts for GB).

.PARAMETER Currency
    ISO 4217 default currency (default prompts for USD).

.PARAMETER PasswordStdin
    Read the password from standard input instead of the hidden prompt. Intended
    for automation; the value is never echoed or stored.

.EXAMPLE
    scripts\bootstrap-admin.ps1
#>
param(
    [string] $Email,
    [string] $Name,
    [string] $Company,
    [string] $Country,
    [string] $Currency,
    [switch] $PasswordStdin
)

. "$PSScriptRoot\lib\common.ps1"

$repoRoot = Get-RepoRoot
$backendDir = Join-Path $repoRoot 'backend'
$python = Get-BackendPython

Import-DotEnv

$arguments = @('-m', 'app.cli', 'bootstrap')
if ($Email) { $arguments += @('--email', $Email) }
if ($Name) { $arguments += @('--name', $Name) }
if ($Company) { $arguments += @('--company', $Company) }
if ($Country) { $arguments += @('--country', $Country) }
if ($Currency) { $arguments += @('--currency', $Currency) }
if ($PasswordStdin) { $arguments += '--password-stdin' }

Write-Step 'Creating the first administrator and company'
Write-Host 'The password is entered interactively; nothing is logged.' -ForegroundColor DarkGray
Push-Location $backendDir
try {
    & $python @arguments
    if ($LASTEXITCODE -ne 0) { throw "bootstrap failed with exit code $LASTEXITCODE" }
}
finally {
    Pop-Location
}

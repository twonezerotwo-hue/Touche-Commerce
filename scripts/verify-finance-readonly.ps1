<#
.SYNOPSIS
    Stage 5A read-only verification of the TOUCHE FINANCE integration boundary.

.DESCRIPTION
    Verifies the Finance worktree revision, inspects the SQLite ledger through a
    mode=ro URI, reads workbook sheet metadata, and proves the database and
    workbook hashes are unchanged. It probes GET /api/health only when Finance is
    already listening; it never starts Finance, because startup recovery can
    legitimately write.

    Exits 0 only when the schema is compatible, the probe reports no file
    changes, and the independent before/after hashes match.
#>
param(
    [string]$FinanceRoot = 'C:\ai-excel',
    [string]$Database = '',
    [string]$Workbook = '',
    [string]$BaseUrl = 'http://127.0.0.1:8765',
    [switch]$Json
)

$ErrorActionPreference = 'Stop'
$repoRoot = Split-Path -Parent $PSScriptRoot
$python = Join-Path $repoRoot 'backend\.venv\Scripts\python.exe'
$probeScript = Join-Path $PSScriptRoot 'finance_readonly_probe.py'

if (-not (Test-Path -LiteralPath $FinanceRoot)) { throw "Finance root not found: $FinanceRoot" }
if (-not (Test-Path -LiteralPath $python)) { throw "Backend Python not found: $python" }
if (-not (Test-Path -LiteralPath $probeScript)) { throw "Probe script not found: $probeScript" }
if (-not $Database) { $Database = Join-Path $FinanceRoot 'veri\finans.db' }
if (-not (Test-Path -LiteralPath $Database)) { throw "Finance database not found: $Database" }

if (-not $Workbook) {
    $toucheDir = Join-Path $env:USERPROFILE 'OneDrive\Desktop\Touche'
    if (Test-Path -LiteralPath $toucheDir) {
        $candidate = Get-ChildItem -LiteralPath $toucheDir -Filter '*.xlsx' -File |
            Where-Object { $_.Name -notlike '*_backup*' } |
            Sort-Object Name | Select-Object -First 1
        if ($candidate) { $Workbook = $candidate.FullName }
    }
}

$head = (& git --no-optional-locks -C $FinanceRoot rev-parse HEAD).Trim()
$branch = (& git --no-optional-locks -C $FinanceRoot branch --show-current).Trim()
$remoteHead = (& git --no-optional-locks -C $FinanceRoot ls-remote origin HEAD 2>$null)
$statusLines = @(& git --no-optional-locks -C $FinanceRoot status --porcelain=v1)

$dbBefore = Get-FileHash -LiteralPath $Database -Algorithm SHA256
$wbBefore = if ($Workbook) { Get-FileHash -LiteralPath $Workbook -Algorithm SHA256 } else { $null }

$probeArgs = @($probeScript, '--finance-root', $FinanceRoot, '--db', $Database, '--json')
if ($Workbook) { $probeArgs += @('--workbook', $Workbook) }
$probeRaw = (& $python @probeArgs) -join "`n"
$probeExit = $LASTEXITCODE
$probe = $null
try { $probe = $probeRaw | ConvertFrom-Json } catch { $probe = $null }

function Test-TcpPort {
    param([string]$HostName, [int]$Port, [int]$TimeoutMs = 300)
    $client = New-Object System.Net.Sockets.TcpClient
    try {
        $task = $client.ConnectAsync($HostName, $Port)
        if (-not $task.Wait($TimeoutMs)) { return $false }
        return $client.Connected
    }
    catch { return $false }
    finally { $client.Dispose() }
}

$uri = [Uri]$BaseUrl
$port = if ($uri.IsDefaultPort) { 80 } else { $uri.Port }
$health = [ordered]@{
    status = 'skipped'
    detail = 'Finance server is not listening; it was not started by this script.'
}
if (Test-TcpPort -HostName $uri.Host -Port $port) {
    try {
        $response = Invoke-RestMethod -Uri "$BaseUrl/api/health" -Method Get -TimeoutSec 2
        $health = [ordered]@{ status = 'observed'; durum = $response.durum; yerel = $response.yerel }
    }
    catch {
        $health = [ordered]@{ status = 'error'; detail = $_.Exception.Message }
    }
}

$dbAfter = Get-FileHash -LiteralPath $Database -Algorithm SHA256
$wbAfter = if ($Workbook) { Get-FileHash -LiteralPath $Workbook -Algorithm SHA256 } else { $null }
$dbUnchanged = $dbBefore.Hash -eq $dbAfter.Hash
$wbUnchanged = if ($Workbook) { $wbBefore.Hash -eq $wbAfter.Hash } else { $true }
$probeOk = ($null -ne $probe) -and ($probeExit -eq 0)
$schemaOk = $probeOk -and ($probe.database.compatible -eq $true)
$probeFilesOk = $probeOk -and
    ($probe.unchanged.database -eq $true) -and
    ($probe.unchanged.database_wal -eq $true) -and
    ($probe.unchanged.workbook -eq $true)

$summary = [ordered]@{
    read_only = $true
    finance = [ordered]@{
        root = $FinanceRoot
        branch = $branch
        head = $head
        remote_head = ($remoteHead | Select-Object -First 1)
        dirty = ($statusLines.Count -gt 0)
        status = $statusLines
    }
    database = $Database
    workbook = $Workbook
    database_hash_before = $dbBefore.Hash
    database_hash_after = $dbAfter.Hash
    database_unchanged = $dbUnchanged
    workbook_hash_before = if ($wbBefore) { $wbBefore.Hash } else { $null }
    workbook_hash_after = if ($wbAfter) { $wbAfter.Hash } else { $null }
    workbook_unchanged = $wbUnchanged
    probe_exit = $probeExit
    probe_compatible = if ($probeOk) { $probe.database.compatible } else { $false }
    probe_counts = if ($probeOk) { $probe.database.counts } else { $null }
    probe_sheets = if ($probeOk) { $probe.workbook.sheets } else { $null }
    probe_unchanged = if ($probeOk) { $probe.unchanged } else { $null }
    health = $health
    passed = ($schemaOk -and $probeFilesOk -and $dbUnchanged -and $wbUnchanged)
}

if ($Json) {
    $summary | ConvertTo-Json -Depth 8
}
else {
    Write-Output 'TOUCHE FINANCE read-only verification (Stage 5A)'
    Write-Output ("  Worktree      : {0} [{1}] {2}" -f $FinanceRoot, $branch, $head)
    Write-Output ("  Remote HEAD   : {0}" -f ($summary.finance.remote_head))
    Write-Output ("  Dirty files   : {0}" -f $statusLines.Count)
    Write-Output ("  Database      : {0}" -f $Database)
    Write-Output ("  DB SHA-256    : {0}" -f $dbBefore.Hash)
    Write-Output ("  DB unchanged  : {0}" -f $dbUnchanged)
    Write-Output ("  Workbook      : {0}" -f $Workbook)
    Write-Output ("  WB unchanged  : {0}" -f $wbUnchanged)
    Write-Output ("  Schema ok     : {0}" -f $schemaOk)
    Write-Output ("  Health        : {0}" -f ($health | ConvertTo-Json -Compress))
    Write-Output ("  PASSED        : {0}" -f $summary.passed)
}

if (-not $summary.passed) { exit 1 }
exit 0


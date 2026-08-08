[CmdletBinding()]
param(
    [switch]$Once,
    [ValidateRange(60, 3600)]
    [int]$IntervalSeconds = 300
)

$ErrorActionPreference = 'Stop'
Set-StrictMode -Version Latest
$snapshotScript = Join-Path $PSScriptRoot 'Write-JosieStorageSnapshot.ps1'
if (-not (Test-Path -LiteralPath $snapshotScript)) { throw 'The storage snapshot script is unavailable.' }
$pythonPath = 'C:\Josie\.venv\Scripts\python.exe'
$corePath = 'C:\Josie\core.py'
if (-not (Test-Path -LiteralPath $pythonPath)) { throw 'Josie Python is unavailable.' }
if (-not (Test-Path -LiteralPath $corePath)) { throw 'Josie Core is unavailable.' }

$createdNew = $false
$mutex = [Threading.Mutex]::new($true, 'Local\JosieStorageMonitor', [ref]$createdNew)
if (-not $createdNew) {
    $mutex.Dispose()
    return
}
$stopEvent = [Threading.EventWaitHandle]::new(
    $false, [Threading.EventResetMode]::AutoReset, 'Local\JosieStorageMonitorStop'
)

try {
    do {
        & $snapshotScript | Out-Null
        & $pythonPath $corePath proposals ingest | Out-Null
        if ($LASTEXITCODE -ne 0) { throw 'Proposal inbox ingestion failed.' }
        if ($Once) { break }
        if ($stopEvent.WaitOne($IntervalSeconds * 1000)) { break }
    } while ($true)
}
finally {
    $stopEvent.Dispose()
    $mutex.ReleaseMutex()
    $mutex.Dispose()
}

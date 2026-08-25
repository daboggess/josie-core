[CmdletBinding()]
param()

$ErrorActionPreference = 'Stop'
Set-StrictMode -Version Latest
$projectRoot = Split-Path -Parent $PSScriptRoot
$pidPath = Join-Path $projectRoot 'data\private\prayer-bridge.pid'

if (-not (Test-Path -LiteralPath $pidPath)) {
    [ordered]@{ status = 'not_running'; records_deleted = $false } | ConvertTo-Json
    exit 0
}
$processId = [int]([System.IO.File]::ReadAllText($pidPath).Trim())
$process = Get-CimInstance Win32_Process -Filter "ProcessId=$processId" -ErrorAction SilentlyContinue
if ($null -ne $process -and $process.CommandLine -like '*core.py*prayer*bridge*') {
    Stop-Process -Id $processId
    $status = 'stopped'
} else {
    $status = 'stale_pid_removed'
}
Remove-Item -LiteralPath $pidPath -Force

[ordered]@{
    status = $status
    records_deleted = $false
    source_configuration_deleted = $false
    credential_deleted = $false
} | ConvertTo-Json

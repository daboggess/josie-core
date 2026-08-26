[CmdletBinding()]
param()

$ErrorActionPreference = 'Stop'
Set-StrictMode -Version Latest
$projectRoot = Split-Path -Parent $PSScriptRoot
$pidPath = Join-Path $projectRoot 'data\private\conversation-control.pid'

if (-not (Test-Path -LiteralPath $pidPath)) {
    [ordered]@{ status = 'not_running'; history_deleted = $false } | ConvertTo-Json
    exit 0
}
$processId = [int]([System.IO.File]::ReadAllText($pidPath).Trim())
$process = Get-CimInstance Win32_Process -Filter "ProcessId=$processId" -ErrorAction SilentlyContinue
if ($null -ne $process -and $process.CommandLine -like '*core.py*conversation*serve*') {
    Stop-Process -Id $processId
    $status = 'stopped'
} else {
    $status = 'stale_pid_removed'
}
Remove-Item -LiteralPath $pidPath -Force

[ordered]@{
    status = $status
    history_deleted = $false
    credential_deleted = $false
} | ConvertTo-Json

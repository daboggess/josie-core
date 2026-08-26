[CmdletBinding()]
param()

$ErrorActionPreference = 'Stop'
Set-StrictMode -Version Latest

$projectRoot = Split-Path -Parent $PSScriptRoot
$logPath = Join-Path $projectRoot 'logs\ollama-background.log'
$startScript = Join-Path $PSScriptRoot 'Start-JosieOllama.ps1'

try {
    $health = Invoke-RestMethod -Uri 'http://127.0.0.1:11434/api/version' -TimeoutSec 2
    if ($health.version) { return }
}
catch {
    # A stopped local service is expected during startup.
}

try {
    & $startScript *>> $logPath
}
catch {
    $timestamp = [DateTimeOffset]::Now.ToString('o')
    "$timestamp ERROR $($_.Exception.Message)" | Out-File -LiteralPath $logPath -Append -Encoding utf8
    throw
}

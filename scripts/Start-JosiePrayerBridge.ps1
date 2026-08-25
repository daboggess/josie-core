[CmdletBinding()]
param()

$ErrorActionPreference = 'Stop'
Set-StrictMode -Version Latest
$projectRoot = Split-Path -Parent $PSScriptRoot
$pythonPath = Join-Path $projectRoot '.venv\Scripts\pythonw.exe'
$pidPath = Join-Path $projectRoot 'data\private\prayer-bridge.pid'
$tokenPath = Join-Path $projectRoot 'data\private\prayer-bridge.token'
$sourceConfigPath = Join-Path $projectRoot 'data\private\prayer-sources.json'
$extensionConfigPath = Join-Path $projectRoot 'browser-extension\prayer-capture\config.js'

foreach ($required in $pythonPath, $tokenPath, $sourceConfigPath, $extensionConfigPath) {
    if (-not (Test-Path -LiteralPath $required)) {
        throw "Prayer bridge is not initialized. Missing local file: $required"
    }
}

try {
    $health = Invoke-RestMethod -Uri 'http://127.0.0.1:8788/health' -TimeoutSec 2
    if ($health.status -eq 'ok') {
        [ordered]@{ status = 'already_running'; binding = '127.0.0.1:8788' } | ConvertTo-Json
        exit 0
    }
} catch { }

$process = Start-Process -FilePath $pythonPath `
    -ArgumentList @('core.py', 'prayer', 'bridge') `
    -WorkingDirectory $projectRoot -WindowStyle Hidden -PassThru
[System.IO.File]::WriteAllText(
    $pidPath, [string]$process.Id, [System.Text.UTF8Encoding]::new($false)
)

$ready = $false
for ($attempt = 0; $attempt -lt 20; $attempt++) {
    Start-Sleep -Milliseconds 250
    try {
        $health = Invoke-RestMethod -Uri 'http://127.0.0.1:8788/health' -TimeoutSec 1
        if ($health.status -eq 'ok') { $ready = $true; break }
    } catch { }
}
if (-not $ready) {
    if (-not $process.HasExited) { Stop-Process -Id $process.Id -Force }
    throw 'The local prayer bridge did not become healthy.'
}

[ordered]@{
    status = 'running'
    binding = '127.0.0.1:8788'
    active_selection_only = $true
    browser_scanning_enabled = $false
    cloud_processing_enabled = $false
    sending_enabled = $false
} | ConvertTo-Json

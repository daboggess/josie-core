[CmdletBinding()]
param()

$ErrorActionPreference = 'Stop'
Set-StrictMode -Version Latest
$projectRoot = Split-Path -Parent $PSScriptRoot
$privateRoot = Join-Path $projectRoot 'data\private'
$sourceConfigPath = Join-Path $privateRoot 'prayer-sources.json'
$tokenPath = Join-Path $privateRoot 'prayer-bridge.token'
$extensionConfigPath = Join-Path $projectRoot 'browser-extension\prayer-capture\config.js'
$markerPath = Join-Path $privateRoot 'prayer-extension-installed.json'

foreach ($required in $sourceConfigPath, $tokenPath, $extensionConfigPath) {
    if (-not (Test-Path -LiteralPath $required)) {
        throw "Prayer capture is not initialized: $required"
    }
}
try {
    $health = Invoke-RestMethod -Uri 'http://127.0.0.1:8788/health' -TimeoutSec 2
} catch {
    throw 'The local prayer bridge is not running.'
}
if ($health.status -ne 'ok') { throw 'The local prayer bridge is not healthy.' }

$marker = [ordered]@{
    installed = $true
    confirmed_at = [DateTimeOffset]::UtcNow.ToString('o')
    confirmation_scope = 'local_chrome_unpacked_extension_only'
}
[System.IO.File]::WriteAllText(
    $markerPath,
    (ConvertTo-Json -InputObject $marker),
    [System.Text.UTF8Encoding]::new($false)
)
$identity = [System.Security.Principal.WindowsIdentity]::GetCurrent().Name
& icacls.exe $markerPath /inheritance:r /grant:r "${identity}:(F)" 'SYSTEM:(F)' | Out-Null
if ($LASTEXITCODE -ne 0) { throw 'The prayer-extension marker could not be restricted.' }

[ordered]@{
    status = 'extension_install_confirmed'
    source_connections = 3
    active_selection_only = $true
    browser_scanning_enabled = $false
    cloud_processing_enabled = $false
    sending_enabled = $false
} | ConvertTo-Json

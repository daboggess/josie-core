[CmdletBinding()]
param()

$ErrorActionPreference = 'Stop'
Set-StrictMode -Version Latest
$projectRoot = Split-Path -Parent $PSScriptRoot
$pythonPath = Join-Path $projectRoot '.venv\Scripts\pythonw.exe'
$privateRoot = Join-Path $projectRoot 'data\private'
$pidPath = Join-Path $privateRoot 'conversation-control.pid'
$tokenPath = Join-Path $privateRoot 'conversation-control.token'

if (-not (Test-Path -LiteralPath $pythonPath)) {
    throw "Josie Python is unavailable: $pythonPath"
}
New-Item -ItemType Directory -Path $privateRoot -Force | Out-Null
if (-not (Test-Path -LiteralPath $tokenPath)) {
    $tokenBytes = New-Object byte[] 32
    $generator = [System.Security.Cryptography.RandomNumberGenerator]::Create()
    try { $generator.GetBytes($tokenBytes) } finally { $generator.Dispose() }
    $token = [Convert]::ToBase64String($tokenBytes).TrimEnd('=').Replace('+', '-').Replace('/', '_')
    [System.IO.File]::WriteAllText(
        $tokenPath, $token, [System.Text.UTF8Encoding]::new($false)
    )
    $token = $null
}
$identity = [System.Security.Principal.WindowsIdentity]::GetCurrent().Name
& icacls.exe $tokenPath /inheritance:r /grant:r "${identity}:(F)" 'SYSTEM:(F)' | Out-Null
if ($LASTEXITCODE -ne 0) { throw 'The conversation credential could not be restricted.' }

try {
    $health = Invoke-RestMethod -Uri 'http://127.0.0.1:8790/health' -TimeoutSec 2
    if ($health.status -eq 'ok') {
        [ordered]@{
            status = 'already_running'
            binding = '127.0.0.1:8790'
            default_provider = 'local_ollama'
            cli_seats = $health.cli_seats
        } | ConvertTo-Json -Depth 6
        exit 0
    }
} catch { }

$process = Start-Process -FilePath $pythonPath `
    -ArgumentList @('core.py', 'conversation', 'serve') `
    -WorkingDirectory $projectRoot -WindowStyle Hidden -PassThru
[System.IO.File]::WriteAllText(
    $pidPath, [string]$process.Id, [System.Text.UTF8Encoding]::new($false)
)

$ready = $false
for ($attempt = 0; $attempt -lt 40; $attempt++) {
    Start-Sleep -Milliseconds 250
    try {
        $health = Invoke-RestMethod -Uri 'http://127.0.0.1:8790/health' -TimeoutSec 1
        if ($health.status -eq 'ok') { $ready = $true; break }
    } catch { }
}
if (-not $ready) {
    if (-not $process.HasExited) { Stop-Process -Id $process.Id -Force }
    throw 'The local conversation control did not become healthy.'
}

[ordered]@{
    status = 'running'
    binding = '127.0.0.1:8790'
    default_provider = 'local_ollama'
    cli_seats = $health.cli_seats
    api_keys_enabled = $false
    new_container = $false
    new_database = $false
} | ConvertTo-Json -Depth 6

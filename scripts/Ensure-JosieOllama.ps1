[CmdletBinding()]
param()

$ErrorActionPreference = 'Stop'
Set-StrictMode -Version Latest
$startScript = Join-Path $PSScriptRoot 'Start-JosieOllama.ps1'

try {
    $health = Invoke-RestMethod -Uri 'http://127.0.0.1:11434/api/version' -TimeoutSec 2
    if ($health.version) { return }
}
catch {
    # A stopped local service is expected during startup.
}

Start-Process -FilePath 'powershell.exe' -WindowStyle Hidden -ArgumentList @(
    '-NoProfile', '-ExecutionPolicy', 'Bypass', '-File', "`"$startScript`""
)

for ($attempt = 0; $attempt -lt 45; $attempt++) {
    Start-Sleep -Seconds 1
    try {
        $health = Invoke-RestMethod -Uri 'http://127.0.0.1:11434/api/version' -TimeoutSec 2
        if ($health.version) { return }
    }
    catch {
        # Continue the bounded readiness wait.
    }
}
throw 'Ollama did not become ready within 45 seconds.'

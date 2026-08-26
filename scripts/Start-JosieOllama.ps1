[CmdletBinding()]
param()

$ErrorActionPreference = 'Stop'
Set-StrictMode -Version Latest
$ollamaPath = 'D:\Josie-Storage\apps\Ollama\0.32.5\ollama.exe'
$modelRoot = 'D:\Josie-Storage\models\ollama'

if (-not (Test-Path -LiteralPath $ollamaPath)) { throw 'The verified Ollama runtime is unavailable.' }
if (-not (Test-Path -LiteralPath $modelRoot)) { throw 'The Ollama model directory is unavailable.' }

$env:OLLAMA_HOST = '0.0.0.0:11434'
$env:OLLAMA_MODELS = $modelRoot
$env:OLLAMA_MAX_LOADED_MODELS = '1'
$env:OLLAMA_NUM_PARALLEL = '1'
$env:OLLAMA_CONTEXT_LENGTH = '4096'
$env:OLLAMA_KEEP_ALIVE = '5m'
$env:OLLAMA_MAX_QUEUE = '8'

$process = Start-Process -FilePath $ollamaPath -ArgumentList @('serve') `
    -WindowStyle Hidden -PassThru
$ready = $false
for ($attempt = 0; $attempt -lt 40; $attempt++) {
    Start-Sleep -Milliseconds 250
    if ($process.HasExited) { break }
    try {
        $health = Invoke-RestMethod -Uri 'http://127.0.0.1:11434/api/version' -TimeoutSec 1
        if ($health.version) { $ready = $true; break }
    }
    catch {
        # The local listener may still be starting.
    }
}
if (-not $ready) {
    if (-not $process.HasExited) { Stop-Process -Id $process.Id -Force }
    throw 'Ollama did not become healthy after its hidden startup.'
}

[ordered]@{
    status = 'running'
    binding = '0.0.0.0:11434'
    pid = $process.Id
    model_root = $modelRoot
} | ConvertTo-Json

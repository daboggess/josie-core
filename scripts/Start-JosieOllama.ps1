[CmdletBinding()]
param()

$ErrorActionPreference = 'Stop'
Set-StrictMode -Version Latest
$ollamaPath = 'I:\Josie-Storage\apps\Ollama\0.32.5\ollama.exe'
$modelRoot = 'I:\Josie-Storage\models\ollama'

# The D: storage volume can become available after a logon-triggered task starts.
$storageReady = $false
for ($attempt = 0; $attempt -lt 60; $attempt++) {
    if ((Test-Path -LiteralPath $ollamaPath) -and (Test-Path -LiteralPath $modelRoot)) {
        $storageReady = $true
        break
    }
    Start-Sleep -Seconds 2
}
if (-not $storageReady) { throw 'The verified Ollama runtime or model directory was unavailable after waiting 120 seconds.' }

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
for ($attempt = 0; $attempt -lt 120; $attempt++) {
    Start-Sleep -Seconds 1
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

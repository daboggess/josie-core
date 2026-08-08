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

& $ollamaPath serve
if ($LASTEXITCODE -ne 0) { throw "Ollama exited with code $LASTEXITCODE." }

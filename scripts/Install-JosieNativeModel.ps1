[CmdletBinding(SupportsShouldProcess, ConfirmImpact = 'High')]
param(
    [Parameter(Mandatory)] [string] $ArchivePath
)

$ErrorActionPreference = 'Stop'
Set-StrictMode -Version Latest
$expectedSha256 = '7c941ae084569d298062d29f8139163a3187c76dbca0479c70d085e78fd8c7bb'
$runtimeRoot = 'D:\Josie-Storage\apps\Ollama\0.32.5'
$ollamaPath = Join-Path $runtimeRoot 'ollama.exe'
$modelRoot = 'D:\Josie-Storage\models\ollama'
$model = 'qwen2.5:1.5b-instruct-q4_K_M'
$josieModel = 'josie-local:1.0'
$projectRoot = Split-Path -Parent $PSScriptRoot
$modelfile = Join-Path $projectRoot 'deploy\Josie.Modelfile'

if (-not (Test-Path -LiteralPath $ArchivePath)) { throw 'The Ollama archive is missing.' }
$actualHash = (Get-FileHash -LiteralPath $ArchivePath -Algorithm SHA256).Hash.ToLowerInvariant()
if ($actualHash -ne $expectedSha256) { throw 'The Ollama archive failed SHA-256 verification.' }
if (-not (Test-Path -LiteralPath 'D:\Josie-Storage')) { throw 'D:\Josie-Storage is unavailable.' }
if (-not (Test-Path -LiteralPath $modelfile)) { throw 'The governed Josie Modelfile is missing.' }

if ($PSCmdlet.ShouldProcess($runtimeRoot, 'Install verified native Ollama and the approved local model')) {
    if (-not (Test-Path -LiteralPath $ollamaPath)) {
        if (Test-Path -LiteralPath $runtimeRoot) {
            throw 'The runtime directory exists but does not contain ollama.exe; refusing to overwrite it.'
        }
        New-Item -ItemType Directory -Force -Path $runtimeRoot,$modelRoot | Out-Null
        Expand-Archive -LiteralPath $ArchivePath -DestinationPath $runtimeRoot
    }
    if (-not (Test-Path -LiteralPath $ollamaPath)) { throw 'ollama.exe was not found after extraction.' }

    & (Join-Path $PSScriptRoot 'Ensure-JosieOllama.ps1')
    & $ollamaPath pull $model
    if ($LASTEXITCODE -ne 0) { throw 'The approved Qwen model download failed.' }
    & $ollamaPath create $josieModel -f $modelfile
    if ($LASTEXITCODE -ne 0) { throw 'The governed Josie model could not be created.' }
}

$list = & $ollamaPath list
if ($LASTEXITCODE -ne 0 -or -not ($list -match [regex]::Escape($josieModel))) {
    throw 'The governed Josie model is unavailable.'
}
$modelLine = @($list | Where-Object { $_ -match ('^' + [regex]::Escape($josieModel) + '\s') })[0]
$parts = $modelLine -split '\s+'
$payload = @{
    model = $josieModel
    prompt = 'Return JSON with status set to OK and source set to local.'
    format = 'json'
    stream = $false
    options = @{ num_ctx = 1024; num_predict = 64; temperature = 0 }
} | ConvertTo-Json -Depth 4
$response = Invoke-RestMethod -Method Post -Uri 'http://127.0.0.1:11434/api/generate' `
    -ContentType 'application/json' -Body $payload -TimeoutSec 180
$parsed = $response.response | ConvertFrom-Json
if ($parsed.status -ne 'OK' -or $parsed.source -ne 'local') {
    throw 'The local structured-output smoke test failed.'
}

[ordered]@{
    status = 'ready'
    runtime = $ollamaPath
    runtime_sha256 = $expectedSha256
    base_model = $model
    model = $josieModel
    observed_model_digest = if ($parts.Count -ge 2) { $parts[1] } else { $null }
    model_storage = $modelRoot
    structured_output_verified = $true
    cloud_spend_enabled = $false
    gpu_enabled = $false
} | ConvertTo-Json -Depth 3

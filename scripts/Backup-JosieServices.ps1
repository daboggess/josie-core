[CmdletBinding()]
param()

$ErrorActionPreference = 'Stop'
Set-StrictMode -Version Latest
$projectRoot = Split-Path -Parent $PSScriptRoot
$composePath = Join-Path $projectRoot 'deploy\compose.yaml'
$environmentPath = Join-Path $projectRoot 'deploy\.env.services'
$backupRoot = 'D:\Josie-Storage\backups\services'
$dockerCommand = Get-Command docker.exe -ErrorAction SilentlyContinue
$dockerPath = if ($dockerCommand) { $dockerCommand.Source } else {
    Join-Path $env:LOCALAPPDATA 'Programs\DockerDesktop\resources\bin\docker.exe'
}
if (-not (Test-Path -LiteralPath $dockerPath)) { throw 'Docker is unavailable.' }
$dockerBin = Split-Path -Parent $dockerPath
$env:Path = "$dockerBin;$env:Path"
if (-not (Test-Path -LiteralPath $environmentPath)) { throw 'Service environment is missing.' }
New-Item -ItemType Directory -Force -Path $backupRoot | Out-Null

$values = @{}
foreach ($line in Get-Content -LiteralPath $environmentPath) {
    if ($line -and -not $line.StartsWith('#') -and $line.Contains('=')) {
        $key, $value = $line.Split('=', 2)
        $values[$key] = $value
    }
}
foreach ($key in 'N8N_IMAGE', 'OPEN_WEBUI_IMAGE') {
    if (-not $values.ContainsKey($key) -or $values[$key] -notmatch '@sha256:[0-9a-fA-F]{64}$') {
        throw "$key is missing an immutable digest."
    }
}

$stamp = [DateTimeOffset]::Now.ToString('yyyyMMdd-HHmmss')
$n8nArchive = Join-Path $backupRoot "n8n-$stamp.tgz"
$webuiArchive = Join-Path $backupRoot "open-webui-$stamp.tgz"
$modelManifest = Join-Path $backupRoot "ollama-models-$stamp.txt"
$mount = ($backupRoot -replace '\\', '/')

try {
    & $dockerPath compose --env-file $environmentPath -f $composePath stop n8n open-webui
    if ($LASTEXITCODE -ne 0) { throw 'Could not stop persistent services for backup.' }
    & $dockerPath run --rm --user 0 --entrypoint /bin/sh `
        -v 'josie_n8n_data:/source:ro' -v "${mount}:/backup" $values['N8N_IMAGE'] `
        -c "tar -czf /backup/$([IO.Path]::GetFileName($n8nArchive)) -C /source ."
    if ($LASTEXITCODE -ne 0) { throw 'n8n backup failed.' }
    & $dockerPath run --rm --user 0 --entrypoint /bin/sh `
        -v 'josie_open_webui_data:/source:ro' -v "${mount}:/backup" $values['OPEN_WEBUI_IMAGE'] `
        -c "tar -czf /backup/$([IO.Path]::GetFileName($webuiArchive)) -C /source ."
    if ($LASTEXITCODE -ne 0) { throw 'Open WebUI backup failed.' }
}
finally {
    & $dockerPath compose --env-file $environmentPath -f $composePath up -d n8n open-webui
}

$ollamaPath = 'D:\Josie-Storage\apps\Ollama\0.32.5\ollama.exe'
if (-not (Test-Path -LiteralPath $ollamaPath)) { throw 'The native Ollama runtime is unavailable.' }
& $ollamaPath list | Set-Content -LiteralPath $modelManifest -Encoding UTF8
if ($LASTEXITCODE -ne 0) { throw 'Ollama model manifest capture failed.' }

foreach ($archive in $n8nArchive, $webuiArchive) {
    if (-not (Test-Path -LiteralPath $archive) -or (Get-Item -LiteralPath $archive).Length -eq 0) {
        throw "Backup archive is missing or empty: $archive"
    }
    & tar.exe -tzf $archive *> $null
    if ($LASTEXITCODE -ne 0) { throw "Backup archive verification failed: $archive" }
    $hash = Get-FileHash -LiteralPath $archive -Algorithm SHA256
    "$($hash.Hash.ToLowerInvariant())  $([IO.Path]::GetFileName($archive))" |
        Set-Content -LiteralPath "$archive.sha256" -Encoding ASCII
}
$manifestHash = Get-FileHash -LiteralPath $modelManifest -Algorithm SHA256
"$($manifestHash.Hash.ToLowerInvariant())  $([IO.Path]::GetFileName($modelManifest))" |
    Set-Content -LiteralPath "$modelManifest.sha256" -Encoding ASCII

[ordered]@{
    status = 'ok'
    created_at = [DateTimeOffset]::Now.ToString('o')
    archives = @($n8nArchive, $webuiArchive)
    model_manifest = $modelManifest
    checksums = @("$n8nArchive.sha256", "$webuiArchive.sha256", "$modelManifest.sha256")
    deletion_performed = $false
} | ConvertTo-Json -Depth 3

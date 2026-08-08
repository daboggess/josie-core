[CmdletBinding()]
param()

$ErrorActionPreference = 'Stop'
Set-StrictMode -Version Latest
$projectRoot = Split-Path -Parent $PSScriptRoot
$dockerPath = Join-Path $env:LOCALAPPDATA 'Programs\DockerDesktop\resources\bin\docker.exe'
$composePath = Join-Path $projectRoot 'deploy\compose.yaml'
$environmentPath = Join-Path $projectRoot 'deploy\.env.services'
$workflowPath = Join-Path $projectRoot 'deploy\n8n\workflows\storage-headroom-guard.json'
$workflowId = '9c3c3efe-e52d-4e79-becd-28893c1bbf83'
$containerName = 'josie-n8n-1'

foreach ($required in $dockerPath, $composePath, $environmentPath, $workflowPath) {
    if (-not (Test-Path -LiteralPath $required)) { throw "Required deployment file is missing: $required" }
}

$values = @{}
foreach ($line in Get-Content -LiteralPath $environmentPath) {
    if ($line -match '^\s*([^#][^=]*)=(.*)$') { $values[$matches[1].Trim()] = $matches[2].Trim() }
}
$image = $values['N8N_IMAGE']
if ($image -notmatch '^[^\s]+:[^\s@]+@sha256:[0-9a-fA-F]{64}$') {
    throw 'N8N_IMAGE is not pinned by tag and digest.'
}

$workflow = Get-Content -LiteralPath $workflowPath -Raw | ConvertFrom-Json
if ($workflow.id -ne $workflowId -or $workflow.active -ne $true) {
    throw 'The canonical workflow ID or staged active state is invalid.'
}
$nodeTypes = @($workflow.nodes | ForEach-Object type)
$forbidden = @('n8n-nodes-base.executeCommand', 'n8n-nodes-base.ssh', 'n8n-nodes-base.httpRequest')
if (@($nodeTypes | Where-Object { $_ -in $forbidden }).Count -ne 0) {
    throw 'The canonical workflow contains a forbidden node.'
}

$mountSource = $workflowPath.Replace('\', '/')
$workflowMount = "${mountSource}:/import/storage-headroom-guard.json:ro"
$composeArguments = @('compose', '--env-file', $environmentPath, '-f', $composePath)

& $dockerPath @composeArguments stop n8n
if ($LASTEXITCODE -ne 0) { throw 'Could not stop n8n for a consistent workflow import.' }
try {
    & $dockerPath run --rm --network none --pull=never --volumes-from $containerName `
        -v $workflowMount $image import:workflow --input=/import/storage-headroom-guard.json
    if ($LASTEXITCODE -ne 0) { throw 'The canonical workflow import failed.' }
    & $dockerPath run --rm --network none --pull=never --volumes-from $containerName `
        $image publish:workflow --id=$workflowId
    if ($LASTEXITCODE -ne 0) { throw 'The canonical workflow publish failed.' }
}
finally {
    & $dockerPath @composeArguments up -d n8n
}

$ready = $false
for ($attempt = 0; $attempt -lt 30; $attempt++) {
    Start-Sleep -Seconds 1
    try {
        $response = Invoke-WebRequest -UseBasicParsing -Uri 'http://127.0.0.1:5678/healthz' -TimeoutSec 2
        if ($response.StatusCode -eq 200) { $ready = $true; break }
    }
    catch {
        # Continue the bounded readiness check.
    }
}
if (-not $ready) { throw 'n8n did not become healthy after workflow publication.' }

$activeOutput = & $dockerPath exec $containerName n8n list:workflow --active=true --onlyId
if ($LASTEXITCODE -ne 0 -or $workflowId -notin @($activeOutput)) {
    throw 'The storage headroom workflow is not active.'
}

[ordered]@{
    status = 'ready'
    workflow_id = $workflowId
    workflow_name = $workflow.name
    active = $true
    sha256 = (Get-FileHash -Algorithm SHA256 -LiteralPath $workflowPath).Hash.ToLowerInvariant()
    n8n_healthy = $true
    external_communication = $false
    executable_node_enabled = $false
} | ConvertTo-Json -Depth 4

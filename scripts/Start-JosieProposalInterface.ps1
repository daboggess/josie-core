[CmdletBinding()]
param()

$ErrorActionPreference = 'Stop'
Set-StrictMode -Version Latest
$projectRoot = Split-Path -Parent $PSScriptRoot
$dockerPath = Join-Path $env:LOCALAPPDATA 'Programs\DockerDesktop\resources\bin\docker.exe'
$composePath = Join-Path $projectRoot 'deploy\compose.yaml'
$environmentPath = Join-Path $projectRoot 'deploy\.env.services'
$proposalRoot = 'D:\Josie-Storage\proposals'
$statusRoot = 'D:\Josie-Storage\status'
$secretRoot = 'D:\Josie-Storage\secrets'
$tokenPath = Join-Path $secretRoot 'proposal-token.txt'
$containerName = 'josie-proposal-server-1'
$webuiContainerName = 'josie-open-webui-1'

foreach ($required in $dockerPath, $composePath, $environmentPath) {
    if (-not (Test-Path -LiteralPath $required)) { throw "Required deployment file is missing: $required" }
}
foreach ($directory in 'inbox', 'processed', 'rejected') {
    New-Item -ItemType Directory -Force -Path (Join-Path $proposalRoot $directory) | Out-Null
}
New-Item -ItemType Directory -Force -Path $secretRoot | Out-Null
New-Item -ItemType Directory -Force -Path $statusRoot | Out-Null
if (-not (Test-Path -LiteralPath $tokenPath)) {
    $tokenBytes = New-Object byte[] 32
    $generator = [System.Security.Cryptography.RandomNumberGenerator]::Create()
    try { $generator.GetBytes($tokenBytes) } finally { $generator.Dispose() }
    $token = [Convert]::ToBase64String($tokenBytes).TrimEnd('=').Replace('+', '-').Replace('/', '_')
    [System.IO.File]::WriteAllText($tokenPath, $token, [System.Text.UTF8Encoding]::new($false))
}
$identity = [System.Security.Principal.WindowsIdentity]::GetCurrent().Name
& icacls.exe $tokenPath /inheritance:r /grant:r "${identity}:(F)" 'SYSTEM:(F)' | Out-Null
if ($LASTEXITCODE -ne 0) { throw 'The proposal credential could not be restricted to the current user and SYSTEM.' }

$token = [System.IO.File]::ReadAllText($tokenPath, [System.Text.Encoding]::UTF8).Trim()
if ([string]::IsNullOrWhiteSpace($token)) { throw 'The proposal credential is empty.' }
$connection = @(
    [ordered]@{
        url = 'http://proposal-server:3030'
        path = '/openapi.json'
        type = 'openapi'
        auth_type = 'bearer'
        key = $token
        spec_type = 'url'
        config = [ordered]@{
            enable = $true
            access_grants = @()
        }
        info = [ordered]@{
            id = 'josie-core-review'
            name = 'Josie Core Review'
            description = 'Reports secret-free read-only status and records bounded local proposals; it never executes actions.'
        }
    }
)
$connectionJson = ConvertTo-Json -InputObject $connection -Compress -Depth 8
$environmentLines = [System.Collections.Generic.List[string]]::new()
foreach ($line in [System.IO.File]::ReadAllLines($environmentPath)) {
    if (-not $line.StartsWith('JOSIE_TOOL_SERVER_CONNECTIONS=')) {
        $environmentLines.Add($line)
    }
}
$environmentLines.Add("JOSIE_TOOL_SERVER_CONNECTIONS=$connectionJson")
[System.IO.File]::WriteAllLines(
    $environmentPath,
    $environmentLines,
    [System.Text.UTF8Encoding]::new($false)
)
& icacls.exe $environmentPath /inheritance:r /grant:r "${identity}:(F)" 'SYSTEM:(F)' | Out-Null
if ($LASTEXITCODE -ne 0) { throw 'The local service configuration could not be restricted.' }
$token = $null
$connectionJson = $null

& $dockerPath compose --profile proposal-interface --env-file $environmentPath `
    -f $composePath up -d proposal-server open-webui
if ($LASTEXITCODE -ne 0) { throw 'The internal proposal interface did not start.' }
& $dockerPath restart $containerName | Out-Null
if ($LASTEXITCODE -ne 0) { throw 'The private proposal and status server did not restart.' }

$ready = $false
for ($attempt = 0; $attempt -lt 30; $attempt++) {
    Start-Sleep -Seconds 1
    $health = & $dockerPath exec $containerName node -e `
        "fetch('http://127.0.0.1:3030/health').then(async r=>{console.log(await r.text());process.exit(r.ok?0:1)}).catch(()=>process.exit(1))" 2>$null
    if ($LASTEXITCODE -eq 0) { $ready = $true; break }
}
if (-not $ready) { throw 'The internal proposal interface did not become healthy.' }

$backendProbe = & $dockerPath exec josie-open-webui-1 python -c `
    "import json,urllib.request; print(json.dumps(json.load(urllib.request.urlopen('http://proposal-server:3030/health',timeout=5))))"
if ($LASTEXITCODE -ne 0) { throw 'Open WebUI cannot reach the internal proposal interface.' }

$modelBinding = & $dockerPath exec $webuiContainerName python /opt/josie/configure-model.py
if ($LASTEXITCODE -ne 0) { throw 'The default Josie model/tool binding could not be configured.' }
& $dockerPath restart $webuiContainerName | Out-Null
if ($LASTEXITCODE -ne 0) { throw 'Open WebUI could not restart after model binding.' }
$webuiReady = $false
for ($attempt = 0; $attempt -lt 30; $attempt++) {
    Start-Sleep -Seconds 1
    $health = & $dockerPath inspect --format '{{.State.Health.Status}}' $webuiContainerName
    if ($LASTEXITCODE -eq 0 -and $health -contains 'healthy') { $webuiReady = $true; break }
}
if (-not $webuiReady) { throw 'Open WebUI did not recover after model binding.' }

$passthroughVerification = & $dockerPath exec $webuiContainerName python /opt/josie/verify-passthrough.py
if ($LASTEXITCODE -ne 0) { throw 'Authenticated tool responses are not grounded exactly.' }

[ordered]@{
    status = 'registered_and_ready'
    server = 'http://proposal-server:3030'
    specification = 'http://proposal-server:3030/openapi.json'
    authentication = 'bearer_token_required'
    connection_id = 'josie-core-review'
    global_tool_enabled = $true
    credential_file = $tokenPath
    published_host_port = $false
    docker_network = 'internal'
    actions_executable = $false
    default_model_binding = ($modelBinding | ConvertFrom-Json)
    authenticated_message_passthrough = ($passthroughVerification | ConvertFrom-Json)
    backend_probe = ($backendProbe | ConvertFrom-Json)
} | ConvertTo-Json -Depth 5

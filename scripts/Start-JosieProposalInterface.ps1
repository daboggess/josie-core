[CmdletBinding()]
param()

$ErrorActionPreference = 'Stop'
Set-StrictMode -Version Latest
$projectRoot = Split-Path -Parent $PSScriptRoot
$dockerPath = Join-Path $env:LOCALAPPDATA 'Programs\DockerDesktop\resources\bin\docker.exe'
$composePath = Join-Path $projectRoot 'deploy\compose.yaml'
$environmentPath = Join-Path $projectRoot 'deploy\.env.services'
$proposalRoot = 'D:\Josie-Storage\proposals'
$secretRoot = 'D:\Josie-Storage\secrets'
$tokenPath = Join-Path $secretRoot 'proposal-token.txt'
$containerName = 'josie-proposal-server-1'

foreach ($required in $dockerPath, $composePath, $environmentPath) {
    if (-not (Test-Path -LiteralPath $required)) { throw "Required deployment file is missing: $required" }
}
foreach ($directory in 'inbox', 'processed', 'rejected') {
    New-Item -ItemType Directory -Force -Path (Join-Path $proposalRoot $directory) | Out-Null
}
New-Item -ItemType Directory -Force -Path $secretRoot | Out-Null
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

& $dockerPath compose --profile proposal-interface --env-file $environmentPath `
    -f $composePath up -d proposal-server open-webui
if ($LASTEXITCODE -ne 0) { throw 'The internal proposal interface did not start.' }

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

[ordered]@{
    status = 'ready_for_admin_connection'
    server = 'http://proposal-server:3030'
    specification = 'http://proposal-server:3030/openapi.json'
    authentication = 'bearer_token_required'
    credential_file = $tokenPath
    published_host_port = $false
    docker_network = 'internal'
    actions_executable = $false
    backend_probe = ($backendProbe | ConvertFrom-Json)
} | ConvertTo-Json -Depth 5

[CmdletBinding()]
param()

$ErrorActionPreference = 'Stop'
$projectRoot = Split-Path -Parent $PSScriptRoot
$dockerPath = Join-Path $env:LOCALAPPDATA 'Programs\DockerDesktop\resources\bin\docker.exe'
& $dockerPath compose --env-file (Join-Path $projectRoot 'deploy\.env.services') `
    -f (Join-Path $projectRoot 'deploy\compose.yaml') stop browser-worker
if ($LASTEXITCODE -ne 0) { throw 'The read-only research connector could not be stopped.' }
[ordered]@{status = 'stopped'; external_research_available = $false} | ConvertTo-Json

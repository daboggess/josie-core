[CmdletBinding()]
param()

$ErrorActionPreference = 'Stop'
Set-StrictMode -Version Latest
$projectRoot = Split-Path -Parent $PSScriptRoot
$dockerPath = Join-Path $env:LOCALAPPDATA 'Programs\DockerDesktop\resources\bin\docker.exe'
$composePath = Join-Path $projectRoot 'deploy\compose.yaml'
$environmentPath = Join-Path $projectRoot 'deploy\.env.services'

& $dockerPath compose --profile proposal-interface --env-file $environmentPath `
    -f $composePath stop proposal-server
if ($LASTEXITCODE -ne 0) { throw 'The internal proposal interface did not stop cleanly.' }

[ordered]@{
    status = 'stopped'
    proposal_files_deleted = $false
    open_webui_stopped = $false
} | ConvertTo-Json

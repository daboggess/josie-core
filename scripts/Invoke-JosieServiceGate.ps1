[CmdletBinding(SupportsShouldProcess, ConfirmImpact = 'High')]
param(
    [Parameter(Mandatory)] [string] $N8nImage,
    [Parameter(Mandatory)] [string] $OpenWebUIImage,
    [Parameter(Mandatory)] [string] $PlaywrightImage
)

$ErrorActionPreference = 'Stop'
Set-StrictMode -Version Latest
$projectRoot = Split-Path -Parent $PSScriptRoot
$composePath = Join-Path $projectRoot 'deploy\compose.yaml'
$environmentPath = Join-Path $projectRoot 'deploy\.env.services'
$pythonPath = Join-Path $projectRoot '.venv\Scripts\python.exe'
$immutableImage = '^[^\s]+:[^\s@]+@sha256:[0-9a-fA-F]{64}$'

foreach ($entry in @{
    N8N_IMAGE = $N8nImage
    OPEN_WEBUI_IMAGE = $OpenWebUIImage
    PLAYWRIGHT_IMAGE = $PlaywrightImage
}.GetEnumerator()) {
    if ($entry.Value -notmatch $immutableImage) {
        throw "$($entry.Key) must include an explicit version tag and verified sha256 digest."
    }
}

$dockerCommand = Get-Command docker.exe -ErrorAction SilentlyContinue
$dockerPath = if ($dockerCommand) { $dockerCommand.Source } else {
    Join-Path $env:LOCALAPPDATA 'Programs\DockerDesktop\resources\bin\docker.exe'
}
if (-not (Test-Path -LiteralPath $dockerPath)) {
    throw 'Docker is unavailable. Complete the attended system gate first.'
}
& $dockerPath info *> $null
if ($LASTEXITCODE -ne 0) { throw 'Docker Desktop is not running or healthy.' }

$storage = 'D:/Josie-Storage'
if (-not (Test-Path -LiteralPath 'D:\Josie-Storage')) {
    throw 'D:\Josie-Storage is unavailable; services will not start on the wrong disk.'
}

$lines = @(
    'JOSIE_STORAGE=D:/Josie-Storage'
    'JOSIE_TIMEZONE=America/New_York'
    "N8N_IMAGE=$N8nImage"
    "OPEN_WEBUI_IMAGE=$OpenWebUIImage"
    "PLAYWRIGHT_IMAGE=$PlaywrightImage"
    'JOSIE_BROWSER_ALLOWLIST='
)
$temporary = "$environmentPath.tmp"
$lines | Set-Content -LiteralPath $temporary -Encoding UTF8
Move-Item -Force -LiteralPath $temporary -Destination $environmentPath

& $pythonPath (Join-Path $projectRoot 'core.py') deploy services-preflight
if ($LASTEXITCODE -ne 0) { throw 'Josie service preflight failed.' }

& $dockerPath compose --env-file $environmentPath -f $composePath config --quiet
if ($LASTEXITCODE -ne 0) { throw 'Docker Compose validation failed.' }

if ($PSCmdlet.ShouldProcess('Josie local service stack', 'Pull immutable images, build locked worker, and start loopback-only services')) {
    & $dockerPath compose --env-file $environmentPath -f $composePath pull
    if ($LASTEXITCODE -ne 0) { throw 'Container image pull failed.' }
    & $dockerPath compose --env-file $environmentPath -f $composePath build --pull=false browser-worker
    if ($LASTEXITCODE -ne 0) { throw 'Browser worker build failed.' }
    & $dockerPath compose --env-file $environmentPath -f $composePath up -d
    if ($LASTEXITCODE -ne 0) { throw 'Service startup failed.' }
}

& $dockerPath compose --env-file $environmentPath -f $composePath ps
Write-Host 'Services are local-only. Browser execution and cloud providers remain locked.'

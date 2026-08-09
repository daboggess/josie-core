[CmdletBinding()]
param(
    [string]$TestUrl = 'https://www.advantech.com/en-us/support/details/manual?id=1-1DXQYC7'
)

$ErrorActionPreference = 'Stop'
Set-StrictMode -Version Latest
$projectRoot = Split-Path -Parent $PSScriptRoot
$dockerPath = Join-Path $env:LOCALAPPDATA 'Programs\DockerDesktop\resources\bin\docker.exe'
$composePath = Join-Path $projectRoot 'deploy\compose.yaml'
$environmentPath = Join-Path $projectRoot 'deploy\.env.services'
$tokenPath = 'D:\Josie-Storage\secrets\browser-token.txt'
$pythonPath = Join-Path $projectRoot '.venv\Scripts\python.exe'

foreach ($required in $dockerPath, $composePath, $environmentPath, $pythonPath) {
    if (-not (Test-Path -LiteralPath $required)) { throw "Required pilot component is missing: $required" }
}
$policy = & $pythonPath (Join-Path $projectRoot 'core.py') browser status | ConvertFrom-Json
if ($LASTEXITCODE -ne 0 -or $policy.status -ne 'read_only_pilot' -or -not $policy.write_actions_locked) {
    throw 'The approved read-only browser policy is unavailable or expired.'
}

New-Item -ItemType Directory -Force -Path (Split-Path -Parent $tokenPath) | Out-Null
if (-not (Test-Path -LiteralPath $tokenPath)) {
    $tokenBytes = New-Object byte[] 32
    $generator = [System.Security.Cryptography.RandomNumberGenerator]::Create()
    try { $generator.GetBytes($tokenBytes) } finally { $generator.Dispose() }
    $token = [Convert]::ToBase64String($tokenBytes).TrimEnd('=').Replace('+', '-').Replace('/', '_')
    [System.IO.File]::WriteAllText($tokenPath, $token, [System.Text.UTF8Encoding]::new($false))
    $token = $null
}
$identity = [System.Security.Principal.WindowsIdentity]::GetCurrent().Name
& icacls.exe $tokenPath /inheritance:r /grant:r "${identity}:(F)" 'SYSTEM:(F)' | Out-Null
if ($LASTEXITCODE -ne 0) { throw 'The browser credential could not be restricted.' }

& $dockerPath compose --env-file $environmentPath -f $composePath up -d --build browser-worker
if ($LASTEXITCODE -ne 0) { throw 'The read-only research connector did not start.' }
$ready = $false
for ($attempt = 0; $attempt -lt 45; $attempt++) {
    Start-Sleep -Seconds 1
    $health = & $dockerPath inspect --format '{{.State.Health.Status}}' josie-browser-worker-1 2>$null
    if ($LASTEXITCODE -eq 0 -and $health -contains 'healthy') { $ready = $true; break }
}
if (-not $ready) { throw 'The read-only research connector did not become healthy.' }

$offAllowlistBlocked = $false
try {
    & $pythonPath (Join-Path $projectRoot 'core.py') browser extract 'https://example.com/' 2>$null | Out-Null
} catch { $offAllowlistBlocked = $true }
if ($LASTEXITCODE -ne 0) { $offAllowlistBlocked = $true }
if (-not $offAllowlistBlocked) { throw 'Off-allowlist validation unexpectedly succeeded.' }

$testResult = & $pythonPath (Join-Path $projectRoot 'core.py') browser extract $TestUrl | ConvertFrom-Json
if ($LASTEXITCODE -ne 0 -or $testResult.status -ne 'ok' -or -not $testResult.content_untrusted) {
    throw 'The approved Advantech extraction test failed.'
}

[ordered]@{
    status = 'ready'
    mode = 'read_only_research'
    allowed_hosts = $policy.allowed_hosts
    approved_test_url = $testResult.final_url
    title = $testResult.title
    bytes_received = $testResult.bytes_received
    page_content_persisted = $false
    downloads_saved = $false
    forms_submitted = $false
    cookies_used = $false
    model_direct_access = $false
    off_allowlist_blocked = $true
    credential_file = $tokenPath
    published_address = '127.0.0.1:3010'
} | ConvertTo-Json -Depth 5

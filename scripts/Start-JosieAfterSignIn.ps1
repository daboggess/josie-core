[CmdletBinding()]
param()

$ErrorActionPreference = 'Stop'
Set-StrictMode -Version Latest
$projectRoot = Split-Path -Parent $PSScriptRoot
$dockerDesktop = Join-Path $env:LOCALAPPDATA 'Programs\DockerDesktop\Docker Desktop.exe'
$dockerPath = Join-Path $env:LOCALAPPDATA 'Programs\DockerDesktop\resources\bin\docker.exe'
$ensureOllama = Join-Path $PSScriptRoot 'Ensure-JosieOllama.ps1'
$storageMonitor = Join-Path $PSScriptRoot 'Start-JosieStorageMonitor.ps1'
$prayerBridge = Join-Path $PSScriptRoot 'Start-JosiePrayerBridge.ps1'
$statusRoot = 'D:\Josie-Storage\status'
$statusPath = Join-Path $statusRoot 'startup-recovery.json'
$containerNames = @(
    'josie-open-webui-1',
    'josie-n8n-1',
    'josie-proposal-server-1',
    'josie-browser-worker-1'
)

$createdNew = $false
$mutex = [Threading.Mutex]::new($true, 'Local\JosieAfterSignIn', [ref]$createdNew)
if (-not $createdNew) {
    $mutex.Dispose()
    return
}
$result = $null

function Test-HttpHealth([string]$Uri) {
    try {
        $response = Invoke-WebRequest -UseBasicParsing -Uri $Uri -TimeoutSec 3
        return $response.StatusCode -ge 200 -and $response.StatusCode -lt 400
    }
    catch { return $false }
}

try {
    foreach ($required in $dockerDesktop, $dockerPath, $ensureOllama, $storageMonitor) {
        if (-not (Test-Path -LiteralPath $required)) {
            throw "Required startup component is missing: $required"
        }
    }
    New-Item -ItemType Directory -Force -Path $statusRoot | Out-Null

    # Native Ollama is independent of Docker and should recover even while Docker
    # Desktop is still changing engine pipes during sign-in.
    & $ensureOllama

    if (-not (Get-Process -Name 'Docker Desktop' -ErrorAction SilentlyContinue)) {
        Start-Process -FilePath $dockerDesktop -WindowStyle Hidden
    }
    $dockerReady = $false
    $consecutiveDockerChecks = 0
    for ($attempt = 0; $attempt -lt 120; $attempt++) {
        & $dockerPath info *> $null
        if ($LASTEXITCODE -eq 0) {
            $consecutiveDockerChecks++
            if ($consecutiveDockerChecks -ge 3) { $dockerReady = $true; break }
        }
        else {
            $consecutiveDockerChecks = 0
        }
        Start-Sleep -Seconds 2
    }
    if (-not $dockerReady) { throw 'Docker did not become ready after sign-in.' }

    # Existing containers retain their pinned images, volumes, networks, and restart policy.
    # This starts an exact known container only if Docker did not restore it automatically.
    foreach ($name in $containerNames) {
        $state = ''
        for ($attempt = 0; $attempt -lt 60; $attempt++) {
            $candidate = & $dockerPath inspect --format '{{.State.Status}}' $name 2>$null
            if ($LASTEXITCODE -eq 0) {
                $state = ($candidate -join '').Trim()
                break
            }
            Start-Sleep -Seconds 2
        }
        if (-not $state) { throw "Expected Josie container is unavailable: $name" }
        if ($state -ne 'running') {
            & $dockerPath start $name | Out-Null
            if ($LASTEXITCODE -ne 0) { throw "Josie container did not start: $name" }
        }
    }

    Start-Process -FilePath 'powershell.exe' -WindowStyle Hidden -ArgumentList @(
        '-NoProfile', '-ExecutionPolicy', 'Bypass', '-File', "`"$storageMonitor`""
    ) | Out-Null
    if (Test-Path -LiteralPath $prayerBridge) {
        Start-Process -FilePath 'powershell.exe' -WindowStyle Hidden -ArgumentList @(
            '-NoProfile', '-ExecutionPolicy', 'Bypass', '-File', "`"$prayerBridge`""
        ) | Out-Null
    }

    $serviceReady = $false
    for ($attempt = 0; $attempt -lt 60; $attempt++) {
        $containerHealth = @{}
        foreach ($name in $containerNames) {
            $healthOutput = & $dockerPath inspect --format `
                '{{if .State.Health}}{{.State.Health.Status}}{{else}}{{.State.Status}}{{end}}' `
                $name 2>$null
            $containerHealth[$name] = if ($LASTEXITCODE -eq 0) {
                ($healthOutput -join '').Trim()
            } else {
                'docker_api_unavailable'
            }
        }
        $ollamaReady = Test-HttpHealth 'http://127.0.0.1:11434/api/version'
        $webUiReady = Test-HttpHealth 'http://127.0.0.1:3000/health'
        $n8nReady = Test-HttpHealth 'http://127.0.0.1:5678/healthz'
        if ($ollamaReady -and $webUiReady -and $n8nReady -and
            -not ($containerHealth.Values | Where-Object { $_ -notin @('healthy', 'running') })) {
            $serviceReady = $true
            break
        }
        Start-Sleep -Seconds 2
    }
    if (-not $serviceReady) { throw 'One or more Josie services failed the recovery health gate.' }

    $result = [ordered]@{
        status = 'healthy'
        checked_at = [DateTimeOffset]::UtcNow.ToString('o')
        trigger = 'after_interactive_sign_in'
        docker = 'ready'
        ollama = 'healthy'
        open_webui = 'healthy'
        n8n = 'healthy'
        containers = $containerHealth
        visible_terminal_windows_requested = $false
    }
}
catch {
    $result = [ordered]@{
        status = 'failed'
        checked_at = [DateTimeOffset]::UtcNow.ToString('o')
        trigger = 'after_interactive_sign_in'
        reason = $_.Exception.Message
        visible_terminal_windows_requested = $false
    }
}
finally {
    if ($null -ne $result) {
        [System.IO.File]::WriteAllText(
            $statusPath,
            (ConvertTo-Json -InputObject $result -Depth 5),
            [System.Text.UTF8Encoding]::new($false)
        )
    }
    $mutex.ReleaseMutex()
    $mutex.Dispose()
}

if ($result.status -ne 'healthy') { exit 1 }

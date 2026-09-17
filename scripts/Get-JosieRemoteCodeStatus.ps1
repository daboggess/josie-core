[CmdletBinding()]
param()

$ErrorActionPreference = 'Stop'
Set-StrictMode -Version Latest

$results = [ordered]@{
    TAILSCALE_SERVICE    = 'FAIL'
    TAILSCALE_NETWORK    = 'FAIL'
    TAILSCALE_SERVE_8443 = 'FAIL'
    OLLAMA_MODEL_PATH    = 'FAIL'
    OLLAMA_SERVER        = 'FAIL'
    OLLAMA_MODELS        = 'FAIL'
    OPENCODE_WEB_4096    = 'FAIL'
}

$reasons = [ordered]@{
    TAILSCALE_SERVICE    = ''
    TAILSCALE_NETWORK    = ''
    TAILSCALE_SERVE_8443 = ''
    OLLAMA_MODEL_PATH    = ''
    OLLAMA_SERVER        = ''
    OLLAMA_MODELS        = ''
    OPENCODE_WEB_4096    = ''
}

# 1. Tailscale Windows service exists and is Running.
try {
    $svc = Get-Service -Name 'Tailscale' -ErrorAction SilentlyContinue
    if ($null -eq $svc) {
        $reasons.TAILSCALE_SERVICE = 'Service does not exist'
    } elseif ($svc.Status -eq 'Running') {
        $results.TAILSCALE_SERVICE = 'PASS'
    } else {
        $reasons.TAILSCALE_SERVICE = "Service status is $($svc.Status)"
    }
} catch {
    $reasons.TAILSCALE_SERVICE = $_.Exception.Message
}

# 2. tailscale status succeeds.
try {
    $statusOut = & tailscale.exe status 2>&1
    if ($LASTEXITCODE -eq 0) {
        $results.TAILSCALE_NETWORK = 'PASS'
    } else {
        $reasons.TAILSCALE_NETWORK = "tailscale status exited with code $LASTEXITCODE"
    }
} catch {
    $reasons.TAILSCALE_NETWORK = $_.Exception.Message
}

# 3. tailscale serve status contains HTTPS port 8443 -> http://127.0.0.1:4096
try {
    $serveOut = & tailscale.exe serve status 2>&1
    if ($LASTEXITCODE -eq 0) {
        $serveText = $serveOut -join "`n"
        $hasPort = $serveText -match '8443'
        $hasProxy = $serveText -match '127\.0\.0\.1:4096'
        if ($hasPort -and $hasProxy) {
            $results.TAILSCALE_SERVE_8443 = 'PASS'
        } else {
            $reasons.TAILSCALE_SERVE_8443 = 'Mapping 8443 -> 127.0.0.1:4096 not found in serve status'
        }
    } else {
        $reasons.TAILSCALE_SERVE_8443 = "tailscale serve status exited with code $LASTEXITCODE"
    }
} catch {
    $reasons.TAILSCALE_SERVE_8443 = $_.Exception.Message
}

# 4. User-level OLLAMA_MODELS is exactly I:\Josie-Storage\models\ollama
try {
    $userModels = [Environment]::GetEnvironmentVariable('OLLAMA_MODELS', 'User')
    $expectedPath = 'I:\Josie-Storage\models\ollama'
    if ($null -ne $userModels -and $userModels.Trim() -eq $expectedPath) {
        $results.OLLAMA_MODEL_PATH = 'PASS'
    } else {
        $reasons.OLLAMA_MODEL_PATH = "Found '$userModels', expected '$expectedPath'"
    }
} catch {
    $reasons.OLLAMA_MODEL_PATH = $_.Exception.Message
}

# 5. A canonical Ollama server process is running from I:\Josie-Storage\apps\Ollama\0.32.5\ollama.exe
try {
    $procs = Get-Process -Name 'ollama' -ErrorAction SilentlyContinue
    $canonicalPath = 'I:\Josie-Storage\apps\Ollama\0.32.5\ollama.exe'
    $foundCanonical = $false
    if ($null -ne $procs) {
        foreach ($p in $procs) {
            try {
                if ($null -ne $p.Path -and $p.Path.Equals($canonicalPath, [System.StringComparison]::OrdinalIgnoreCase)) {
                    $foundCanonical = $true
                    break
                }
            } catch {}
        }
    }
    if ($foundCanonical) {
        $results.OLLAMA_SERVER = 'PASS'
    } else {
        $reasons.OLLAMA_SERVER = "Canonical Ollama process not running from $canonicalPath"
    }
} catch {
    $reasons.OLLAMA_SERVER = $_.Exception.Message
}

# 6. Ollama model inventory contains gemma4:12b and qwen3:14b
try {
    $ollamaList = & ollama.exe list 2>&1
    if ($LASTEXITCODE -eq 0) {
        $listText = $ollamaList -join "`n"
        $hasGemma = $listText -match '\bgemma4:12b\b'
        $hasQwen = $listText -match '\bqwen3:14b\b'
        if ($hasGemma -and $hasQwen) {
            $results.OLLAMA_MODELS = 'PASS'
        } else {
            $missing = @()
            if (-not $hasGemma) { $missing += 'gemma4:12b' }
            if (-not $hasQwen) { $missing += 'qwen3:14b' }
            $reasons.OLLAMA_MODELS = "Missing models: $($missing -join ', ')"
        }
    } else {
        $reasons.OLLAMA_MODELS = "ollama list exited with code $LASTEXITCODE"
    }
} catch {
    $reasons.OLLAMA_MODELS = $_.Exception.Message
}

# 7. TCP port 4096 is listening locally for OpenCode Web.
try {
    $tcpConnection = Test-NetConnection -ComputerName '127.0.0.1' -Port 4096 -InformationLevel Quiet -ErrorAction SilentlyContinue
    if ($tcpConnection) {
        $results.OPENCODE_WEB_4096 = 'PASS'
    } else {
        $reasons.OPENCODE_WEB_4096 = 'TCP port 4096 is not listening locally'
    }
} catch {
    $reasons.OPENCODE_WEB_4096 = $_.Exception.Message
}

# Output results
foreach ($key in $results.Keys) {
    $status = $results[$key]
    $reason = $reasons[$key]
    if ($status -eq 'PASS' -or [string]::IsNullOrWhiteSpace($reason)) {
        "$key`: $status"
    } else {
        "$key`: $status - $reason"
    }
}

$allPass = $true
foreach ($key in $results.Keys) {
    if ($results[$key] -ne 'PASS') {
        $allPass = $false
        break
    }
}

if ($allPass) {
    'OVERALL_STATUS: PASS'
    exit 0
} else {
    'OVERALL_STATUS: FAIL'
    exit 1
}

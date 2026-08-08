[CmdletBinding(SupportsShouldProcess, ConfirmImpact = 'High')]
param(
    [Parameter(Mandatory)] [string] $DockerInstaller,
    [Parameter(Mandatory)] [string] $TailscaleInstaller,
    [switch] $ResumeAfterReboot
)

$ErrorActionPreference = 'Stop'
Set-StrictMode -Version Latest
$projectRoot = Split-Path -Parent $PSScriptRoot
$statePath = Join-Path $projectRoot 'data\system-gate-state.json'

function Test-Administrator {
    $identity = [Security.Principal.WindowsIdentity]::GetCurrent()
    $principal = [Security.Principal.WindowsPrincipal]::new($identity)
    return $principal.IsInRole([Security.Principal.WindowsBuiltInRole]::Administrator)
}

function Assert-SignedInstaller([string] $Path, [string] $PublisherPattern) {
    $resolved = (Resolve-Path -LiteralPath $Path).Path
    if ([IO.Path]::GetExtension($resolved) -ne '.exe') {
        throw "Installer must be an .exe: $resolved"
    }
    $signature = Get-AuthenticodeSignature -LiteralPath $resolved
    if ($signature.Status -ne 'Valid' -or $signature.SignerCertificate.Subject -notmatch $PublisherPattern) {
        throw "Installer signature is not valid for expected publisher: $resolved"
    }
    return $resolved
}

function Save-State([string] $Step, [bool] $RebootRequired) {
    $state = [ordered]@{
        schema_version = 1
        step = $Step
        reboot_required = $RebootRequired
        updated_at = [DateTimeOffset]::Now.ToString('o')
    }
    $temporary = "$statePath.tmp"
    $state | ConvertTo-Json | Set-Content -LiteralPath $temporary -Encoding UTF8
    Move-Item -Force -LiteralPath $temporary -Destination $statePath
}

if (-not (Test-Administrator)) {
    throw 'This attended gate must be run from PowerShell as Administrator. UAC must remain enabled.'
}

$dockerPath = Assert-SignedInstaller $DockerInstaller 'Docker'
$tailscalePath = Assert-SignedInstaller $TailscaleInstaller 'Tailscale'

$wslStatus = & cmd.exe /d /c 'wsl.exe --status 2>&1'
if ($LASTEXITCODE -ne 0) {
    if ($ResumeAfterReboot) {
        throw 'WSL is still unavailable after reboot; stop and inspect Windows features.'
    }
    if ($PSCmdlet.ShouldProcess('Windows Subsystem for Linux', 'Enable WSL 2 without installing a distribution')) {
        & cmd.exe /d /c 'wsl.exe --install --no-distribution'
        if ($LASTEXITCODE -ne 0) { throw "WSL enablement failed with exit code $LASTEXITCODE" }
        Save-State 'wsl_enabled' $true
        Write-Host 'Restart Windows, then rerun this script with -ResumeAfterReboot and the same installer paths.'
        exit 3010
    }
}

$wslTemplate = Join-Path $PSScriptRoot 'wslconfig.template'
$wslTarget = Join-Path ([Environment]::GetFolderPath('UserProfile')) '.wslconfig'
if (-not (Test-Path -LiteralPath $wslTarget)) {
    Copy-Item -LiteralPath $wslTemplate -Destination $wslTarget
}

if (-not (Get-Command docker.exe -ErrorAction SilentlyContinue)) {
    if ($PSCmdlet.ShouldProcess('Docker Desktop', 'Install per-user with WSL 2 Linux containers')) {
        $process = Start-Process -FilePath $dockerPath -Wait -PassThru `
            -ArgumentList 'install', '--user', '--backend=wsl-2', '--no-windows-containers'
        if ($process.ExitCode -ne 0) { throw "Docker installer failed with exit code $($process.ExitCode)" }
        Save-State 'docker_installed' $false
    }
}

if (-not (Get-Command tailscale.exe -ErrorAction SilentlyContinue)) {
    if ($PSCmdlet.ShouldProcess('Tailscale', 'Open the signed installer for attended setup')) {
        $process = Start-Process -FilePath $tailscalePath -Wait -PassThru
        if ($process.ExitCode -ne 0) { throw "Tailscale installer failed with exit code $($process.ExitCode)" }
        Save-State 'tailscale_installed_auth_pending' $false
    }
}

Save-State 'system_gate_complete_auth_may_be_pending' $false
Write-Host 'System installation gate complete. Tailscale sign-in remains a separate visible authentication step.'

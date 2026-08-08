[CmdletBinding()]
param()

$ErrorActionPreference = 'Stop'
$wsl = & cmd.exe /d /c 'wsl.exe --status 2>&1'
$wslReady = $LASTEXITCODE -eq 0
$docker = Get-Command docker.exe -ErrorAction SilentlyContinue
$tailscale = Get-Command tailscale.exe -ErrorAction SilentlyContinue

[ordered]@{
    wsl_ready = $wslReady
    docker_detected = $null -ne $docker
    tailscale_detected = $null -ne $tailscale
    reboot_pending = $null -ne (Get-ItemProperty `
        'HKLM:\SOFTWARE\Microsoft\Windows\CurrentVersion\WindowsUpdate\Auto Update\RebootRequired' `
        -ErrorAction SilentlyContinue)
    wsl_output = @($wsl | ForEach-Object { ("$_" -replace "`0", '').Trim() } | Where-Object { $_ })
} | ConvertTo-Json -Depth 4

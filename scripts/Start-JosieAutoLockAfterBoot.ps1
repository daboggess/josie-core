[CmdletBinding()]
param(
    [ValidateRange(30, 600)]
    [int]$DelaySeconds = 120
)

$ErrorActionPreference = 'Stop'
Set-StrictMode -Version Latest
$bootTime = (Get-CimInstance Win32_OperatingSystem).LastBootUpTime
$uptime = (Get-Date) - $bootTime

# A later logoff/logon is a human session, not unattended power recovery.
if ($uptime.TotalMinutes -gt 20) { return }

Start-Sleep -Seconds $DelaySeconds
& "$env:WINDIR\System32\rundll32.exe" user32.dll,LockWorkStation

[CmdletBinding()]
param(
    [switch]$AllowWithoutBitLocker
)

$ErrorActionPreference = 'Stop'
Set-StrictMode -Version Latest
$projectRoot = Split-Path -Parent $PSScriptRoot
$autologonPath = 'D:\Josie-Storage\apps\Sysinternals\Autologon\Autologon64.exe'
$lockRunner = Join-Path $PSScriptRoot 'Run-JosieAutoLockHidden.vbs'
$recoveryShortcut = Join-Path ([Environment]::GetFolderPath('Startup')) `
    'Josie Background Services.lnk'
$lockShortcut = Join-Path ([Environment]::GetFolderPath('Startup')) `
    'Josie Automatic Re-Lock.lnk'

$principal = [Security.Principal.WindowsPrincipal]::new(
    [Security.Principal.WindowsIdentity]::GetCurrent()
)
if (-not $principal.IsInRole([Security.Principal.WindowsBuiltInRole]::Administrator)) {
    throw 'Run this attended setup as administrator.'
}
if ((Get-ItemProperty -LiteralPath `
    'HKLM:\SOFTWARE\Microsoft\Windows\CurrentVersion\Policies\System' `
    -Name EnableLUA).EnableLUA -ne 1) {
    throw 'UAC must remain enabled before unattended recovery is configured.'
}
foreach ($required in $autologonPath, $lockRunner, $recoveryShortcut) {
    if (-not (Test-Path -LiteralPath $required)) {
        throw "Required unattended-recovery component is missing: $required"
    }
}
$signature = Get-AuthenticodeSignature -LiteralPath $autologonPath
if ($signature.Status -ne 'Valid' -or
    $signature.SignerCertificate.Subject -notmatch 'Microsoft Corporation') {
    throw 'The staged Microsoft Autologon signature is invalid.'
}

$bitLockerOutput = (& manage-bde.exe -status C: 2>&1) -join "`n"
$bitLockerProtected = $bitLockerOutput -match 'Protection Status:\s+Protection On'
if (-not $bitLockerProtected -and -not $AllowWithoutBitLocker) {
    throw (
        'BitLocker protection on C: was not proven. Resolve disk protection or rerun ' +
        'with -AllowWithoutBitLocker only after accepting the physical-access risk.'
    )
}

# The password is entered only into Microsoft's attended GUI. It is never a
# script parameter, command-line argument, environment variable, file, or log.
$process = Start-Process -FilePath $autologonPath -Verb RunAs -Wait -PassThru
if ($process.ExitCode -ne 0) { throw 'Microsoft Autologon did not exit successfully.' }

$winlogonPath = 'HKLM:\SOFTWARE\Microsoft\Windows NT\CurrentVersion\Winlogon'
$winlogon = Get-ItemProperty -LiteralPath $winlogonPath
$autoAdminProperty = $winlogon.PSObject.Properties['AutoAdminLogon']
$defaultPasswordProperty = $winlogon.PSObject.Properties['DefaultPassword']
if ($null -eq $autoAdminProperty -or [string]$autoAdminProperty.Value -ne '1') {
    throw 'Autologon was not enabled in the Microsoft dialog.'
}
if ($null -ne $defaultPasswordProperty -and
    -not [string]::IsNullOrWhiteSpace([string]$defaultPasswordProperty.Value)) {
    throw 'A plaintext Winlogon password was detected; unattended recovery is rejected.'
}

$shell = New-Object -ComObject WScript.Shell
$shortcut = $shell.CreateShortcut($lockShortcut)
$shortcut.TargetPath = 'C:\Windows\System32\wscript.exe'
$shortcut.Arguments = "//B //NoLogo `"$lockRunner`""
$shortcut.WorkingDirectory = $projectRoot
$shortcut.Description = 'Locks Windows after unattended Josie startup begins.'
$shortcut.Save()

[ordered]@{
    status = 'enabled_pending_power_recovery_test'
    account = "$( $env:USERDOMAIN )\$( $env:USERNAME )"
    password_received_by_josie = $false
    password_on_command_line = $false
    plaintext_winlogon_password = $false
    bitlocker_protection_proven = $bitLockerProtected
    uac_enabled = $true
    automatic_lock_delay_seconds = 120
    autologon_bypass = 'Hold Shift during startup'
    bios_ac_recovery_verified = $false
} | ConvertTo-Json

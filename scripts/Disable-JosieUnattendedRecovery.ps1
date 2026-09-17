[CmdletBinding()]
param()

$ErrorActionPreference = 'Stop'
Set-StrictMode -Version Latest
$autologonPath = 'I:\Josie-Storage\apps\Sysinternals\Autologon\Autologon64.exe'
$lockShortcut = Join-Path ([Environment]::GetFolderPath('Startup')) `
    'Josie Automatic Re-Lock.lnk'

if (-not (Test-Path -LiteralPath $autologonPath)) {
    throw 'The signed Microsoft Autologon utility is missing.'
}
$signature = Get-AuthenticodeSignature -LiteralPath $autologonPath
if ($signature.Status -ne 'Valid' -or
    $signature.SignerCertificate.Subject -notmatch 'Microsoft Corporation') {
    throw 'The Microsoft Autologon signature is invalid.'
}

# Click Disable in the attended Microsoft dialog.
$process = Start-Process -FilePath $autologonPath -Verb RunAs -Wait -PassThru
if ($process.ExitCode -ne 0) { throw 'Microsoft Autologon did not exit successfully.' }
$winlogon = Get-ItemProperty -LiteralPath `
    'HKLM:\SOFTWARE\Microsoft\Windows NT\CurrentVersion\Winlogon'
$autoAdminProperty = $winlogon.PSObject.Properties['AutoAdminLogon']
if ($null -ne $autoAdminProperty -and [string]$autoAdminProperty.Value -eq '1') {
    throw 'Autologon remains enabled; the automatic-lock shortcut was preserved.'
}
if (Test-Path -LiteralPath $lockShortcut) {
    Remove-Item -LiteralPath $lockShortcut -Force
}

[ordered]@{
    status = 'disabled'
    autologon_enabled = $false
    automatic_lock_installed = $false
    background_service_recovery_preserved = $true
} | ConvertTo-Json

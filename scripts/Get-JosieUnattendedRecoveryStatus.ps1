[CmdletBinding()]
param()

$ErrorActionPreference = 'Stop'
Set-StrictMode -Version Latest
$autologonPath = 'I:\Josie-Storage\apps\Sysinternals\Autologon\Autologon64.exe'
$startupRoot = [Environment]::GetFolderPath('Startup')
$winlogon = Get-ItemProperty -LiteralPath `
    'HKLM:\SOFTWARE\Microsoft\Windows NT\CurrentVersion\Winlogon'
$autoAdminProperty = $winlogon.PSObject.Properties['AutoAdminLogon']
$defaultPasswordProperty = $winlogon.PSObject.Properties['DefaultPassword']
$signature = if (Test-Path -LiteralPath $autologonPath) {
    Get-AuthenticodeSignature -LiteralPath $autologonPath
} else {
    $null
}

[ordered]@{
    status = 'read_only'
    autologon_enabled = (
        $null -ne $autoAdminProperty -and [string]$autoAdminProperty.Value -eq '1'
    )
    plaintext_winlogon_password_present = (
        $null -ne $defaultPasswordProperty -and
        -not [string]::IsNullOrWhiteSpace([string]$defaultPasswordProperty.Value)
    )
    microsoft_autologon_staged = ($null -ne $signature -and $signature.Status -eq 'Valid')
    background_recovery_installed = Test-Path -LiteralPath `
        (Join-Path $startupRoot 'Josie Background Services.lnk')
    automatic_lock_installed = Test-Path -LiteralPath `
        (Join-Path $startupRoot 'Josie Automatic Re-Lock.lnk')
    uac_enabled = ((Get-ItemProperty -LiteralPath `
        'HKLM:\SOFTWARE\Microsoft\Windows\CurrentVersion\Policies\System' `
        -Name EnableLUA).EnableLUA -eq 1)
    password_value_returned = $false
    bios_ac_recovery_verified = $false
} | ConvertTo-Json

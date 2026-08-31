[CmdletBinding()]
param()

$ErrorActionPreference = 'Stop'
Set-StrictMode -Version Latest
$projectRoot = Split-Path -Parent $PSScriptRoot
$runnerPath = Join-Path $PSScriptRoot 'Run-JosieAfterSignInHidden.vbs'
$startupRoot = [Environment]::GetFolderPath('Startup')
$shortcutPath = Join-Path $startupRoot 'Josie Background Services.lnk'

if (-not (Test-Path -LiteralPath $runnerPath)) {
    throw 'The hidden Josie startup runner is missing.'
}
$shell = New-Object -ComObject WScript.Shell
$shortcut = $shell.CreateShortcut($shortcutPath)
$shortcut.TargetPath = 'C:\Windows\System32\wscript.exe'
$shortcut.Arguments = "//B //NoLogo `"$runnerPath`""
$shortcut.WorkingDirectory = $projectRoot
$shortcut.Description = 'Starts Josie services silently after Dustin signs into Windows.'
$shortcut.Save()

[ordered]@{
    status = 'installed'
    trigger = 'current_user_interactive_sign_in'
    autologin_enabled = $false
    hidden_runner = $true
    administrator_required = $false
} | ConvertTo-Json

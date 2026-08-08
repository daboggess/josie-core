[CmdletBinding(SupportsShouldProcess, ConfirmImpact = 'High')]
param()

$ErrorActionPreference = 'Stop'
Set-StrictMode -Version Latest
$ruleName = 'Josie-Ollama-Docker-Only'
$ollamaPath = 'D:\Josie-Storage\apps\Ollama\0.32.5\ollama.exe'
$dockerSources = @('172.18.0.0/16', '172.31.0.0/20', '192.168.65.0/24')
$principal = [Security.Principal.WindowsPrincipal]::new(
    [Security.Principal.WindowsIdentity]::GetCurrent()
)
if (-not $principal.IsInRole([Security.Principal.WindowsBuiltInRole]::Administrator)) {
    throw 'Administrator approval is required for the firewall rule.'
}
if (-not (Test-Path -LiteralPath $ollamaPath)) { throw 'The verified Ollama runtime is unavailable.' }

$profiles = @(Get-NetFirewallProfile -PolicyStore ActiveStore)
if ($profiles.Count -ne 3 -or ($profiles | Where-Object DefaultInboundAction -ne Block)) {
    throw 'All Windows Firewall profiles must retain default inbound blocking.'
}

$broadRules = foreach ($rule in Get-NetFirewallRule -PolicyStore ActiveStore -ErrorAction Stop |
    Where-Object { $_.Enabled -eq 'True' -and $_.Direction -eq 'Inbound' -and $_.Action -eq 'Allow' }) {
    $application = $rule | Get-NetFirewallApplicationFilter
    $port = $rule | Get-NetFirewallPortFilter
    $address = $rule | Get-NetFirewallAddressFilter
    if (($application.Program -like '*ollama.exe' -or $port.LocalPort -contains '11434') -and
        ($address.RemoteAddress -contains 'Any')) {
        $rule.DisplayName
    }
}
if ($broadRules) { throw "Broad Ollama firewall access already exists: $($broadRules -join ', ')" }

if ($PSCmdlet.ShouldProcess($ruleName, 'Create an inbound allow rule limited to Docker/WSL source networks')) {
    $existing = Get-NetFirewallRule -Name $ruleName -ErrorAction SilentlyContinue
    if ($existing) { Remove-NetFirewallRule -Name $ruleName }
    New-NetFirewallRule -Name $ruleName -DisplayName 'Josie Ollama - Docker only' `
        -Direction Inbound -Action Allow -Enabled True -Profile Any -Protocol TCP `
        -LocalPort 11434 -Program $ollamaPath -RemoteAddress $dockerSources `
        -EdgeTraversalPolicy Block | Out-Null
}

$created = Get-NetFirewallRule -Name $ruleName -ErrorAction Stop
$addressFilter = $created | Get-NetFirewallAddressFilter
[ordered]@{
    status = 'ready'
    rule = $created.DisplayName
    action = [string]$created.Action
    direction = [string]$created.Direction
    remote_addresses = @($addressFilter.RemoteAddress)
    lan_allowed = $false
    tailscale_allowed = $false
} | ConvertTo-Json -Depth 3

[CmdletBinding(SupportsShouldProcess, ConfirmImpact = 'High')]
param()

$ErrorActionPreference = 'Stop'
Set-StrictMode -Version Latest
$ruleName = 'Josie-Ollama-Docker-Only'
$ollamaPath = 'I:\Josie-Storage\apps\Ollama\0.32.5\ollama.exe'
$dockerSources = @('172.18.0.0/16', '172.19.0.0/16', '172.31.0.0/20', '192.168.65.0/24')
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

$broadRules = @(foreach ($rule in Get-NetFirewallRule -PolicyStore PersistentStore -ErrorAction Stop |
    Where-Object { $_.Enabled -eq 'True' -and $_.Direction -eq 'Inbound' -and $_.Action -eq 'Allow' }) {
    $application = $rule | Get-NetFirewallApplicationFilter
    $port = $rule | Get-NetFirewallPortFilter
    $address = $rule | Get-NetFirewallAddressFilter
    if ($rule.Name -ne $ruleName -and
        ($application.Program -like '*ollama.exe' -or $port.LocalPort -contains '11434') -and
        ($address.RemoteAddress -contains 'Any')) {
        $rule
    }
})

if ($PSCmdlet.ShouldProcess($ruleName, 'Create an inbound allow rule limited to Docker/WSL source networks')) {
    $existing = Get-NetFirewallRule -Name $ruleName -PolicyStore PersistentStore `
        -ErrorAction SilentlyContinue
    if ($existing) {
        Set-NetFirewallRule -Name $ruleName -PolicyStore PersistentStore `
            -Direction Inbound -Action Allow `
            -Enabled True -Profile Any -EdgeTraversalPolicy Block | Out-Null
        $existing | Get-NetFirewallApplicationFilter | Set-NetFirewallApplicationFilter `
            -Program $ollamaPath | Out-Null
        $existing | Get-NetFirewallPortFilter | Set-NetFirewallPortFilter `
            -Protocol TCP -LocalPort 11434 | Out-Null
        $existing | Get-NetFirewallAddressFilter | Set-NetFirewallAddressFilter `
            -RemoteAddress $dockerSources | Out-Null
    }
    else {
        New-NetFirewallRule -Name $ruleName -PolicyStore PersistentStore `
            -DisplayName 'Josie Ollama - Docker only' `
            -Direction Inbound -Action Allow -Enabled True -Profile Any -Protocol TCP `
            -LocalPort 11434 -Program $ollamaPath -RemoteAddress $dockerSources `
            -EdgeTraversalPolicy Block | Out-Null
    }
    foreach ($broadRule in $broadRules) {
        Set-NetFirewallRule -Name $broadRule.Name -PolicyStore PersistentStore `
            -Enabled False | Out-Null
    }
}

$created = Get-NetFirewallRule -Name $ruleName -PolicyStore ActiveStore -ErrorAction Stop
$addressFilter = $created | Get-NetFirewallAddressFilter
$remainingBroadRules = @(foreach ($rule in
    Get-NetFirewallRule -PolicyStore ActiveStore -ErrorAction Stop |
    Where-Object { $_.Enabled -eq 'True' -and $_.Direction -eq 'Inbound' -and $_.Action -eq 'Allow' }) {
    $application = $rule | Get-NetFirewallApplicationFilter
    $port = $rule | Get-NetFirewallPortFilter
    $address = $rule | Get-NetFirewallAddressFilter
    if ($rule.Name -ne $ruleName -and
        ($application.Program -like '*ollama.exe' -or $port.LocalPort -contains '11434') -and
        ($address.RemoteAddress -contains 'Any')) {
        $rule.Name
    }
})
if ($remainingBroadRules.Count -ne 0) {
    throw 'One or more broad Ollama inbound rules remain enabled.'
}
[ordered]@{
    status = 'ready'
    rule = $created.DisplayName
    action = [string]$created.Action
    direction = [string]$created.Direction
    remote_addresses = @($addressFilter.RemoteAddress)
    broad_rules_disabled = $broadRules.Count
    firewall_rules_deleted = 0
    lan_allowed = $false
    tailscale_allowed = $false
} | ConvertTo-Json -Depth 3

[CmdletBinding()]
param(
    [Parameter(Mandatory = $true)]
    [ValidatePattern('^https://app\.slack\.com/client/[^/]+/[^/?#]+')]
    [string]$SlackChannelUrl,

    [Parameter(Mandatory = $true)]
    [ValidatePattern('^https://messages\.google\.com/web/u/0/conversations/[^/?#]+')]
    [string]$GoogleMessagesConversationUrl,

    [Parameter(Mandatory = $true)]
    [ValidateLength(1, 160)]
    [string]$WhatsAppConversationHeading
)

$ErrorActionPreference = 'Stop'
Set-StrictMode -Version Latest
$projectRoot = Split-Path -Parent $PSScriptRoot
$privateRoot = Join-Path $projectRoot 'data\private'
$sourceConfigPath = Join-Path $privateRoot 'prayer-sources.json'
$tokenPath = Join-Path $privateRoot 'prayer-bridge.token'
$extensionConfigPath = Join-Path $projectRoot 'browser-extension\prayer-capture\config.js'
$installationMarkerPath = Join-Path $privateRoot 'prayer-extension-installed.json'

function Get-Sha256([string]$Value) {
    $bytes = [System.Text.Encoding]::UTF8.GetBytes($Value)
    $hash = [System.Security.Cryptography.SHA256]::HashData($bytes)
    return [Convert]::ToHexString($hash).ToLowerInvariant()
}

function Get-CanonicalSlackLocator([string]$Value) {
    $uri = [Uri]$Value
    $parts = $uri.AbsolutePath.Trim('/').Split('/')
    if ($uri.Scheme -ne 'https' -or $uri.Host -ne 'app.slack.com' -or
        $parts.Count -lt 3 -or $parts[0] -ne 'client') {
        throw 'Slack source must be one exact HTTPS channel URL.'
    }
    return "https://app.slack.com/client/$($parts[1])/$($parts[2])"
}

function Get-CanonicalMessagesLocator([string]$Value) {
    $uri = [Uri]$Value
    $parts = $uri.AbsolutePath.Trim('/').Split('/')
    if ($uri.Scheme -ne 'https' -or $uri.Host -ne 'messages.google.com' -or
        $parts.Count -lt 5 -or $parts[0] -ne 'web' -or $parts[1] -ne 'u' -or
        $parts[2] -ne '0' -or $parts[3] -ne 'conversations') {
        throw 'Google Messages source must be one exact HTTPS conversation URL.'
    }
    return "https://messages.google.com/web/u/0/conversations/$($parts[4])"
}

New-Item -ItemType Directory -Force -Path $privateRoot | Out-Null
if (Test-Path -LiteralPath $installationMarkerPath) {
    Remove-Item -LiteralPath $installationMarkerPath -Force
}
$slackLocator = Get-CanonicalSlackLocator $SlackChannelUrl
$messagesLocator = Get-CanonicalMessagesLocator $GoogleMessagesConversationUrl
$whatsAppLocator = "https://web.whatsapp.com/|$($WhatsAppConversationHeading.Trim())"
$verifiedAt = [DateTimeOffset]::UtcNow.ToString('o')

$configuration = [ordered]@{
    schema_version = 1
    sources = @(
        [ordered]@{
            source_context = 'slack_prayer_team'
            hostname = 'app.slack.com'
            locator_sha256 = Get-Sha256 $slackLocator
            verified_at = $verifiedAt
            enabled = $true
        },
        [ordered]@{
            source_context = 'google_messages_giant_killers'
            hostname = 'messages.google.com'
            locator_sha256 = Get-Sha256 $messagesLocator
            verified_at = $verifiedAt
            enabled = $true
        },
        [ordered]@{
            source_context = 'whatsapp_sunday'
            hostname = 'web.whatsapp.com'
            locator_sha256 = Get-Sha256 $whatsAppLocator
            verified_at = $verifiedAt
            enabled = $true
        }
    )
    controls = [ordered]@{
        active_selection_only = $true
        read_only = $true
        cloud_processing = $false
        sending = $false
        cross_posting = $false
    }
}
[System.IO.File]::WriteAllText(
    $sourceConfigPath,
    (ConvertTo-Json -InputObject $configuration -Depth 6),
    [System.Text.UTF8Encoding]::new($false)
)

if (-not (Test-Path -LiteralPath $tokenPath)) {
    $tokenBytes = New-Object byte[] 32
    [System.Security.Cryptography.RandomNumberGenerator]::Fill($tokenBytes)
    $token = [Convert]::ToBase64String($tokenBytes).TrimEnd('=').Replace('+', '-').Replace('/', '_')
    [System.IO.File]::WriteAllText(
        $tokenPath, $token, [System.Text.UTF8Encoding]::new($false)
    )
}
$token = [System.IO.File]::ReadAllText($tokenPath, [System.Text.Encoding]::UTF8).Trim()
if ($token.Length -lt 32) { throw 'The local prayer bridge credential is invalid.' }
$extensionConfiguration = (
    'globalThis.JOSIE_PRAYER_CONFIG = Object.freeze({bridgeUrl: "http://127.0.0.1:8788", token: "' +
    $token + '"});' + [Environment]::NewLine
)
[System.IO.File]::WriteAllText(
    $extensionConfigPath,
    $extensionConfiguration,
    [System.Text.UTF8Encoding]::new($false)
)

$identity = [System.Security.Principal.WindowsIdentity]::GetCurrent().Name
foreach ($path in $sourceConfigPath, $tokenPath, $extensionConfigPath) {
    & icacls.exe $path /inheritance:r /grant:r "${identity}:(F)" 'SYSTEM:(F)' | Out-Null
    if ($LASTEXITCODE -ne 0) { throw "Local prayer bridge file permissions could not be restricted." }
}
$token = $null

[ordered]@{
    status = 'initialized'
    approved_source_count = 3
    source_identifiers_persisted_in_git = $false
    active_selection_only = $true
    browser_scanning_enabled = $false
    cloud_processing_enabled = $false
    sending_enabled = $false
} | ConvertTo-Json

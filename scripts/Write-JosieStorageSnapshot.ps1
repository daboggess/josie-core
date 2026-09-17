[CmdletBinding()]
param(
    [string]$Destination
)

$ErrorActionPreference = 'Stop'
Set-StrictMode -Version Latest

$projectRoot = Split-Path -Parent $PSScriptRoot
if (-not $Destination) {
    $storageRoot = if ($env:JOSIE_EXTERNAL_STORAGE) {
        $env:JOSIE_EXTERNAL_STORAGE
    } elseif ($env:JOSIE_STORAGE) {
        $env:JOSIE_STORAGE
    } else {
        $envFile = Join-Path $projectRoot '.env'
        if (Test-Path -LiteralPath $envFile) {
            $line = Get-Content -LiteralPath $envFile | Where-Object {
                $_ -match '^\s*JOSIE_EXTERNAL_STORAGE\s*=\s*(.+)$' -or
                $_ -match '^\s*JOSIE_STORAGE\s*=\s*(.+)$'
            } | Select-Object -First 1
            if ($line -match '=\s*(.+)$') {
                $Matches[1].Trim().Trim('"').Trim("'")
            }
        }
    }
    if (-not $storageRoot) {
        $storageRoot = 'I:\Josie-Storage'
    }
    $Destination = Join-Path $storageRoot 'staging\storage-status.json'
}

$destinationDir = Split-Path -Parent $Destination
if (-not (Test-Path -LiteralPath $destinationDir)) {
    New-Item -ItemType Directory -Path $destinationDir -Force | Out-Null
}

$sysDrive = [IO.Path]::GetPathRoot($env:SystemDrive + '\')
$projDrive = [IO.Path]::GetPathRoot($projectRoot)
$destDrive = [IO.Path]::GetPathRoot($Destination)

$driveRoots = @($sysDrive, $projDrive, $destDrive) |
    Where-Object { -not [string]::IsNullOrWhiteSpace($_) } |
    ForEach-Object { $_.TrimEnd('\') + '\' } |
    Select-Object -Unique

$drives = foreach ($root in $driveRoots) {
    if ([IO.Directory]::Exists($root)) {
        $drive = [IO.DriveInfo]::new($root)
        if ($drive.IsReady) {
            [ordered]@{
                drive = $drive.Name.ToUpper()
                total_gb = [math]::Round($drive.TotalSize / 1GB, 1)
                free_gb = [math]::Round($drive.AvailableFreeSpace / 1GB, 1)
            }
        }
    }
}

$cDriveEntry = $drives | Where-Object { $_.drive -eq ($sysDrive.TrimEnd('\') + '\').ToUpper() }
$cFree = if ($cDriveEntry) { $cDriveEntry.free_gb } else { 0 }
$status = if ($cFree -lt 15) { 'critical' } elseif ($cFree -lt 20) { 'warning' } else { 'ok' }
$snapshot = [ordered]@{
    schema_version = 1
    created_at = [DateTimeOffset]::Now.ToString('o')
    status = $status
    warning_below_gb = 20
    critical_below_gb = 15
    drives = @($drives)
    cloud_activity = $false
    deletion_performed = $false
}
$temporary = "$destination.tmp"
$snapshot | ConvertTo-Json -Depth 4 | Set-Content -LiteralPath $temporary -Encoding UTF8
Move-Item -Force -LiteralPath $temporary -Destination $destination
$snapshot | ConvertTo-Json -Depth 4

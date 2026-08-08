[CmdletBinding()]
param()

$ErrorActionPreference = 'Stop'
Set-StrictMode -Version Latest
$destination = 'D:\Josie-Storage\staging\storage-status.json'
$drives = foreach ($root in 'C:\','D:\') {
    $drive = [IO.DriveInfo]::new($root)
    [ordered]@{
        drive = $drive.Name
        total_gb = [math]::Round($drive.TotalSize / 1GB, 1)
        free_gb = [math]::Round($drive.AvailableFreeSpace / 1GB, 1)
    }
}
$cFree = ($drives | Where-Object drive -eq 'C:\').free_gb
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

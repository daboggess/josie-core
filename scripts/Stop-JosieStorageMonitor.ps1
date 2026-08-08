[CmdletBinding()]
param()

$ErrorActionPreference = 'Stop'
Set-StrictMode -Version Latest
try {
    $stopEvent = [Threading.EventWaitHandle]::OpenExisting('Local\JosieStorageMonitorStop')
}
catch [Threading.WaitHandleCannotBeOpenedException] {
    return
}
try {
    $stopEvent.Set() | Out-Null
}
finally {
    $stopEvent.Dispose()
}

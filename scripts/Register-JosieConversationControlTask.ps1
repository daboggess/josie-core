[CmdletBinding()]
param()

$ErrorActionPreference = 'Stop'
Set-StrictMode -Version Latest
$taskPath = '\Josie\'
$taskName = 'Josie Conversation Control'
$identity = [System.Security.Principal.WindowsIdentity]::GetCurrent().Name
$execute = 'C:\Windows\System32\wscript.exe'
$arguments = '//B //NoLogo "C:\Josie\scripts\Run-JosieConversationControlHidden.vbs"'
$workingDirectory = 'C:\Josie'

$existing = Get-ScheduledTask -TaskPath $taskPath -TaskName $taskName `
    -ErrorAction SilentlyContinue
if ($null -ne $existing) {
    $action = @($existing.Actions)[0]
    if (
        $action.Execute -ne $execute -or
        $action.Arguments -ne $arguments -or
        $action.WorkingDirectory -ne $workingDirectory
    ) {
        throw 'The existing conversation-control task does not match the verified definition.'
    }
    $status = 'verified_existing'
}
else {
    $action = New-ScheduledTaskAction -Execute $execute -Argument $arguments `
        -WorkingDirectory $workingDirectory
    $trigger = New-ScheduledTaskTrigger -AtLogOn -User $identity
    $trigger.Delay = 'PT15S'
    $principal = New-ScheduledTaskPrincipal -UserId $identity `
        -LogonType Interactive -RunLevel Limited
    $settings = New-ScheduledTaskSettingsSet -AllowStartIfOnBatteries `
        -DontStopIfGoingOnBatteries -Hidden -StartWhenAvailable `
        -MultipleInstances IgnoreNew -RestartCount 3 `
        -RestartInterval (New-TimeSpan -Minutes 1) `
        -ExecutionTimeLimit (New-TimeSpan -Minutes 2)
    Register-ScheduledTask -TaskPath $taskPath -TaskName $taskName `
        -Description 'Starts Josie local conversation control silently at sign-in on 127.0.0.1:8790.' `
        -Action $action -Trigger $trigger -Principal $principal -Settings $settings |
        Out-Null
    $status = 'registered'
}

Start-ScheduledTask -TaskPath $taskPath -TaskName $taskName
Start-Sleep -Seconds 3
$info = Get-ScheduledTaskInfo -TaskPath $taskPath -TaskName $taskName
$task = Get-ScheduledTask -TaskPath $taskPath -TaskName $taskName
$health = Invoke-RestMethod -Uri 'http://127.0.0.1:8790/health' -TimeoutSec 3

[ordered]@{
    status = $status
    task_name = $task.TaskName
    hidden = $task.Settings.Hidden
    last_result = $info.LastTaskResult
    service_status = $health.status
    binding = $health.binding
} | ConvertTo-Json

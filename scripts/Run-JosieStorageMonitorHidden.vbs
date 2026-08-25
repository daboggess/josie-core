Option Explicit

Dim shell, command, exitCode
Set shell = CreateObject("WScript.Shell")

command = """C:\Windows\System32\WindowsPowerShell\v1.0\powershell.exe""" & _
    " -NoProfile -ExecutionPolicy Bypass -Command ""& 'C:\Josie\scripts\Start-JosieStorageMonitor.ps1' *>> 'C:\Josie\logs\storage-monitor-background.log'"""

exitCode = shell.Run(command, 0, True)
WScript.Quit exitCode

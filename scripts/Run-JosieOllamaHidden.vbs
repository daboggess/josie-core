Option Explicit

Dim shell, command, exitCode
Set shell = CreateObject("WScript.Shell")

command = """C:\Windows\System32\WindowsPowerShell\v1.0\powershell.exe""" & _
    " -NoProfile -ExecutionPolicy Bypass -File ""C:\Josie\scripts\Run-JosieOllamaBackground.ps1"""

exitCode = shell.Run(command, 0, True)
WScript.Quit exitCode

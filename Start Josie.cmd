@echo off
cd /d C:\Josie
start "Josie Local Model" powershell.exe -NoProfile -WindowStyle Hidden -ExecutionPolicy Bypass -File "C:\Josie\scripts\Ensure-JosieOllama.ps1"
start "Josie Storage Monitor" powershell.exe -NoProfile -WindowStyle Hidden -ExecutionPolicy Bypass -File "C:\Josie\scripts\Start-JosieStorageMonitor.ps1"
start "Josie 1.0" ".venv\Scripts\pythonw.exe" "core.py" gui

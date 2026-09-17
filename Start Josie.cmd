@echo off
cd /d D:\Josie
start "Josie Local Model" powershell.exe -NoProfile -WindowStyle Hidden -ExecutionPolicy Bypass -File "D:\Josie\scripts\Ensure-JosieOllama.ps1"
start "Josie Storage Monitor" powershell.exe -NoProfile -WindowStyle Hidden -ExecutionPolicy Bypass -File "D:\Josie\scripts\Start-JosieStorageMonitor.ps1"
start "Josie Prayer Bridge" powershell.exe -NoProfile -WindowStyle Hidden -ExecutionPolicy Bypass -File "D:\Josie\scripts\Start-JosiePrayerBridge.ps1"
start "Josie 1.0" ".venv\Scripts\pythonw.exe" "core.py" gui

# Controlled Reboot Acceptance — 2026-08-31

Status: `PASSED`

Josie completed a controlled Windows reboot with Windows autologin disabled.
After Dustin signed in normally, the hidden current-user recovery launcher
restored and verified the local service stack without opening a terminal
window.

## Verified result

- Boot time: 2026-08-31 18:20:37 America/New_York
- Full recovery proof: 2026-08-31 18:25:23 America/New_York
- Boot-to-healthy duration: approximately 4.8 minutes
- Docker Desktop: ready
- Open WebUI: healthy; local health endpoint returned HTTP 200
- n8n: healthy; local health endpoint returned HTTP 200
- proposal server: healthy
- browser worker: healthy
- native Ollama: healthy, version 0.32.5
- Open WebUI container to native Ollama: verified
- Tailscale service: running
- visible PowerShell, Command Prompt, or Windows Terminal windows: zero
- Windows autologin: disabled

## Firewall boundary

The two Windows-created broad Ollama inbound rules remain present but disabled.
No firewall rule was deleted. The active Josie rule permits TCP port 11434 only
from the verified Docker/Desktop network ranges used by this installation:

- 172.18.0.0/16
- 172.19.0.0/16
- 192.168.65.0/24

LAN and Tailscale clients are not granted direct Ollama access.

## Recovery behavior

The recovery launcher starts after an interactive Windows sign-in. It does not
enable or require autologin. It starts native Ollama independently, tolerates
Docker Desktop changing engine pipes during startup, waits for three consecutive
Docker readiness checks, starts only the four exact known Josie containers when
needed, and writes its result to:

`D:\Josie-Storage\status\startup-recovery.json`

The first retest exposed Docker/Ollama startup timing races. Those races were
repaired before this passing run; the earlier failed run is not treated as
acceptance evidence.

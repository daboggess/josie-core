# Attended Windows system gate

This is the only grouped setup phase that must not run while Dustin is away.
It preserves UAC and does not enable automatic login, change the firewall,
expose a port, accept a cloud charge, or sign into an account automatically.

## Before starting

- Be physically present or controlling Josie through a trusted interactive session.
- Close important work because WSL enablement may require one reboot.
- Use only the already verified Tailscale installer and a Docker Desktop installer
  downloaded from Docker's official Windows page.
- The script independently verifies both Authenticode publishers before changes.

## Run

Open PowerShell as Administrator and run the script with the two installer paths.
PowerShell will show one high-impact confirmation. If WSL requires a reboot, the
script records its state and stops. After restart, repeat with `-ResumeAfterReboot`.

Because Josie's current PowerShell policy blocks local unsigned scripts, invoke
this one reviewed script with `powershell.exe -NoProfile -ExecutionPolicy Bypass
-File C:\Josie\scripts\Invoke-JosieSystemGate.ps1 ...`. This bypass applies only
to that PowerShell process and does not alter the machine or user execution policy.

The `.wslconfig` template limits WSL to 8 GB RAM, four logical processors, and a
2 GB swap file. An existing `.wslconfig` is preserved rather than overwritten.

## Explicit exclusions

- No Linux distribution or local model is installed.
- No Docker socket is shared with containers.
- No service is exposed beyond loopback.
- Tailscale authentication remains visible and human-controlled.
- The script never calls `Set-ExecutionPolicy` or changes UAC.
- Docker image downloads and service activation occur in the later service gate.

# Josie operator and recovery runbook

For the Windows deployment audited 2026-08-28. Commands are PowerShell unless labeled otherwise. Start with observation. **Restart/backup commands below are maintenance actions; the doctor never executes them.** See [inventory](CURRENT_STATE.md) and [backup checklist](BACKUP_CHECKLIST.md).

## Normal use and first check

Desktop: http://localhost:3000. Phone: connect Tailscale, open https://refurb.tail0ab4d2.ts.net, sign in, select **Josie** (`josie-local:1.0`). Ordinary chat is local. “Ask Codex …” / “Ask Gemini …” uses the optional consultant. Do not use a delegation request as a health check: it can edit files.

```powershell
Set-Location C:/Josie
& 'C:/Program Files/Git/bin/bash.exe' C:/Josie/josie-doctor.sh
```

Or use existing Windows Python directly:

```powershell
& C:/Josie/.venv/Scripts/python.exe -B C:/Josie/scripts/josie_doctor.py
& C:/Josie/.venv/Scripts/python.exe -B C:/Josie/scripts/josie_doctor.py --json
```

PASS = check succeeded; WARN = limitation/optional absence/attention; FAIL = critical check failed. Exit code 1 means a FAIL. Missing NVIDIA and Windows' lack of Unix load average are warnings. A restricted shell may not see Docker/CIM: rerun in a normal host terminal.

Doctor uses fixed read-only commands and allowlisted loopback GETs, disables redirects/proxies, withholds raw error/log text, and performs no inference, consultant call, restart or repair. Paths/IPs still identify this machine; review output before public sharing.

## After reboot

Tailscale starts at boot. Josie tasks run **after Dustin signs in**, when D: must be mounted. Docker Desktop currently needs **manual launch**.

```powershell
Test-Path D:/Josie-Storage/models/ollama
Get-ScheduledTask -TaskPath '\Josie\' | Select-Object TaskName,State
Get-Service Tailscale
Invoke-RestMethod http://127.0.0.1:11434/api/version -TimeoutSec 5
Invoke-RestMethod http://127.0.0.1:8790/health -TimeoutSec 5
docker.exe version
docker.exe ps -a --format 'table {{.Names}}\t{{.Status}}\t{{.Ports}}'
```

If Docker is not running, launch the existing application, not an installer:

```powershell
if (-not (Get-Process -Name 'Docker Desktop' -ErrorAction SilentlyContinue)) {
    Start-Process -FilePath 'C:/Users/dusti/AppData/Local/Programs/DockerDesktop/Docker Desktop.exe' -WindowStyle Hidden
}
docker.exe info --format '{{.ServerVersion}}'
```

Allow engine startup, then rerun the last command. Do not repeatedly launch Docker. Existing unless-stopped containers should start when the engine does. If a diagnosed existing container remains stopped:

```powershell
docker.exe start josie-open-webui-1
```

Other exact names: josie-n8n-1, josie-browser-worker-1, josie-proposal-server-1. Start separately only when needed. This does not recreate containers or download images. Read-only Compose inventory:

```powershell
docker.exe compose ls
docker.exe compose --project-name josie --env-file C:/Josie/deploy/.env.services -f C:/Josie/deploy/compose.yaml --profile proposal-interface ps -a
```

If a container or named volume is **missing**, stop and inspect backups. Blind recreation can present an empty new database as lost history. Do not initialize replacement volumes over missing evidence.

## WebUI does not load

```powershell
Invoke-RestMethod http://127.0.0.1:3000/health -TimeoutSec 5
docker.exe inspect --format '{{.State.Status}} {{if .State.Health}}{{.State.Health.Status}}{{end}} {{.Config.Image}}' josie-open-webui-1
docker.exe volume inspect josie_open_webui_data --format '{{.Name}} {{.Mountpoint}}'
docker.exe logs --tail 80 josie-open-webui-1
```

Logs can contain private requests; inspect locally and redact before sharing. If localhost works but phone fails, check Tailscale. If WebUI loads but local answers fail, check Ollama. If ordinary chat works but explicit tools fail, check :8790 and the attached filter/tool records; do not enable Summit.

If Docker is not on PATH, use the existing binary:

```powershell
& 'C:/Users/dusti/AppData/Local/Programs/DockerDesktop/resources/bin/docker.exe' ps
```

Do not print full Docker environment or expanded Compose configuration: secrets may be included.

## Ollama and direct model testing

Read-only checks:

```powershell
& 'D:/Josie-Storage/apps/Ollama/0.32.5/ollama.exe' --version
& 'D:/Josie-Storage/apps/Ollama/0.32.5/ollama.exe' list
& 'D:/Josie-Storage/apps/Ollama/0.32.5/ollama.exe' ps
Invoke-RestMethod http://127.0.0.1:11434/api/version -TimeoutSec 5
(Invoke-RestMethod http://127.0.0.1:11434/api/tags -TimeoutSec 5).models |
    Select-Object name,size,digest
```

No loaded model after five idle minutes is normal. The server can be healthy without a resident model.

For a direct test without WebUI, first confirm no chat/job is active, then opt into the one bounded local benchmark:

```powershell
Set-Location C:/Josie
.venv/Scripts/python.exe -B scripts/measure_pre_gpu.py --run
```

Without --run, no inference occurs. The script refuses if a model is already resident; wait for normal expiry instead of evicting someone's model. It never downloads a model, calls a cloud provider or saves chat history. Use the same script after the GPU upgrade.

If Ollama is stopped and D: is ready, this existing readiness helper starts it:

```powershell
& C:/Josie/scripts/Ensure-JosieOllama.ps1
```

That is a start action, not a read-only check. Avoid repeatedly using Start-JosieOllama.ps1 directly; it is the lower-level launcher, not the readiness guard.

## Tailscale, addresses and listening ports

```powershell
& 'C:/Program Files/Tailscale/tailscale.exe' version
& 'C:/Program Files/Tailscale/tailscale.exe' status
& 'C:/Program Files/Tailscale/tailscale.exe' ip -4
& 'C:/Program Files/Tailscale/tailscale.exe' serve status
Get-NetIPAddress -AddressFamily IPv4 |
    Select-Object InterfaceAlias,IPAddress,PrefixLength
Get-NetTCPConnection -State Listen |
    Where-Object LocalPort -in 3000,11434,8790,5678,3010,8788,443 |
    Select-Object LocalAddress,LocalPort,OwningProcess
```

Serve should show tailnet-only WebUI → 127.0.0.1:3000 and n8n → 127.0.0.1:5678. An online Tailscale service does not prove healthy upstream containers. Do not reset Serve, enable Funnel, log out, publish ports or disable the firewall as troubleshooting shortcuts.

To identify one observed PID (replace 12345):

```powershell
Get-CimInstance Win32_Process -Filter 'ProcessId=12345' |
    Select-Object ProcessId,Name,ExecutablePath
```

Avoid broad process-command-line/environment dumps. Ollama's wildcard bind and broad firewall rules are documented risks for separate review.

## RAM, disk, uptime and logs

```powershell
Get-CimInstance Win32_OperatingSystem |
    Select-Object Caption,Version,LastBootUpTime,TotalVisibleMemorySize,FreePhysicalMemory
Get-CimInstance Win32_Processor |
    Select-Object Name,NumberOfCores,NumberOfLogicalProcessors,LoadPercentage
Get-CimInstance Win32_LogicalDisk -Filter 'DriveType=3' |
    Select-Object DeviceID,Size,FreeSpace
Get-CimInstance Win32_PageFileUsage |
    Select-Object Name,AllocatedBaseSize,CurrentUsage,PeakUsage
Get-ChildItem C:/Josie/logs -File | Select-Object Name,Length,LastWriteTime
Get-Content C:/Josie/logs/conversation-control-background.log -Tail 50
Get-Content C:/Josie/logs/ollama-background.log -Tail 50
docker.exe logs --tail 60 josie-n8n-1
```

OS memory values are KiB; pagefile values are MiB. Windows has no native Unix load average. Task Scheduler Operational history and Docker Desktop diagnostics help with startup failures. Logs may be stale: correlate timestamps with current health. Do not infer a current GPU failure from an old matching log line.

## Targeted restarts — maintenance window only

Save work; confirm no active chat, consultant, backup, maintenance or delegation. Check UI/receipts and C:/Josie/.git/josie-delegate.lock. An absent lock is not universal proof of inactivity; never delete one just to proceed.

**WebUI:** restart only the named existing container. Connections drop; volume remains.

```powershell
docker.exe restart josie-open-webui-1
Invoke-RestMethod http://127.0.0.1:3000/health -TimeoutSec 5
```

Allow startup before retrying health. Optional services can be individually restarted by their exact existing container names after diagnosis.

**Conversation control:** the existing stop helper validates the stored PID command. If it reports missing/stale PID while :8790 is still alive, inspect the actual process instead of killing Python broadly.

```powershell
& C:/Josie/scripts/Stop-JosieConversationControl.ps1
Start-ScheduledTask -TaskPath '\Josie\' -TaskName 'Josie Conversation Control'
Invoke-RestMethod http://127.0.0.1:8790/health -TimeoutSec 5
```

The existing start helper preserves/creates the token and restricts its ACL; it is not a read-only action.

**Ollama:** after confirming no active inference, verify the exact listener executable before stopping it. Any failed guard means stop and investigate.

```powershell
$ollamaListeners = @(Get-NetTCPConnection -State Listen -LocalPort 11434 -ErrorAction Stop)
$ollamaIds = @($ollamaListeners.OwningProcess | Sort-Object -Unique)
if ($ollamaIds.Count -ne 1) { throw 'Expected one Ollama owner; investigate.' }
$ollamaProcess = Get-CimInstance Win32_Process -Filter ("ProcessId=" + $ollamaIds[0])
if ($ollamaProcess.ExecutablePath -ine 'D:\Josie-Storage\apps\Ollama\0.32.5\ollama.exe') {
    throw 'Unexpected executable; no process stopped.'
}
Stop-Process -Id $ollamaIds[0]
& C:/Josie/scripts/Ensure-JosieOllama.ps1
```

**Storage monitor:** do not disable backups or interrupt one in progress. The cooperative stop event ends the loop; wait until its task is no longer Running before restarting.

```powershell
& C:/Josie/scripts/Stop-JosieStorageMonitor.ps1
Get-ScheduledTask -TaskPath '\Josie\' -TaskName 'Josie Storage Monitor'
```

Only after it has stopped:

```powershell
Start-ScheduledTask -TaskPath '\Josie\' -TaskName 'Josie Storage Monitor'
```

Its next start may recreate today's daily backup.

**Prayer bridge:** current scheduled task directly owns its Python process. End it only when no capture is active:

```powershell
Stop-ScheduledTask -TaskPath '\Josie\' -TaskName 'Josie Prayer Bridge'
Get-NetTCPConnection -State Listen -LocalPort 8788 -ErrorAction SilentlyContinue
```

If a listener remains, inspect its owner before proceeding. Once stopped:

```powershell
Start-ScheduledTask -TaskPath '\Josie\' -TaskName 'Josie Prayer Bridge'
Invoke-RestMethod http://127.0.0.1:8788/health -TimeoutSec 5
```

**Tailscale:** if status diagnosis requires a restart, use an elevated **local console**; remote access drops.

```powershell
Restart-Service -Name Tailscale
& 'C:/Program Files/Tailscale/tailscale.exe' status
```

Do not restart all WSL/Docker for a single application failure without diagnosing the engine first.

## Git, tests and data recovery

```powershell
Set-Location C:/Josie
git status --short --branch
git diff --stat
git log -5 --oneline
git tag --list
.venv/Scripts/python.exe -B -m unittest discover -s tests -v
```

Tests use fixtures and may bind test-only loopback servers. They are not identical to the read-only doctor. Do not run write-capable acceptance jobs just to test health.

Failed reboot recovery order: D: and login → native APIs → Docker engine → existing named volumes → individual containers/logs. Do not rebuild/re-import history to fix startup.

Git restores code, not .env, auth, databases, volumes or models. For damaged data:

1. Preserve live evidence and schedule a recovery window.
2. Choose a verified backup with matching application/schema and keys.
3. Restore to a **separate location** first; verify integrity and relevant records.
4. Replace production only with approval and all writers stopped.
5. Verify history, consultant/maintenance records, versions and health before reopening access.

Use the existing checkpoint/restore-drill utilities documented in the repo, not an improvised live-file overwrite. No destructive one-line production restore is supplied here. Restore older WebUI archives with their matching image; never downgrade a migrated live database in place.

## Never do these casually

- Docker down -v, volume deletion, factory reset, prune, or delete Docker's VHDX.
- Delete SQLite/WAL files, model blobs, source archives, receipts or backups.
- Run legacy Start Josie.cmd, kill all Python, or repeatedly start servers.
- Pull latest, reinstall WebUI/Ollama, change model/provider routes or import history.
- Print .env, auth/token files or expanded Docker environment.
- Disable security/backups, broaden ports, rewrite Git history or remove checkpoints.
- Install NVIDIA/CUDA, flash BIOS or use driver-cleaner utilities before the separate approved upgrade.

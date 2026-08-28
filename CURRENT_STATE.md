# Josie current state — 2026-08-28

This is an observed Windows inventory, not a change to Josie's Constitution, authority or canonical rules. Paths use Windows-compatible forward slashes. See [architecture](ARCHITECTURE.md), [runbook](RUNBOOK.md), [measurements](PRE_GPU_BASELINE.md), [backups](BACKUP_CHECKLIST.md) and [future GPU plan](GPU_UPGRADE_PLAN.md).

## What Josie is

Open WebUI is the local chat front door. Native Windows Ollama supplies ordinary local inference. An authenticated Python control service supplies evidence, memory and existing consultant/maintenance/delegation tools. Open WebUI chat history and Josie Core SQLite are separate stores. Optional authenticated Codex/Gemini consultants are not dependencies for ordinary local chat.

No runtime configuration, provider, model selection, authority, service or driver was changed during this pass. No software/container was installed. One bounded local inference measurement was made without creating a conversation/history record.

## Git and verification

- Repository **C:/Josie**, branch **local-agent-runtime**.
- Starting HEAD **da6eccfb459e4f74f16301663cefa2acab8a8f8c**, dated 2026-08-27.
- Pre-existing modified file: `deploy/compose.yaml`, adding `ENABLE_TOOL_PERMISSIONS: "true"`; this setting is also live.
- Pre-existing untracked file: `docs/operations/phone-local-proof-20260827.txt`.
- Those changes are preserved and excluded from this documentation checkpoint. Git alone therefore does not capture the whole live deployment.
- Existing history/maintenance/grounding/runtime tags remain intact, including `history-inheritance-0.1-phase2-20260826`.
- Actual original suite: **157/157 passed**. Older 96/106/112-test results describe earlier checkpoints. Final results: [PRE_GPU_BASELINE.md](PRE_GPU_BASELINE.md).

Evidence: Git and source scripts; CIM; Task Scheduler; firewall/listener queries; Docker inspect, Compose and volume listings; read-only SQLite; loopback health APIs; Ollama inventory/residency; Tailscale status/Serve; backup-file inventories. No private chat text or secrets appear here. Healthy endpoints do not prove all business workflows or consultant authentication/quota.

## Host and storage

| Item | Observed |
| --- | --- |
| OS | Windows 11 Pro 64-bit, 10.0.26200 build 26200 |
| Last boot | 2026-08-26 20:59:25 -04:00 |
| CPU | Intel i7-7700 @ 3.60 GHz, 4 cores / 8 logical processors |
| OS-visible RAM | 34,274,889,728 bytes, approximately 31.92 GiB |
| GPU | Intel HD Graphics 630, driver 31.0.101.2140; no NVIDIA adapter detected |
| NVIDIA tooling | nvidia-smi not found |
| OS motherboard/BIOS report | SKYBAY; manufacturer/model contain “Default string”; BIOS 5.0.1.2 dated 2019-01-31 |
| C: | Healthy SATA SQF-S25V2-128G-SBC SSD; volume 126,915,440,640 bytes; free 19,782,918,144 bytes (18.42 GiB) |
| D: | Healthy UnionSine USB3.2 “External HDD”; volume 10,000,695,029,760 bytes; free 9,362,185,928,704 bytes |
| Pagefile | C:/pagefile.sys; 2,048 MiB allocated, 52 MiB used at benchmark, 880 MiB peak since boot |
| Temperatures | Existing ACPI query supplied no usable CPU temperature; not measured |

**Physical discrepancy:** older attended notes identify an Advantech AIMB-205G2 and different BIOS; older canonical notes mention a **200 W PSU**. Current PSU, board identity, slot, case clearance and exact EVGA SKU cannot be verified from these OS readings. Resolve physically before GPU installation; do not guess.

Docker's data disk is `C:/Users/dusti/AppData/Local/Docker/wsl/disk/docker_data.vhdx`, about 28.94 GiB. C: headroom is limited. D: contains the actual model server executable and models, not just archives. Do not delete the VHDX, unplug D: or change its drive letter.

## Components

| Component | Current evidence | Purpose / importance |
| --- | --- | --- |
| Open WebUI | Docker v0.11.1, healthy | Critical front door and persistent chat |
| Ollama | Native Windows 0.32.5, healthy | Critical local inference; not a container or Windows service |
| Conversation control | Native pythonw, core.py conversation serve, healthy | Critical for explicit tools/evidence; ordinary local chat may still work without tool service |
| Docker Desktop | Per-user application; engine/client 29.6.2; Linux/WSL2 | Critical for WebUI and its volumes |
| Josie SQLite | C:/Josie/data/josie.db, quick_check OK | Critical memory, history, consultant and audit data |
| Tailscale | 1.102.2, automatic Windows service, online | Required for private phone access; optional for localhost |
| n8n | Container 2.30.5, healthy | Bounded operational workflows, not default reasoning |
| Playwright worker | Existing 1.62.0-noble image, healthy | Optional authenticated read-only research |
| Proposal server | Existing Node container, healthy | Optional proposal/review interface |
| Prayer bridge | Native Python, healthy | Optional active-selection capture |
| Storage monitor | Hidden PowerShell loop, running | Important daily DB backups/status/proposal publication |
| Codex CLI | Existing Codex app CLI detected | Optional ChatGPT-authenticated consultant/delegate |
| Gemini CLI | Existing 0.56.0 npm installation | Optional Google-authenticated consultant |
| OpenCode | Existing 1.18.23 executable on D: | Optional local development worker |

No consultant or browser automation was called during this audit. Existing CLI detection is not fresh proof of login/quota.

Tailscale and WSLService are automatic/running. vmcompute/HNS are manual/triggered and running. No native Ollama Windows service was found. Docker is a per-user desktop app: Windows service status alone does not establish engine health.

Only the `docker-desktop` WSL2 distribution was found, not a separate Josie Ubuntu installation. There are no identified Josie systemd units or host cron jobs; Windows Task Scheduler and n8n scheduling are the actual mechanisms.

## Docker, Open WebUI and networking

Compose project `josie`: `C:/Josie/deploy/compose.yaml`, with secret `deploy/.env.services`. Existing images are digest-pinned, not floating `latest`.

| Container | Host binding | Persistent/config dependencies |
| --- | --- | --- |
| josie-open-webui-1 | 127.0.0.1:3000 → 8080 | josie_open_webui_data → /app/backend/data; read-only deploy/open-webui helpers |
| josie-n8n-1 | 127.0.0.1:5678 | josie_n8n_data → /home/node/.n8n; D:/Josie-Storage bind |
| josie-browser-worker-1 | 127.0.0.1:3010 | deploy/browser-worker; config/browser-policy.json; D:/Josie-Storage/secrets/browser-token.txt |
| josie-proposal-server-1 | No host port; internal 3030 | deploy/proposal-server; D: proposals/status; proposal-token.txt; proposal-interface profile |

All four were healthy, with `restart: unless-stopped`. A manually stopped container may stay stopped. Proposal server reuses the pinned n8n image's Node runtime. Browser/proposal containers have read-only filesystems, dropped capabilities and resource limits. n8n's D: bind is broader than its application-level allowed staging path.

Networks include the Compose default and internal `josie_tools` network. No nginx/Traefik/Caddy proxy container was found. Docker settings live in `C:/Users/dusti/AppData/Roaming/Docker/settings-store.json`. `C:/Users/dusti/.wslconfig` caps WSL at 8 GB RAM, 4 processors and 2 GB swap; localhost forwarding, gradual reclaim and sparse VHD are configured. Native Ollama is outside that WSL cap.

### Actual WebUI route

- Desktop **http://localhost:3000**.
- Phone **https://refurb.tail0ab4d2.ts.net**, connected to Dustin's tailnet; WebUI sign-in still required.
- One active model record: `josie-local:1.0`, display name `Josie`; latest stored chat IDs agree. Current browser selection was not inspected.
- Ollama enabled, base `http://host.docker.internal:11434`; OpenAI API route disabled; signup disabled; persistent config override disabled.
- Active non-global model filter `josie_exact_tool_response`; obsolete `josiesummit01` function inactive.
- Model tool IDs `server:josie-core-review` and `server:josie-subscription-seats`.
- Existing authenticated tool servers `http://proposal-server:3030` and `http://host.docker.internal:8790`. The Docker Desktop host bridge already reaches the loopback control service; widening its bind is unnecessary.
- WebUI DB snapshot: **56 chats, 2 memories, 1 model, 2 functions**. Messages are in chat JSON; zero rows in its separate message table do not mean lost history. External tool registration is not the empty standalone tool table.

| Request | Existing route |
| --- | --- |
| Ordinary chat | Local josie-local:1.0 |
| Ask Codex … / Ask Gemini … | Deterministic authenticated CLI consultation; actual response/evidence ID |
| Maintainer Mode: … | Existing deterministic maintenance policy |
| Delegate Codex: … | Explicit Codex development job |
| Delegate Local: … | Explicit OpenCode/Ollama development job |
| Delegate Local status: ID | Read job receipt without rerunning |

Maintainer Mode and delegation are **different safety boundaries**. Local delegation allows actual task-scoped shell work; protected-file instructions are not an OS filesystem sandbox. This pass did not change or exercise that authority. Existing 8B CPU delegation may take many minutes; it is not the small chat model.

### Exposure

| Endpoint | Purpose |
| --- | --- |
| 127.0.0.1:3000 | WebUI |
| 127.0.0.1:8790 | Authenticated control API; unauthenticated health |
| 127.0.0.1:5678 | n8n |
| 127.0.0.1:3010 | Authenticated browser worker |
| 127.0.0.1:8788 | Prayer bridge |
| Wildcard :11434 | Ollama; configured 0.0.0.0, OS listener :: |
| Tailscale HTTPS :443 | Private Serve → WebUI :3000 |
| Tailscale HTTPS :5678 | Private Serve → n8n :5678 |

LAN 192.168.5.95/22, WSL host 172.31.0.1/20 and Tailscale 100.72.174.112 are observed addresses, not static guarantees. Serve reports tailnet-only; no public Funnel or netsh portproxy entry was observed. Other Windows listeners (135,139,445,3389,5040,5357,7680 and dynamic ports) are not new Josie APIs.

**Unresolved security finding:** two enabled “ollama” application firewall rules allow TCP/UDP on Private/Public from remote Any for the active executable. A separate narrow Docker-subnet rule does not override those broader allows. The Ollama API is not authenticated like control. External/LAN reachability was not tested from another device. No firewall or bind changes were made.

## Native models and runtimes

Ollama executable `D:/Josie-Storage/apps/Ollama/0.32.5/ollama.exe`; models `D:/Josie-Storage/models/ollama`. User `C:/Users/dusti/.ollama` exists. No second executable was found in the standard LocalAppData Programs/Ollama location checked.

Launcher settings: host 0.0.0.0:11434, one loaded model, one parallel request, context 4096, keep-alive 5 minutes, queue 8. Chat model uses three threads and temperature 0. Bundled cuda_v12/cuda_v13/vulkan directories are not proof of installed CUDA Toolkit or NVIDIA acceleration.

| Tag | Logical bytes | Use |
| --- | ---: | --- |
| josie-local:1.0 | 986,063,150 | Current 1.5B chat |
| qwen2.5:1.5b-instruct-q4_K_M | 986,061,892 | Chat base |
| josie-local:pre-grounding | 986,062,016 | Preserved older alias |
| josie-code-local:1.5b-16k | 986,061,984 | Earlier code configuration |
| qwen2.5-coder:7b | 4,683,087,561 | Installed candidate |
| josie-qual-qwen25-coder:7b-32k | 4,683,087,653 | Qualification alias |
| qwen3:8b | 5,225,388,164 | Local worker base |
| josie-qual-qwen3:8b-32k | 5,225,388,180 | Current optional local worker |

All report Q4_K_M. Aliases share blobs; do not sum logical sizes as disk usage. `config/opencode-local.json` selects the 8B/32K worker at 127.0.0.1:11434/v1.

## Startup and recurring processes

| Trigger | Existing action | Observation |
| --- | --- | --- |
| Windows boot | Tailscale service | Automatic/running |
| User logon +5s | Josie Local Model, hidden VBS launcher | Ready/success after detached server start |
| Logon +15s | Josie Conversation Control, hidden VBS | Ready/success after detached Python start |
| Logon +15s | Josie Prayer Bridge, pythonw directly | Running |
| Logon +30s | Josie Storage Monitor, hidden VBS/PowerShell | Running, 300-second interval |
| Manual Docker Desktop launch | WSL/engine → existing containers | Currently required |
| Monitor first pass/calendar-day change | Daily paired SQLite backup | Seven retained daily copies/location; separate checkpoints preserved |

Tasks are under `\Josie\`, enabled/hidden, interactive-user logon tasks, not a boot-without-login guarantee. Ready after a detached launcher exits is normal. Restart-on-failure on that launcher is not continuous supervision of the detached child.

Docker has a Run entry but both Docker `AutoStart=false` and Windows StartupApproved disable sign-in startup. Current operation therefore does not prove unattended reboot recovery. Fragility: D: availability, fixed task delays, manual Docker start, and WebUI/native-service readiness races. Nothing was redesigned.

Legacy `Start Josie.cmd` opens multiple windows/GUI processes; it is preserved but not the current quiet startup path. The five-minute monitor intentionally spawns Python for status, proposal ingestion, foundation publication and daily backups. Do not kill these merely because they recur. Old startup shortcuts are preserved in backup artifacts; Google Gemini and Tailscale shortcuts are separate from Josie's task launchers.

n8n has one active workflow: **Josie - C Drive Headroom Guard**. Five FSV review/approval/token workflows are inactive. No n8n reasoning workflow was added or run.

## Important locations and persistence

- `C:/Josie/josie`, core.py, tests, scripts, deploy, config, docs: existing core and operational source. Root requirements are standard-library-only.
- `C:/Josie/.venv`: Python 3.12.10 based on C:/Program Files/Python312; not rebuilt.
- `deploy/Josie.Modelfile`: tracked custom chat-model definition; model manifests/blobs are separately stored on D:. Rebuild helpers are maintenance actions, not startup requirements.
- Node projects: `deploy/browser-worker/package.json` for the existing container worker and `data/tools/gemini-cli/package.json` for the existing CLI. Proposal server reuses its container's Node; no host npm installation was added.
- Environment files: `.env`, `deploy/.env.services`, and their `.example` counterparts. Examples are not substitutes for protected live values.
- `C:/Josie/data/josie.db`: at audit 8 memories, 143 messages, 8 consultants, 1 maintenance job, **990 Gemini conversations / 5,108 historical records**. Normal monitor audit events advance; sampled count 4,065.
- History platform was google_gemini only. `D:/Josie-Storage/ChatGPTTO` exists, but directory existence is not an import. No history import was performed.
- `C:/Josie/data/private`: protected tokens/source config, PID files, local-code-jobs, local-code-runtime and codex-delegations receipts.
- `C:/Josie/data/tools/gemini-cli`: package.json, lock and existing node_modules. Host node/npm are not on PATH; existing adapter discovers bundled Node. No new Node stack needed.
- `D:/Josie-Storage/apps/OpenCode/1.18.23/opencode.exe`: existing worker.
- `C:/Program Files/Git`: Git and Git Bash. PATH bash may be a WSL shim; use the explicit Git Bash executable.
- `C:/Users/dusti/.codex`, `.gemini`: authentication/configuration stores; never print them into reports.
- `C:/Josie/.env`, `deploy/.env.services`, `data/private` tokens and `D:/Josie-Storage/secrets`: secret-bearing inputs. Legacy API variable/provider names do not prove paid APIs are active.
- Protected policies: config/permissions.json, maintainer-policy.json, evidence/economic/browser policies and canonical rules.
- D: also contains apps, archives, backups, datasets, downloads, generated, handoffs, logs-archive, models, proposals, staging, status and immutable GoogleTO source evidence.
- Logs: C:/Josie/logs; LocalAppData/Ollama/server.log if present; Docker logs; Task Scheduler history; Docker Desktop diagnostics. Launcher logs may be stale/empty.

### Existing operational script map

| Group | Files / meaning |
| --- | --- |
| Quiet Ollama launch | scripts/Run-JosieOllamaHidden.vbs, Run-JosieOllamaBackground.ps1, Start-JosieOllama.ps1; Ensure-JosieOllama.ps1 is the readiness guard |
| Control launch | Run-JosieConversationControlHidden.vbs, Start/Stop-JosieConversationControl.ps1; Register-JosieConversationControlTask.ps1 changes task registration, not a health check |
| Storage/status/backup loop | Run-JosieStorageMonitorHidden.vbs, Start/Stop-JosieStorageMonitor.ps1, Write-JosieStorageSnapshot.ps1 |
| Optional services | Start/Stop-JosiePrayerBridge.ps1, Start/Stop-JosieProposalInterface.ps1, Start/Stop-JosieResearchPilot.ps1 |
| Recovery | scripts/Backup-JosieServices.ps1; core.py backups checkpoint/daily commands |
| Setup/gates, not routine startup | Install-JosieNativeModel.ps1, Rebuild-JosieLocalModel.ps1, Set-JosieOllamaFirewall.ps1, Install-JosieN8nWorkflows.ps1, Invoke-JosieServiceGate.ps1, Invoke-JosieSystemGate.ps1, Get-JosieGateStatus.ps1, Initialize/Confirm-JosiePrayer helpers |
| Browser extension | browser-extension/prayer-capture; local source/token configuration is sensitive |
| New diagnostics only | josie-doctor.sh, scripts/josie_doctor.py; separate opt-in scripts/measure_pre_gpu.py |

No existing shell script was replaced. The new .sh is a Git Bash entry point to existing Windows Python, not a Linux deployment.

Today's `C:/Josie/data/backups/josie-2026-08-28.db` and `D:/Josie-Storage/backups/josie-database/josie-2026-08-28.db` passed quick_check. Latest paired service archives in D:/Josie-Storage/backups/services are **20260826-065537**. A later WebUI-only archive is under backups/open-webui-v0.8.9-pre-upgrade-20260826-221447. No fresh full-volume backup of today's v0.11.1/delegation state was found. Older restore drills do not verify today's service state.

Never casually delete SQLite/sidecars, Docker volumes/VHDX, model blobs, keys, source/manifests, receipts, checkpoint tags/backups, canonical rules, Compose/env or startup definitions. Git does not back up most of these.

## Readiness

The working stack is suitable for a comparison baseline, **not yet cleared for GPU installation**. Remaining issues: physical PSU/board/card-fit uncertainty; stale full-service recovery; no verified independent/off-device backup; manual Docker startup; broad Ollama firewall allows; limited C: headroom; and different persistence/authority boundaries that must not be conflated.

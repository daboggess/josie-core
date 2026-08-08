# Josie Core

The canonical build roadmap is [docs/JOSIE_SETUP_CHECKLIST.md](docs/JOSIE_SETUP_CHECKLIST.md).
The non-destructive external-drive procedure is [docs/EXTERNAL_DRIVE_PLAN.md](docs/EXTERNAL_DRIVE_PLAN.md).
The capability policy is [docs/PERMISSIONS_MATRIX.md](docs/PERMISSIONS_MATRIX.md).

Josie Core is a lightweight, local-first orchestration foundation for Josie 1.0. The Python kernel uses only the standard library. Native Windows Ollama runs the CPU-only `josie-local:1.0` model from the external drive; no GPU packages are installed and cloud providers remain locked off.

Large, archival, and replaceable data is rooted at `D:\Josie-Storage`; the live
application and SQLite database remain on the internal SSD.

The 128 GB internal SSD is guarded by a 20 GB warning threshold and a 15 GB
critical threshold. Docker's WSL disk remains on C: for the existing services,
so storage monitoring is mandatory even though Ollama and its model are on D:.

## Safety model

- Secrets live in `.env`, which Git ignores.
- Logs rotate under `logs/`, which Git ignores.
- Tools must be registered in `josie/tools.py`; arbitrary shell execution is intentionally unavailable.
- Diagnostics report whether cloud keys exist but never print their values.
- Local-model text is untrusted. A deterministic allowlist—not model output—decides which review-only handler proposals may be recorded.
- n8n cannot access node environment variables and explicitly excludes command, local-file-trigger, and SSH nodes.
- Economic capability is machine-locked to zero dollars: no spending, wallet, debt, transfer, or self-modifiable limit.

## First-time start

Open PowerShell in `C:\Josie`, then run:

```powershell
python -m venv .venv
.\.venv\Scripts\python.exe .\core.py health
.\.venv\Scripts\python.exe .\core.py gui
```

No package installation or environment activation is currently required. This
direct form works even when PowerShell's script execution policy blocks
`Activate.ps1`.

Activation is optional. If it is already permitted on the machine, you may use:

```powershell
.\.venv\Scripts\Activate.ps1
python .\core.py health
deactivate
```

## Everyday commands

```powershell
cd C:\Josie
.\.venv\Scripts\python.exe .\core.py health
.\.venv\Scripts\python.exe .\core.py health --json
.\.venv\Scripts\python.exe .\core.py tools list
.\.venv\Scripts\python.exe .\core.py providers status
.\.venv\Scripts\python.exe .\core.py propose "Please check Josie system health"
.\.venv\Scripts\python.exe .\core.py proposals status
.\.venv\Scripts\python.exe .\core.py proposals ingest
.\.venv\Scripts\python.exe .\core.py handoffs create sophie "Review Josie's health"
.\.venv\Scripts\python.exe .\core.py handoffs list
.\.venv\Scripts\python.exe .\core.py browser status
.\.venv\Scripts\python.exe .\core.py economics status
.\.venv\Scripts\python.exe .\core.py deploy status
.\.venv\Scripts\python.exe .\core.py deploy safe
.\.venv\Scripts\python.exe .\core.py providers check openai
.\.venv\Scripts\python.exe .\core.py providers check gemini
.\.venv\Scripts\python.exe -m unittest discover -s tests -v
```

## Private local chat

From a device connected to Dustin's Tailscale network, open:

```text
https://refurb.tail0ab4d2.ts.net/
```

Open WebUI sends model requests to the native Ollama server through Docker's
host gateway. The model server is not published through Tailscale or the LAN.
OpenAI API access remains disabled, so this chat path cannot create OpenAI API
charges.

Open WebUI is the direct conversational surface for `josie-local:1.0`. The
governed Core proposal boundary is available from the local GUI with
`ask Josie ...` or from the `core.py propose` command. It accepts only three
review-only intents: health check, secret-free memory export, and non-overwriting
restore drill. Model text cannot queue or execute any of them.

An authenticated OpenAPI bridge is active so Open WebUI can record those same
three proposal types. It has no host port, uses a private Docker network and
bearer token, and can only write bounded JSON records. The
host monitor validates and imports those records into Core; it never executes
them. Successful tool results include a fixed evidence-only reply, and the local
model is tested to avoid invented post-tool claims. See
[docs/OPENWEBUI_CORE_BRIDGE.md](docs/OPENWEBUI_CORE_BRIDGE.md).

Sophie and Bernie coordination uses local handoff drafts, not provider APIs.
`ask Sophie ...` and `ask Bernie ...` in the GUI save a secret-screened draft
with a machine-enforced zero-cent API budget. Dustin or Codex Remote must relay
it manually; Josie has no send command. See
[docs/MODEL_HANDOFFS.md](docs/MODEL_HANDOFFS.md).

Browser automation remains locked with an empty site allowlist and every
capability disabled. The machine-readable policy prefers dedicated connectors,
blocks internal/private destinations, and treats page content as untrusted. See
[docs/BROWSER_CAPABILITY_REVIEW.md](docs/BROWSER_CAPABILITY_REVIEW.md).

Economic and wallet capability remains disabled with every limit fixed at zero
cents. Tax, identity, contracting, purchases, bids, subscriptions, and transfers
are human-controlled. See [docs/ECONOMIC_BOUNDARY.md](docs/ECONOMIC_BOUNDARY.md).

Start or repair the local model and containers:

```powershell
cd C:\Josie
.\scripts\Ensure-JosieOllama.ps1
.\scripts\Start-JosieStorageMonitor.ps1 -Once
docker compose --env-file .\deploy\.env.services -f .\deploy\compose.yaml up -d
```

Stop the containers without deleting data, then unload the local model:

```powershell
docker compose --env-file .\deploy\.env.services -f .\deploy\compose.yaml stop
.\scripts\Stop-JosieStorageMonitor.ps1
& 'D:\Josie-Storage\apps\Ollama\0.32.5\ollama.exe' stop josie-local:1.0
```

Check the model, storage thresholds, and acceptance state:

```powershell
& 'D:\Josie-Storage\apps\Ollama\0.32.5\ollama.exe' list
.\scripts\Write-JosieStorageSnapshot.ps1
.\.venv\Scripts\python.exe .\core.py deploy validate
.\.venv\Scripts\python.exe .\core.py audit
```

Josie's GUI and storage monitor start at sign-in. The storage monitor refreshes
`D:\Josie-Storage\staging\storage-status.json` every five minutes; the active
n8n headroom guard checks it daily and records a failed execution if C: reaches
warning or critical status. It sends no external message and uses no network node.
The same monitor also ingests and validates any records in the proposal inbox.

The `gui` command opens Josie's local chat-style command center. It understands
`help`, `status`, `system status`, `repository status`, `health`, `cloud status`,
`storage health`, `uptime`, `backup status`, `tools`, `time`, `remember ...`, `memories`,
`add task ...`, `tasks`, `complete task N`, `ask Josie ...`,
`external proposals`, `ask Sophie ...`, `ask Bernie ...`, and `handoffs`.
Conversations, memories, and task
records are stored locally in the ignored `data/josie.db` SQLite database.
Tasks are records only and never execute automatically. Unrecognized requests
stay local and are never forwarded to a cloud provider.

Approval commands are `request action ...`, `approvals`, `approve N`, and
`deny N`. Approval decisions are audited but never execute an action. Use
`activity` to review the local audit trail. The GUI creates one local database
snapshot per day under `data/backups` and retains the seven newest snapshots.

Memory correction, soft deletion, and restoration are two-step operations. Use
`request correct memory N: ...`, `request delete memory N`, or
`request restore memory N`; approve the generated request; then use
`apply memory change N`. `memory history` shows active and archived records.
Nothing is hard-deleted, and the original value remains in the audit record.

The GUI includes quick-action buttons for Status, System, SSD, Tasks, Approvals,
Backups, and Activity. Each button invokes the same local allowlisted command as
typing its label; it does not bypass approval or cloud-spending controls.

The right-side dashboard provides visual approval and activity panels. Use
`remind me in 15 minutes to ...`, `reminders`, `warnings`, and `export report`
for local reminders, threshold checks, and secret-free JSON diagnostics exports.
While the GUI is open, Josie runs a local health check every five minutes.
Windows named-mutex protection prevents Startup and desktop launches from
opening more than one Josie GUI instance.

## Cloud configuration

Edit `C:\Josie\.env` locally and place keys after the appropriate equals sign. Do not paste keys into chat or commit `.env`.

```text
OPENAI_API_KEY=
GEMINI_API_KEY=
```

Provider status never prints secret values. A provider `check` sends one short,
non-stored live request and may incur API usage charges. Cloud calls are locked
off by default with `JOSIE_ALLOW_CLOUD=false`; a check cannot reach a provider
until that local setting is deliberately changed to `true`. These cloud adapters
do not grant either provider access to Josie's local tool allowlist.

## Recovery

Inspect the current state and recent checkpoints:

```powershell
git status
git log --oneline --decorate -5
```

Restore one tracked file to the last committed version:

```powershell
git restore -- path\to\file
```

Create a recovery branch before experimenting:

```powershell
git switch -c experiment-name
```

The `.env`, `.venv`, and logs are local and are not restored by Git. Keep API keys in a password manager; revoke and replace any key that is accidentally exposed.

The optional proposal bridge can be stopped without deleting its inbox:

```powershell
.\scripts\Stop-JosieProposalInterface.ps1
```

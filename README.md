# Josie Core

Josie Core is a lightweight, local-first orchestration foundation for Josie 1.0. The current checkpoint uses only the Python standard library, runs safely on the Intel HD 630 system, and does not install local models or GPU packages.

## Safety model

- Secrets live in `.env`, which Git ignores.
- Logs rotate under `logs/`, which Git ignores.
- Tools must be registered in `josie/tools.py`; arbitrary shell execution is intentionally unavailable.
- Diagnostics report whether cloud keys exist but never print their values.

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
.\.venv\Scripts\python.exe .\core.py providers check openai
.\.venv\Scripts\python.exe .\core.py providers check gemini
.\.venv\Scripts\python.exe -m unittest discover -s tests -v
```

Josie is currently command-based, not a background service. Each command stops when its result is printed. If a future long-running command is added, press `Ctrl+C` to stop it.

The `gui` command opens Josie's local chat-style command center. It understands
`help`, `status`, `system status`, `repository status`, `health`, `cloud status`,
`storage health`, `uptime`, `backup status`, `tools`, `time`, `remember ...`, `memories`,
`add task ...`, `tasks`, and `complete task N`. Conversations, memories, and task
records are stored locally in the ignored `data/josie.db` SQLite database.
Tasks are records only and never execute automatically. Unrecognized requests
stay local and are never forwarded to a cloud provider.

Approval commands are `request action ...`, `approvals`, `approve N`, and
`deny N`. Approval decisions are audited but never execute an action. Use
`activity` to review the local audit trail. The GUI creates one local database
snapshot per day under `data/backups` and retains the seven newest snapshots.

The GUI includes quick-action buttons for Status, System, SSD, Tasks, Approvals,
Backups, and Activity. Each button invokes the same local allowlisted command as
typing its label; it does not bypass approval or cloud-spending controls.

The right-side dashboard provides visual approval and activity panels. Use
`remind me in 15 minutes to ...`, `reminders`, `warnings`, and `export report`
for local reminders, threshold checks, and secret-free JSON diagnostics exports.
While the GUI is open, Josie runs a local health check every five minutes.

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

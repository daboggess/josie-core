# Subscription-backed local Josie

Open WebUI is Josie's permanent conversation front door and native chat-history
owner. Ordinary conversation stays on the existing `josie-local:1.0` Ollama
model. The existing SQLite file at `C:\Josie\data\josie.db` receives a local
mirror of Open WebUI conversation messages plus consultant decisions and final
consultant responses.

## Use Josie

- On the desktop, open `http://127.0.0.1:3000/` and select **Josie**.
- On a phone connected to Dustin's Tailscale network, open
  `https://refurb.tail0ab4d2.ts.net/` and select **Josie**.
- Talk normally for local Ollama conversation.
- Say `Ask Codex ...` when a stronger OpenAI reasoning opinion is wanted.
- Say `Ask Gemini ...` when a Google second opinion is wanted.
- Ask `What did we discuss/decide/remember about ...?` to search Josie's local
  SQLite history.

The local router does not call both consultants for every message. It selects
`consult_codex` or `consult_gemini` only for an explicit request or a question
that clearly needs that advisory seat. Consultant output is advisory: Josie's
local model remains responsible for the final conversation response.

## Boundaries

The local control service listens only on `127.0.0.1:8790`. The existing Open
WebUI container reaches it through `host.docker.internal`; no host firewall,
LAN, Tailscale, or public listener exposes that port. The service reuses the
existing SQLite database and adds no container, database, workflow engine, or
provider framework.

Codex runs through the official Codex CLI's existing ChatGPT login. Gemini runs
through the official Gemini CLI's cached Google OAuth login. Child environments
remove API-key, ADC, Vertex, organization, and project billing paths. Neither
seat is mandatory and neither is configured with a paid API credential.

Every CLI call is read-only and time-bounded. Unavailable executables, logout,
quota/rate limits, upstream errors, and timeouts return a structured
`local_fallback_available` result. Open WebUI then continues with local Ollama.
Failed calls are audited locally; successful final responses and the decision
to consult are stored in SQLite memory.

## Quiet startup and recovery

Task Scheduler starts these hidden components at sign-in:

- `Josie Local Model` starts native Ollama and returns after health verification.
- `Josie Conversation Control` starts the Python loopback service through
  `pythonw.exe` and returns after health verification.
- `Josie Prayer Bridge` preserves the existing loopback prayer service.
- `Josie Storage Monitor` intentionally checks storage every five minutes.

The obsolete legacy GUI startup shortcut is disabled. The old Summit Open WebUI
function and two FSV n8n workflows are disabled, not deleted. Their useful
history and recovery artifacts remain available.

Useful operator checks:

```powershell
cd C:\Josie
.\.venv\Scripts\python.exe .\core.py conversation status
Invoke-RestMethod http://127.0.0.1:8790/health
Invoke-RestMethod http://127.0.0.1:11434/api/version
Get-ScheduledTask -TaskPath '\Josie\'
```

Restart only the conversation bridge without deleting history:

```powershell
.\scripts\Stop-JosieConversationControl.ps1
.\scripts\Start-JosieConversationControl.ps1
```

Recreate or verify its hidden logon task after a recovery:

```powershell
.\scripts\Register-JosieConversationControlTask.ps1
```

GPU-specific model selection, context tuning, and desktop-control capability are
deliberately deferred until the RTX 3060 12GB is installed.

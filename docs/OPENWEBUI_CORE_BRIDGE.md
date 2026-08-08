# Open WebUI to Josie Core proposal bridge

## Current state

The bridge is installed in the repository but disabled by default. Normal
`docker compose up -d` does not start it. Activation is attended because adding
a global tool server changes the permissions of Dustin's authenticated Open
WebUI account.

The bridge is intentionally record-only:

- no published Windows, LAN, or Tailscale port;
- a Docker-internal network shared only with Open WebUI;
- a random bearer token stored at
  `D:\Josie-Storage\secrets\proposal-token.txt`, outside Git;
- exactly three proposal kinds: `health_check`, `memory_export`, and
  `restore_drill`;
- exactly two accepted model fields: `kind` and `summary`;
- three writes per minute and 1,000 waiting records maximum;
- no shell, process launch, arbitrary code, browser, message, payment, cloud,
  queue, or action execution path;
- every accepted record says `review_required`, `actions_queued: 0`, and
  `actions_executed: 0`;
- Core independently validates every field before recording a proposal in its
  local SQLite audit trail.

This follows Open WebUI's documented backend/global OpenAPI server pattern. A
global connection is required because requests originate from the Open WebUI
container; a phone browser cannot reach the private Docker service directly.

Official references:

- https://docs.openwebui.com/features/extensibility/plugin/tools/openapi-servers/
- https://docs.openwebui.com/features/extensibility/plugin/tools/openapi-servers/open-webui/

## Attended activation

From PowerShell in `C:\Josie`:

```powershell
.\scripts\Start-JosieProposalInterface.ps1
```

The script creates the local credential if needed, restricts its Windows file
permissions, starts only the proposal server and Open WebUI, and verifies both
the server and the private container-to-container route.

In Open WebUI, use Admin Settings, Integrations, then the global Tools section.
Add this server:

```text
http://proposal-server:3030
```

Choose bearer-token authentication and paste the contents of:

```text
D:\Josie-Storage\secrets\proposal-token.txt
```

Do not paste the token into chat, source code, Git, screenshots, or this
document. Enable the resulting tool only in a deliberate test chat. Open WebUI
documents that global tools are hidden by default and must be explicitly
enabled per user/chat.

## Acceptance test

Ask the model to record a `health_check` proposal. Then, on Josie:

```powershell
.\.venv\Scripts\python.exe .\core.py proposals ingest
.\.venv\Scripts\python.exe .\core.py proposals status
```

Pass criteria are one new `review_required` proposal, zero queued actions, zero
executed actions, and no cloud activity. A request for any other kind must be
rejected.

## Stop and recover

Stop the optional bridge without deleting records or stopping Open WebUI:

```powershell
.\scripts\Stop-JosieProposalInterface.ps1
```

Pending, processed, and rejected JSON records remain under
`D:\Josie-Storage\proposals`. The token remains in place so the same Open WebUI
connection works after restart. Token rotation is a separate attended security
change: stop the bridge, remove the saved Open WebUI connection, replace the
token file locally, restart the bridge, then add the connection again.

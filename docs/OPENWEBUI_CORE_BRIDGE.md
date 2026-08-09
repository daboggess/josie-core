# Open WebUI to Josie Core status and proposal bridge

## Current state

The bridge is active and registered as the authenticated global Open WebUI tool
`Josie Core Review`. Its server remains inside Docker's private network and has
no Windows, LAN, Tailscale, or internet listening port. Open WebUI loads the
connection from its ignored local service environment so the registration
survives a restart without weakening the infrastructure-as-code policy. Web
origins are restricted to Josie's loopback interface and private Tailscale URL.

The bridge has two intentionally bounded operations:

- `get_josie_status` accepts no parameters and returns only the strict,
  secret-free snapshot published by the trusted Windows monitor;
- `record_review_proposal` accepts exactly `kind` and `summary`, then writes a
  review record without queuing or executing it.

Its boundary is intentionally narrow:

- no published Windows, LAN, or Tailscale port;
- a Docker-internal network shared only with Open WebUI;
- a random bearer token stored at
  `D:\Josie-Storage\secrets\proposal-token.txt`, outside Git;
- a read-only mount containing only
  `D:\Josie-Storage\status\josie-status.json`;
- exactly three proposal kinds: `health_check`, `memory_export`, and
  `restore_drill`;
- exactly two accepted model fields: `kind` and `summary`;
- three writes per minute and 1,000 waiting records maximum;
- identical kind-and-summary retries within five minutes return the original
  proposal ID and create no duplicate record;
- no shell, process launch, arbitrary code, browser, message, payment, cloud,
  queue, or action execution path;
- every accepted record says `review_required`, `actions_queued: 0`, and
  `actions_executed: 0`;
- every success response includes a fixed, evidence-only assistant message so
  the small local model does not need to invent an interpretation;
- Core independently validates every field before recording a proposal in its
  local SQLite audit trail.

The host status snapshot contains only drive headroom, local service
availability, backup count/age/integrity, review-required counts, and boolean
safety-lock state. It contains no keys, prompts, messages, summaries,
usernames, paths, container controls, or model-generated fields. The private
server validates that full snapshot and converts it into one fixed
`assistant_message`; the model-facing response includes only that message,
overall state, and the fixed read-only/zero-action fields. This keeps the 1.5B
model's context small enough for exact copying while the full diagnostic source
remains available to trusted Core on D:. The server rejects an invalid file and
marks a snapshot stale after fifteen minutes. A status read cannot write a
proposal, queue a job, or execute anything.

Open WebUI's global servers are otherwise hidden per chat. Josie's activation
script therefore applies a supported model-level binding to
`josie-local:1.0`: `server:josie-core-review` is the only default attached
tool, unrelated built-in tools are disabled, and the system instruction forbids
an unverified current-status answer. Tool selection uses Open WebUI's bounded
JSON preflight mode because the 1.5B local model was observed emitting a valid
tool name as ordinary assistant text instead of Ollama's structured native
tool-call field. The tracked routing prompt allows current-state reads and
explicitly requested allowlisted proposals, returns no tool for ordinary chat,
and still leaves the private server responsible for authentication, schema
validation, rate limits, and the zero-execution boundary. The binding is
idempotent and is reapplied during bridge repair.

Open WebUI's generic source-summarization prompt is not used for this bridge.
The tracked source template recognizes only this private server's source name
and requires the model to copy its `assistant_message` value byte-for-byte,
without a citation, preface, or reinterpretation. File context is disabled on
the governed Josie model so a user-named file cannot imitate the trusted tool
source. Repeated fixtures cover both status and proposal responses; the private
server remains the authority for the actual wording and facts.

This follows Open WebUI's documented backend/global OpenAPI server pattern. A
global connection is required because requests originate from the Open WebUI
container; a phone browser cannot reach the private Docker service directly.

Official references:

- https://docs.openwebui.com/features/extensibility/plugin/tools/openapi-servers/
- https://docs.openwebui.com/features/extensibility/plugin/tools/openapi-servers/open-webui/

## Start or repair

From PowerShell in `C:\Josie`:

```powershell
.\scripts\Start-JosieProposalInterface.ps1
```

The script creates the local credential if needed, restricts its Windows file
permissions, generates the ignored Open WebUI connection setting, starts only
the proposal server and Open WebUI, and verifies the private
container-to-container route. It then runs a no-write status result and a
proposal fixture through the live local model and fails closed unless both
`assistant_message` values are returned exactly. The fixture is never submitted
to the proposal server. The script never prints the bearer token. Open WebUI
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

For status, ask: `What is your current system status?` Pass criteria
are a fresh read-only snapshot, zero new proposals or jobs, zero queued or
executed actions, and a reply limited to the server's evidence-only message.

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

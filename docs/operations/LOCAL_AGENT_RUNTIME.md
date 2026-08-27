# Local coding runtime — blocked proof checkpoint (2026-08-27)

## Status and architecture

Implemented, but **not proven or deployed to the live Open WebUI filter**:

Open WebUI explicit trigger → existing conversation-control bridge →
`josie.local_code.delegate_local_code` → native OpenCode → loopback Ollama → C:\Josie.

No new service, container, cloud API, credential, or Codex runtime dependency.
`consult_codex` and `delegate_codex` remain unchanged fallbacks. No historical or
canonical data was modified. The existing Compose Tool Permissions edit is unrelated.

## Installed components

- OpenCode 1.18.23: `D:\Josie-Storage\apps\OpenCode\1.18.23\opencode.exe`.
- Official portable ZIP: https://github.com/anomalyco/opencode/releases/download/v1.18.23/opencode-windows-x64.zip
- ZIP SHA-256: `a2fe9e8c2d074d26975024d494927b966680b3efdc3e0377eadb9afb05f7e191`.
- Existing Ollama 0.32.5: `http://127.0.0.1:11434` (its existing listening configuration was not changed).
- New alias `josie-code-local:1.5b-16k` reuses existing `qwen2.5:1.5b-instruct-q4_K_M`
  weights with `num_ctx=16384`. Existing model definitions are untouched; no weights downloaded.
- Native config: `config/opencode-local.json`. Only the Ollama provider is enabled.
  Both primary/small model settings are local. Replace the model keys/settings together
  when a qualified local coding/tool model is available.
- Native `josie-local` agent currently exposes only bash to simplify the 1.5B model's
  tool menu. Git Bash can run Python, Git, tests and repo file operations. This did NOT
  rescue the proof. It is not an OS security boundary. Native read/edit/glob/grep can
  be re-enabled after qualifying a suitable model; no additional proxy is needed.

Ollama's OpenAI-compatible API does not set context size through the standard request.
The dedicated alias sets it server-side without changing the conversational model.
See https://docs.ollama.com/api/openai-compatibility and
https://opencode.ai/docs/providers/ . The active alias context was verified via `/api/ps`;
it ran on CPU, not a newly installed GPU.

To reproduce the alias only if it is absent:

```powershell
$body = @{model='josie-code-local:1.5b-16k'; from='qwen2.5:1.5b-instruct-q4_K_M'; parameters=@{num_ctx=16384}; stream=$false} | ConvertTo-Json -Depth 4
Invoke-RestMethod http://127.0.0.1:11434/api/create -Method Post -ContentType application/json -Body $body
```

## Invocation and authority

Python entrypoint, from C:\Josie with the existing venv:

```python
from josie.local_code import delegate_local_code
result = delegate_local_code(
    'Run .venv/Scripts/python.exe --version and report actual output.',
    'A real command runs successfully and its result is reported.',
    request_id='local-example-0001', project_root='C:/Josie')
print(result['assistant_message'])
```

Use a unique ID for a NEW task. Reusing an ID returns its receipt rather than rerunning.
Never retry an uncertain operation under a new ID until its receipt/process is inspected.

The added, not-yet-deployed chat trigger is `Delegate Local Code: <complete bounded task>`;
status trigger is `Delegate Local Code status: <job-id>`.
The existing authenticated bridge routes are `/v1/delegate/local-code` and
`/v1/delegate/local-code/status`; clients cannot choose another root, runtime, flags or timeout.
The filter forwards the original request and replaces interim model text with the actual
receipt. Automated routing tests pass, but **phone/live UI execution is not verified**.
Do not install the updated filter or advertise this as operational until the proof passes.

The existing Maintainer policy must load and be enabled. Its protected paths are supplied
as task authority instructions. Explicit task authorization governs consequential edits;
the adapter does not implement a second filesystem sandbox. Ordinary repo commands are
available, but publishing, credential access, production data changes and unrelated system
administration are outside this delegation. Model instructions are not an OS access ACL.

## Receipts, failures, and concurrency

Receipts: `data/private/local-code-jobs/<id>.json`, `.events.jsonl`, `.stderr.txt`.
They include start/duration, repository/branch/commit before and after, runtime/model,
exit/timeout, completed tool events, final text, test-command output, and Git-visible file
hash differences (including changes to already-dirty files). Ignored production payloads
are not scanned. Removed temporary files leave no final hash difference; tool logs remain
the activity evidence. No generic semantic acceptance-criteria judge is implemented.

`completed` means exit 0 + successful actual tool activity + a final event; it does not
prove arbitrary task requirements independently. Text alone, malformed events, tool
errors, nonzero exits and missing final output fail honestly. Receipts retain activity
even when final capture fails. Full logs are local/private, not committed.

The existing `.git/josie-delegate.lock` serializes local and Codex jobs. Timeout is 900s;
termination targets only the spawned process tree. A lock is retained if termination
cannot be confirmed. Do not delete a lock until its owner/process tree is confirmed stopped.

## Actual verification and blocker

An initial direct OpenCode/Ollama probe executed `python --version` through a real bash
tool event and returned Python 3.12.10. That is only a command-level connectivity probe.

The required adapter proof asked for a harmless fixture containing `LOCAL_RUNTIME_OK`,
read-back assertion, Python execution, one unittest, and Git status. Three real attempts:

| Receipt ID | Configuration | Actual result |
| --- | --- | --- |
| local-proof-20260827-01 | Original model, 4K active context | One file read; invalid tool schemas; no fixture/test; failed |
| local-proof-20260827-02 | Dedicated 16K alias, read/edit/bash tools | Invented paths and invalid tool arguments; no completed actions/final; failed |
| local-proof-20260827-03 | 16K alias, shell-only, exact short command | Exit 0 but no tool or final-text events; no file changes; failed |

All three receipts are under the private receipt directory. Their `cloud_required` is
false. The local adapter, not Codex, launched every attempt. Neither requested fixture
exists and no job lock remains. No successful engineering execution or test execution
through the agent is claimed. Increasing context fixed context allocation, not the
model's observed tool-use failure. This does not prove OpenCode fundamentally incompatible
with Ollama; it blocks acceptance with this current model/configuration.

Smallest next step: qualify a stronger locally runnable tool-capable model against the
same fixture/test task. Do not redesign the bridge or begin UFO² until that gate passes.
UFO² and the Playwright follow-on assessment were deferred because the prerequisite failed.

## Tests and recovery

Run `.venv\Scripts\python.exe -m unittest discover -s tests -q` from C:\Josie.
Focused local-runtime and frozen Codex tests: 33 passed. The pre-change full suite ran
131 tests with one transient Windows connection-aborted error in an HTTP auth test;
that exact test passed immediately on rerun. Final full suite: **149/149 passed**
(37.990s); 18 focused local-runtime tests were added. No skipped/failing tests.

No global PATH, Windows service, startup task, firewall, Tailscale, or existing Open WebUI
deployment was changed. OpenCode is launched on demand. Its private XDG config/cache/data/state
and own session database live under `C:\Josie\data\private\local-code-runtime`.
OpenCode may populate its own native provider dependencies there during first startup.

To undo external installation changes after ensuring no local job is active:

1. Remove only the added alias with the existing executable:
   `D:\Josie-Storage\apps\Ollama\0.32.5\ollama.exe rm josie-code-local:1.5b-16k`.
   Do not remove the base model or either existing Josie model.
2. Archive/rename `D:\Josie-Storage\apps\OpenCode\1.18.23` if no longer wanted.
3. Archive/rename only `C:\Josie\data\private\local-code-runtime` and
   `C:\Josie\data\private\local-code-jobs` if rolling back runtime state. Preserve receipts
   if needed for diagnosis; never remove the parent private/data directories.
4. Revert only this task's Git checkpoint if desired. Do not reset the working tree or
   revert the unrelated `deploy/compose.yaml` edit. No live filter/service rollback is
needed because the new source routes were not deployed/restarted during this task.
   The new HTTP routes will load on the bridge's next normal restart; the live Open WebUI
   filter still needs deliberate installation after a successful proof.

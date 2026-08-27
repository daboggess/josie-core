# Codex repository delegation

In a normal Josie chat in Open WebUI, send:

    Delegate Codex: <complete engineering task and acceptance criteria>

This is an explicit authorization to perform that bounded task, not an advisory
question. The existing exact-response filter routes the original text to
`delegate_codex` (`POST /v1/delegate/codex`) and returns the captured result.
`Ask Codex ...` / `consult_codex` remain advisory and read-only.

The host conversation-control service launches the existing ChatGPT-authenticated
Codex CLI in the actual Josie repository. No API key or separate paid API provider,
new terminal, clone, container, database, or approval framework is introduced.
The standard workspace-write sandbox permits repo development, with the repo's
Git directory also writable. Commands cannot request sandbox escalation; network
access is disabled for sandboxed commands. Existing user config/rules are not
inherited. This is task-level authorization, **not per-command Allow/Deny**.

The task prompt carries the existing Maintainer policy and explicitly prohibits
unrelated work, credential exposure, production/history/canonical data changes,
Phase 3, destructive system actions, permission expansion, remote push and Git
history/recovery-tag rewriting. These task boundaries are instructions, not a
new protected-file sandbox. Protected source edits require Dustin's explicit
authorization in the task. Maintainer Mode itself is unchanged.

One `.git/josie-delegate.lock` excludes other delegated jobs on the same working
tree. Do not run independent manual/Codex/Maintainer edits concurrently. Existing
dirty files are reported to the delegate and must be preserved. The delegate is
instructed to use a `maintenance/delegate-...` branch before edits.

The call may take up to 15 minutes. Timeout terminates the exact child process tree;
partial edits remain for inspection. A failed termination retains the lock.
Retries with the same request ID return the saved receipt, not a second execution.
For an interrupted browser request, use:

    Delegate Codex status: <job-id>

Receipts, final responses and execution logs live in ignored
`data/private/codex-delegations/`, not the historical SQLite database. Logs are
local and should not be shared unreviewed. A completed CLI turn is not proof that
every task criterion passed: inspect the response, exit code, execution events,
before/after Git state and test evidence. Zero execution events are reported as zero.

Recovery: read the receipt first. If a lock remains after a crash, verify both the
recorded owner and child PID are no longer running before manually removing only
that lock. Never auto-remove an apparently stale lock or automatically reset Git.
The existing Conversation Control scheduled task remains the startup mechanism.
Restart that service and Open WebUI only when no job is running after deploying
code/filter changes. No historical imports or data migrations are needed.

## Deployment and verified compatibility

Install only the filter source (not a model/config reset), then restart Open WebUI:

    Get-Content -Raw C:\Josie\deploy\open-webui\install-delegation-filter.py | docker exec -i josie-open-webui-1 python -
    docker restart josie-open-webui-1

The installer backs up the prior function record inside the Open WebUI data volume
as `josie-filter-before-delegate-<sha256>.json` and preserves every other field.
The source module is loaded by the existing host Conversation Control service;
restart it using `scripts/Stop-JosieConversationControl.ps1`, then start the existing
`\Josie\Josie Conversation Control` scheduled task. Do not restart during a job.

Verified with Codex CLI `0.150.0-alpha.8` and Open WebUI `0.11.1`.
This CLI needed the standard `default_permissions=":workspace"` setting rather
than the legacy `--sandbox workspace-write` switch to obtain the requested scope.
It uses the already-installed elevated Windows sandbox and a writable Git directory;
no custom filesystem profile was added. The Open WebUI outlet now handles structured
output and emits the final completion event so the browser displays the captured
result, not the local model's draft. Delegation runs in a worker thread, leaving
Open WebUI's event loop responsive. Advisory filter behavior is retained.

Acceptance: an actual Josie chat created/switched a task branch in `C:\Josie`,
wrote/read/verified/removed a disposable doc file, ran Python 3.12.10, passed a
focused unittest and read Git status. The receipt recorded five successful command
events. The disposable file was removed; existing dirty files were preserved.
Use the final `JOSIE CODEX DELEGATION — ACTUAL RESULT`, not any streamed model draft.

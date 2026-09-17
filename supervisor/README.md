# Josie Coder Supervisor

Small deterministic supervisor for bounded local coding workers. For `harness: coder`, it selects Goose 1.50.0 with Ollama `qwen3:14b` first and invokes OpenCode 1.18.23 with the same model only after a supervisor-observed fallback condition. It does not submit normal jobs to both harnesses.

The production entry point remains Open WebUI -> Josie conversation control -> explicit `Delegate Local Code:` gate -> this supervisor. Josie performs retrieval before compiling a task-scoped work order. Workers receive only the bounded evidence excerpts in that order and have no authority over protected memory.

Job IDs are durable: validation/detail failures receive terminal receipts before a result is returned, validated work orders are queryable as `ACCEPTED` before a worker receipt exists, and unexpected submission failures receive an authoritative failure receipt. Status lookup checks terminal receipts first and then persisted work orders; it never infers `RUNNING` merely from a work-order file.

The supervisor validates JSON work orders, pins the harness and model, checks local Ollama and thermal preflight, snapshots workspace state, contains worker process trees, terminates a worker that reaches its configured no-tool stall threshold, classifies timeout/stall/no-tool failures, bounds repeated tool calls, runs independent acceptance, enforces path scope, and writes immutable per-attempt and fallback receipts.

Run a work order from the Josie root:

```powershell
python -m supervisor.run_job D:\path\to\work-order.json
```

Pinned components:

- Goose: `I:\Josie-Storage\apps\goose-1.50.0\goose-package\goose.exe`
- Goose config: `C:\Users\dusti\AppData\Roaming\Block\goose\config\config.yaml`
- OpenCode: `I:\Josie-Storage\apps\OpenCode\1.18.23\opencode.exe`
- OpenCode config: `D:\Josie\config\opencode-local.json`
- Model/context: `qwen3:14b`, 8192 input tokens, 2048 output tokens

Fallback is allowed for launch/runtime failure, bounded timeout or stall, no meaningful tool activity, invalid tool execution, bounded repeated verification/tool loops, acceptance failure after the allowed repair attempt, unsupported operation, or a concrete worker blocker. Scope and resource-policy failures fail closed instead of changing harnesses. A successful worker exit or worker narrative never determines PASS; only supervisor policy applied to external evidence does.

Supported acceptance checks are `file_exists`, `file_exact`, `command`, `changed_paths`, and `no_unexpected_files`. Paths are workspace-relative and traversal is rejected.

Run deterministic qualification tests without an LLM:

```powershell
$env:PYTHONDONTWRITEBYTECODE='1'
python -m unittest supervisor.tests.test_supervisor -v
```

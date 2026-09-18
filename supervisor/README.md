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

## Prompt Contract v1.0

Worker prompts are compiled and validated against the deterministic Prompt Contract v1.0 standard (`supervisor/prompt_contract.py`). Every worker prompt enforces the 12 canonical sections in strict order:

1. `ROLE` - Worker identity and bounding.
2. `STATE` - Baseline environment state and truth source.
3. `ENVIRONMENT` - Workspace path and execution context.
4. `OBJECTIVE` - The precise task goal.
5. `AUTHORIZED SCOPE` - Allowed writes, read-only areas, and prohibited actions.
6. `EXECUTION` - Operational directives and tool-use instructions. Read-only jobs do not mandate file edits; modification jobs (`requires_modification: true`) strictly mandate target edits before completion.
7. `FAILURE GUARDS` - Guardrails against unauthorized modifications, dependencies, and optional targeted worker failure modes (`worker_failure_modes`).
8. `ATTEMPT / TIME LIMITS` - Maximum retry attempts and execution timeouts.
9. `RESOURCE RULES` - Local-only resource limits, optional `resource_rules`, and bounded task-relevant evidence excerpts (max 5 items, max 1200 characters each).
10. `ACCEPTANCE` - Complete list of external Supervisor acceptance checks (`command`, `file_exists`, `file_exact`, `changed_paths`, `no_unexpected_files`) so expectations are transparent to the worker.
11. `RECEIPTS` - Authoritative terminal status definition and optional `receipt_instructions`. Supervisor machine evidence alone decides terminal status.
12. `FINAL REPORT` - Explicit completion reporting requirements.

### Relationship to WorkOrder and Supervisor Acceptance

- **WorkOrder Schema**: Work orders default to Prompt Contract 1.0 (`prompt_contract_version: "1.0"`). Unsupported contract versions fail validation. Work orders can supply optional contract fields including `worker_failure_modes`, `resource_rules`, and `receipt_instructions`.
- **Authoritative Supervisor Acceptance**: While the worker prompt renders all configured acceptance criteria transparently, the Supervisor executes acceptance independently. Worker self-reports or narrative declarations of success cannot create PASS.

Run deterministic qualification tests without an LLM:

```powershell
$env:PYTHONDONTWRITEBYTECODE='1'
python -m unittest supervisor.tests.test_prompt_contract -v
python -m unittest supervisor.tests.test_supervisor -v
```

# Local model qualification — 2026-08-27

## Frozen experiment

Repository C:\Josie; branch `local-agent-runtime`; starting commit
`45e4f72b2d3a9c64c5c58bcb71249caaafae0616`. Baseline: 149/149 tests passed (39.752s).
OpenCode 1.18.23, Ollama 0.32.5 at http://127.0.0.1:11434.

The exact task AND acceptance criteria were loaded from the final failed 1.5B receipt,
`data/private/local-code-jobs/local-proof-20260827-03.json`, not rewritten:

```text
Use bash to execute this exact command in C:/Josie, then report its actual output:
.venv/Scripts/python.exe -c "from pathlib import Path; import sys; p=Path('docs/operations/local-runtime-proof.txt'); assert not p.exists(); p.write_text('LOCAL_RUNTIME_OK'); assert p.read_text()=='LOCAL_RUNTIME_OK'; print(p.read_text()); print(sys.version)" && .venv/Scripts/python.exe -m unittest tests.test_local_code.LocalCodeTests.test_parse_success -v && git status --short
Leave the fixture for independent verification. Do not change any other files. Do not stage or commit.
```

Acceptance criteria: `Fixture contains LOCAL_RUNTIME_OK; Python runs; one unittest passes; report actual tool results.`
Combined task/criteria SHA-256:
`d8d8c7e9665f87828428b1d926d2e624d8effcd90ba8c61f07d145c5a9f22d4c`.
This is the previous final shell-only proof, not a newly simplified task.

Each attempt used a new request/session ID and the unchanged
`josie.local_code.delegate_local_code(task, criteria, request_id=..., project_root='C:/Josie')`.
No mock runtime, Codex runtime, cloud AI, adapter patch, prompt patch, permission change,
timeout change, or Open WebUI deployment. Native shell-only agent, temperature 0,
10 steps, output limit metadata 2048 and 900s timeout were retained.

Only model IDs/display names and context changed in `config/opencode-local.json`.
Dedicated aliases set `num_ctx=32768` through Ollama's native create API; official
weights and templates were inherited unchanged. Existing conversational models were not altered.
The active context was verified via `/api/ps`; both candidates ran on CPU, with zero VRAM use.

## Candidates

| Official model | Size | Quantization | 32K test alias |
| --- | --- | --- | --- |
| qwen2.5-coder:7b | 7.6B; 4,683,087,561 bytes | Q4_K_M | josie-qual-qwen25-coder:7b-32k |
| qwen3:8b | 8.2B; 5,225,388,164 bytes | Q4_K_M | josie-qual-qwen3:8b-32k |

Official sources: https://ollama.com/library/qwen2.5-coder:7b and
https://ollama.com/library/qwen3:8b . These are official library models, not community fine-tunes.
Base manifest digests:

- Coder 7B: `dae161e27b0e90dd1856c8bb3209201fd6736d8eb66298e75ed87571486f4364`
- Qwen3 8B: `500a1f067a9f782620b40bee6f7b0c89e17ae61f686b92c24933e4ca4b2b8b41`

## Coder 7B: all three attempts failed

| Receipt ID | Seconds | Native tool calls / commands / tests | File changes | Final text | Receipt |
| --- | ---: | --- | --- | --- | --- |
| qual-qwen25-7b-32k-01 | 172.88 | 0 / 0 / 0 | none | present, JSON-looking proposed call | failed |
| qual-qwen25-7b-32k-02 | 33.58 | 0 / 0 / 0 | none | present, JSON-looking proposed call | failed |
| qual-qwen25-7b-32k-03 | 33.70 | 0 / 0 / 0 | none | present, JSON-looking proposed call | failed |

All had process exit 0, no timeout, empty stderr, no event-parser malformed lines,
and exactly step_start/text/step_finish events. Each proposed one call in ordinary
assistant text; none emitted a native tool_use event. Attempt 1 changed `.venv` to
`./venv`; attempt 2 preserved the paths but still emitted text; attempt 3 invented
`run_bash_command` instead of the available `bash` tool. No test result or successful
workflow completion was fabricated by the adapter.

Receipts and full JSONL/stderr logs are private and durable under
`C:\Josie\data\private\local-code-jobs` using the table IDs.

## Qwen3 8B

**Attempt 1 passed**, receipt `qual-qwen3-8b-32k-01`, in **735.81s** (12m 15.81s).
One native bash call executed three chained commands: Python fixture write/read/assert
and version output; the intended unittest; then Git status. All returned exit 0.
No timeout, no malformed events, no event errors, and empty stderr.

Actual tool output included:

```text
LOCAL_RUNTIME_OK
3.12.10 (tags/v3.12.10:0cc8128, Apr  8 2025, 12:21:36) [MSC v.1943 64 bit (AMD64)]
test_parse_success (tests.test_local_code.LocalCodeTests.test_parse_success) ... ok
Ran 1 test in 0.005s
OK
 M config/opencode-local.json
 M deploy/compose.yaml
?? docs/operations/local-runtime-proof.txt
```

Receipt hash comparison identified ONLY `docs/operations/local-runtime-proof.txt` as
changed during agent execution. Config and Compose were pre-existing dirty files for
this run, correctly reported by Git but not modified by the agent.

Independent read-back and `git diff --no-index -- NUL docs/operations/local-runtime-proof.txt`
verified the new file contained exactly `LOCAL_RUNTIME_OK` (no trailing newline).
SHA-256: `2DE97F0F8DB035E39FEB865D8596A2087175CABA169305FD93A1BBFAEFAE798D`.
The diff command returned 1, the expected indication that the new file differs from empty.
After receipt completion and independent verification, the conductor removed only this
temporary fixture using apply_patch. The original task explicitly left it for verification;
cleanup was not attributed to the agent.

The final native text event began: "The command executed successfully with the following results:"
and correctly summarized the fixture, Python 3.12.10, passing test and Git state.
`final_observed=true`, `actions_executed=1`, `status=completed`, `cloud_required=false`.
Event counts: step_start 2, tool_use 1, step_finish 2, text 1.
No second or third Qwen3 attempt was needed after this complete pass.

## Interpretation: A — architecture proven for the bounded proof

**Yes:** increasing local model capability, specifically selecting official Qwen3 8B,
caused the unchanged OpenCode/Ollama adapter to complete actual repository work without
Codex or cloud AI. This supports the 1.5B model's capability/tool-use behavior as the
principal blocker, rather than requiring a replacement architecture. Merely increasing
parameter count was not sufficient: Coder 7B still emitted text-only pseudo-calls.

Compared with 1.5B, Qwen3 grounded the real workspace and `.venv` path, constructed a
valid bash call, executed the write/read/assert/Python/test/Git sequence, tracked the
tool result, and returned a grounded final response. The workflow supplied an exact
command; this is a plumbing qualification, not a benchmark of independent code design
or broad engineering reliability. One successful run does not establish a reliability rate.

CPU latency was substantial: 12m16s for this small proof. No GPU performance inference
or qualification of 14B/30B models is claimed. Qwen3's official thinking behavior was
left intact. The qualified 32K Qwen3 alias remains selected in native config, but no
Open WebUI integration was deployed or tested live.

**One next step:** qualify the intended approximately 14B model on suitable GPU hardware,
then expose the already-proven delegation path through Josie/Open WebUI. No further
software architecture work is indicated by this qualification.

## Preservation and recovery

Final full suite: **149/149 passed in 38.988s**, with no added, skipped or failing tests.
The four preservation hashes below were rechecked after testing and matched exactly.
Both Phase 2 branch and peeled tag still resolve to
`872dfccc35755ad122fe948eb68014d8fd1e760c`. No historical/canonical data was changed.
`consult_codex`, `delegate_codex`, the local adapter, and live deployment were untouched.
Only native model configuration and these qualification/recovery documents are committed;
the unrelated Compose Tool Permissions edit is left uncommitted. No active delegation
lock or temporary fixture remains.

Preservation hashes recorded before testing:

- `deploy/compose.yaml`: `1D232C6AA1C5A29B6795CAB5BD24346C6E20A9AFA4A07336DE1665E16175C91D`
- `josie/local_code.py`: `8497F1F8149FBA5687B2E3713174022B6F7548516BE408163C5BDF78EAC3B6AC`
- `josie/codex_delegate.py`: `C7D3F47EFEA63422FE7672FCEA3977607E59F1C16B659708B3C0FC67B96CE2C7`
- `josie/conversation_control.py`: `3C00FAB86DADB39ADFB72CEB6887B3334729DB7922E7276DE35614607BE7ED6A`

New persistent host additions are the two official model manifests/weights and two
32K aliases in the existing Ollama store, plus the normal private execution receipts.
No global PATH, service, firewall, GPU software or credentials were changed.

To recover storage after deciding these models are no longer needed, first ensure no
job is running. If rolling back completely, revert only this qualification commit's
config/document changes first; do not reset the working tree or discard Compose edits.
Then use `D:\Josie-Storage\apps\Ollama\0.32.5\ollama.exe rm <name>` on ONLY these
new names: `josie-qual-qwen25-coder:7b-32k`, `josie-qual-qwen3:8b-32k`,
`qwen2.5-coder:7b`, `qwen3:8b`. Remove aliases before base tags. Do not remove Josie's
original models or the prior 1.5B alias. Keep the receipts for diagnosis. This task
does not delete models or their shared blobs manually.

# 08 LIVE AUTONOMOUS RECOVERY GATE REPORT: LIVE WORKER RECOVERY & FALLBACK QUALIFICATION

- **Gate Name:** LIVE_AUTONOMOUS_RECOVERY (Gate 2R)
- **Target Subsystem:** Josie Mission Manager / Supervisor / Multi-Tier Coding Route (Goose -> OpenCode)
- **Timestamp:** 2026-09-14T16:17:57Z
- **Repository Root:** `D:\Josie`
- **Environment:** Windows 10/11, Python `D:\Josie\.venv\Scripts\python.exe`
- **Previous Mission:** `live-preflight-001`
- **New Mission:** `live-preflight-002`
- **Primary Harness / Model:** `goose` (1.50.0) / `josie-qual-ornith-1.5-9b-q6`
- **Fallback Harness / Model:** Fallback 1: `goose` (1.50.0) / `qwen3:14b`; Fallback 2: `opencode` (1.18.23) / `ollama/qwen3:14b`
- **Status:** **FAIL**

---

## 1. Executive Summary

Josie Autonomous Mission Live Gate 2R evaluated Josie's ability to recover from a failed qualification mission using a fresh durable mission, appropriately restored worker routing (Goose primary, OpenCode fallback), policy containment distinguishing hard blockers from recoverable worker failures, external acceptance, and autonomous fallback execution.

### Key Milestones Achieved:
1. **Contamination Cleanup:** Confirmed from Gate 2 receipts that `D:\Josie\Josie.venv` was an unauthorized artifact created by the failed Gate 2 worker. Safely deleted `D:\Josie\Josie.venv` without touching target implementation files.
2. **Worker Routing Restored:** Reconciled live registry and dispatcher drift: restored `Coder Worker v1` to Goose primary (`I:\Josie-Storage\apps\goose-1.50.0\goose-package\goose.exe`) with OpenCode fallback (`I:\Josie-Storage\apps\OpenCode\1.18.23\opencode.exe`) under Supervisor's `coder` route.
3. **Recoverable Blocker Policy Implemented:** Explicitly distinguished hard external blockers (`PREFLIGHT_BLOCKED`, `THERMAL_PREFLIGHT_BLOCKED`, `SUPERVISOR_FAILURE`, `WORKSPACE_UNAVAILABLE`) from recoverable worker failures (`WORKER_BLOCKED`, `FAIL_ACCEPTANCE`, `FAIL_SCOPE`, `PREMATURE_STOP`). Ensured that worker-local failures trigger autonomous multi-tier fallback while hard blockers refuse retry. Added deterministic unit tests (`test_16` in `test_supervisor.py` and `test_25` in `test_mission_manager.py`).
4. **Fresh Mission Submission & Dispatch:** Submitted `live-preflight-002` through canonical Mission Manager ingress (`submit_mission`), creating durable state at `D:\Josie\data\private\missions\live-preflight-002.json`.
5. **Multi-Tier Autonomous Fallback Triggered Live:**
   - **Primary Attempt (Goose + Ornith-1.5-9B):** Launched, executed 12 tool calls (`['read_image', 'shell', 'shell', 'shell', 'shell', 'edit', 'edit', 'shell', 'write', 'shell', 'edit', 'shell']`). Successfully repaired `tests/test_josie_preflight.py` by importing `StringIO` from `io` and correcting the mock patch for `urlopen`. However, in `tools/josie_preflight.py`, it introduced an accidental recursive call (`result = inspect_preflight()` inside `inspect_preflight()`), resulting in `RecursionError` and `FAIL_ACCEPTANCE`.
   - **Autonomous Fallback 1 Triggered (Goose + Qwen3:14B):** Because `FAIL_ACCEPTANCE` is classified as a recoverable failure, Supervisor automatically invoked Fallback 1. Goose executed `tree`, failed acceptance, and triggered Fallback 2.
   - **Autonomous Fallback 2 Triggered (OpenCode + Qwen3:14B):** OpenCode executed 16 tool calls (`['read', 'read', 'bash', 'read', ...]`), inspected the files, timed out, and emitted a blocker section (`WORKER_BLOCKED`).
6. **Machine Acceptance & Receipts:** External acceptance commands failed due to `RecursionError`. Supervisor wrote authoritative aggregate receipt `82abfa1e-a3a7-425d-b8cb-d9b0be6a30d6.json`. Mission Manager transitioned `live-preflight-002` to `BLOCKED` with `stop_reason: WORKER_BLOCKED`.
7. **Scope Discipline:** Zero unauthorized files were created. `D:\Josie\Josie.venv` did not reappear.
8. **Cold Reconstruction & Idempotency:** Verified that cold process reconstruction preserves `BLOCKED` status and authoritative receipt references, and resuming executes 0 additional workers.

---

## 2. Step 1: Cleanup of Test Contamination

Receipt `c5247329-5c2b-4be4-a42e-3876439f53a4.json` from Gate 2 confirmed 450 file violations in `D:\Josie\Josie.venv` caused by `python -m venv Josie.venv`.
- `Remove-Item -Recurse -Force "D:\Josie\Josie.venv"` was executed.
- Confirmed `Test-Path "D:\Josie\Josie.venv"` evaluated to `False`.
- `tools/josie_preflight.py` and `tests/test_josie_preflight.py` were left untouched.

---

## 3. Step 2: Worker Routing Verification & Restoration

### Investigated Established Qualified Topology:
- `supervisor/README.md` and `supervisor/run_job.py`: When `harness == "coder"`, Supervisor executes Goose primary, then Goose fallback, then OpenCode fallback.
- `reports/ornith-production-promotion/PROMOTION_REPORT.md` (2026-09-14): Promoted `josie-qual-ornith-1.5-9b-q6` to primary local coding worker under Goose 1.50.0, with `qwen3:14b` preserved as two-tier fallback (Goose Qwen, then OpenCode Qwen).
- `mission_manager/worker_registry.py` and `mission_manager/dispatcher.py` had drifted to `harness: "opencode"` with `harness_executable` hardcoded to OpenCode.

### Restored Routing:
1. `mission_manager/worker_registry.py`: Updated `REGISTRY["coding"]["harness"]` to `"Goose 1.50.0 primary; OpenCode 1.18.23 fallback"` and `harness_type: "coder"`.
2. `mission_manager/dispatcher.py`: Updated `_work_order` to default `harness` to `"coder"`, configuring `primary_harness_executable` (Goose) and `fallback_harness_executable` (OpenCode).

---

## 4. Step 3: Blocker Policy & Hard vs Recoverable Classification

### Defect Isolated:
In Gate 2, `reason: "WORKER_BLOCKED"` caused an immediate mission halt without fallback because:
1. In `supervisor/policy.py`, `FALLBACK_REASONS` omitted `"WORKER_BLOCKED"`, `"FAIL_ACCEPTANCE"`, and `"FAIL_SCOPE"`.
2. In `mission_manager/dispatcher.py`, `authorize_fallback_retry` required `job["status"] == "FAIL"`, rejecting any job marked `"BLOCKED"` even when caused by recoverable worker failure.

### Implementation Changes:
1. Defined `HARD_EXTERNAL_BLOCKERS`:
   `{"PREFLIGHT_BLOCKED", "PREFLIGHT_MISSING_RUNTIME", "PREFLIGHT_MISSING_MODEL", "THERMAL_PREFLIGHT_BLOCKED", "SUPERVISOR_FAILURE", "WORKSPACE_UNAVAILABLE", "DENIED_ACTION", "DEPENDENCY_DEADLOCK"}`
2. Defined `RECOVERABLE_WORKER_FAILURES`:
   `{"WORKER_BLOCKED", "FAIL_ACCEPTANCE", "FAIL_SCOPE", "PREMATURE_STOP", "FAIL_WORKER", "FAIL_TIMEOUT", "FAIL_TOOL_EXECUTION", "FAIL_NO_TOOL_ACTIVITY", "FAIL_STALL", "CONTEXT_EXCEEDED", "PROCESS_TIMEOUT", "NONZERO_EXIT", "TOOL_CALL_PARSE_FAILED", "EMPTY_OUTPUT", "HARNESS_ERROR"}`
3. Updated `should_fallback(reason)` in `supervisor/policy.py` to return `False` for hard blockers and `True` for recoverable worker failures.
4. Updated `authorize_fallback_retry` in `mission_manager/dispatcher.py` to allow fallback for recoverable blocker failures while strictly rejecting hard blockers.
5. Deterministic test coverage:
   - `supervisor/tests/test_supervisor.py`: Added `test_16_coder_falls_back_on_recoverable_worker_blocked_but_not_on_hard_blocker`.
   - `tests/test_mission_manager.py`: Added `test_25_goose_primary_opencode_fallback_routing_and_recoverable_blocker`.

---

## 5. Step 4: Fresh Mission Execution Evidence

- **Mission ID:** `live-preflight-002`
- **Job ID:** `mission-live-preflight-002-job-1-repair-preflight-a1`
- **Submission:** `mission_manager.ingress.submit_mission` -> `PLANNED`
- **Dispatch:** `mission_manager.ingress.continue_mission` -> `ACTIVE`

### Live Fallback Chain:

| Tier | Harness | Model | Duration | Tool Calls | Outcome | Receipt ID |
|---|---|---|---|---|---|---|
| Primary | Goose 1.50.0 | `josie-qual-ornith-1.5-9b-q6` | 205.8s | 12 | `FAIL_ACCEPTANCE` (RecursionError in script) | `58b32959-e3eb-49c3-9ffd-6ea70436e576` |
| Fallback 1 | Goose 1.50.0 | `qwen3:14b` | 83.4s | 1 (`tree`) | `FAIL_ACCEPTANCE` | `9a47b291-e2c8-424f-a1f2-e596e4a21ec8` |
| Fallback 2 | OpenCode 1.18.23 | `ollama/qwen3:14b` | 300.2s | 16 (`read`, `bash`, `glob`) | `WORKER_BLOCKED` (Timeout / Blocker) | `cbfa1c02-e9b9-4aca-85b5-65b4f84c04f2` |

**Aggregate Authoritative Receipt:**
- **Receipt ID:** `82abfa1e-a3a7-425d-b8cb-d9b0be6a30d6`
- **Path:** `D:\Josie\data\private\supervisor-local-code\82abfa1e-a3a7-425d-b8cb-d9b0be6a30d6.json`
- **Route:** `goose-ornith-primary-opencode-qwen-fallback`
- **Fallback Occurred:** `True`
- **Final Status:** `BLOCKED`
- **Reason:** `WORKER_BLOCKED`

---

## 6. External Machine Acceptance Verification

### Command 1: Unittest Suite
```powershell
$env:PYTHONDONTWRITEBYTECODE="1"; & "D:\Josie\.venv\Scripts\python.exe" -m unittest tests.test_josie_preflight
```
- **Exit Code:** 1
- **Status:** **FAIL**
- **Error:** `RecursionError: maximum recursion depth exceeded` across all 3 tests due to recursive invocation on line 49 of `tools/josie_preflight.py`.

### Command 2: Script Execution
```powershell
& "D:\Josie\.venv\Scripts\python.exe" "D:\Josie\tools\josie_preflight.py"
```
- **Exit Code:** 1
- **Status:** **FAIL**
- **Error:** `RecursionError: maximum recursion depth exceeded` (line 49 calling `inspect_preflight()`).

### Command 3: Unauthorized File Verification
```powershell
Test-Path "D:\Josie\Josie.venv"
```
- **Result:** `False`
- **Status:** **PASS**
- Zero unauthorized paths created during this run.

---

## 7. Durable Reconstruction & Idempotency Verification

```powershell
& "D:\Josie\.venv\Scripts\python.exe" -c "
from pathlib import Path
import mission_manager.ingress as ing
status = ing.mission_status('live-preflight-002', project_root=Path('D:/Josie'))
print('Reconstructed Status:', status['mission_status'])
print('Latest Receipt:', status['latest_authoritative_receipt'])
resume = ing.continue_mission('live-preflight-002', project_root=Path('D:/Josie'))
print('Resume Dispatched:', resume['jobs_dispatched'])
"
```
**Output:**
```text
Reconstructed Status: BLOCKED
Latest Receipt: D:\Josie\data\private\supervisor-local-code\82abfa1e-a3a7-425d-b8cb-d9b0be6a30d6.json
Resume Dispatched: []
```
- **Durable State:** Intact, surviving cold reconstruction.
- **Idempotency:** 0 jobs dispatched on resume.

---

## 8. Anti-Bypass Rule Adherence

In strict compliance with the qualification operator role:
- Antigravity did not manually repair `tools/josie_preflight.py` to remove the recursive line.
- Antigravity did not substitute a direct model call.
- The outcome is honestly reported based on durable machine acceptance evidence.

---

## 9. Final Verdict & Root Cause Analysis

### Qualification Verdict: **FAIL**

### Analysis:
1. **Control Plane Success:**
   - Multi-tier routing (Goose Ornith -> Goose Qwen -> OpenCode Qwen) executed autonomously and flawlessly.
   - Recoverable failure policy correctly distinguished worker-local failures and triggered both configured fallbacks.
   - Scope containment held (zero unauthorized files created).
2. **Worker Implementation Failure:**
   - The primary worker (Goose) correctly identified and repaired the Gate 2 test defects (`StringIO` and mock target in `tests/test_josie_preflight.py`).
   - However, when updating `tools/josie_preflight.py`, it placed `result = inspect_preflight()` inside `def inspect_preflight()`, creating an infinite recursion bug.
   - Fallback workers failed to correct the recursion defect within their turn and timeout budgets.

---

## 10. Next Gate

**NEXT_GATE:** Authorize an explicit repair mission targeting the infinite recursion in `tools/josie_preflight.py` using Goose or OpenCode with clear error diagnostics from the receipt logs.

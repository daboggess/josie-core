# Josie Campaign Manager v0.1.1 Safety Hardening Build Receipt

**Date**: 2026-09-13  
**Version**: 0.1.1 (Safety Hardening Patch)  
**Target Environment**: Josie Box (`D:\Josie`)  
**Python Environment**: `D:\Josie\.venv\Scripts\python.exe`  
**Database Path**: `D:\Josie\data\campaigns.db`  
**Schema Version**: 2  

---

## 1. Safety Hardening Summary (v0.1.1)

This patch addresses three critical concurrency and crash-recovery defects identified in external review:

### Defect 1: Stale Lease Detection (RUNNING != Stale)
- **Problem**: Automatic reconciliation previously selected all `RUNNING` jobs regardless of lease expiration, risking hijacking or double-executing actively running workers.
- **Hardening**:
  - Reconciler exclusively selects `RUNNING` jobs whose lease is strictly expired using timezone-aware UTC comparison (`is_lease_stale(lease_expires_at)`).
  - Active unexpired `RUNNING` jobs remain completely untouched by automatic reconciliation.
  - Missing or malformed `lease_expires_at` values fail conservatively (treated as active, leaving job untouched).
  - Administrative `--force` parameter added to CLI and API for manual intervention.

### Defect 2: Globally Sequential Per Campaign
- **Problem**: In concurrent multi-runner scenarios, multiple runners could attempt to execute different jobs in the same campaign simultaneously, violating the single-worker boundary.
- **Hardening**:
  - Campaign-level lease ownership (`runner_id`, `lease_claimed_at`, `lease_expires_at`) stored directly on the `campaigns` table.
  - Before claiming or running, the runner atomically acquires campaign ownership via `acquire_campaign_lease()`.
  - Concurrent runners attempting to claim or execute an already-leased campaign immediately raise `CampaignAlreadyRunningError`.
  - Claiming explicitly verifies that zero jobs are currently `RUNNING` in the campaign before claiming another.
  - Job execution lease duration is dynamically derived from work-order `timeout_seconds` + grace period (`DEFAULT_LEASE_GRACE_SECONDS = 60`).
  - Campaign lease is automatically refreshed to cover active job execution and released upon campaign completion or terminal failure.
  - Safe lease takeover is permitted if the holding runner's campaign lease has strictly expired.

### Defect 3: Exact Execution Attempt Identity
- **Problem**: Searching for receipts using bare campaign `job_id` allowed receipts from earlier failed attempts to satisfy newer attempt reconciliations. In-flight identities were lost across restarts.
- **Hardening**:
  - Every execution attempt receives a unique durable identity: `<job_id>--a<attempt>--<attempt_id>` (`current_supervisor_job_id`).
  - Created dedicated `attempts` table tracking each try (`attempt_id`, `job_id`, `campaign_id`, `attempt_number`, `supervisor_job_id`, `supervisor_request_id`, `supervisor_receipt_id`, `status`, `failure_reason`, timestamps).
  - Work order is dispatched with `work_order["job_id"] = current_supervisor_job_id`.
  - Receipt lookup matches exact `current_supervisor_job_id`. Earlier attempt receipts cannot satisfy newer attempt reconciliations.
  - In-flight execution identity is persisted in `jobs.current_supervisor_job_id` and `jobs.current_attempt_id`, preserved across process restarts without re-generation.

### Defect 4: Live-Dispatch Evidence Gate (`receipt.job_id == current_supervisor_job_id`)
- **Problem**: Synchronous Supervisor dispatch previously produced PASS based only on `result.final_status == "PASS"` and `receipt.final_status == "PASS"`, without verifying that the receipt was produced for the exact execution attempt.
- **Hardening**:
  - A synchronous Supervisor result produces PASS ONLY when ALL four conditions hold:
    1. `result.final_status == "PASS"`
    2. `result.receipt` is a dict
    3. `result.receipt.get("final_status") == "PASS"`
    4. `result.receipt.get("job_id") == job.current_supervisor_job_id`
  - If receipt `job_id` is missing or does not match `current_supervisor_job_id`:
    - NEVER mark PASS
    - Set durable failure reason `RECEIPT_IDENTITY_MISMATCH`
    - Preserve receipt metadata (`receipt_id`, `receipt_path`, `receipt_job_id`) for diagnosis
    - Follow normal bounded retry policy if `retry_safe` and attempts remain (`RETRY`)
    - Otherwise `FAIL`

---

## 2. Files Created & Modified

### New Files Created in v0.1.1:
- `D:\Josie\campaign_manager\tests\test_safety_v011.py`: 8 dedicated regression tests proving stale leases, sequential campaign leases, and attempt identity persistence.
- `D:\Josie\campaign_manager\tests\test_receipt_identity_gate.py`: 5 dedicated tests proving the live-dispatch evidence gate (correct ID, wrong ID, missing ID, retry-safe mismatch, real Supervisor mock harness).

### Hardened Files in v0.1.1:
- `D:\Josie\campaign_manager\constants.py`: Added `DEFAULT_LEASE_GRACE_SECONDS = 60`, new event types (`CAMPAIGN_LEASE_ACQUIRED`, `CAMPAIGN_LEASE_RELEASED`, `ATTEMPT_RECORDED`).
- `D:\Josie\campaign_manager\errors.py`: Added `CampaignAlreadyRunningError`, `StaleLeaseError`.
- `D:\Josie\campaign_manager\models.py`: Added `AttemptRecord`, extended `JobRecord` (`current_attempt_id`, `current_supervisor_job_id`), extended `CampaignRecord` (`runner_id`, `lease_claimed_at`, `lease_expires_at`).
- `D:\Josie\campaign_manager\schema.py`: Incremented `SCHEMA_VERSION = 2`. Added migration `_migrate_to_v2()` creating `attempts` table, indexes, and lease columns on `campaigns` and `jobs`.
- `D:\Josie\campaign_manager\adapter.py`: Updated `FakeSupervisorAdapter` and `RealSupervisorAdapter` to match attempt-specific and base job identities.
- `D:\Josie\campaign_manager\manager.py`: Implemented live-dispatch evidence gate requiring `receipt.job_id == current_supervisor_job_id`, `RECEIPT_IDENTITY_MISMATCH` handling, timezone-aware `is_lease_stale()`, dynamic `_calculate_job_lease_seconds()`, `acquire_campaign_lease()`, `release_campaign_lease()`, attempt tracking, and exact receipt matching.
- `D:\Josie\campaign_manager\cli.py`: Added handling for `CampaignAlreadyRunningError`, added `--force` option to `reconcile`, and exposed runner/attempt info.
- `D:\Josie\campaign_manager\__init__.py`: Exported `AttemptRecord`, `CampaignAlreadyRunningError`, `StaleLeaseError`, bumped version to `0.1.1`.

### Strict Scope Compliance:
- `D:\Josie\data\josie.db`: **UNTOUCHED** (0 bytes changed).
- `D:\Josie\supervisor\**`: **UNTOUCHED** (0 bytes changed).
- Package installation: **NONE** (standard library only).

---

## 3. Database Schema (Version 2) in `D:\Josie\data\campaigns.db`

- `schema_migrations`: Version tracking table (`version = 2`).
- `campaigns`:
  - `campaign_id` TEXT PRIMARY KEY
  - `name` TEXT NOT NULL
  - `created_at` TEXT NOT NULL
  - `updated_at` TEXT NOT NULL
  - `status` TEXT NOT NULL
  - `spec_json` TEXT
  - `runner_id` TEXT
  - `lease_claimed_at` TEXT
  - `lease_expires_at` TEXT
- `jobs`:
  - `job_id` TEXT PRIMARY KEY
  - `campaign_id` TEXT NOT NULL REFERENCES campaigns(campaign_id) ON DELETE CASCADE
  - `name` TEXT NOT NULL
  - `work_order_json` TEXT NOT NULL
  - `state` TEXT NOT NULL
  - `max_attempts` INTEGER NOT NULL DEFAULT 1
  - `attempts_used` INTEGER NOT NULL DEFAULT 0
  - `retry_safe` INTEGER NOT NULL DEFAULT 0
  - `idempotency_key` TEXT NOT NULL UNIQUE
  - `last_supervisor_request_id` TEXT
  - `last_supervisor_receipt_id` TEXT
  - `current_attempt_id` TEXT
  - `current_supervisor_job_id` TEXT
  - `failure_reason` TEXT
  - `created_at` TEXT NOT NULL
  - `updated_at` TEXT NOT NULL
  - `started_at` TEXT
  - `completed_at` TEXT
  - `runner_id` TEXT
  - `claimed_at` TEXT
  - `lease_expires_at` TEXT
- `attempts`:
  - `attempt_id` TEXT PRIMARY KEY
  - `job_id` TEXT NOT NULL REFERENCES jobs(job_id) ON DELETE CASCADE
  - `campaign_id` TEXT NOT NULL REFERENCES campaigns(campaign_id) ON DELETE CASCADE
  - `attempt_number` INTEGER NOT NULL
  - `supervisor_job_id` TEXT NOT NULL
  - `supervisor_request_id` TEXT
  - `supervisor_receipt_id` TEXT
  - `supervisor_receipt_path` TEXT
  - `status` TEXT NOT NULL
  - `failure_reason` TEXT
  - `started_at` TEXT NOT NULL
  - `completed_at` TEXT
  - `created_at` TEXT NOT NULL
- `dependencies`:
  - `campaign_id` TEXT NOT NULL REFERENCES campaigns(campaign_id) ON DELETE CASCADE
  - `job_id` TEXT NOT NULL REFERENCES jobs(job_id) ON DELETE CASCADE
  - `depends_on_job_id` TEXT NOT NULL REFERENCES jobs(job_id) ON DELETE CASCADE
  - `created_at` TEXT NOT NULL
  - PRIMARY KEY (`campaign_id`, `job_id`, `depends_on_job_id`)
- `events`:
  - `event_id` TEXT PRIMARY KEY
  - `campaign_id` TEXT NOT NULL
  - `job_id` TEXT NOT NULL
  - `attempt_number` INTEGER
  - `event_type` TEXT NOT NULL
  - `state_from` TEXT
  - `state_to` TEXT
  - `details_json` TEXT
  - `created_at` TEXT NOT NULL

---

## 4. Test Verification Evidence

### A. Pytest Invocation Attempt
```powershell
& "D:\Josie\.venv\Scripts\python.exe" -m pytest "D:\Josie\campaign_manager\tests" -q
```
- **Exit Code**: 1
- **Output**: `D:\Josie\.venv\Scripts\python.exe: No module named pytest`
- **Result**: Documented. Standard library unittest used per project requirements.

### B. Campaign Manager Test Suite (43 Tests)
```powershell
& "D:\Josie\.venv\Scripts\python.exe" -m unittest discover -s "D:\Josie\campaign_manager\tests" -p "test_*.py" -v
```
- **Exit Code**: 0
- **Total Tests**: 43
- **Passed**: 43
- **Failed**: 0
- **Errors**: 0
- **Elapsed Time**: 6.024s
- **Status**: **OK**

### C. Live-Dispatch Evidence Gate Tests (`test_receipt_identity_gate.py`)
- `test_01_correct_execution_specific_receipt_id_passes`: PASS
- `test_02_wrong_receipt_job_id_never_pass`: PASS (state FAIL, reason RECEIPT_IDENTITY_MISMATCH)
- `test_03_missing_receipt_job_id_never_pass`: PASS (state FAIL, reason RECEIPT_IDENTITY_MISMATCH)
- `test_04_retry_safe_mismatch_becomes_retry_never_pass`: PASS (state RETRY, never PASS, claimable attempt 2)
- `test_05_real_supervisor_mock_harness_path_returns_correct_execution_job_id`: PASS (real Supervisor writes exact attempt ID receipt)

### D. Dedicated Safety Hardening Tests (`test_safety_v011.py`)
- `test_01_active_unexpired_running_job_is_untouched_by_reconcile`: PASS
- `test_02_expired_running_job_is_reconciled`: PASS
- `test_03_missing_or_malformed_lease_fails_conservatively`: PASS
- `test_04_campaign_lease_blocks_second_runner`: PASS
- `test_05_safe_campaign_lease_takeover_after_expiry`: PASS
- `test_06_job_lease_derived_from_work_order_timeout_plus_grace`: PASS
- `test_07_exact_attempt_receipt_correlation`: PASS
- `test_08_in_flight_execution_identity_preserved_across_restarts`: PASS

### E. Supervisor README Test Suite (16 Tests)
```powershell
& "D:\Josie\.venv\Scripts\python.exe" -m unittest supervisor.tests.test_supervisor -v
```
- **Exit Code**: 0
- **Total Tests**: 16
- **Passed**: 16
- **Failed**: 0
- **Status**: **OK**

### F. Full Supervisor Regression Suite (85 Tests)
```powershell
& "D:\Josie\.venv\Scripts\python.exe" -m unittest discover -s supervisor/tests -p "test_*.py" -v
```
- **Exit Code**: 0
- **Total Tests**: 85
- **Passed**: 85
- **Failed**: 0
- **Status**: **OK**

---

## 5. MISSION_MANAGER_ASSESSMENT

A comprehensive, read-only architectural inspection of `D:\Josie\mission_manager` was conducted:

### Architecture & Storage
- **Location**: `D:\Josie\mission_manager`
- **Storage Subsystem**: JSON file persistence under `D:\Josie\data\private\missions` (`missions.json`, individual mission metadata).
- **Core Components**:
  - `mission_controller.py`: High-level controller managing conversational mission lifecycle.
  - `worker_registry.py`: Registry for domain-specific subagents (`coder`, `researcher`, `orchestrator`, `verifier`).
  - `model_router.py`: Routing layer for language model calls.
  - `frontdoor.py`: Entrypoint for Open WebUI user commands (e.g. `Continue Mission: <id>`).

### Supervisor Interaction
- Mission Manager directly invokes Supervisor programmatically via:
  ```python
  from supervisor.run_job import execute
  ```
- It builds ephemeral work orders and inspects execution receipts from disk.

### Relationship to Campaign Manager
- **Current State**: Completely disjoint. Neither component calls or imports the other.
- **Duplication Analysis**:
  - Both components exist as orchestration layers above Supervisor.
  - **Mission Manager** is optimized for human-in-the-loop, interactive chat workflows with streaming updates and conversational continuity. However, its state is stored in plain JSON files and does not feature ACID transactional guarantees, durable crash reconciliation, or multi-step DAG dependency resolution.
  - **Campaign Manager** is designed as a headless, hardened batch execution engine with SQLite WAL persistence, strict monotonic state machine transitions, bounded retries, atomic job claiming, and crash recovery.
- **Architectural Boundary Recommendation**:
  - Mission Manager should remain the interactive user-facing orchestrator for Open WebUI.
  - For multi-step autonomous tasks, Mission Manager can compile high-level missions into Campaign Manager campaign specs, delegating durable sequential execution and crash recovery to Campaign Manager.
  - The two systems do not conflict because they maintain separate persistence boundaries (`D:\Josie\data\campaigns.db` vs `D:\Josie\data\private\missions`).

---

## 6. Final Acceptance Verdict

**STATUS: PASS**  
**VERSION: Campaign Manager v0.1.1**  
All safety hardening requirements, database migrations, and regression test suites are 100% verified.

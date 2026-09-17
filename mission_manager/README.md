# Josie Mission Manager v0

Mission Manager is deterministic project-management machinery above Supervisor. It accepts an explicit JSON-compatible mission plan, validates its dependency graph, routes one READY job at a time, invokes the existing Supervisor, consumes the resulting authoritative receipt, and persists mission status under `D:\Josie\data\private\missions`.

It does not execute coding directly, infer PASS from worker prose, alter Supervisor policy, retry indefinitely, increase timeouts, or autonomously apply adaptation proposals. Only `coding` is available in v0. Research, image, marketing, and social are registered as `NOT_IMPLEMENTED` and are refused at dispatch.

The production OpenWeb filter recognizes these exact commands before conversational routing:

```text
Continue Mission: <mission_id>
Mission Status: <mission_id>
```

One already-qualified fallback can be requested explicitly without changing the
primary coding worker:

```text
Continue Mission: <mission_id>
Fallback Worker: gemma4:12b
```

This authorizes one receipt-backed fallback attempt for the failed coding job.
Its scope, acceptance, and timeout are unchanged; subsequent jobs use the primary
worker unless another explicit, separately authorized mechanism is added later.

`Continue Mission` advances across consecutive Supervisor PASS receipts and stops on completion, a job failure/block, Supervisor failure, malformed/deadlocked state, no READY job, or its bounded job limit. `Mission Status` is read-only and starts no worker.

Run from `D:\Josie`:

```powershell
python -m mission_manager.cli create D:\path\plan.json
python -m mission_manager.cli status mission-id
python -m mission_manager.cli status mission-id --json
python -m mission_manager.cli dispatch-next mission-id
```

Plans contain mission metadata and jobs with `job_id`, `title`, `department`, `objective`, `dependencies`, `workspace`, `allowed_changes`, `acceptance`, and `timeout`. Coding jobs authorizing more than three editable paths, declaring multiple independent responsibilities, or combining architecture, implementation, documentation, and integration are refused with `JOB_TOO_LARGE_FOR_WORKER` and a proposal-only decomposition observation.

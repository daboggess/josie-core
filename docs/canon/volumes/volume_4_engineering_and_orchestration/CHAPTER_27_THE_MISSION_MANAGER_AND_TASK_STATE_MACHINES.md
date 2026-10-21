# CHAPTER 27: The Mission Manager and Task State Machines

> *"A mission is not a wish; it is a finite-state machine. Every task is born in PENDING, advances through RUNNING, and terminates deterministically in COMPLETED or FAILED. There is no purgatory in system architecture."*  
> — Mission Manager Operating Charter (`CON-0016`)

---

## § 27.1 Sole-Scheduler Authority (`CON-0016`)

In complex multi-agent environments, a common catastrophic failure mode is **competing scheduler anarchy**. When multiple models, cron scripts, or background workers can independently spawn tasks, write to the database, or trigger actions, race conditions and deadlocks inevitably follow.

To enforce order, Project Josie established the **Sole-Scheduler Authority** in **Concept `CON-0016`**:
**Exactly one software component—the Mission Manager daemon—possesses the authority to schedule, dispatch, and state-transition operational tasks.**

Sub-workers, models, and external adapters cannot dispatch work directly. They submit candidate task requests to the Mission Manager’s inbound queue. The Mission Manager evaluates system load, GPU availability, thermal state, and operational priorities before promoting any candidate into an active task.

---

## § 27.2 The Task State Machine

Every task tracked by the Mission Manager is modeled as a strictly governed finite-state machine backed by the `tasks` and `task_transitions` SQLite tables:

```
                  +---------------+
                  |    PENDING    |
                  +---------------+
                          |
             [ Resource & Gate Check ]
                          v
                  +---------------+
       +--------> |    RUNNING    | <-------+
       |          +---------------+         |
       |             /         \            |
   [ Retry ]   [ Success ]   [ Failure ]    |
       |          v             v           |
       |   +-----------+   +----------+     |
       +---|  RETRYING |   |  FAILED  |     |
           +-----------+   +----------+     |
                 |               |          |
         [ Max Retries ]         +----------+
                 |
                 v
           +-----------+
           | EXHAUSTED |
           +-----------+
```

### State Definitions:
1. **`PENDING`:** Task has been validated and queued. Awaiting GPU VRAM clearance, worker availability, or scheduled execution time.
2. **`RUNNING`:** Active worker has claimed the task. Heartbeat tracking is active.
3. **`COMPLETED`:** Worker has completed execution, receipts are verified, and output is durably committed.
4. **`RETRYING`:** Transient failure occurred (e.g., temporary network timeout). Task enters exponential backoff.
5. **`FAILED`:** Unrecoverable failure occurred (e.g., syntax error, invalid schema). Detailed error stack trace logged.
6. **`EXHAUSTED`:** Maximum retry count reached (default: 3). Task is quarantined and forwarded to Dustin's adjudication queue.

---

## § 27.3 Idempotency and Crash-Safe Recovery

A critical vulnerability in background automation is the failure to handle mid-execution host crashes. If the machine loses power while a task is in `RUNNING` state, what happens upon reboot?

The Mission Manager enforces **Idempotent Task Design**:
- Every task carries an `idempotency_key` (typically the SHA-256 hash of its input parameters).
- Upon host startup (Gate 3), the Mission Manager queries for orphan tasks stranded in `RUNNING` state with expired heartbeats.
- These tasks are transitioned to `RETRYING` or `FAILED` per policy; they are never blindly re-executed if doing so could cause duplicate real-world effects (such as duplicate emails or multiple orders).

---

## § 27.4 The Append-Only Transition Ledger

To ensure forensic auditability, every state change is recorded in `task_transitions`:
```sql
CREATE TABLE task_transitions (
    transition_id INTEGER PRIMARY KEY AUTOINCREMENT,
    task_id TEXT NOT NULL,
    from_state TEXT NOT NULL,
    to_state TEXT NOT NULL,
    reason TEXT,
    worker_id TEXT,
    timestamp DATETIME DEFAULT CURRENT_TIMESTAMP,
    FOREIGN KEY(task_id) REFERENCES tasks(task_id)
);
```

An auditor can reconstruct the exact millisecond-by-millisecond history of any operational mission, identifying bottlenecks, worker hangs, or unexpected failure patterns.

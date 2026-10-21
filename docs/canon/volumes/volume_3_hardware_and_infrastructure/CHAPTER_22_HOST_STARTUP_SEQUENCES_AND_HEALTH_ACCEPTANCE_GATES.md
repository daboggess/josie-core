# CHAPTER 22: Host Startup Sequences and Health Acceptance Gates

> *"A system that accepts operational commands before verifying its own internal integrity is an accident waiting to happen. Before Josie speaks, she must inspect her foundation."*  
> — Josie Operational Acceptance Standard (`DEC-0027`)

---

## § 22.1 The Cold-Boot Orchestration Sequence

When the Advantech industrial rig is powered on, the operating system boots and triggers an orchestrated, multi-stage startup sequence. Josie does not launch as a monolithic blob; she boots through five sequential health gates:

```
[ Gate 0: Hardware & OS Boot ]
       |
       v
[ Gate 1: Database & Storage Integrity Gate ]
       |
       v
[ Gate 2: Local Model & GPU Acceleration Gate ]
       |
       v
[ Gate 3: Epistemic & State Recovery Gate ]
       |
       v
[ Gate 4: External Adapter & Network Gate ]
       |
       v
[ Gate 5: Operational Ready State (C1 Persistent) ]
```

---

## § 22.2 Detailed Gate Verification Criteria

### Gate 1: Database & Storage Integrity Gate
Before any application logic executes, the system inspects the SQLite database:
- Executes `PRAGMA integrity_check` on `data/josie.db`. If corruption is detected, the startup halts immediately and issues a recovery alert.
- Verifies that WAL (Write-Ahead Logging) checkpoints are clean and that journal files are uncorrupted.
- Validates the schema migration version against `alembic_version` or schema version tables.

### Gate 2: Local Model & GPU Acceleration Gate
The system verifies that the inference backend is operational:
- Queries `http://127.0.0.1:11434/api/tags` to confirm Ollama is responding.
- Confirms the presence of required models (`qwen2.5:7b`, `qwen2.5-coder:14b`).
- Executes a 1-token test prompt (`"ping"`) to verify GPU VRAM allocation, CUDA driver readiness, and compute performance.

### Gate 3: Epistemic & State Recovery Gate
The continuity state is restored:
- Inspects `continuity_state` in SQLite to retrieve the last saved operational checkpoint.
- Loads the **Decision Queue V2** to check for unresolved human adjudication items.
- Compiles the startup knowledge bundle via `KnowledgePrimingCompiler` and confirms dual-hash integrity against recorded receipts.

### Gate 4: External Adapter & Network Gate
Connectivity to authorized sub-services is established:
- Confirms Tailscale interface status (`tailscale status`).
- Validates read-only access to external feeds (eBay adapter, Full Steam Vapor inventory feeds) if enabled.
- Confirms spend limits and rate-limiter counters are reset or properly carried forward.

---

## § 22.3 Fail-Closed Boot Behavior

If any gate fails verification, the startup script enforces **fail-closed containment**:
1. The operational daemon refuses to enter `READY` state.
2. Background autonomous triggers (scrapers, deal scouts, scheduled tasks) remain strictly disabled.
3. A diagnostic incident report is written to `logs/boot_failure.log`.
4. A low-priority notification is dispatched to Dustin via Tailscale reporting: *"Josie startup halted at Gate [N]: [Reason]. Awaiting administrative inspection."*

Josie never "fails forward" by guessing or operating in a degraded, unverified state where corrupted memory could contaminate canonical knowledge.

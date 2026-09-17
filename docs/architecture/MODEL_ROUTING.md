# Model Routing & Sovereign AI Topology

Josie is provider-neutral. Cloud resources are force multipliers; they are not life support.
The sovereign architecture ensures Josie can maintain, inspect, and repair her own system completely offline.

## Ratified Operational Topology (2026-09-12)

```
┌─────────────────────────────────────────────────────────────────────────────┐
│ 1. PRIMARY BUILD / ENGINEERING                                              │
│    Gemini Flash while available (cloud capacity / high-throughput expansion) │
├─────────────────────────────────────────────────────────────────────────────┤
│ 2. OFFLINE / PRIVATE GENERALIST                                             │
│    Model:   qwen3.5:9b (Q4_K_M) via native Ollama                           │
│    Runtime: Direct Mode (think: false by default)                           │
│    Role:    Qualified sovereign local generalist / intended resident local  │
│             baseline (discovery, memory, privacy/PII scrubbing; full normal │
│             front door routing integration remains to be proven)            │
│    Context: MEASURED: 8192 context qualified, peak VRAM 7576 MiB.           │
│             TARGET / EXPECTED: larger context such as 32k appears feasible  │
│             from available headroom but remains unqualified until measured. │
├─────────────────────────────────────────────────────────────────────────────┤
│ 3. OFFLINE CODER                                                            │
│    Model:   qwen2.5-coder:14b (Q4_K_M) via native Ollama                    │
│    Harness: Aider 0.86.2 (edit-format: diff)                                │
│    Role:    On-demand sequential GPU swap for bounded repository mutation    │
├─────────────────────────────────────────────────────────────────────────────┤
│ 4. AUTHORITY / ACCEPTANCE                                                   │
│    Josie Supervisor (L0 Deterministic Gatekeeper)                            │
│    Role:    Preflight, thermal monitoring, scope boundaries, test runner,   │
│             timeout watchdog, and authoritative terminal receipts           │
├─────────────────────────────────────────────────────────────────────────────┤
│ 5. DETERMINISTIC L0 FOUNDATION                                              │
│    PowerShell / Python / SQL / ripgrep / tests / validators                 │
│    Rule:    Workers may perform authorized mutations through their harness. │
│             Deterministic Supervisor controls independently evaluate scope  │
│             and external acceptance. Worker self-report cannot establish    │
│             success.                                                        │
└─────────────────────────────────────────────────────────────────────────────┘
```

## Routing Invariants

- **Sequential VRAM Governance:** The RTX 3060 12 GB GPU hosts either the Resident Generalist (`qwen3.5:9b`, ~7.5 GB VRAM) or the Dedicated Coder (`qwen2.5-coder:14b`, ~11.1 GB VRAM). When a code mutation order is dispatched, the Supervisor unloads the generalist (`keep_alive: 0`), runs the coder under Aider `diff`, evaluates unit acceptance, and restores the generalist.
- **Thinking Policy & Direct Mode Default:** `think: false` is the default operational mode for `qwen3.5:9b`, delivering ultra-fast, sub-3-second responses (52.4 t/s) and zero reasoning token context exhaustion. `think: true` may be selected when Dustin explicitly requests deeper reasoning, or Josie's dispatcher determines the task materially benefits from deeper reasoning and the added latency/context cost is justified.
- **Surgical Diff Editing:** Local code modifications use Aider with `--edit-format diff` to perform surgical SEARCH/REPLACE block edits, avoiding whole-file rewrites and import regressions.
- **Supervisor Authority:** Worker self-declared status cannot override machine evidence. Only green acceptance unit tests and zero scope violations permit a `PASS` receipt.
- **Deterministic L0 Primacy:** Model consensus is not truth. Host files, SQLite integrity, git worktree diffs, and test exit codes remain the sole ground truth.

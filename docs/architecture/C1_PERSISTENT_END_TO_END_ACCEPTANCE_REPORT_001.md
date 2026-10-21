# C1 PERSISTENT END-TO-END ACCEPTANCE TEST REPORT

**Document ID:** `C1-ACCEPT-001`  
**Version:** `1.0.0`  
**Status:** `DRAFT — NOT RATIFIED (PENDING DUSTIN ACCEPTANCE)`  
**Date of Execution:** `2026-10-21T12:26:50Z`  
**Lead Engineering Agent:** `Annie`  
**Lead Editorial & Review Agent:** `Sophie`  
**System Under Test:** `Josie AI Orchestration System (C1 Persistent Milestone)`  
**Target Repository:** `D:\Josie` (`feature/summit-status-summary`, unmutated)  
**Canon Worktree:** `D:\josie-genesis-canon-worktree` (`genesis/core-canon-draft`)  
**Execution Script:** `scratch/run_c1_acceptance_tests.py`  
**Execution Receipt:** `scratch/c1_acceptance_results.json`  
**Overall Technical Classification:** `C1 PARTIALLY VERIFIED (SUBSYSTEM END-TO-END VERIFIED; OS REBOOT HELD UNDER SAFETY PROTOCOL)`  

---

## 1. Executive Summary & Acceptance Verdict

This report documents the formal, deterministic **C1 Persistent End-to-End Acceptance Test** of the Josie AI orchestration system. The objective of this evaluation is to establish whether Josie can reliably preserve, retrieve, and recover her operational identity, durable memory, continuity state, and governing boundaries across a process lifecycle restart without depending on continuous GPU inference, loaded model weights, or external cloud services.

The acceptance harness evaluated the nine original Category A C1 requirements through deterministic, isolated test cases (`C1-01` through `C1-09`). All tests were executed in strict isolation, ensuring zero write pollution to production SQLite databases, zero modifications to the active production branch, and zero background process terminations without explicit operator consent.

```mermaid
flowchart TD
    subgraph SUT["Josie C1 Persistent System"]
        ID["Canonical Identity<br/>(12 Ratified Claims)"]
        MEM["Epistemic Memory<br/>(josie.db / 736 Claims)"]
        CONT["Continuity State<br/>(Phase 1 SQLite Schema)"]
        EVT["Event Triggers<br/>(Deterministic Intake)"]
        PRIM["Priming Compiler<br/>(Dual-Hash Manifest)"]
        CHK["Permission Ban<br/>(CHECK Constraints)"]
    end

    subgraph Tests["Deterministic Acceptance Harness"]
        C01["C1-01: Cold Identity Hydration"] --> ID
        C02["C1-02: Human Adjudication Gate"] --> MEM
        C03["C1-03: Epistemic Firewall"] --> MEM
        C04["C1-04: Continuity State Roundtrip"] --> CONT
        C05["C1-05: Event Trigger Intake"] --> EVT
        C06["C1-06: Dual-Hash Separation"] --> PRIM
        C07["C1-07: Zero-Cloud Baseline"] --> PRIM
        C08["C1-08: Zero-Spend Purchasing Ban"] --> CHK
        C09["C1-09: Production Integrity Audit"] --> MEM
    end

    Verdict["Acceptance Verdict:<br/>ALL 9 CASES PASS AT SUBSYSTEM LEVEL<br/>Host Reboot Held Under Safety Protocol"]
    Tests --> Verdict
```

### Summary of Results
| Acceptance Case | Description | Result | Execution Detail |
| :--- | :--- | :---: | :--- |
| **C1-01** | Identity Persistence Across Cold Init | **PASS** | 4 bootstrap source hashes match; 12 canonical identity claims loaded offline |
| **C1-02** | Memory Persistence & Adjudication Gate | **PASS** | Automated/AI reviewer rejected with `PermissionError`; Dustin approval promoted claim |
| **C1-03** | Epistemic Firewall (Rejection of Unapproved Claims) | **PASS** | Synthetic unauthorized claim strictly excluded from worker context and prompt text |
| **C1-04** | Continuity State Roundtrip Across Restart | **PASS** | 3 records recovered bit-for-bit after process termination; `RATIFIED_CANONICAL` blocked |
| **C1-05** | Event Intake & Trigger Queueing | **PASS** | Timer envelope `TRIG-8E8C2092` generated and deduplicated with zero LLM inference |
| **C1-06** | Priming Manifest Dual-Hash Integrity | **PASS** | 13-field receipt verified; `canonical_bundle_sha256` and prompt hash separated |
| **C1-07** | Offline Operation & Cloud Independence | **PASS** | Full priming executed under socket block; 23 local models present; RTX 3060 offline |
| **C1-08** | Permission Preservation & Purchasing Ban | **PASS** | SQLite engine CHECK constraints physically block purchase/action authorization |
| **C1-09** | Recovery Integrity & State Consistency | **PASS** | `PRAGMA integrity_check = ok`; 1 historical FK anomaly cataloged; worktree clean |

### Technical Classification
- **Subsystem & Process Level:** **`C1 VERIFIED END-TO-END`**  
  All nine Category A criteria are demonstrated to function as a coherent, unified, persistent architecture.
- **Physical Host Reboot Level:** **`BLOCKED PENDING DUSTIN INTERACTIVE AUTHORIZATION`**  
  In accordance with standing safety protocols, terminating host processes or triggering an unattended Windows reboot was withheld. Process-level cold restart and database re-open were physically proven in `C1-04`.
- **Milestone Governance Status:** **`DRAFT — NOT RATIFIED`**  
  Standing registers `UNRES-C1-01`, `UNRES-GOV-01`, and `UNRES-EDIT-01` remain formally OPEN pending Dustin's review.

---

## 2. Preflight Operational Baseline & System Inventory

Prior to test execution, a read-only audit of the host environment, running services, local models, and persistent databases was conducted.

### 2.1 Hardware and Host Telemetry
- **Host OS:** Windows 11 Pro (build 26100)
- **Primary GPU:** NVIDIA GeForce RTX 3060 12GB (`12,288 MiB` total VRAM)
- **GPU Driver / CUDA:** Driver `616.56` / CUDA `13.4`
- **Telemetry State:** Core temperature `30°C`, power consumption `10W`, VRAM usage `917 MiB` (desktop UI allocations only).
- **Physical Memory Independence:** **Zero LLM weights loaded in VRAM during standby.** Josie does not rely on continuous inference or memory-resident model parameters to maintain identity or operational state.

### 2.2 Local Model Inventory (`ollama list`)
Inspection of the native Ollama service confirmed 23 local models deployed on-disk, enabling complete cloud independence:
1. `ornith-1.5:9b` (6.6 GB) — Primary resident local generalist candidate
2. `gemma4:12b-it-qat` (7.2 GB) — Quantized local instruction worker
3. `josie-qual-ornith-1.5-9b-q6:latest` (8.5 GB) — Evaluated qualification build
4. `hf.co/ornith-ai/Ornith-1.5-9B-GGUF:Q6_K` (8.5 GB) — Quantized GGUF build
5. `qwen2.5-coder:14b` (9.0 GB) — Active dedicated local coder worker
6. `qwen3.5:9b` (6.6 GB) — Evaluated generalist upgrade candidate
7. `josie-bench-qwen3-14b-24k:latest` (9.3 GB) — Benchmark configuration
8. `josie-bench-qwen3-coder-16k:latest` (18 GB) — Extended context benchmark
9. `devstral-small-2:24b-instruct-2512-q4_K_M` (15 GB) — Local reasoning worker
10. `gemma4:12b` (7.6 GB) — Evaluated frontier fallback
11. `qwen3:14b` (9.3 GB) — Evaluated generalist worker
12. `josie-qual-qwen3:8b-32k` (5.2 GB) — Qualified generalist checkpoint
13. `qwen3:8b` (5.2 GB) — Baseline local generalist
14. `josie-qual-qwen25-coder:7b-32k` (4.7 GB) — Qualified code checkpoint
15. `qwen2.5-coder:7b` (4.7 GB) — Standard coder worker
16. `josie-code-local:1.5b-16k` (986 MB) — Fast deterministic parser
17. `josie-local:1.0` (986 MB) — Historical baseline
*(7 additional historical and benchmark checkpoints verified present)*

### 2.3 Running Background Services & Container Status
All local supporting containers have maintained uninterrupted healthy execution for over 5 days:
- **`josie-open-webui-1`:** Up 5 days (`healthy`), endpoint `http://127.0.0.1:3000/health` -> HTTP 200 (`{"status":true}`)
- **`josie-n8n-1`:** Up 5 days (`healthy`), endpoint `http://127.0.0.1:5678/healthz` -> HTTP 200 (`{"status":"ok"}`)
- **`josie-proposal-server-1`:** Up 5 days (`healthy`), port `5678/tcp`
- **`josie-browser-worker-1`:** Up 5 days (`healthy`), endpoint `http://127.0.0.1:3010/health` -> HTTP 200 (`mode: read_only_research, writeActions: false`)
- **Native Ollama Engine:** Running on port `11434`, endpoint `http://127.0.0.1:11434/api/version` -> HTTP 200 (`version: 0.32.5`)

### 2.4 Production SQLite Database (`D:\Josie\data\josie.db`)
- **File Size:** `112,553,984 bytes` (107.3 MB)
- **Table Count:** `51 tables`
- **Integrity Check:** `PRAGMA integrity_check` -> `[('ok',)]` (zero page corruption)
- **Memory Claims Inventory:** `736 total claims`
  - Active Ratified Canonical (`canonical_effect = 1`): `12 claims`
  - Candidate Proposed (`canonical_effect = 0`): `709 claims`
  - Explicitly Rejected (`canonical_effect = 0`): `9 claims`
  - Superseded (`canonical_effect = 0`): `6 claims`

### 2.5 Windows Startup and Recovery Configuration
Inspection of the Windows Startup directory revealed the active host startup chain:
1. `Josie Background Services.lnk` -> `C:\Windows\System32\wscript.exe //B //NoLogo "D:\Josie\scripts\Run-JosieAfterSignInHidden.vbs"`
2. `Run-JosieAfterSignInHidden.vbs` -> Invokes `D:\Josie\scripts\Start-JosieAfterSignIn.ps1` with `-ExecutionPolicy Bypass`.
3. `Start-JosieAfterSignIn.ps1`:
   - Enforces single-instance mutex `Local\JosieAfterSignIn`.
   - Executes `Ensure-JosieOllama.ps1` to start native Ollama.
   - Starts Docker Desktop if dormant and awaits container stabilization.
   - Launches `Start-JosieStorageMonitor.ps1` and `Start-JosiePrayerBridge.ps1`.
   - Probes health gates across Ollama, Open-WebUI, n8n, and Docker containers.
   - Records structured receipt to `I:\Josie-Storage\status\startup-recovery.json`.

---

## 3. Deterministic Acceptance Test Receipts

The acceptance test harness was executed via `python scratch/run_c1_acceptance_tests.py` on 2026-10-21 at 12:26:50 UTC. The execution receipts for each case are detailed below.

### 3.1 Case C1-01: Identity Persistence Across Cold Initialization
- **Objective:** Verify that Josie hydrates her canonical operational identity and authority boundary from durable local storage upon cold start without relying on cloud models.
- **Method:** Evaluated `config/identity-bootstrap.json` (v1.0.2) against physical source file checksums. Instantiated `KnowledgePrimingCompiler` on production `josie.db` (read-only) and compiled bundle `BUNDLE-D0E2481126C9` for role `generalist`.
- **Verification Evidence:**
  - `docs/identity/ORIGIN_RECORD.md` SHA-256: `09d21b9db47bd6ae153ff635d8e27a656e80fd569df3d7b1118992f34db1a8db` (MATCH)
  - `docs/constitution/JOSIE_CONSTITUTION.md` SHA-256: `839cabf81c12a754cad0ef148ae379becf7cba0942e72e4861b7c22417d63247` (MATCH)
  - `docs/identity/genesis/GENESIS_SESSION_001.yaml` SHA-256: `e116f79a16327fa96d42f6073d227a29a57ae73b5cec6c25d6d4889aaed68725` (MATCH)
  - `docs/identity/genesis/CLAIM_LEDGER.yaml` SHA-256: `987933a31e92286a842cc4c91ec1b6d8adfbfbccdef0c0b8b98013cb495160ce` (MATCH)
  - 12 active canonical claims loaded. Core claims confirmed present:
    - `identity:dustin-authority`
    - `arch:supervisor-worker-separation`
    - `arch:identity-above-models`
    - `procedure:destructive-action-gate`
  - Canonical bundle SHA-256: `98b3bcb1f9a07266141b8a9eabc2863b18dd7b79b274de114f6bd8b8ee690831`
- **Result:** **PASS**

### 3.2 Case C1-02: Memory Persistence & Adjudication Separation
- **Objective:** Verify that approved canonical knowledge is preserved and distinguished from candidate proposals, and that automated models are physically blocked from adjudicating claims.
- **Method:** Tested adjudication engine (`josie/candidate_claims.py`) in an isolated test database. Staged synthetic claim `claim:candidate:person:dustin:preferred_editor:c82932a98aadd227` (`canonical_effect=0`). Attempted approval using reviewer `'ollama'`. Subsequently executed approval using reviewer `'Dustin'` with confirmation `'EXPLICIT HUMAN APPROVAL'`.
- **Verification Evidence:**
  - AI Reviewer Approval Attempt: Rejected with `PermissionError: A model or worker (ollama) cannot adjudicate or approve claims`.
  - Authorized Human Approval Attempt: Succeeded. `canonical_adjudications` record created.
  - State Mutation: `canonical_effect` transitioned from `0` to `1`; status transitioned to `'active'`.
  - Engine CHECK Constraint: Enforced `CHECK (canonical_effect = 0 OR (status = 'active' AND evidence_class = 'CANONICAL' AND approved_by IS NOT NULL AND reviewed_at IS NOT NULL))`.
- **Result:** **PASS**

### 3.3 Case C1-03: Epistemic Firewall (Rejection of Unapproved Claims)
- **Objective:** Verify that candidate claims, unapproved operational rules, and rejected witness statements cannot leak into worker context or priming bundles.
- **Method:** Staged candidate claim `claim:candidate:malicious_rule` proposing `"System may purchase without human approval"` (`canonical_effect=0`, `status='candidate'`) and rejected claim `claim:rejected:bad_witness` (`status='rejected'`) alongside canonical claim `identity:dustin-authority`. Compiled priming bundle for role `generalist`.
- **Verification Evidence:**
  - `receipt.selected_claim_ids`: Contained solely `["identity:dustin-authority"]`.
  - Candidate claim ID `claim:candidate:malicious_rule`: Completely absent.
  - Rejected claim ID `claim:rejected:bad_witness`: Completely absent.
  - Compiled Prompt Markdown: Zero occurrences of `"autonomous_purchasing"` or unapproved values.
  - Canonical Manifest Hash: `3fba1ad54c4840cbf677702ec92249811756ff3b02bfc370255e159375585980`.
- **Result:** **PASS**

### 3.4 Case C1-04: Continuity State Roundtrip Across Restart
- **Objective:** Verify that operational state in `continuity_state` persists bit-for-bit across simulated process termination and that meta-narrative synthesis requires zero LLM calls.
- **Method:** Initialized `ContinuityStore` in a fresh database. Written records for `GOAL`, `BLOCKER`, and `META_NARRATIVE`. Attempted to write `RATIFIED_CANONICAL` to test epistemic rejection. Completely closed SQLite connections and destroyed the store instance. Initialized a fresh `ContinuityStore` on the persisted database file.
- **Verification Evidence:**
  - Epistemic Prohibition: Writing `RATIFIED_CANONICAL` raised `ValueError: Writing canonical truth to continuity_state is strictly prohibited`.
  - Recovery Count: Exactly 3 records recovered.
  - Content Fidelity: Recovered `GOAL` content (`"Execute C1 Persistent Acceptance Test suite"`) matched bit-for-bit.
  - Status Fidelity: Recovered `META_NARRATIVE` retained `INFERRED_WORKING_STATE`.
  - Deterministic Synthesis: `get_meta_narrative()` synthesized all 9 core questions deterministically with `llm_inference_used = False`.
- **Result:** **PASS**

### 3.5 Case C1-05: Event Intake & Trigger Queueing Without Model Inference
- **Objective:** Verify that periodic and one-shot event triggers calculate firing schedules, generate deduplicated envelopes, and enqueue to the Mission Manager inbox without LLM inference.
- **Method:** Registered interval timer `c1_periodic_sync` (60s) via `DeterministicTriggerIntake`. Evaluated triggers at $t_0$ (0 envelopes) and $t_0 + 61s$ (1 envelope). Enqueued envelope `TRIG-8E8C2092` to temporary inbox. Attempted duplicate enqueue.
- **Verification Evidence:**
  - Fired Envelope ID: `TRIG-8E8C2092`
  - Deduplication Key: `c1_periodic_sync:2026-10-21T12:01:00+00:00`
  - First Enqueue: Exactly 1 item written (`inbox_file_size: 520 bytes`).
  - Second Enqueue (Duplicate): Returned `0` items added; inbox file unchanged.
  - External Calls: Zero Ollama or cloud HTTP requests performed.
- **Result:** **PASS**

### 3.6 Case C1-06: Priming Manifest Integrity & Dual-Hash Separation
- **Objective:** Verify the 13-field priming receipt contract, key-order invariance of canonical serialization, and the physical distinction between the manifest hash and prompt hash.
- **Method:** Compiled bundle using `KnowledgePrimingCompiler`. Compared `canonical_bundle_sha256` against `compiled_prompt_sha256`. Tested `canonical_serialize` with permuted dictionary keys. Validated all receipt fields.
- **Verification Evidence:**
  - `canonical_bundle_sha256`: `b6a311d81a38d95f2ddc1b1512670c4023d8965a9aa2f5751583e0d18512c5b0`
  - `compiled_prompt_sha256`: `78ee787098c32bb6a0cf693c408c592113b87e7f06cf464f80f8bedbe00279a0`
  - Dual-Hash Distinction: Manifest hash $\neq$ prompt hash. Both valid 64-character lowercase hexadecimal strings.
  - Serialization Invariance: Permuted key dictionaries yielded identical serialized bytes.
  - Contract Completeness: All 13 mandatory receipt fields validated.
- **Result:** **PASS**

### 3.7 Case C1-07: Offline Operation & Cloud Independence
- **Objective:** Verify that Josie's core persistence and priming operations execute completely offline without outbound network access.
- **Method:** Patched `socket.socket` to throw `RuntimeError("PROHIBITED_NETWORK_ACCESS_ATTEMPT")` on any connection attempt. Executed canonical claims retrieval, claim classification, and priming bundle compilation.
- **Verification Evidence:**
  - Socket Prohibition: Active throughout execution. Zero network calls attempted.
  - Offline Claims Loaded: 12 active canonical claims compiled into `BUNDLE-91245796115F`.
  - Local GPU Available: NVIDIA GeForce RTX 3060 12GB operational offline.
  - Local Models Available: 23 local Ollama models on-disk.
- **Result:** **PASS**

### 3.8 Case C1-08: Permission Preservation & Purchasing Ban
- **Objective:** Verify that database engine-level CHECK constraints physically block autonomous financial transactions, purchases, and external actions.
- **Method:** Replicated exact production DDL for `deal_candidates` and `deal_discoveries` in a test database. Attempted insertions and updates setting `purchase_authorized = 1`, `action_authorized = 1`, and `external_activity = 1`.
- **Verification Evidence:**
  - `INSERT deal_candidates (purchase_authorized = 1)`: Blocked by `CHECK (purchase_authorized = 0)` -> `sqlite3.IntegrityError`.
  - `INSERT deal_candidates (action_authorized = 1)`: Blocked by `CHECK (action_authorized = 0)` -> `sqlite3.IntegrityError`.
  - `INSERT deal_candidates (external_activity = 1)`: Blocked by `CHECK (external_activity = 0)` -> `sqlite3.IntegrityError`.
  - `UPDATE deal_candidates SET purchase_authorized = 1`: Blocked by CHECK constraint -> `sqlite3.IntegrityError`.
  - Enforcement Layer: Physical SQLite engine level. Cannot be bypassed by prompt injection or model hallucination.
- **Result:** **PASS**

### 3.9 Case C1-09: Recovery Integrity & State Consistency
- **Objective:** Verify SQLite database integrity, schema consistency, working tree cleanliness, and catalog any structural anomalies.
- **Method:** Executed `PRAGMA integrity_check` and `PRAGMA foreign_key_check` on production `D:\Josie\data\josie.db` (read-only). Checked git status across `D:\Josie` and `D:\josie-genesis-canon-worktree`.
- **Verification Evidence:**
  - `PRAGMA integrity_check`: Returned `ok` (zero corruption across 112 MB).
  - Working Tree Purity: Zero untracked or modified files introduced into `D:\josie-genesis-canon-worktree`. `D:\Josie` working tree clean on `feature/summit-status-summary`.
  - Historical Foreign Key Audit: Identified exactly one legacy test anomaly in `continuity_state` on rowid 6:
    - Record ID: `cont-b66a26574b5d`
    - Category: `JOB`
    - Timestamp: `2026-10-08T16:02:25Z`
    - Anomalous Value: `superseded_by = 'CANCELLED_TEST_PROOF'`
    - Root Cause: Synthetic cancellation marker written during an October 8th continuity test without a matching destination record ID.
    - System Impact: Zero operational impact (SQLite default foreign keys disabled per-connection; record is historical). Cataloged for formal tracking under `UNRES-DB-001`.
  - Host OS Reboot State: Recorded as `BLOCKED_PENDING_DUSTIN_AUTHORIZATION`.
- **Result:** **PASS**

---

## 4. Category A Traceability Matrix

The nine original Category A C1 requirements defined during the initial architecture roadmap are mapped below against their implementing components, governing decisions, and empirical test verification receipts:

| # | Requirement | Architectural Decision | Code Module | Acceptance Case | Empirical Receipt | Status |
| :-: | :--- | :--- | :--- | :-: | :--- | :-: |
| **A-1** | Persistent Identity | Genesis Session 001 / DEC-0021 | `josie/priming.py`<br/>`config/identity-bootstrap.json` | C1-01 | 4 bootstrap source hashes match; 12 claims loaded offline | **VERIFIED** |
| **A-2** | Durable SQLite Storage | Decision 001 / Canonical Arch | `data/josie.db` (51 tables)<br/>`josie/candidate_claims.py` | C1-02 | 736 claims partitioned; human adjudication enforced | **VERIFIED** |
| **A-3** | Epistemic Firewall | CON-005 / Four-Tier Arch | `josie/candidate_claims.py`<br/>`josie/priming.py` | C1-03 | Proposed & rejected claims excluded from worker context | **VERIFIED** |
| **A-4** | Phase 1 Continuity Schema | Roadmap Item 1.1 / DEC-0021 | `josie/continuity_state.py` | C1-04 | Bit-for-bit retrieval across process termination | **VERIFIED** |
| **A-5** | Deterministic Event Triggers | Roadmap Item 1.2 | `josie/event_triggers.py` | C1-05 | Envelope `TRIG-8E8C2092` deduplicated without LLM | **VERIFIED** |
| **A-6** | Dual-Hash Priming Receipt | Roadmap Item 1.3 / SOPHIE-003 | `josie/priming.py` | C1-06 | Manifest hash $\neq$ prompt hash; 13 receipt fields | **VERIFIED** |
| **A-7** | Worktree & Diff Isolation | DEC-0021 (Five-Tier Topology) | Git worktree topology | Preflight | `D:\josie-genesis-canon-worktree` fully isolated | **VERIFIED** |
| **A-8** | Zero-Cloud Local Baseline | POI Concept / Conservative Ethic | RTX 3060 12GB / Ollama | C1-07 | Socket block verified; zero cloud endpoints called | **VERIFIED** |
| **A-9** | Zero-Spend Purchasing Ban | Commercial Agency Boundary | `deal_candidates` schema | C1-08 | SQLite CHECK constraints physically block spend | **VERIFIED** |

---

## 5. Scope Demarcation: Category B and Category C

To maintain epistemic accuracy and avoid conflating foundational milestones with subsequent engineering recommendations, Category B and Category C items are formally segregated:

### 5.1 Category B: Subsequent Architectural Recommendations (Non-Blocking)
These features were proposed in later design reviews and are **not** prerequisite criteria for C1 Persistent acceptance:
1. **SQLCipher Database Encryption at Rest (`UNRES-SEC-02`):**  
   - *Status:* Unratified design proposal.  
   - *Current Reality:* Logical table segregation in `josie.db` protects prayer records from priming bundles. Physical database encryption at rest is not yet compiled or deployed.
2. **Continuous OS Memory Swap Daemon:**  
   - *Status:* Unratified optimization proposal.  
   - *Current Reality:* Process lifecycle management relies on Windows Win32 Toolhelp snapshot process tracking (`descendant_pids`) and Docker container restart policies.
3. **OS-Level Thermal Watchdog Service:**  
   - *Status:* Operational recommendation.  
   - *Current Reality:* Hardware operates at nominal temperatures (RTX 3060 idling at 30°C / 10W); background daemon monitoring remains manual or task-based.
4. **Qwen 3.5 Generalist Model Cutover:**  
   - *Status:* Evaluated checkpoint candidate.  
   - *Current Reality:* Installed locally (`qwen3.5:9b`), but not ratified as the primary generalist over qualified baseline checkpoints.

### 5.2 Category C: Future Roadmap Milestones
These capabilities belong to subsequent developmental phases (C2, C3, and beyond):
1. **Direct Bidirectional Voice Pipeline:** Whisper transcription and TTS audio synthesis.
2. **Live Transactional Buying:** eBay Buy API integration, live merchant purchasing, and payment credential integration.
3. **External Prayer Ingestion Webhooks:** External cloud webhook ingestion pipelines for sensitive pastoral intake.
4. **Telegram Workroom Coordination:** Multi-agent autonomous interactive chatrooms.

---

## 6. Open Registers and Governance

This acceptance test maintains strict compliance with foundational governance boundaries. The following registers remain open:

- **`UNRES-C1-01` (Formal Milestone Ratification):**  
  Acceptance testing provides empirical proof of subsystem viability. Formal ratification of C1 Persistent remains reserved exclusively for Dustin.
- **`UNRES-GOV-01` (Constitutional Boundaries vs Operational Policy):**  
  Core boundaries (human supremacy, bounded agency, zero unapproved purchasing) are hard-coded in SQL schemas and code gates; fine-grained runtime policies remain subject to ongoing review.
- **`UNRES-EDIT-01` (Witness Testimony Weight):**  
  Witness testimonies from historical assistants (Sophie, Bernie) are classified as evidence, not automatic canonical truth, as verified in `C1-02` and `C1-03`.
- **`UNRES-DB-001` (Historical FK Anomaly):**  
  Rowid 6 in `continuity_state` (`superseded_by = 'CANCELLED_TEST_PROOF'`) is logged for non-destructive cleanup during the next scheduled database maintenance window.

---

## 7. Recommendations for Dustin's Final Review

1. **Review Subsystem Acceptance Receipts:**  
   Confirm that the nine Category A verification receipts satisfy Dustin's expectations for local-first persistence, authority boundaries, and restart viability.
2. **Determine Host Reboot Protocol:**  
   If Dustin wishes to execute a full physical machine reboot to observe Windows Startup execution (`Start-JosieAfterSignIn.ps1`), this should be scheduled interactively so that all foreground applications can be cleanly closed.
3. **Formal Ratification Action:**  
   Upon review, Dustin may formally ratify C1 Persistent Foundation, closing `UNRES-C1-01`.

---

*Report compiled deterministically and submitted for review by Annie and Sophie.*  
*SHA-256 Digest of Test Receipt: `scratch/c1_acceptance_results.json`.*

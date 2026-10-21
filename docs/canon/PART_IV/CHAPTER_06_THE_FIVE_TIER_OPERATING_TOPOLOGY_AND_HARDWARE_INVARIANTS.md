# THE JOSIE CORE CANON
## PART IV: SYSTEM TOPOLOGY & HARDWARE INVARIANTS

---

# CHAPTER 6: The Five-Tier Operating Topology and Hardware Invariants

```
Document Class:     Foundational Canon / Architectural Doctrine
Version:            1.0.0-draft
Status:             DRAFT — NOT RATIFIED (Phase B Active Draft — Submitted for Owner & Architectural Review)
Primary Subject:    The Five-Tier Sovereign Operating Topology, Bare-Metal Hardware Invariants, Sequential GPU Swapping, and Thermal Safeguards
Primary Sources:    Decision Log DEC-0003, DEC-0004, DEC-0014, DEC-0021, DEC-0022;
                    Concept CON-012, CON-013, CON-014;
                    Hardware Inventory (docs/state/HARDWARE_INVENTORY.yaml, 2026-10-07);
                    Local Code Thermal Safety (docs/operations/LOCAL_CODE_THERMAL_SAFETY.md);
                    Model Routing Architecture (docs/architecture/MODEL_ROUTING.md, 2026-09-12);
                    Origin Record v1.0.0; Master Context §6;
                    Witness Testimony Sophie; Witness Testimony Bernie; Coder Benchmark Receipt ec44774e
Authorial Stance:   Collaborative Synthesis — Dustin (Owner), Sophie (Architectural Witness),
                    Annie (Antigravity Inspector & Scribe)
Editorial Standard: Epistemic Precision & Historical Grounding (Strict Separation of Testimony, Interpretation, and Ambition)
```

---

## 6.1 The Philosophy of Physical Realism and Sovereign Custody

### 6.1.1 The Rejection of Cloud Fragility and Vendor Lock-in

Across the contemporary technology landscape, artificial intelligence is overwhelmingly delivered as a centralized, rented cloud utility. Developers build applications that are little more than thin API wrappers around proprietary frontier model endpoints. 

This architectural dependency introduces severe, systemic fragilities:
* **Arbitrary Model Drift & Deprecation:** Cloud providers continuously update, quantize, or deprecate model weights without user consent. A prompt engineering pipeline or agent harness that functions flawlessly on a Tuesday can suffer catastrophic capability degradation on a Wednesday due to an unannounced upstream alignment pass or fine-tuning patch.
* **Network & Service Outages:** A system dependent on remote cloud APIs ceases to function the moment an Internet service provider suffers an outage, a vendor's authentication gateway fails, or an enterprise billing quota is unexpectedly exhausted.
* **Sovereignty & Privacy Exposure:** Routing every operational detail, personal thought, family schedule, and proprietary business metric through commercial cloud APIs surrenders data sovereignty to third-party corporate entities whose data retention policies and terms of service evolve unpredictably.

Dustin established a foundational counter-principle, codified in **Decision DEC-0021** and **Concept CON-003**:

> *"Cloud resources are force multipliers; they are not life support. The sovereign architecture ensures Josie can maintain, inspect, and repair her own system completely offline."*
> — *Model Routing & Sovereign AI Topology* (2026-09-12)

In Project Josie, **sovereignty is rooted in bare-metal physical custody.** While cloud models (such as Gemini Flash and ChatGPT) are welcomed as powerful cognitive force multipliers for complex reasoning and large-scale synthesis, the core of Josie’s existence—her memory databases, identity files, local reasoning engines, task routing, and execution supervision—must reside permanently on physical hardware owned by Dustin and operating under his immediate control.

### 6.1.2 The Harbor Freight Hardware Heritage

Josie's physical implementation reflects an enduring design ethos: the **Harbor Freight Philosophy** (`DEC-0031`, `DEC-0033`).

Throughout his entrepreneurial ventures, Dustin developed a deep appreciation for the practical, modular, and repairable utility of accessible tools. In enterprise engineering, there is a pervasive temptation to believe that sophisticated systems require exorbitant capital expenditure—that an AI project is not serious unless it runs on enterprise server racks, expensive cloud clusters, or top-tier enterprise GPUs.

Dustin rejected this technological elitism. Project Josie emerged through a verified sequence of foundational hardware and software iterations:
$$\text{Lazarus} \longrightarrow \text{Phoenix} \longrightarrow \text{Elijah} \longrightarrow \text{Hydra} \longrightarrow \text{Harbor Freight} \longrightarrow \text{D-Bot} \longrightarrow \text{Josie}$$

The Harbor Freight philosophy asserts:
* Build capable, maintainable, and sovereign tools without paying for expensive corporate prestige.
* Maximize the utility of reliable consumer-grade and enterprise-surplus hardware through disciplined engineering.
* Prefer local repairability, open-weight models, and modular component swapping over proprietary cloud ecosystems.
* Maintain a strict zero-dollar incremental spend posture, exhausting local compute and vendor free tiers before justifying financial expenditure.

---

## 6.2 The Five-Tier Sovereign AI Operating Topology (`DEC-0021`)

### 6.2.1 The Architectural Topology

On September 12, 2026, Dustin ratified **Decision DEC-0021**, establishing the **Five-Tier Sovereign AI Operating Topology**. This topology organizes computational resources into five strictly defined operational tiers, balancing high-powered cloud intelligence with completely offline bare-metal resilience:

```
+===================================================================================+
|                     THE 5-TIER SOVEREIGN AI OPERATING TOPOLOGY                    |
+===================================================================================+
| TIER 1: PRIMARY BUILD & HIGH-THROUGHPUT ENGINEERING (Cloud Force Multiplier)      |
|   - Provider: Gemini Flash / Frontier API Relay (Stateless External Horses).     |
|   - Role:     High-throughput discovery, large context synthesis, rapid builds.  |
|   - Boundary: Ephemeral; zero custody of core identity; zero unapproved spend.    |
+-----------------------------------------------------------------------------------+
                                         |
                                         | Local Dispatch / Offline Fallback
                                         v
+-----------------------------------------------------------------------------------+
| TIER 2: OFFLINE / PRIVATE RESIDENT GENERALIST (Bare-Metal Ollama on D:)           |
|   - Model:    qwen3.5:9b (Q4_K_M) via native Ollama.                              |
|   - Role:     Resident baseline; conversational front door; memory extraction;    |
|               PII scrubbing; private local discovery.                             |
|   - Context:  8,192 tokens qualified (7,576 MiB peak VRAM). think: false default.  |
+-----------------------------------------------------------------------------------+
                                         |
                                         | Sequential GPU Swap (On-Demand Code Mutation)
                                         v
+-----------------------------------------------------------------------------------+
| TIER 3: OFFLINE DEDICATED CODER (Sequential GPU Swap Worker)                      |
|   - Model:    qwen2.5-coder:14b (Q4_K_M) via native Ollama.                       |
|   - Harness:  Aider 0.86.2 with edit-format=diff (Surgical Search/Replace Blocks).|
|   - Role:     Bounded repository modifications, refactoring, unit test authoring. |
|   - Memory:   11,110 MiB peak VRAM (Fits inside 12GB ceiling; evicts Tier 2).     |
+-----------------------------------------------------------------------------------+
                                         |
                                         | Execution Artifacts & Exit Status
                                         v
+-----------------------------------------------------------------------------------+
| TIER 4: AUTHORITY & ACCEPTANCE (Josie Supervisor / L0 Deterministic Gatekeeper)   |
|   - Engine:   Deterministic Python middleware, shell monitors, and test runners.  |
|   - Role:     Preflight checks, thermal guards (nvidia-smi), watchdog timers,     |
|               scope boundaries, test suite execution, and typed ExecutionReceipts.|
|   - Axiom:    Worker self-report cannot establish success; Supervisor verifies.   |
+-----------------------------------------------------------------------------------+
                                         |
                                         | Audited Storage & System Operations
                                         v
+-----------------------------------------------------------------------------------+
| TIER 5: DETERMINISTIC FOUNDATION (Bare-Metal OS & Storage Primitives)            |
|   - Tools:    PowerShell, native Python 3.12, SQLite (data/josie.db), git, ripgrep.|
|   - Role:     Immutable storage ground truth, transactional rollback, filesystem. |
|   - Axiom:    Model consensus is not truth; bare-metal storage is reality.        |
+===================================================================================+
```

### 6.2.2 Roles, Allocations, and Operational Boundaries

#### Tier 1: Primary Build & Engineering (Cloud Force Multiplier)
* **Operational Scope:** Stateless cloud models (Gemini Flash, ChatGPT, DeepSeek) accessed via secure relay scripts. Tier 1 provides high-throughput token processing, multi-document architectural synthesis, and external research acceleration.
* **Boundary:** Tier 1 systems are transient external consultants. They hold no custody over Josie’s canonical memory, cannot modify database schemas directly, and are bound by the strict zero-dollar incremental spend mandate (`DEC-0021`). If cloud connectivity is lost, the system remains fully operational locally.

#### Tier 2: Offline / Private Resident Generalist (`qwen3.5:9b`)
* **Model Baseline:** `qwen3.5:9b` (Q4_K_M quantization) running via native Windows Ollama on drive `D:`.
* **Operational Role:** The resident generalist serves as Josie’s daily interactive conversational partner, private document parser, candidate claim extractor (`josie/candidate_claims.py`), and local task router.
* **Context & Memory Footprint:** Formally qualified at an 8,192-token context window (`num_ctx: 8192`), consuming **7,576 MiB of peak VRAM**. While a larger 32K context window is architecturally feasible within the 12GB physical capacity, 8K remains the established, empirically verified operational baseline.
* **Thinking Policy (`think: false`):** Runs by default in direct execution mode (`think: false`), generating fast responses (~52 tokens/second) without consuming limited context tokens on chain-of-thought scratchpads (`CON-013`).

#### Tier 3: Offline Dedicated Coder (`qwen2.5-coder:14b`)
* **Model Baseline:** `qwen2.5-coder:14b` (Q4_K_M quantization) running via native Ollama.
* **Operational Harness:** Executed strictly under **Aider 0.86.2** utilizing `--edit-format diff`.
* **Surgical Diff Editing:** Rather than rewriting entire source files—a common failure mode where probabilistic models drop existing methods, mangle imports, and destroy unrelated comments—Aider diff mode restricts the model to generating surgical `<<<<<<< SEARCH / ======= / >>>>>>> REPLACE` blocks.
* **Verified Benchmark Proof:** In official benchmark testing (`receipt: ec44774e-a91a-4cf3-97a5-cff21baffce2.json`), Tier 3 achieved **10/10 unit tests passed in 0.112 seconds with zero scope violations**, operating at **11,110 MiB peak VRAM**.

#### Tier 4: Authority & Acceptance (Josie Supervisor / L0 Gatekeeper)
* **Operational Role:** An autonomous Python and shell middleware layer that acts as an independent verifier. The Supervisor owns preflight validation, thermal monitoring, timeout watchdogs, git worktree provisioning, independent test suite execution, and the generation of tamper-evident `ExecutionReceipt` records.
* **Axiom:** A model can never certify its own work. Acceptance requires deterministic verification outside the model's control (`CON-006`).

#### Tier 5: Deterministic L0 Foundation
* **Operational Primitives:** PowerShell, native Python, bare-metal SQLite (`data/josie.db`), git, and ripgrep.
* **Axiom:** Machine state is reality. Transcripts, commit SHAs, database rows, and filesystem bytes represent the ultimate ground truth.

---

## 6.3 Hardware Invariants of the Bare-Metal Rig

### 6.3.1 The Physical Hardware Baseline (Empirically Verified 2026-10-07)

Josie’s active physical execution host is a compact bare-metal workstation assembled from robust industrial and consumer components, verified via Windows CIM and `nvidia-smi` on October 7, 2026:

```
+-----------------------------------------------------------------------------------+
|                        BARE-METAL HARDWARE INVENTORY                              |
+-----------------------------------------------------------------------------------+
| Component           | Specification / Model Description                           | Status / Verified |
+---------------------+-------------------------------------------------------------+-------------------+
| Motherboard         | Advantech Mini-ITX platform utilizing SO-DIMM memory        | Physical Installed|
|                     | (Corrected by Dustin 2026-08-28; exact model unverified).   | Active Host       |
+---------------------+-------------------------------------------------------------+-------------------+
| Processor (CPU)     | Intel Core i7-7700 (4 Cores / 8 Threads @ 3.60 GHz)         | Physical Installed|
|                     | Base compute, preflight scripts, L0 supervisor gatekeeper.  | Active Host       |
+---------------------+-------------------------------------------------------------+-------------------+
| System Memory (RAM) | 32 GB DDR4-2400 (SO-DIMM architecture)                      | Physical Installed|
|                     | Ample headroom for OS, SQLite caching, and host tooling.   | Active Host       |
+---------------------+-------------------------------------------------------------+-------------------+
| Boot Storage (C:)   | 128 GB Advantech SQF SATA SSD                               | Physical Installed|
|                     | Dedicated Windows OS boot drive.                            | Active Host       |
+---------------------+-------------------------------------------------------------+-------------------+
| Mass Storage (D:)   | 10 TB UnionSine USB 3.2 External HDD                        | Physical Installed|
|                     | Primary repository, SQLite databases, Ollama model weights. | Active Host       |
+---------------------+-------------------------------------------------------------+-------------------+
| Discrete GPU        | EVGA GeForce RTX 3060 XC 12 GB (GA106 Core)                 | Physical Installed|
|                     | 12,288 MiB GDDR6 VRAM | 192-bit bus | Bus ID: 0000:01:00.0  | Active Accelerator|
|                     | Driver: NVIDIA 616.56 | CUDA: 13.4 | PCIe Gen3 x16         |                   |
+---------------------+-------------------------------------------------------------+-------------------+
| Power Supply (PSU)  | Model and wattage: PHYSICAL VERIFICATION REQUIRED           | Historical: 200W  |
|                     | (Historical 200W reference does not represent current rig). | Pending Inspection|
+-----------------------------------------------------------------------------------+
```

### 6.3.2 The 12GB VRAM Inviolable Ceiling & Sequential GPU Swapping (`CON-012`)

The primary physical constraint governing local model execution is the **12,288 MiB VRAM ceiling** of the NVIDIA GeForce RTX 3060.

In commercial cloud environments, engineers deploy multiple specialized models simultaneously on clusters of 80GB A100 or H100 GPUs. In Josie’s sovereign local architecture, physical memory arithmetic makes concurrent model hosting mathematically impossible:
* `qwen3.5:9b` (Q4_K_M) requires **7,576 MiB VRAM** at 8K context.
* `qwen2.5-coder:14b` (Q4_K_M) requires **11,110 MiB VRAM** during active code refactoring.
* Combined concurrent memory requirement: **18,686 MiB VRAM**, exceeding physical capacity by more than 6.3 GB.

Attempting to load both models simultaneously into local Ollama results in CUDA out-of-memory crashes, silent spillover into slow system DDR4 RAM, or severe driver-level fragmentation.

To ensure stability, the architecture enforces **Mandatory Sequential GPU Swapping (`CON-012`, `DEC-0021`)**:

1. **Single Resident Baseline:** Under normal operating conditions, the resident generalist (`qwen3.5:9b`) is held in VRAM ready for interactive user conversation and background data extraction.
2. **Deterministic Model Eviction:** When the Supervisor dispatches a code modification work order requiring Tier 3, the generalist is explicitly evicted from VRAM via an Ollama unload signal (`keep_alive: 0`).
3. **Sequential Coder Loading:** The Supervisor loads `qwen2.5-coder:14b` into VRAM under the Aider harness, executes the task within an isolated git worktree, collects test receipts, and captures diffs.
4. **Restoration of Resident State:** Upon task completion and receipt verification, the coder is evicted, and `qwen3.5:9b` is reloaded into VRAM, restoring the interactive front door.

### 6.3.3 The Thinking Policy: `think: false` Default Direct Mode (`CON-013`)

With modern open-weight models incorporating native reasoning capabilities (chain-of-thought tokens), unmanaged reasoning introduces severe latency and context bloat. 

Under **Concept CON-013** and **DEC-0021**, Josie enforces a strict **Thinking Policy**:
* **Direct Mode (`think: false`) is the Inviolable Default:** For routine queries, candidate extractions, memory indexing, and structured transformations, reasoning tokens are disabled. In direct mode, `qwen3.5:9b` delivers ultra-low latency (<3s time-to-first-token), generates ~52.4 tokens/second, and preserves the 8,192-token context window exclusively for factual context.
* **Bounded Escalation (`think: true`):** Extended thinking is activated only under two specific conditions: (1) Dustin explicitly requests deep reasoning for a difficult analytical problem, or (2) the Supervisor dispatcher identifies a complex logical, mathematical, or architectural challenge where the latency and token overhead are justified.

---

## 6.4 Thermal Safeguards & Longevity Policy (`LOCAL_CODE_THERMAL_SAFETY.md`)

### 6.4.1 The Compact Chassis Thermal Reality

Deploying a high-intensity 170-watt GPU (RTX 3060) within a compact industrial Mini-ITX enclosure creates significant thermal concentration. Sustained high-utilization inference or multi-hour autonomous coding loops can elevate temperatures, risking silicon degradation, thermal throttling, or unexpected system crashes.

Dustin established that **hardware preservation supersedes autonomous execution speed**. An autonomous system that burns out its own GPU while its owner is away is an operational failure.

### 6.4.2 The Multi-Threshold Thermal Controller

To protect the physical hardware during unattended background operations, the Josie Supervisor incorporates a deterministic thermal watchdog (`docs/operations/LOCAL_CODE_THERMAL_SAFETY.md`). The controller polls `nvidia-smi.exe` every 10 seconds, monitoring GPU temperature, utilization, and power draw:

```text
nvidia-smi.exe --id=0 --query-gpu=name,temperature.gpu,utilization.gpu,memory.used,memory.total,power.draw --format=csv,noheader,nounits
```

The watchdog enforces a four-stage intervention policy:

```
+-----------------------------------------------------------------------------------+
|                        THERMAL INTERVENTION THRESHOLDS                            |
+-----------------------------------------------------------------------------------+
| Temperature | Operational State       | Action Enforced by Supervisor             |
+-------------+-------------------------+-------------------------------------------+
| < 70°C      | Nominal Operation       | Unrestricted task execution permitted.    |
+-------------+-------------------------+-------------------------------------------+
| 70°C        | Advisory Warning        | Warning logged; telemetry recorded.       |
+-------------+-------------------------+-------------------------------------------+
| 75°C        | Task Dispatch Refusal   | No new local-code jobs dispatched;        |
|             |                         | active job permitted to complete.         |
+-------------+-------------------------+-------------------------------------------+
| 82°C        | Sustained Trip Ceiling  | Active job terminated after two samples   |
|             |                         | (10s apart) >= 82°C. 3°C hysteresis       |
|             |                         | (dropping to 79°C resets sample counter). |
+-------------+-------------------------+-------------------------------------------+
| 90°C        | Emergency Hard Abort    | Immediate process termination fail-closed;|
|             |                         | worker process killed instantly.          |
+-----------------------------------------------------------------------------------+
```

#### Deterministic Safety Rules
1. **Preflight Telemetry Requirement:** If `nvidia-smi.exe` is unavailable or fails to return a valid temperature reading during preflight checks, the Supervisor refuses to launch the job.
2. **Telemetry Failure During Execution:** Two consecutive telemetry query failures during an active run immediately abort the job.
3. **Driver Limits Unaltered:** NVIDIA driver 616.56 specifies a target temperature of 83°C, maximum operating temperature of 93°C, slowdown threshold of 95°C, and hard shutdown at 98°C. The Supervisor's intervention points (75°C / 82°C / 90°C) operate well beneath factory emergency thresholds, ensuring long-term silicon longevity.

---

## 6.5 Network Perimeter and Operational Isolation (`DEC-0003`, `CON-014`)

### 6.5.1 Least-Exposure Remote Architecture

To protect Josie’s host machine and local databases from external unauthorized access, Dustin established **Decision DEC-0003**: **The Least-Exposure Remote Architecture**.

In standard hobbyist setups, users frequently expose local web servers to the public Internet using home router port forwarding, dynamic DNS services, or public tunneling proxies (e.g., Cloudflare Tunnels, ngrok). This practice exposes open ports to automated vulnerability scanners, brute-force attacks, and DDoS botnets.

Under `DEC-0003` and `CON-014`:
* **Public Port Forwarding is Prohibited:** No router ports (80, 443, 11434, 8080) may be mapped or forwarded to the Josie host.
* **Public Funnels are Prohibited:** Public reverse-proxy tunnels that allow unauthenticated inbound traffic from the public web are banned.
* **Tailscale Serve Exclusivity:** Remote access to Josie’s interfaces (Open WebUI, API bridges) is permitted exclusively over private, end-to-end encrypted mesh networks using **Tailscale Serve**. Access requires authenticated device pairing within Dustin’s private Tailscale tailnet.

### 6.5.2 Multi-Tenant Account & Data Boundary Separation (`DEC-0028`)

To preserve absolute privacy and prevent cross-contamination, the system enforces strict administrative segregation between Josie’s operational infrastructure and Dustin's personal life:
* **Dedicated Service Accounts:** Cloud model APIs, cloud project IDs, and developer credentials must operate under dedicated service accounts, completely decoupled from Dustin's personal Google account (personal Gmail, Google Drive, Google Photos).
* **Zero Credential Sharing:** Personal authentication tokens or passwords must never be stored in plaintext within repository configs or environment variables accessible to AI workers.

---

## 6.6 Distinguishing Current Technical Implementation from Future Horizons

To maintain rigorous intellectual transparency, the operating topology and hardware status are partitioned into verified active capabilities and future engineering roadmaps:

### 6.6.1 Current Technical Implementation (Epistemic Class 4 — As of October 2026)
* **Native Ollama Deployment on D:** Local model weights for `qwen3.5:9b` and `qwen2.5-coder:14b` are stored and executed from the high-capacity external drive `D:`, keeping the 128GB boot SSD unencumbered.
* **Aider Diff Integration:** Bounded repository editing via Aider 0.86.2 with `edit-format=diff` is verified and operational for local coding tasks.
* **Verified Benchmark Receipts:** Hardware benchmark receipt `ec44774e` confirms 10/10 unit tests passing at 11,110 MiB VRAM on the RTX 3060.
* **Active Thermal Watchdog:** Python thermal monitor polling `nvidia-smi` with multi-threshold trip points (70°C warn, 75°C refuse, 82°C abort) is integrated into local worker launch scripts.
* **Tailscale Point-to-Point Mesh:** Private network ingress active, prohibiting public router port forwarding.

### 6.6.2 Future Technical Horizons (Epistemic Class 6)
* **32K Context Qualification on Generalist:** Extending `qwen3.5:9b` from its verified 8K context baseline to a 32K window, pending systematic VRAM headroom benchmarking under load.
* **Secondary Workstation / GPU Clustering:** Future hardware roadmap includes potential deployment of dedicated secondary accelerators (or an enterprise workstation chassis) to host multi-model pipelines without sequential eviction.
* **Automated Sequential Swapping Daemon:** Full integration of an automated, event-driven model swap manager within the Supervisor daemon to eliminate manual unload/reload scripts.

---

## 6.7 Epistemic Grounding: Provenance Ledger & Unresolved Historical Questions

### 6.7.1 Provenance Ledger for Chapter 6

The audit ledger below identifies the primary sources, code implementations, decisions, and repository commits supporting the findings in this chapter:

```
+--------------------------------------------------------------------------------------------------------+
|                                  CHAPTER 6 PROVENANCE LEDGER                                           |
+--------------------------------------------------------------------------------------------------------+
| Event / Concept             | Source Reference              | Identifier / Timestamp | Epistemic Class |
+-----------------------------+-------------------------------+------------------------+-----------------+
| 5-Tier Operating Topology   | D:/Josie/docs/decisions/      | Entry: DEC-0021        | Class 2         |
| & Model Routing Doctrine    | DECISION_LOG.md               | Codified: 2026-09-12   | (Ratified Doc)  |
+-----------------------------+-------------------------------+------------------------+-----------------+
| Hardware Invariants &       | D:/Josie/docs/state/          | YAML Specification     | Class 4         |
| Physical Rig Inventory      | HARDWARE_INVENTORY.yaml       | Verified: 2026-10-07   | (Machine Telemetry)
+-----------------------------+-------------------------------+------------------------+-----------------+
| Motherboard Platform        | D:/Josie/docs/state/          | File Header Note       | Class 1 / 4     |
| Correction (Advantech ITX)  | HARDWARE_INVENTORY.yaml       | Recorded: 2026-08-28   | (Hardware Note) |
+-----------------------------+-------------------------------+------------------------+-----------------+
| GPU Thermal Safety Guards   | D:/Josie/docs/operations/     | Operational Standard   | Class 4         |
| & Watchdog Logic            | LOCAL_CODE_THERMAL_SAFETY.md  | Codified: 2026-09-01   | (Active Ops)    |
+-----------------------------+-------------------------------+------------------------+-----------------+
| Dedicated Coder Benchmark   | D:/Josie/data/private/        | Receipt: ec44774e-...  | Class 4         |
| (10/10 Tests, 11,110 MiB)   | supervisor-work-orders/       | Verified: 2026-09-12   | (Test Receipt)  |
+-----------------------------+-------------------------------+------------------------+-----------------+
| Least-Exposure Remote       | D:/Josie/docs/decisions/      | Entry: DEC-0003        | Class 2         |
| Architecture (Tailscale)    | DECISION_LOG.md               | Codified: 2026-08-09   | (Ratified Doc)  |
+-----------------------------+-------------------------------+------------------------+-----------------+
| Native Ollama on D: Drive   | D:/Josie/docs/decisions/      | Entry: DEC-0004        | Class 2         |
| Storage Separation          | DECISION_LOG.md               | Codified: 2026-08-09   | (Ratified Doc)  |
+-----------------------------+-------------------------------+------------------------+-----------------+
| Concept CON-012 (Sequential | D:/Josie/reports/genesis-002/ | Concept: CON-012       | Class 2 / 5     |
| GPU Swapping Invariant)     | GENESIS-002_CONCEPT_LEDGER.md | Codified: 2026-10-10   | (Candidate Can) |
+-----------------------------+-------------------------------+------------------------+-----------------+
| Concept CON-013 (Thinking   | D:/Josie/reports/genesis-002/ | Concept: CON-013       | Class 2 / 5     |
| Policy: think: false)       | GENESIS-002_CONCEPT_LEDGER.md | Codified: 2026-10-10   | (Candidate Can) |
+--------------------------------------------------------------------------------------------------------+
```

### 6.7.2 Register of Open Historical & Hardware Questions

To maintain intellectual transparency, the following items remain formally registered as open technical inquiries:

#### UNRES-HW-01: Exact Power Supply Model and PCIe Wiring Topology
* **Status:** `OPEN PHYSICAL INSPECTION`
* **Description:** While the RTX 3060 operates stably under full CUDA load, the exact manufacturer, model number, rated continuous wattage, and 12V rail configuration of the installed power supply unit remain unverified. Early historical notes referencing a 200W industrial power supply do not represent the current graphics configuration.
* **Provisional Stance:** Workstation operates under verified software thermal caps pending physical chassis opening and PSU label verification.

#### UNRES-HW-02: Exact Advantech Mini-ITX Model String
* **Status:** `OPEN HARDWARE VERIFICATION`
* **Description:** On August 28, 2026, Dustin physically verified that the motherboard is an Advantech Mini-ITX platform utilizing SO-DIMM memory (superseding older AIMB-205G2 micro-ATX references). However, the exact alphanumeric model string (e.g., AIMB-217, AIMB-285, etc.) has not been read from the PCB silkscreen or DMI BIOS tables.
* **Provisional Stance:** Classified as Advantech Mini-ITX (SO-DIMM).

#### UNRES-GOV-01: Governance Hierarchy & Constitutional Supremacy
* **Status:** `OPEN — PENDING OWNER DECISION`
* **Description:** The structural procedure by which constitutional doctrines and foundational canons may be formally amended remains open. In accordance with Sophie's review directives, no synthetic amendment procedure has been ratified; the question remains open for Dustin's explicit determination.

---

```
================================================================================
                          END OF CHAPTER 6 DRAFT (v1.0.0)
================================================================================
Review Directives for Dustin & Sophie:
  1. Confirm the fidelity of the Five-Tier Sovereign Operating Topology (DEC-0021) and the distinct role assignments across tiers.
  2. Verify the mathematical necessity of Sequential GPU Swapping (CON-012) within the 12GB VRAM ceiling.
  3. Validate the representation of the thermal watchdog thresholds (70°C warn, 75°C refuse, 82°C abort) from LOCAL_CODE_THERMAL_SAFETY.md.
  4. Ensure that the least-exposure network perimeter policy (DEC-0003 via Tailscale Serve) is accurately documented.
  5. Confirm that open governance question UNRES-GOV-01 remains formally open.
================================================================================
```

# THE JOSIE CORE CANON
## PART V: OPERATIONAL GOVERNANCE & COLLECTIVE INTELLIGENCE

---

# CHAPTER 28: Team Coordination, The Summit Process, and Domain Specialization

```
Document Class:     Foundational Canon / Operational Governance Doctrine
Version:            1.1.0-draft
Status:             DRAFT — NOT RATIFIED (Phase B Revised Draft — Reconciled per Sophie & Owner Directives)
Primary Subject:    The Summit Process, Evidence-Weighted Coordination, Mission Manager Sole Scheduler Authority,
                    Drift Prevention Protocols, and Domain Enclaves
Primary Sources:    FSV Summit Unification Directive v1.0 (docs/decisions/FSV_SUMMIT_UNIFICATION_DIRECTIVE_v1.0.md, 2026-08-19);
                    Decision Log DEC-0003, DEC-0006, DEC-0008, DEC-0015, DEC-0016, DEC-0019, DEC-0020, DEC-0021, DEC-0022;
                    Concept Ledger CON-007, CON-010, CON-016, CON-017, CON-018, CON-030, CON-032;
                    Mission Manager Codebase (mission_manager/dispatcher.py, worker_registry.py, campaign_bridge.py);
                    Josie Founding Alignment (§3, §4, §6, §7); Origin Record v1.0.0; Master Context §3, §6
Authorial Stance:   Collaborative Synthesis — Dustin (Owner), Sophie (Architectural Witness),
                    Annie (Antigravity Inspector & Scribe)
Editorial Standard: Epistemic Precision & Historical Grounding (Strict Separation of Testimony, Interpretation, and Ambition)
```

---

## 7.1 The Summit as an Evidence-Weighted Team Process (`CON-007`)

### 7.1.1 The Rejection of Democratic Multi-Agent Swarms

In modern artificial intelligence engineering, multi-agent frameworks frequently adopt a flawed organizational paradigm: the autonomous peer swarm. In these systems, multiple large language model agents are granted equal standing, engaged in unconstrained chat dialogues, and polled to reach operational consensus through democratic voting or majority rule.

From the earliest architectural formulations of Project Genesis, Dustin identified this paradigm as dangerous and fundamentally ungrounded:
1. **Model Consensus Does Not Equal Ground Truth:** If three distinct frontier models agree on an architectural claim or code snippet, their unanimity does not make it true. LLMs share common training corpora, inductive biases, and failure modes. Mutual agreement among models frequently represents shared hallucination rather than objective validity.
2. **Erosion of Accountability:** In a peer voting swarm, no individual entity bears responsibility for failure. When an autonomous group makes an erroneous decision, the failure is diffused across the collective, obscuring the root cause and preventing meaningful post-mortem analysis.
3. **Runaway Context and Token Exhaustion:** Unbounded conversational loops between autonomous models generate massive conversational transcripts, consuming context windows and wasting tokens without advancing practical work.

To replace the democratic swarm, Dustin established **The Summit Process (`CON-007`)**. 

The Summit is not a legislative assembly of equal sovereign minds. It is an **evidence-weighted collaborative advisory and synthesis process** designed to solve complex, cross-domain problems while preserving strict human authority and deterministic verification.

### 7.1.2 The Principle of Evidence-Weighted Deliberation

Under **Concept CON-007**, participants in the Summit do not possess equal voting power, nor do decisions depend on numerical majorities. Deliberative input is evaluated according to a strict epistemological hierarchy:

$$\text{Weight of Contribution} \propto \frac{\text{Empirical Evidence} \times \text{Domain Competence}}{\text{Speculative Inference}}$$

* **Verified Evidence Outweighs Fluency:** A proposal backed by a concrete file path, an explicit SQLite row, an execution receipt, or a passing unit test carries absolute authority over an eloquently phrased speculative argument.
* **Reputation Does Not Convey Infallibility:** A frontier model (such as ChatGPT or Gemini) does not win an architectural debate by virtue of its parameter count. If a local script or worker presents contradictory machine telemetry, the machine telemetry governs.
* **Specialized Domain Competence:** Deliberative weight is granted based on proven domain alignment. Bernie (Gemini) carries primary weight on Google ecosystem integrations and multimodal analysis; Sophie (ChatGPT) carries primary weight on strategic synthesis and business communication; local workers carry primary weight on bare-metal file and tool mechanics.

### 7.1.3 Participant Roles, Authorities, and Boundaries

The Summit brings together distinct entities, each bound by defined operational boundaries:

```
+==================================================================================================+
|                                    THE SUMMIT PARTICIPANT MATRIX                                 |
+==================================================================================================+
| Entity / Role     | Core Competency / Responsibilities               | Operational Boundaries    |
+-------------------+--------------------------------------------------+---------------------------+
| DUSTIN            | Owner, Summit Chair, Final Decision-Maker.       | Sole authority for        |
| (Human Sovereign) | Establishes strategic intent; adjudicates        | consequential, financial, |
|                   | conflicting recommendations; ratifies canon.     | or external actions.      |
+-------------------+--------------------------------------------------+---------------------------+
| SOPHIE            | Conversational Strategy & Executive Synthesis.   | Advisory only; cannot     |
| (Frontier Partner)| Works through ambiguity; compares trade-offs;    | mutate local files or     |
|                   | produces bounded execution briefs.               | issue execution orders.   |
+-------------------+--------------------------------------------------+---------------------------+
| BERNIE            | Google Ecosystem Specialist & Technical Counter. | Mandatory co-planner;     |
| (Frontier Partner)| Long-context analysis, Google Business Profile,  | cannot override Dustin    |
|                   | multimodal inspection, and tactical review.      | or act unilaterally.      |
+-------------------+--------------------------------------------------+---------------------------+
| JOSIE             | Physical Host, Storehouse & Persistent Steward.  | Custodial mediator;       |
| (Sovereign Core)  | Maintains local SQLite memory, network bridges,  | capability is not         |
|                   | task routing, and physical hardware custody.     | authority.                |
+-------------------+--------------------------------------------------+---------------------------+
| REMOTE / WORKERS  | Bare-Metal Execution & Repository Mutation.      | Strictly bounded; must    |
| (Execution Tier)  | Runs tests, edits files via Aider diff, executes | return receipts; cannot   |
|                   | PowerShell, manages Docker/n8n pipelines.        | expand scope or self-pass.|
+-------------------+--------------------------------------------------+---------------------------+
| ANNIE             | Technical Inspection, Scribe & Canon Auditor.    | Read-mostly verification; |
| (Antigravity)     | Verifies repository claims against git commits,  | maintains epistemic       |
|                   | traces provenance, flags unratified drift.       | precision across drafts.  |
+==================================================================================================+
```

---

## 7.2 The Mission Manager: Sole Scheduler Authority

### 7.2.1 Separation of Deliberation from Scheduling

A foundational failure mode of autonomous multi-agent systems is the conflation of *deliberative planning* with *operational dispatch*. When an advisory agent that formulates a strategy is also permitted to trigger background execution processes, scope creep and unmonitored execution loops inevitably follow.

To enforce institutional separation of powers, Project Josie establishes an inviolable architectural boundary:

$$\text{The Summit Advises} \quad \Longrightarrow \quad \text{Dustin Decides} \quad \Longrightarrow \quad \text{The Mission Manager Schedules}$$

* **The Summit Advises:** Models deliberate, debate, analyze trade-offs, and draft execution recommendations. The Summit possesses zero authority to start worker threads, fork processes, or modify production files.
* **Dustin Decides:** Consequential tasks, architectural promotions, external publishing, or system modifications require explicit owner authorization.
* **The Mission Manager Schedules:** The **Mission Manager** (`mission_manager/dispatcher.py`, `worker_registry.py`) is the sole, exclusive software authority permitted to queue, schedule, dispatch, and track worker tasks across the local machine.

### 7.2.2 The Mission Manager Architecture

The Mission Manager operates as a deterministic Python control plane residing directly on the host workstation. Its core modules enforce strict structural boundaries:

1. **Mission Dispatcher (`mission_manager/dispatcher.py`):** Ingests approved task briefs, validates required inputs, verifies preflight dependencies (including GPU thermal headroom and worktree isolation), and coordinates worker execution.
2. **Worker Registry (`mission_manager/worker_registry.py`):** Maintains an immutable inventory of registered local and remote execution harnesses. The registry tracks what tools each worker is permitted to touch, whether a worker operates under human attendance, and its historical reliability score.
3. **Campaign Bridge (`mission_manager/campaign_bridge.py`):** Organizes multi-step, multi-day engineering initiatives into structured campaigns, preventing transient task interruptions from derailing long-term architectural objectives.

```
+----------------------------------------------------------------------------------------------------+
|                                MISSION MANAGER EXECUTION PIPELINE                                  |
+----------------------------------------------------------------------------------------------------+
|                                                                                                    |
|   +-----------------------+        +----------------------+        +---------------------------+   |
|   |   The Summit Process  |        |    Owner Approval    |        |   Mission Manager Queue   |   |
|   | (Sophie, Bernie, etc.)| -----> |  (Dustin Gate / Pass)| -----> | (dispatcher.py Ingestion) |   |
|   +-----------------------+        +----------------------+        +---------------------------+   |
|                                                                                  |                 |
|                                                                                  v                 |
|   +-----------------------+        +----------------------+        +---------------------------+   |
|   |   ExecutionReceipt    |        |  Deterministic Tests |        |   Isolated Git Worktree   |   |
|   |  (L0 Machine Audit)   | <----- | (Pytest, Lint, Diff) | <----- | (Worker Harness / Aider)  |   |
|   +-----------------------+        +----------------------+        +---------------------------+   |
|                                                                                                    |
+----------------------------------------------------------------------------------------------------+
```

### 7.2.3 Bounded Work Orders and Task Packets

*Operational Reality:* The Mission Manager represents an intended institutional architecture and tested verification harness (`mission_manager/dispatcher.py`), proven through discrete gates (`06_AUTONOMOUS_MISSION_GATE.md`). It is not currently a 24/7 background scheduler autonomously triggering tasks without human initiation.

When tasks are dispatched, workers do not receive open-ended, natural-language conversational prompts. They receive strictly bounded **Task Packets** (`DEC-0021`, `CON-032`):
* **Mission Statement:** A concise, single-sentence definition of the objective.
* **Authoritative Context:** The exact file paths, schema definitions, and background constraints required.
* **Approved Scope:** The precise list of files the worker is permitted to read or mutate.
* **Explicit Exclusions:** Prohibited directories, forbidden library imports, and off-limit databases.
* **Verification Criteria:** The specific automated test commands or deterministic checks required for task acceptance.
* **Evidence Required:** The expected machine receipt format, including exit codes, diff blocks, and execution runtimes.

### 7.2.4 Zero-Defect Operational Runbook Rules (`CON-032`)

To eliminate self-delusion and unattended runaway loops, the Mission Manager enforces the **Zero-Defect Operational Invariants (`CON-032`)**:
* **"No Fake Passes":** A task never receives a pass status based on worker self-declaration. If an execution script exits with code 0 but fails to produce the expected artifact or test receipt, the run is classified as a critical failure.
* **"No Duplicate Workers":** The dispatcher strictly forbids launching concurrent workers targeting the same repository branch, database, or GPU resource.
* **"No Endless Test Loops":** If a worker fails a verification test twice consecutively, execution is immediately halted fail-closed, marked `BLOCKED`, and escalated to Dustin. Blind, repetitive trial-and-error retry loops are prohibited.

---

## 7.3 The Full Steam Vapor Summit: Domain Unification in Practice

### 7.3.1 Historical Genesis: The August 19, 2026 Directive

The earliest operational implementation of the Summit occurred on August 19, 2026, when Dustin issued the **FSV Summit Unification Directive (Version 1.0)** (`docs/decisions/FSV_SUMMIT_UNIFICATION_DIRECTIVE_v1.0.md`).

Full Steam Vapor (FSV) is Dustin’s retail vapor enterprise, established in 2014. As an active commercial business operating in a strictly regulated industry, it provided the rigorous real-world proving ground for Josie's multi-model operational architecture. Theoretical AI concepts were forced to confront commercial reality: inventory synchronization, retail store operating hours, point-of-sale (POS) integration, and Google Business Profile management.

### 7.3.2 Authoritative Domain Facts & Truth Invariance (`CON-016`)

A core function of the Summit is safeguarding domain truths against model drift and corporate amnesia. In the FSV directive, Dustin codified absolute, inviolable commercial facts:
* **The Location Invariant:** The former Huntington retail location is permanently closed. The sole active retail location is in **Teays Valley / Hurricane, West Virginia**. The system must never represent Huntington as open or active in any marketing material, data pipeline, or customer communication.
* **Operating Hours:** Monday–Friday 8:00 AM–8:00 PM; Saturday 11:00 AM–8:00 PM; Sunday closed.
* **Brand Identity:** Full Steam Vapor has served the local community since 2014, emphasizing knowledgeable, friendly, one-on-one service for adult consumers.
* **Source Material Grounding:** Customer announcements and product updates are grounded in locally vetted source material (e.g., store records and approved social channels).

### 7.3.3 The 12-Stage Summit State Machine

*Architectural Classification: Ratified Design & Phased Operational Specification (`FSV_SUMMIT_UNIFICATION_DIRECTIVE_v1.0.md`).*

To coordinate multi-model collaboration without conversational chaos, the FSV directive established a formal **12-Stage Finite State Machine** to govern task lifecycle across phased milestones:

```
+----------------------------------------------------------------------------------------------------+
|                                    THE 12-STAGE SUMMIT STATE MACHINE                               |
+----------------------------------------------------------------------------------------------------+
|                                                                                                    |
|    [ INTAKE ] --------------> [ CONTEXT_READY ]                                                    |
|                                       |                                                            |
|                                       +------------+                                               |
|                                       |            |                                               |
|                                       v            v                                               |
|                             [ WAITING_FOR_SOPHIE ] [ WAITING_FOR_BERNIE ]                          |
|                                       |            |                                               |
|                                       +-----+------+                                               |
|                                             |                                                      |
|                                             v                                                      |
|                                   [ READY_FOR_SYNTHESIS ]                                          |
|                                             |                                                      |
|                                             v                                                      |
|                                    [ WAITING_FOR_DUSTIN ]                                          |
|                                             |                                                      |
|                                             v                                                      |
|                                   [ APPROVED_FOR_REMOTE ]                                          |
|                                             |                                                      |
|                                             v                                                      |
|                                        [ EXECUTING ]                                               |
|                                             |                                                      |
|                                             v                                                      |
|                                        [ VERIFYING ]                                               |
|                                             |                                                      |
|                        +--------------------+--------------------+                                 |
|                        |                    |                    |                                 |
|                        v                    v                    v                                 |
|                   [ COMPLETE ]         [ BLOCKED ]          [ SKIPPED ]                            |
|                                                                                                    |
+----------------------------------------------------------------------------------------------------+
```

#### Quorum and Approval Rules:
1. **Mandatory Dual-Model Consultation:** A thread cannot advance to `APPROVED_FOR_REMOTE` until:
   * Sophie has contributed her strategic analysis or explicitly deferred;
   * Bernie has contributed his Google-ecosystem analysis or recorded that no additional input is required;
   * Both positions have been synthesized into a unified brief;
   * Dustin has explicitly approved the decision.
2. **Quorum Waiver:** Only Dustin can waive the normal quorum requirement for an emergency or clearly mechanical task.
3. **Turn Control:** To prevent infinite conversational ping-pong, discussions are restricted to a **default maximum of two Sophie/Bernie discussion rounds** before automatic escalation to synthesis.

### 7.3.4 The Shared Collaboration Surface & Append-Only Storage

The physical coordination surface for the FSV Summit was specified across two integrated layers:
1. **The Shared Surface (Private Google Sheet):** A structured Google Sheet named `FSV Summit` designed as the human-readable collaboration dashboard, partitioned into dedicated tabs: `Threads`, `Messages`, `Decisions`, `Tasks`, `Capabilities`, `Artifacts`, and `Audit`.
2. **Persistent Store (Bare-Metal SQLite):** An independent SQLite database running in Write-Ahead Logging (WAL) mode maintaining the authoritative history, with n8n deterministic workflows designated as the database writer to avoid concurrency conflicts.
3. **Append-Only Immutability:** Overwriting existing entries was strictly prohibited; corrections append new linked message versions.

### 7.3.5 The Two-Click Confirmed Publishing Protocol (`CON-017`): Design vs. Prototype Reality

Publishing business information to public platforms (such as Google Business Profile) represents an irreversible external action. A faulty automated script or hallucinated post could cause immediate commercial and reputational damage.

To govern external publishing, Dustin mandated the **Two-Click Confirmed Publishing Protocol (`CON-017`)**:
* **Signed Single-Use Expiring Tokens:** Publishing drafts generate a cryptographically signed approval token with a strict expiration window.
* **The Email Prefetch Threat:** Modern email clients, anti-virus gateways, and security scanners routinely prefetch HTTP links contained in incoming emails to check for malware. If an email contained a single "Click here to publish" link, the email scanner bot would automatically trigger publication without human intent.
* **The Two-Click Guard:** 
  * **Click 1 (Intent):** The link in the approval email opens a secure, authenticated review page on Dustin’s private Tailscale network, rendering the exact text, images, and target platform.
  * **Click 2 (Execution):** Publication occurs *only* when Dustin manually clicks the secondary confirmation button on that rendered web page.

#### Empirical Implementation Reality (`FSV-LOCAL-TEST-001` Verification)
Live inspection of repository artifacts (`docs/workflows/full_steam_vapor/FSV_LOCAL_TEST_001_CHECKPOINT.md`) reveals the exact implementation boundary:
* **Implemented Prototype:** The protocol was constructed as four n8n workflows (`fsv-review-intake.json`, `fsv-review-decision-portal.json`, `fsv-approval-audit-append.json`, and table initializer) running in container `josie-n8n-1` accessible over Tailscale Serve (`https://refurb.tail0ab4d2.ts.net:5678`).
* **Verified Tested Capabilities:** Controlled testing confirmed that a 64-byte random token was generated, its HMAC-SHA256 digest stored, a 72-hour expiry enforced, and an invalid token correctly rejected with HTTP 403 over Tailscale. The portal workflow verified intent on GET without mutating state.
* **What Was NOT Deployed to Production:** The checkpoint explicitly records that **no production publishing node or live Google Business Profile webhook was connected, no live Gmail message was sent, and nothing could publish to Google**. Status remained: `SAFE / READY FOR CONTROLLED PHONE TEST / AWAITING DUSTIN CONFIRMATION`. The two-click publishing protocol is a verified, token-safe workflow prototype, not a production-deployed automated publishing pipeline.

---

## 7.4 Inter-Model Drift Prevention & Communication Protocols

### 7.4.1 The Pathology of Inter-Model Drift (`CON-030`)

When multiple large language models interact directly without human oversight, they exhibit a well-documented pathological failure mode: **autonomous drift**.

In unconstrained environments, Model A generates a slightly imprecise assumption; Model B interprets that assumption as established fact and builds upon it; Model A validates Model B's elaboration, compounding the error. Within three to four conversational turns, both models hallucinate mutual agreement on imaginary requirements, invalid code APIs, or non-existent files.

Dustin formally addressed this vulnerability in Conversation 1716, codified in **Concept CON-030 (Sophie-Bernie Drift Prevention Protocol)**:
> *"Sophie and Bernie cannot independently keep chatting, hallucinating mutual agreements, or modifying files without human review. Every handoff must be bounded by receipts."*

### 7.4.2 The Asynchronous Build Board Wire (`DEC-0008`)

To eliminate the conversational drift inherent in real-time communication sockets, multi-model handoffs are governed by the **Asynchronous Build Board Wire**:
* **Zero Live Chat Sockets:** Models are strictly prohibited from maintaining live, streaming conversational sockets with one another.
* **Payload Handoffs via Disk/Database:** Communication occurs exclusively through discrete, structured JSON payloads written to local disk files (`data/build_board.json`) or SQLite tables.
* **Deterministic Middleware Validation:** Before a payload written by one model is exposed to another model, deterministic Python middleware parses the schema, validates required fields, verifies referenced file paths against the real filesystem, and strips speculative prose.

### 7.4.3 Structured Communication Format Standards

To enforce intellectual discipline during Summit deliberations, substantive contributions from Sophie or Bernie must adhere to a standardized eight-part reporting structure:
1. **Confirmed Facts:** Machine-verified truths and direct owner statements.
2. **Accessed Sources:** Specific file paths, URLs, or database tables inspected.
3. **Analysis & Inference:** Explicitly labeled analytical deductions, kept separate from primary facts.
4. **Concrete Recommendations:** Actionable proposals with defined success criteria.
5. **Best-Positioned Executor:** The specific model or worker harness best qualified to perform the work.
6. **Risks & Compliance Concerns:** Platform-specific constraints, terms-of-service limitations, or hardware risks.
7. **Unanswered Questions:** Explicit registration of remaining unknowns or missing information.
8. **Requested Next Participant:** Clear indication of who should evaluate the brief next.

---

## 7.5 Domain Specialization and Capability Registries

### 7.5.1 The Capability Registry: Observed Facts vs. Assumed Abilities

A primary vector of AI failure is the assumption that an LLM can perform an action simply because it claims it can. A model will confidently state that it can interact with an API, execute a script, or edit a database, only to crash when presented with real-world authentication, network, or permission barriers.

Under the Summit architecture, capabilities are cataloged in an **Empirical Capability Registry (`FSV_CAPABILITIES.json`)**:
* **Observed Reality Only:** A capability is never registered based on model assertion. It must be demonstrated through a successful, machine-verified test run (`Class 4` evidence).
* **Granular Permission Dimensions:** For every participant (Sophie, Bernie, Josie, Remote, local scripts), the registry explicitly defines:
  * What it can read (exact filesystem directories, database tables, APIs).
  * What it can write (staging areas, scratch directories, approved tables).
  * What it can execute (PowerShell, Python, Git, Docker commands).
  * Authentication surface (OAuth, API key, local process credentials).
  * Operational mode (Supervised interactive vs. Unattended background).
  * Confirmation requirements (Dustin approval gates).
  * Known limitations and failure boundaries.
  * Timestamp of last empirical verification.

### 7.5.2 Domain Enclaves: Segregation of Concerns

To protect privacy, prevent cross-contamination, and preserve focus, Josie organizes her operational assistance into strictly segregated **Domain Enclaves**:

```
+==================================================================================================+
|                                    JOSIE DOMAIN ENCLAVE ARCHITECTURE                             |
+==================================================================================================+
| Enclave                 | Primary Function                  | Isolation & Boundary Safeguards    |
+-------------------------+-----------------------------------+------------------------------------+
| COMMERCIAL ENTERPRISE   | Business retail logistics,        | Strict commercial truth invariance |
| (Full Steam Vapor)      | inventory tracking, POS data,     | (CON-016); two-click publishing   |
|                         | Google Business Profile updates.  | (CON-017); dedicated SQLite store. |
+-------------------------+-----------------------------------+------------------------------------+
| DEAL HUNTER             | Hardware discovery, price         | Research-only mode (CON-010);      |
| (Commercial Research)   | monitoring, eBay API ingestion,   | autonomous bidding/purchasing      |
|                         | market opportunity analysis.      | strictly prohibited (DEC-0006).    |
+-------------------------+-----------------------------------+------------------------------------+
| PERSONAL ADMINISTRATION | Household scheduling, family      | Dedicated service accounts         |
| & PRODUCTIVITY          | workflows, task coordination,     | (CON-028); zero personal Google    |
|                         | document drafting.                | credential contamination.          |
+-------------------------+-----------------------------------+------------------------------------+
| SCRIPTURAL STUDY &      | Comparative biblical research,    | Scripture interprets Scripture     |
| THEOLOGICAL REFLECTION  | commentary analysis, linguistic   | (CON-018); ministerial counsel;   |
|                         | study (Greek/Hebrew texts).       | non-oracle advisory stance.        |
+-------------------------+-----------------------------------+------------------------------------+
| PRAYER STEWARDSHIP      | Pastoral prayer records, family   | Logical table segregation in       |
| (Sacred Registry)       | spiritual burdens, personal       | josie.db (DEC-0019, DEC-0020);     |
|                         | reflections, intercession notes.  | excluded from inspected priming;   |
|                         |                                   | zero encryption at rest.           |
+==================================================================================================+
```

#### Enclave Integrity Principles:
1. **The Deal Hunter Boundary (`CON-010`, `DEC-0006`, `DEC-0015`):** The Deal Hunter workflow is strictly read-only. It may query the eBay Browse API, scrape approved public listings, calculate profit margins, and present opportunities in a local staging database. **Autonomous bidding, purchasing, or credit card checkout is permanently forbidden.** Final execution requires Dustin's direct physical action.
2. **The Scriptural Study Principle (`CON-018`):** In theological inquiry, Josie operates as a study partner, not a spiritual authority. She compares scripture with scripture, examines original language roots and historical contexts, and treats historic theological commentaries as wise human counsel rather than divine revelation. She offers grounding without claiming prophetic insight or replacing pastoral fellowship.
3. **The Prayer Stewardship Enclave (`DEC-0019`, `DEC-0020`, `CON-015`):** Consistent with the technical audit in Chapter 4, the Prayer Stewardship Registry is implemented via logical table segregation (`prayer_requests`, `prayer_sessions`, `prayer_updates`) within the shared `data/josie.db` database, rather than a physically distinct database file. Its exclusion from general worker memory is verified along inspected canonical priming paths (`josie/priming.py`). However, no database encryption at rest is currently implemented, and no system-wide technical guarantee exists against uninspected future code paths. The governing operational requirement remains inviolable: sensitive prayer information must never enter unrelated commercial, deal-hunting, or general worker contexts.

---

## 7.6 Epistemic Grounding: Provenance Ledger & Unresolved Questions

### 7.6.1 Provenance Ledger for Chapter 7

The audit ledger below identifies the primary sources, operational directives, codebase modules, and verified historical decisions supporting the findings in this chapter:

```
+--------------------------------------------------------------------------------------------------------+
|                                  CHAPTER 7 PROVENANCE LEDGER                                           |
+--------------------------------------------------------------------------------------------------------+
| Event / Concept             | Source Reference              | Identifier / Timestamp | Epistemic Class |
+-----------------------------+-------------------------------+------------------------+-----------------+
| FSV Summit Unification      | D:/Josie/docs/decisions/      | Directive v1.0         | Class 1 / 2     |
| Directive (August 2026)     | FSV_SUMMIT_UNIFICATION_...md  | Codified: 2026-08-19   | (Ratified Doc)  |
+-----------------------------+-------------------------------+------------------------+-----------------+
| Concept CON-007 (The Summit | D:/Josie/reports/genesis-002/ | Concept: CON-007       | Class 2 / 5     |
| Evidence-Weighted Process)  | GENESIS-002_CONCEPT_LEDGER.md | Codified: 2026-10-10   | (Candidate Can) |
+-----------------------------+-------------------------------+------------------------+-----------------+
| Mission Manager Dispatcher  | D:/Josie/mission_manager/     | Module: dispatcher.py  | Class 4         |
| & Worker Registry Codebase  | dispatcher.py, worker_reg...  | Verified: 2026-09-15   | (Live Software) |
+-----------------------------+-------------------------------+------------------------+-----------------+
| Concept CON-030 (Sophie-    | D:/Josie/reports/genesis-003/ | Concept: CON-030       | Class 2 / 5     |
| Bernie Drift Prevention)    | GENESIS-003_CONCEPT_LEDGER.md | Historical: Conv 1716  | (Candidate Can) |
+-----------------------------+-------------------------------+------------------------+-----------------+
| Concept CON-017 (Two-Click  | D:/Josie/reports/genesis-002/ | Concept: CON-017       | Class 2         |
| Confirmed Publishing Link)  | JOSIE_CANON_CANDIDATE.md      | Directive: FSV v1.0    | (Operational)   |
+-----------------------------+-------------------------------+------------------------+-----------------+
| Concept CON-016 (FSV Store  | D:/Josie/docs/decisions/      | Invariant: Teays Valley| Class 1 / 2     |
| Location Invariants)        | FSV_SUMMIT_UNIFICATION_...md  | Huntington Closed 2026 | (Commercial Fact)
+-----------------------------+-------------------------------+------------------------+-----------------+
| Decision DEC-0008 (Scoped   | D:/Josie/docs/decisions/      | Entry: DEC-0008        | Class 2         |
| Relationship to Bernie)     | DECISION_LOG.md               | Codified: 2026-08-09   | (Ratified Doc)  |
+-----------------------------+-------------------------------+------------------------+-----------------+
| Decision DEC-0006 & DEC-0015| D:/Josie/docs/decisions/      | Entries: DEC-0006/0015 | Class 2         |
| (Deal Hunter Purchase Ban)  | DECISION_LOG.md               | Codified: Aug-Sep 2026 | (Ratified Doc)  |
+-----------------------------+-------------------------------+------------------------+-----------------+
| Concept CON-018 (Scripture  | D:/Josie/reports/genesis-002/ | Concept: CON-018       | Class 2         |
| Examines Scripture)         | JOSIE_FOUNDING_ALIGNMENT.md   | Alignment: §6          | (Founding Doc)  |
+-----------------------------+-------------------------------+------------------------+-----------------+
| Decision DEC-0019 & DEC-0020| D:/Josie/docs/decisions/      | Entries: DEC-0019/0020 | Class 2 / 4     |
| (Prayer Registry Isolation) | DECISION_LOG.md               | Codified: 2026-09-08   | (Schema Guard)  |
+--------------------------------------------------------------------------------------------------------+
```

### 7.6.2 Register of Open Historical & Operational Questions

To preserve intellectual integrity, the following items remain formally registered as open technical inquiries:

#### UNRES-OPS-03: Automation Scope of Multi-Model Relay Synchronization
* **Status:** `OPEN OPERATIONAL EVALUATION`
* **Description:** While the 12-stage Summit state machine was codified in August 2026, the transition between manual human copy-pasting of briefs, semi-automated browser extension relays (CDP), and fully automated n8n webhook listeners remains varied across operational domains. The long-term architectural goal is deterministic n8n orchestration, but manual human-in-the-loop relays remain active for high-consequence decisions.
* **Provisional Stance:** All multi-model handoffs require explicit receipt capture regardless of transport mechanism.

#### UNRES-GOV-01: Governance Hierarchy & Constitutional Supremacy
* **Status:** `OPEN — PENDING OWNER DECISION`
* **Description:** The structural procedure by which constitutional doctrines, operational canons, and decision logs may be formally amended remains open. In accordance with Sophie's review directives, no synthetic amendment procedure has been ratified; the question remains open for Dustin's explicit determination.

---

```
================================================================================
                          END OF CHAPTER 7 DRAFT (v1.1.0)
================================================================================
Review Directives for Dustin & Sophie:
  1. Confirm the representation of The Summit as an evidence-weighted deliberation process rather than a democratic voting swarm.
  2. Validate the architectural separation between Summit deliberation and Mission Manager scheduling authority.
  3. Verify the fidelity of the Full Steam Vapor Summit implementation, distinguishing ratified design from prototype n8n testing.
  4. Review the Two-Click Confirmed Publishing Protocol (CON-017) designed to defeat automated email prefetch crawlers.
  5. Validate the inter-model drift prevention protocols (CON-030) and asynchronous build board constraints.
  6. Confirm the domain enclave boundaries (Commercial, Deal Hunter, Personal, Biblical, and logically segregated Prayer Stewardship).
  7. Confirm that open governance question UNRES-GOV-01 remains formally open.
================================================================================
```

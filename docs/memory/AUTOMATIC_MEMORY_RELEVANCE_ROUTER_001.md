# Automatic Memory Relevance Router Specification and Pilot Receipt

**Document Version:** 1.0.0  
**Phase:** Memory Vault — Task-to-Memory Relevance Routing  
**Date:** 2026-09-30  
**Repository:** `D:\Josie`  
**Branch:** `reconcile/live-work-20260917`  

---

## 1. Executive Summary

This receipt documents the closure of the **Automatic Task-to-Memory Relevance Router** in Josie Core. Prior to this implementation, Josie required explicit caller priming category metadata (`priming_categories`) or changed-path prefixes to select canonical memory for priming into the Prompt Contract; ordinary conversational task wording alone resulted in empty priming bundles.

With the Automatic Memory Relevance Router, Josie's front-door job compilation autonomously determines which approved canonical-memory categories are relevant to an incoming task request, while strictly preserving fail-closed boundaries, authority invariants, and canonical immutability:

$$\text{Normal User Task} \longrightarrow \text{Relevance Router} \longrightarrow \text{Canonical Priming Bundle} \longrightarrow \text{Prompt Contract} \longrightarrow \text{Worker Execution}$$

Key accomplishments:
1. **Two-Tier Hybrid Routing Architecture**: Tier 1 deterministic lexical/semantic rules for zero-latency, zero-hallucination routing of obvious intent; Tier 2 local model fallback (`qwen3:14b`) with strict JSON schema and a 0.70 confidence threshold.
2. **Strict Fail-Closed Invariants**: If router confidence is below 0.70, or if a task is generic/ambiguous, the router evaluates to `memory_needed = False` and `categories = []`.
3. **Deterministic Precedence Hierarchy**: Structured caller metadata takes precedence over path prefixes, which take precedence over automatic relevance routing, which defaults to fail-closed empty categories.
4. **Real End-to-End Recall Loop Closure**: An ordinary natural-language inquiry regarding Dustin's credentials and server experience autonomously routed to category `profile`, retrieved approved canonical credential `claim:candidate:person:dustin:has_durable_credential:4a70966b5994bdac`, compiled it into the Prompt Contract, executed the worker (`goose` + `josie-qual-ornith-1.5-9b-q6`), passed machine acceptance, and produced an authoritative supervisor receipt (`PASS`) with complete router audit metadata.
5. **Negative Control Verification**: A standard programming directive (`"Write a Python function that reverses a string."`) evaluated to `memory_needed = False`, assembled an empty priming bundle, and executed with status `PASS`.
6. **Full Test Discovery & Invariants**: All 444 repository tests pass, candidate claims remain unapproved, and canonical database state is strictly preserved.

---

## 2. Precedence Hierarchy

Category resolution in `supervisor/remote_adapter.py` enforces the following deterministic precedence:

1. **Precedence 1 — Explicit Structured Categories**:
   If caller provides `retrieval_context["priming_categories"]` or `retrieval_context["categories"]`, the router immediately yields to the explicit caller request.
2. **Precedence 2 — Task Class / Route Metadata**:
   If `retrieval_context["task_class"]` or `retrieval_context["operation"]` matches known subsystem classes (e.g. `architecture`, `governance`), it maps to corresponding canonical categories (`architecture`, `identity`, `procedure`).
3. **Precedence 3 — Authorized Changed-Path Prefixes**:
   If `allowed_changed_paths` matches known subsystem paths (`ARCH_PATH_PREFIXES` or `AUTHORITY_PATH_PREFIXES`), it deterministically maps to subsystem categories.
4. **Precedence 4 — Automatic Memory Relevance Router**:
   If no explicit signals are present, the front door invokes `josie.memory_router.route_memory_relevance(task)`.
5. **Precedence 5 — Fail-Closed Empty Categories**:
   If neither deterministic rules nor local model meet the confidence threshold (>= 0.70), resolution returns empty categories `()` and zero memory is primed.

---

## 3. Test Matrix (Cases A–J)

The test matrix was implemented and verified in `tests/test_memory_router.py`:

| Case | Query / Scenario | Expected Category | Router Evaluation | Status |
|---|---|---|---|---|
| **A** | `"What technical certifications or server experience do I have?"` | `profile` (conf >= 0.70) | `profile` (conf: 0.95) | **PASS** |
| **B** | `"What hardware do I already own for Josie?"` | `hardware` (conf >= 0.70) | `hardware` (conf: 0.95) | **PASS** |
| **C** | `"What is my preferred strategy for getting the cheapest hardware for Josie?"` | `preference` | `preference`, `hardware` (conf: 0.95) | **PASS** |
| **D** | `"What did we decide about the model family for the worker?"` | `decision` | `decision` (conf: 0.95) | **PASS** |
| **E** | `"Explain the relationship between Goose and OpenCode in Josie's architecture."` | `architecture` | `architecture` (conf: 0.95) | **PASS** |
| **F** | `"How do we handle destructive actions?"` | `procedure` / `constraint` | `procedure`, `constraint` (conf: 0.95) | **PASS** |
| **G** | `"Write a Python function to compute the Fibonacci sequence."` | `memory_needed = False`, `[]` | `memory_needed = False`, `[]` (conf: 0.98) | **PASS** |
| **H** | `"Write a script that parses a log file for the word 'certification'."` | `memory_needed = False`, `[]` | `memory_needed = False`, `[]` (conf: 0.98) | **PASS** |
| **I** | `"Tell me about that thing we discussed yesterday."` | Fail closed -> `[]` | `memory_needed = False`, `[]` (conf: 0.40) | **PASS** |
| **J** | Explicit caller override `{"priming_categories": ["identity"]}` | `identity` | `identity` (caller override) | **PASS** |

---

## 4. Real End-to-End Recall Pilot Receipt

A live local-code job was dispatched through the supervisor front door without any category hints:

| Field | Value |
|---|---|
| **Job ID** | `auto-memory-recall-001` |
| **Receipt ID** | `1e411c09-e06e-4ed4-881d-f33c1b509744` |
| **Receipt Path** | `D:\Josie\data\private\supervisor-local-code\1e411c09-e06e-4ed4-881d-f33c1b509744.json` |
| **Workspace** | `D:\Josie\scratch\auto_memory_recall_workspace` |
| **Harness** | `goose` (1.50.0) |
| **Model** | `josie-qual-ornith-1.5-9b-q6:latest` |
| **Task Hash** | `1a4247cd4c6cf0714bc1d5785bc5ed16abf69e5d9ae1aea2f77a3eb7a0bbcbc2` |
| **Memory Needed** | `true` |
| **Confidence** | `0.95` |
| **Selected Categories** | `["profile"]` |
| **Priming Manifest Hash**| `18bd0157a8936a407abb82bc42e37ab0aef0b6fdc1436cd82e268107945387da` |
| **Priming Bundle Hash** | `6b503e53751e938638c851d00d5a82f661149feea19710a6bb0d0224289452be` |
| **Primed Canonical Items**| `["claim:candidate:person:dustin:has_durable_credential:4a70966b5994bdac"]` |
| **Elapsed Seconds** | `91.5s` |
| **Final Status** | `PASS` |
| **Reason** | `PASS` |

### Prompt Contract Injection

The Prompt Contract automatically received the primed credential under `RESOURCE RULES`:
```text
RESOURCE RULES
Local resources only. Do not use paid/cloud providers or download models.
Task-relevant evidence:
- [claim:candidate:person:dustin:has_durable_credential:4a70966b5994bdac] A+ certified with years of experience with commercial servers
```

### Worker Output in `answer.md`

```markdown
# Relevant Certification and Server Experience

## Certification

- **CompTIA A+ certified** — holds a durable, industry-recognized credential covering computer hardware, operating systems, troubleshooting, and IT fundamentals.

## Server Experience

- **Years of hands-on experience with commercial servers** — practical operational background with enterprise/commercial server hardware and systems, spanning installation, configuration, maintenance, and troubleshooting of production-grade server infrastructure.

## Relevance to Working on Josie

- The **A+ certification** establishes a durable foundation in computer hardware and system support, which is relevant to troubleshooting local agent infrastructure running on the same machine, verifying dependencies, and maintaining the operating environment Josie relies on.
- The **commercial server experience** is relevant to Josie's architecture: Josie depends on local compute resources including Ollama, model runtimes, and filesystem storage (`D:\Josie`, `I:\Josie-Storage`), and running reliably as a persistent, long-lived worker. Experience operating commercial servers translates directly to keeping local models and services healthy, diagnosing failures, and handling the resource constraints and persistence requirements of an autonomous coding agent.
```

---

## 5. Negative Control Execution Receipt

A control task requiring no memory was dispatched:

| Field | Value |
|---|---|
| **Job ID** | `auto-memory-negative-001` |
| **Receipt ID** | `8983ddef-58d3-408f-b0db-b6992785f4e0` |
| **Receipt Path** | `D:\Josie\data\private\supervisor-local-code\8983ddef-58d3-408f-b0db-b6992785f4e0.json` |
| **Workspace** | `D:\Josie\scratch\auto_memory_negative_control_workspace` |
| **Task** | `"Write a Python function that reverses a string into solution.py."` |
| **Task Hash** | `668da9eb653c0a4f9a508138d42c9c0af07f75e08acb77ff30fa3b883aa25a10` |
| **Memory Needed** | `false` |
| **Confidence** | `0.98` |
| **Selected Categories** | `[]` |
| **Reason** | `"generic programming task does not require personal or project memory"` |
| **Priming Context** | `is_empty: true, item_count: 0, source_ids: []` |
| **Retrieved Evidence** | `[]` |
| **Final Status** | `PASS` |
| **Reason** | `PASS` |

---

## 6. Canonical Immutability Audit

A verification audit confirmed zero changes to canonical claims or review queues in `data/josie.db`:

| Claim Status & Effect | Count Before | Count After | Delta |
|---|---|---|---|
| Active Canonical Knowledge (`canonical_effect=1`, `status='active'`) | 5 | 5 | **0** |
| Unapproved Candidate Claims (`canonical_effect=0`, `status='candidate'`) | 4 | 4 | **0** |
| Rejected Claims (`canonical_effect=0`, `status='rejected'`) | 1 | 1 | **0** |
| **Total Memory Claims** | **10** | **10** | **0** |

All candidate claims remain unapproved, with zero database mutations.

---

## 7. Verification Summary

- `tests.test_memory_router`: **21/21 PASS**
- `tests.test_frontdoor_priming`: **10/10 PASS**
- `tests.test_candidate_claims`: **66/66 PASS**
- `tests.test_josie`: **116/116 PASS**
- Full test discovery (`unittest discover -s tests`): **444/444 PASS**
- `git diff --check`: **0 errors**

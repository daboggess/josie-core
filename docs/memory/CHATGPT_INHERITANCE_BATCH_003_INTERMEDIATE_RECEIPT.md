# Build Receipt: ChatGPT Inheritance Batch 003 Intermediate Extraction

**Milestone:** Production Candidate Claim Extraction Batch 003 Intermediate-Scale Run  
**Repository:** `daboggess/josie-core` (`D:\Josie`)  
**Branch:** `reconcile/live-work-20260917`  
**Date:** 2026-10-04  
**Extractor Engine:** `LocalModelClaimExtractor(qwen3:14b)` on local Ollama (`http://127.0.0.1:11434`)  
**Manifest SHA-256:** `8a4763d68a2c90425eb659be68191105538c80d2708fca43327b0238c00b456f`  
**Database:** `data/josie.db`  
**Canonical Invariant:** Exactly 10 claims before -> exactly 10 claims after (`canonical_effect=1`)  
**Human Review Packet:** `docs/memory/CHATGPT_INHERITANCE_BATCH_003_INTERMEDIATE.md`  
**Scale Recommendation:** `READY_FOR_BULK_STAGED_EXTRACTION`

---

## 1. Executive Summary & Validation Results

This receipt certifies the execution of **ChatGPT Inheritance Batch 003**, the first intermediate-scale candidate extraction run on Josie's historical ChatGPT corpus.

Batch 003 evaluated 15 previously unprocessed ChatGPT conversations (759 conversation messages, 299 user turns). Extraction was executed entirely via local `qwen3:14b` with zero cloud inference, hardened with the newly implemented **Epistemic Guard (Rule 6)**, **Memory Destination Routing (Rule 7)**, and **Sensitive Personal Claim Quarantine**.

### Key Validation Outcomes:

1. **Canonical Memory Safety Invariant:** The canonical memory store remained strictly at **10 claims**. Exactly 0 candidates were automatically promoted.
2. **Epistemic Guard Success:** Fictional backstories, imagined architectures, and proposed future hardware states were successfully prevented from polluting current hardware ownership or personal identity.
3. **Domain & Destination Routing:** Machine hardware facts (17 claims) were routed to `hardware_state` rather than forced into `person:dustin`. BIOS user/admin state was routed to `runbook_procedure`.
4. **Sensitive Personal Claim Quarantine:** The claim `identifies_as_inherently_dangerous_to_self_and_others` was reclassified to `sensitive_review` with `canonical_eligible=False`.
5. **Transient Suppression:** Ephemeral rewards balances and situational purchase limits (5 claims) were classified as `transient_noise` and explicitly flagged `canonical_eligible=False`.
6. **Evidence Authority:** 100% of claims concerning Dustin originated strictly from direct user statements (`role='user'`). 2 assistant-generated proposals were rejected during authority filtering.
7. **Replay Idempotency Verified:** Re-executing staging against the exact same proposals created **0 duplicate claims** and **0 mutations**.

---

## 2. Deterministic Batch Selection & Manifest

- **Batch Identifier:** `CHATGPT_INHERITANCE_BATCH_003_INTERMEDIATE`
- **Manifest SHA-256:** `8a4763d68a2c90425eb659be68191105538c80d2708fca43327b0238c00b456f`
- **Total Conversations Selected:** 15 (contiguous reverse-chronological order from Batch 002)
- **Total Textual Conversation Messages:** 759
- **User Messages:** 299 (strictly $\le 300$ boundary)
- **Assistant Messages:** 460
- **Extraction Chunks Processed:** 59 chunks (bundles $\le 15$ msgs; 1 chunk with 0 user turns skipped)

| Conv ID | Date Range | Title |
|:---|:---|:---|
| **1684** | 2026-08-19..2026-08-19 | Sign In Then Retry |
| **1683** | 2026-08-19..2026-08-19 | Google workflow planning |
| **1682** | 2026-08-18..2026-08-18 | Compare Whey Proteins |
| **1679** | 2026-08-17..2026-08-17 | Cans vs rewards points |
| **1678** | 2026-08-15..2026-08-15 | Prayer List from Texts |
| **1677** | 2026-08-15..2026-08-15 | James Bible Study Outline |
| **1676** | 2026-08-14..2026-08-14 | Clothing Modesty Discussion |
| **1675** | 2026-08-14..2026-08-14 | 2026 Ascent Tailgate Setup |
| **1642** | 2026-07-29..2026-08-14 | G2A AI Subscription Risks |
| **1673** | 2026-08-14..2026-08-14 | Remote Control via Phone |
| **1671** | 2026-08-11..2026-08-13 | Write ministry discernment |
| **1670** | 2026-08-10..2026-08-13 | Josie Local AI Strategy |
| **1662** | 2026-08-07..2026-08-10 | Stewardship vs Sovereignty Insights |
| **1669** | 2026-08-10..2026-08-10 | Codex usage limit hit |
| **1668** | 2026-08-09..2026-08-09 | Master Codex Handoff Guide |

---

## 3. Extraction Funnel & Staged Candidates Inventory

- **Raw Model Proposals:** 37
- **Rejected on Evidence Authority:** 2
- **Rejected on Textual Entailment:** 0
- **Rejected on Epistemic Guard (Hypothetical/Fictional):** 0
- **Rejected on Event != Preference:** 0
- **Rejected on Other Validation:** 0
- **Valid Proposals Staged:** 35
- **Unique Candidates Staged:** 35
- **Evidence Links Created:** 36

### Destination Routing Breakdown:

| Destination | Count | Notes |
|:---|:---|:---|
| `hardware_state` | 17 | Laptop network config, Advantech chassis, 200W PSU, DDR4 RAM |
| `personal_canonical` | 6 | Core desires (independence, income generation, browser automation) |
| `transient_noise` | 5 | Nicotine can caps, Zen points cash-out, transient deal browsing |
| `historical_only` | 4 | Historical $50 budget, Tesla T4 vs A2000 trade-off musings |
| `sensitive_review` | 1 | Quarantined: identifies_as_inherently_dangerous_to_self_and_others |
| `project_architecture` | 1 | Josie system memory architecture |
| `runbook_procedure` | 1 | Advantech BIOS user vs admin password bypass |

---

## 4. Epistemic Safety & Invariant Verification

```
Canonical memory claims pre-staging:  10
Canonical memory claims post-staging: 10 (Strict Invariant: PASS)
Non-canonical claims pre-staging:     44
Non-canonical claims post-staging:    79 (+35 newly staged Batch 003 candidates)
Candidate approval leakage:           0 claims (approved_by=NULL, reviewed_at=NULL)
Replay staging idempotency:           0 duplicate claims created on second pass (PASS)
```

### Active Canonical Baseline (Immutable 10):

1. `identity:dustin-authority` (human_authority)
2. `arch:supervisor-worker-separation` (supervisor_worker_boundary)
3. `arch:identity-above-models` (identity_above_models)
4. `procedure:destructive-action-gate` (consequential_action_boundary)
5. `claim:candidate:person:dustin:has_durable_credential:4a70966b5994bdac` (A+ certified with commercial server experience)
6. `claim:candidate:person:dustin:seeks_profit_work_tier_with_minimal_regular_involvement:d8c141212d959159` (Minimal regular personal involvement preference)
7. `claim:candidate:person:dustin:operates_business:666e11a5c4ee1d97` (Dustin and Jess run a vape shop together)
8. `claim:candidate:person:dustin:ministry_co_leader:df3a909ad2b90e6e` (Everyday Discipleship study co-leader Kevin Slack)
9. `claim:candidate:person:dustin:uses_finance_tracker:253ba567db86c80b` (Rocket Money personal finance tracker)
10. `claim:candidate:person:dustin:has_monthly_mortgage:030243e889b7fefd` (Household mortgage payment ~$1,500/month)

---

## 5. Comparative Quality Across Batches

| Dimension | Batch 001 (Baseline) | Batch 002 (Hardened) | Batch 003 (Intermediate + Epistemic Guard) |
|:---|:---|:---|:---|
| **Conversations Processed** | 5 | 9 | 15 |
| **Total Conversation Msgs** | 200 | 183 | 759 |
| **User Messages** | 102 | 73 | 299 |
| **Raw Model Proposals** | 16 | 12 | 37 |
| **Entailment Hallucinations** | 2 (GreenSky, 401k) | 0 | 0 |
| **Fictional Hardware Errors** | N/A | 1 (Dual Xeon/3090) | 0 (Properly suppressed / guarded) |
| **Machine Facts in Dustin Profile** | Yes (BIOS, network) | Yes (Advantech BIOS) | 0 (17 routed to hardware_state, 1 to runbook) |
| **Transient Rewards Staged** | 1 ($80 Upside, $50 Zen) | 2 (Flagged transient) | 5 (Suppressed as transient_noise) |
| **Sensitive Quarantined** | 0 | 0 | 1 (Quarantined in sensitive_review) |
| **Personal Canonical Staged** | 16 (all forced personal) | 9 | 6 (High signal, genuine personal facts/desires) |
| **Canonical Invariant** | 10 (Mutated via manual test) | 10 (Preserved) | 10 (Strictly Preserved) |
| **Replay Idempotency** | Verified | Verified | Verified (0 duplicates) |

---

## 6. Scale Decision & Production Recommendations

**RECOMMENDATION:** **`READY_FOR_BULK_STAGED_EXTRACTION`**

### Rationale:
1. The pipeline successfully ingested **15 conversations / 759 messages** with zero crashes, zero data corruption, and 100% replay idempotency.
2. The Epistemic Guard completely eliminated the fictional backstory failure mode observed in Batch 002.
3. Destination routing cleanly separates machine telemetry and network topology from Dustin's personal identity.
4. Sensitive personal claims are quarantined from canonical promotion into `sensitive_review`.
5. Zero unentailed institutions or accounts were generated.
6. Canonical safety invariant is 100% stable at exactly 10 claims.
7. Staging throughput scales linearly and safely while human review remains bounded and advisory.

STOP
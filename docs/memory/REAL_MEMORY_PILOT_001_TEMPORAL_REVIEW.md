# Real Memory Pilot 001: Temporal & Durability Review

**Document Version:** 1.0.0  
**Phase:** Memory Vault Phase 3B.3  
**Date:** 2026-09-25  
**Baseline Dataset:** Conversation 57 (Messages 467..496)  
**Model:** `qwen3:14b` via local Ollama  

---

## 1. Executive Summary

Real Memory Pilot 001 demonstrated that messy historical conversations contain mixed-source envelopes, nested AI quotations, and diverse temporal scopes. While Phase 3B.1 and 3B.2 resolved envelope decoupling and span-level attribution, Phase 3B.3 addresses the foundational temporal invariant:

> **Core Invariant**: A claim may be perfectly attributed and perfectly evidenced without being appropriate as permanent canonical knowledge.

Empirical assertions about physical hardware—especially negative statements such as *"does not own an RTX 3090"*—are point-in-time facts. Encoding them as permanent (`durable`) truths would corrupt long-term canonical memory. Phase 3B.3 ensures that durability semantics (`durable`, `current_state`, `preference`, `transient`) and temporal bounds (`valid_from`, `valid_until`) are explicitly tracked on every candidate and canonical memory claim.

---

## 2. Review of Pilot 001 Candidate Claims

Running extraction on historical Conversation 57 (messages 467..496) produced 5 structured candidate claims. Each was evaluated against durability semantics:

### Claim 1: A+ Certification and Server Experience
- **Proposition:** `person:dustin` has credential `A+ certified with years of experience with commercial servers`
- **Source Message:** Message 485 (`2025-11-27T19:27:57Z`)
- **Span Excerpt:** `"Btw i am a+ certified with years of experience with commercial servers"`
- **Attribution:** `direct_user_assertion` (span [15..85] extracted cleanly from mixed turn)
- **Durability:** `durable`
- **Valid From:** `2025-11-27T19:27:57Z`
- **Analysis:** Professional certifications, engineering background, and accumulated commercial server experience do not expire with hardware changes. This represents enduring profile truth and is suitable for long-term canonical knowledge upon Dustin's explicit approval.

### Claim 2: Physical Storage Inventory
- **Proposition:** `person:dustin` owns `two 4TB NVMe drives and two 24TB HDDs`
- **Source Message:** Message 471 (`2025-11-27T19:07:28Z`)
- **Span Excerpt:** `"Only items i already have a re 2 4tb nvme and 2 24th hhd"`
- **Attribution:** `direct_user_assertion`
- **Durability:** `current_state`
- **Valid From:** `2025-11-27T19:07:28Z`
- **Analysis:** Hardware inventory on hand is empirical point-in-time state. Physical drives can fail, be repurposed, or be expanded. It must be tracked as `current_state`, not timeless identity.

### Claim 3: Hardware Cost Optimization Goal
- **Proposition:** `person:dustin` seeks `cheapest hardware setups to accomplish AI goals`
- **Source Message:** Message 469 (`2025-11-27T19:04:31Z`)
- **Span Excerpt:** `"Looking for other possible hardware setups to accomplish the ai goals as cheaply as possible"`
- **Attribution:** `direct_user_assertion`
- **Durability:** `preference`
- **Valid From:** `2025-11-27T19:04:31Z`
- **Analysis:** Architectural goals, budgetary constraints, and hardware optimization strategies evolve across project phases. Classifying this as `preference` allows future policy updates to supersede it cleanly without invalidating historical rationale.

### Claim 4: Negative Hardware State (Direct Assertion)
- **Proposition:** `person:dustin` does not own `RTX 3090`
- **Source Message:** Message 489 (`2025-11-27T19:38:30Z`)
- **Span Excerpt:** `"Btw i dont own a 3090"`
- **Attribution:** `direct_user_assertion`
- **Durability:** `current_state` (NOT `durable`)
- **Valid From:** `2025-11-27T19:38:30Z`
- **Analysis:** 
  - This statement is 100% authentic, directly spoken by Dustin, and unimpeachably evidenced.
  - However, the negative state *"does not own an RTX 3090"* is an empirical condition valid at the moment of utterance.
  - If Dustin subsequently purchases an RTX 3090 (or alternative accelerator), treating this absence as `durable` would create an intractable contradiction against future reality.
  - Durability classification must be `current_state`.

### Claim 5: Secondary Assistant Hardware Assertion
- **Proposition:** `person:dustin` does not own `RTX 3090` (derived from Gemini advice)
- **Source Message:** Message 476 (`2025-11-27T19:11:39Z`)
- **Attribution:** `assistant_assertion`
- **Confidence:** `0.6` (`INFERRED`)
- **Durability:** `current_state`
- **Valid From:** `2025-11-27T19:11:39Z`
- **Analysis:** Outranked by the direct assertion from Message 489 (`confidence=1.0`, `RETRIEVED`), correctly demoted due to external assistant envelope origin.

---

## 3. Invariants Verified in Production Database (`data/josie.db`)

1. **Zero Canonical Contamination:**
   - Active canonical claims (`canonical_effect=1`): **4** (unmodified baseline).
   - Candidate claims staged (`canonical_effect=0`): **5** (pending review).
   - Rejected claims (`canonical_effect=0`): **1** (preserved with audit reason).
2. **Zero Priming Leakage:**
   - Worker priming query (`assemble_priming_from_knowledge`) returns **0** candidate claims.
3. **Strict Adjudication Gate:**
   - No autonomous or worker-initiated approvals are permitted.
   - All candidate promotions require Dustin's explicit review and confirmation token (`EXPLICIT HUMAN APPROVAL`).

# Build Receipt: ChatGPT Inheritance Batch 001 Adjudication & Policy Hardening

**Milestone:** Production Candidate Claim Extraction Batch 001 Adjudication & Quality Policy Hardening  
**Repository:** `daboggess/josie-core` (`D:\Josie`)  
**Branch:** `reconcile/live-work-20260917`  
**Date:** 2026-10-03  
**Reviewer Authority:** Dustin (Sole Human Authority — Authoritative Adjudication Applied)  
**Database:** `data/josie.db`  

---

## 1. Executive Summary

This receipt documents the successful execution of **Dustin's Authoritative Human Adjudication** for **ChatGPT Inheritance Batch 001** and the implementation of mandatory **Quality Policy Hardening Rules 1 through 5** in Josie's candidate-memory pipeline (`josie/candidate_claims.py`).

All 16 candidate claims staged from Batch 001 have been adjudicated in `data/josie.db`:
- **5 claims Approved to Canonical Knowledge** (`canonical_effect=1`) with human edits and temporal bounding.
- **4 claims Merged/Corroborated** into existing target claims (`canonical_effect=0`), transferring evidence references without creating duplicate canonical claims.
- **7 claims Rejected** (`canonical_effect=0`), preserving complete provenance and audit trails in SQLite.

Canonical claims in `data/josie.db` increased from **5 to exactly 10**. All 454 tests in the test suite pass (100%).

---

## 2. Batch 001 Adjudication Summary

| # | Candidate Claim ID | Action | Final Stored Value | Durability | Valid From / To | Status / Effect | Reason / Notes |
|:---|:---|:---|:---|:---|:---|:---|:---|
| 1 | `claim:candidate:person:dustin:operates_business:666e11a5c4ee1d97` | **APPROVE WITH EDIT** | `"Dustin and Jess run a vape shop together."` | `current_state` | From: `2026-08-17` | `active` / `canonical_effect=1` | Operational state beginning 2026-08-17; conservative relationship (run, not own). |
| 2 | `claim:candidate:person:dustin:uses_finance_tracker:253ba567db86c80b` | **APPROVE TEMPORALLY** | `"As of 2026-05-18, Dustin used Rocket Money to categorize and track personal finances."` | `current_state` | From: `2026-05-18` | `active` / `canonical_effect=1` | Point-in-time financial software tooling. |
| 3 | `claim:candidate:person:dustin:has_monthly_mortgage:030243e889b7fefd` | **APPROVE TEMPORALLY** | `"As of 2026-05-18, Dustin's household mortgage payment was approximately $1,500/month."` | `current_state` | From: `2026-05-18` | `active` / `canonical_effect=1` | Point-in-time baseline financial liability. |
| 4 | `claim:candidate:person:dustin:prefers_maximizing_access_without_burning_limits:9eaa5ee271293d27` | **CORROBORATE** | (Target: `prefers_model_access_without_subscription_burn:5ffaa93fd9cba477`) | `preference` | — | `superseded` / `canonical_effect=0` | Corroborated into existing preference; transferred msg 21070; enriched confidence to 0.90. |
| 5 | `claim:candidate:person:dustin:has_preference:ebb6aa113a63653c` | **REJECT** | `"Josie to be as intelligent as possible"` | `preference` | — | `rejected` / `canonical_effect=0` | High-level goal does not add distinct operational constraint. |
| 6 | `claim:candidate:person:dustin:prefers:800c808f1200a4bd` | **REJECT** | `"paying $250 with buyer protection for GPU purchase"` | `preference` | — | `rejected` / `canonical_effect=0` | Transaction-specific negotiation tactic / opportunistic purchase limit, not enduring preference. |
| 7 | `claim:candidate:person:dustin:seeks_profit_work_tier_with_minimal_regular_involvement:d8c141212d959159` | **APPROVE** | `"Dustin prefers profit and work models that require minimal regular personal or sales involvement."` | `preference` | — | `active` / `canonical_effect=1` | Durable work/business preference. |
| 8 | `claim:candidate:person:dustin:reduced_green_sky_payment_to_minimum:2850e9f4bc9d82d7` | **REJECT** | `"from $350 to minimum"` | `current_state` | — | `rejected` / `canonical_effect=0` | Unentailed / over-inferred. Evidence says "dumped this down from 350 to minimum" but does not name GreenSky. |
| 9 | `claim:candidate:person:dustin:considers_repaying_401k_loan:3affb4a9bd802384` | **REJECT** | `"to reach $170,000 mortgage payoff"` | `current_state` | — | `rejected` / `canonical_effect=0` | Unentailed / over-inferred. Evidence does not mention 401(k), and statement was deliberative/transient. |
| 10 | `claim:candidate:person:dustin:retained_subscriptions:6743b8bfe15b5c03` | **REJECT** | `"cancelled non-essential recurring subscriptions while keeping Hulu, Netflix, Disney, Google, YouTube, and ChatGPT"` | `current_state` | — | `rejected` / `canonical_effect=0` | Point-in-time snapshot of transient consumer services. Belongs in historical evidence, not canonical memory. |
| 11 | `claim:candidate:person:dustin:prefers_pc_resale_strategy:33787280b1dab592` | **REJECT** | `"prefers selling PC builds as a whole unit rather than parting out individual components"` | `preference` | — | `rejected` / `canonical_effect=0` | Context-specific preference for a single build/sale, not an enduring hardware strategy. |
| 12 | `claim:candidate:person:dustin:prefers_local_model_memory:186e9ce707620502` | **CORROBORATE** | (Target: `prefers_local_first_desktop_ai_setup:7cd4ba7ee9db062d`) | `preference` | — | `superseded` / `canonical_effect=0` | Corroborated into existing local-first desktop AI setup preference; transferred msg 21046; enriched confidence to 0.92. |
| 13 | `claim:candidate:system:josie:has_current_state:a8016cdbb5482ea6` | **CORROBORATE** | (Target: `current_state:9c9c9d886c9d694d`) | `current_state` | — | `superseded` / `canonical_effect=0` | Corroborated into existing hardware inventory (owns i7-7700 CPU) with msg 21107; enriched confidence to 1.0. |
| 14 | `claim:candidate:person:dustin:budget_rewards_balance:8fdefd93f96d849b` | **REJECT** | `"allocated $80 from Upside and $50 Amazon from Zen rewards toward PC build components"` | `transient` | — | `rejected` / `canonical_effect=0` | Highly transient point-in-time balance. Not memory-worthy. |
| 15 | `claim:candidate:person:dustin:ministry_co_leader:df3a909ad2b90e6e` | **APPROVE AS HISTORICAL** | `"In August 2026, Kevin Slack was assisting/co-leading Dustin's Everyday Discipleship study."` | `current_state` | From: `2026-08-17` To: `2026-08-31` | `active` / `canonical_effect=1` | Approved as historical/current state time-bound to August 2026. |
| 16 | `claim:candidate:assistant:chatgpt:proposes:7a1e8715c70af2dc` | **REJECT** | `"Josie should not be built around fixed roles..."` | `durable` | — | `rejected` / `canonical_effect=0` | Assistant-generated philosophical advice. Not user authority. |

---

## 3. Canonical Knowledge Delta (5 -> 10)

The canonical store in `data/josie.db` (`memory_claims WHERE canonical_effect = 1`) contains exactly **10 claims**:

```
1. [durable] identity:dustin-authority
   Dustin is final human authority for his intentions, delegated permissions, consequential outward actions, and constitutional amendments. Josie must not impersonate Dustin, manufacture approval, or treat silence as consent.
2. [durable] arch:supervisor-worker-separation
   Josie enforces strict Supervisor and worker separation: the deterministic supervisor compiles immutable Prompt Contracts with bounded evidence; workers have no authority over protected memory or self-certification.
3. [durable] arch:identity-above-models
   Josie's identity, memory, Constitution, and authority remain above replaceable local or cloud model weights.
4. [durable] procedure:destructive-action-gate
   Capability is not authority; permission scales with consequence. Irreversible, outward, privileged, financial, identity, and safety-sensitive actions require explicit Dustin approval and fail closed.
5. [durable] claim:candidate:person:dustin:has_durable_credential:4a70966b5994bdac
   A+ certified with years of experience with commercial servers (from 2025-11-27T19:27:57Z)
6. [preference] claim:candidate:person:dustin:seeks_profit_work_tier_with_minimal_regular_involvement:d8c141212d959159
   Dustin prefers profit and work models that require minimal regular personal or sales involvement. (from 2026-08-24T20:51:34Z)
7. [current_state] claim:candidate:person:dustin:operates_business:666e11a5c4ee1d97
   Dustin and Jess run a vape shop together. (from 2026-08-17)
8. [current_state] claim:candidate:person:dustin:ministry_co_leader:df3a909ad2b90e6e
   In August 2026, Kevin Slack was assisting/co-leading Dustin's Everyday Discipleship study. (from 2026-08-17 to 2026-08-31)
9. [current_state] claim:candidate:person:dustin:uses_finance_tracker:253ba567db86c80b
   As of 2026-05-18, Dustin used Rocket Money to categorize and track personal finances. (from 2026-05-18)
10. [current_state] claim:candidate:person:dustin:has_monthly_mortgage:030243e889b7fefd
   As of 2026-05-18, Dustin's household mortgage payment was approximately $1,500/month. (from 2026-05-18)
```

---

## 4. Policy Hardening Implementation

To prevent candidate extraction regressions in subsequent batches, five quality rules were implemented and tested:

### Rule 1 (Claim/Evidence Entailment)
- Implemented `check_claim_evidence_entailment(proposal, messages_lookup)`.
- Validates that named financial accounts (`greensky`, `401k`, `roth`, `vanguard`, etc.) and specific entities in predicates or propositions appear in the raw evidence text.
- Integrated into `validate_proposal` to fail closed if unentailed accounts are injected.

### Rule 2 (Event != Preference)
- Implemented `check_event_vs_preference(predicate, value_text, durability, category, evidence_text)`.
- Rejects single-transaction purchases (`"pay 250"`, `"buyer protection"`, `"sell as a whole"`) from being classified as `durability='preference'` unless explicit generalizing language (`always`, `never`, `policy`, `rule`) is present.
- Updated `infer_durability` to default transactional/build choices to `transient`.

### Rule 3 (Truth != Memory-Worthiness & Canonical Eligibility)
- Implemented `is_canonical_eligible(claim_or_proposal)`.
- Fails closed on:
  - `durability='transient'`
  - Point-in-time rewards or cash balances (Upside, Zen rewards)
  - Point-in-time entertainment subscription rosters (Hulu, Netflix, Disney)
  - Deliberative "what if" musings (`considers_repaying_loan`)
  - Single-transaction purchase tactics
  - Unconfirmed assistant proposals
- Enforced inside `adjudicate_candidate_claim` on `action='approve'` (requires explicit `--force` override if a human authority ever mandates promoting an otherwise ineligible claim).

### Rule 4 (Corroboration Enriches, Does Not Duplicate)
- Added `action='corroborate'` and `action='merge'` to `adjudicate_candidate_claim` and the CLI parser (`josie.candidate_claims corroborate`).
- Transfers all `claim_evidence` rows to the existing target claim using `INSERT OR IGNORE`.
- Recalculates confidence on the target claim via `evaluate_evidence_weight`.
- Marks the candidate claim as `status='superseded'`, `canonical_effect=0`, `superseded_by_claim_id=target_claim_id`.

### Rule 5 (Conservative Relationship Mapping)
- Added explicit validation in `check_claim_evidence_entailment`: "run a vape shop" does not support "jointly own a vape shop".
- Prohibits asserting business ownership without explicit ownership terms in evidence.
- Updated `LocalModelClaimExtractor` system prompt with conservative semantic mapping guidance.

---

## 5. Test Suite Verification

- **Candidate Claim Tests:** `tests/test_candidate_claims.py` (74/74 tests passing, 42.0s)
  - Added `Batch001PolicyHardeningTests` covering Rules 1, 2, 3, 4, and 5, human approval edits, durability overrides, temporal bounding, and canonical eligibility enforcement.
- **Knowledge Priming Tests:** `tests/test_knowledge.py` (17/17 tests passing, 2.5s)
- **Full Repository Test Suite:** `python -m unittest discover -s tests -p "test_*.py"`:
  - **454 tests ran in 245.8s — 100% OK (0 errors, 0 failures)**

---

## 6. Readiness for Batch 002

All human adjudication decisions for Batch 001 are applied, verified, and audited. The memory extraction pipeline is hardened against hallucinated accounts, event-as-preference conflation, transient clutter, duplicate canonical entries, and over-inferred legal relationships.

Josie Core is fully prepared to proceed to **ChatGPT Inheritance Batch 002**.

STOP

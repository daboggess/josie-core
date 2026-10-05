# CHATGPT INHERITANCE BATCH 001 — HUMAN REVIEW PACKET

**Date:** 2026-10-03  
**Repository:** `D:\Josie`  
**Branch:** `reconcile/live-work-20260917`  
**Batch Identifier:** `CHATGPT_INHERITANCE_BATCH_001`  
**Manifest SHA-256:** `c9a94e6e7e39f4c532954ae6bf3c76cb225bdaacc54169024d59bfd3fe23a7da`  
**Extractor Engine:** `LocalModelClaimExtractor(qwen3:14b)` on local Ollama + Fail-Closed Contract Validation  
**Staging Target:** `data/josie.db` (`memory_claims`, `claim_evidence`, `candidate_extractions`)  
**Canonical Effect:** `0` (Zero automatic promotions; 5 active canonical claims remain immutable)  
**Adjudication Scope:** Advisory Only — Awaiting Explicit Human Adjudication (Dustin)

---

## 1. Executive Summary & Operational Scope

This operational review packet documents **ChatGPT Inheritance Batch 001**, the first bounded candidate-memory extraction executed on Josie's ingested historical ChatGPT archive (`openai_chatgpt`).

### Core Epistemic Invariants Maintained:
1. **Zero Canonical Mutation:** Canonical memory claims in `data/josie.db` remain strictly at **5** (`canonical_effect=1`). Zero candidates were automatically approved or promoted.
2. **Evidence Authority Rule Enforced:** Only `role='user'` assertions establish facts about Dustin (`person:dustin`). Assistant assertions and pasted AI text blocks (`**BLUF:**...`) were strictly restricted to contextual/demonstrated behavior or rejected when unconfirmed.
3. **Bounded & Deterministic Selection:** Working backward from the newest point in the archive (August 25, 2026), exactly **5 complete conversations** comprising **244 textual conversation messages** (103 user, 141 assistant) were inspected, strictly within the $\le 250$ conversation message ceiling and $\le 150$ user message ceiling.
4. **Provenanced & Audited:** Every candidate claim links to exact `history_message_id` records in `claim_evidence` with verbatim text excerpts and character span boundaries.
5. **Replay Idempotency Verified:** Re-executing staging against the same batch produced **0 duplicate claims** and **0 mutations**.
6. **Zero Cloud Leakage:** All inference executed locally via Ollama with `qwen3:14b`.

---

## 2. Deterministic Batch Manifest & Corpus Inventory

| Conv ID | Date Range | Total Msgs | User | Asst | Conversation Title | Primary Domain / Topics |
|:---|:---|:---|:---|:---|:---|:---|
| **1692** | 2026-08-25 | 87 | 40 | 47 | Design Summit Chat Architecture | Josie AI system design, local model memory preference, multi-model debate |
| **1674** | 2026-08-14..25 | 38 | 13 | 25 | AI PC Build Resale | GPU resale build strategy, Upside/Zen rewards budget, case/PSU sourcing |
| **1691** | 2026-08-23..24 | 4 | 1 | 3 | TaskBounty emerges as the best agent marketplace | Autonomous agent workflows, minimal hands-on sales involvement |
| **1680** | 2026-08-17..24 | 83 | 40 | 43 | Everyday Discipleship Study | Vape shop business with Jess, Everyday Discipleship Study co-led with Kevin Slack |
| **1536** | 2026-05-18..08-23 | 32 | 9 | 23 | Budget Control Assistance | Rocket Money tracking, retained streaming subscriptions, mortgage debt baseline |

*Total Corpus:* **5 complete conversations**, **244 textual conversation messages**, **103 user messages**, **141 assistant messages** (thoughts/empty nodes excluded).  
*Batch Manifest Checksum:* `c9a94e6e7e39f4c532954ae6bf3c76cb225bdaacc54169024d59bfd3fe23a7da`

---

## 3. Extraction & Staging Audit

- **Proposals Generated & Validated:** 16 candidate claim proposals
- **Proposals Staged:** 16 candidate claims successfully staged into `memory_claims` (`canonical_effect=0`)
- **Evidence Links:** 16 provenance records created in `claim_evidence`
- **Candidate Extractions Records:** 16 audit rows in `candidate_extractions`
- **Proposals Excluded on Evidence Authority / Contract:** 1 proposal (attempted to assert Custom GPTs capability from pasted assistant turn without user confirmation)
- **Database Pre-Staging State:** 5 canonical claims, 21 non-canonical claims (Total: 26)
- **Database Post-Staging State:** 5 canonical claims, 37 non-canonical claims (Total: 42)
- **Canonical Invariant Check:** 5 == 5 (**PASS**)

---

## 4. Grouped Review Entries & Advisory Recommendations

### Profile / Identity / Business Background

#### Candidate 1: `claim:candidate:person:dustin:operates_business:666e11a5c4ee1d97`
- **Proposition:** operates a vape shop business with his wife Jess
- **Subject Entity:** `person:dustin`
- **Predicate:** `operates_business`
- **Category:** `profile`
- **Durability:** `durable`
- **Confidence:** `0.95` (Direct user statement in historical conversation (primary evidence))
- **Evidence Class:** `RETRIEVED`
- **Valid From:** `2026-08-17T19:36:55Z`
- **Advisory Recommendation:** **`APPROVE`**
- **Advisory Rationale:** Direct, durable personal profile fact stated by Dustin. Confirms joint business ownership (vape shop) with wife Jess, providing foundational family/business context.
- **Relationship to Existing Memory:** New primary profile fact; corroborates family relationship context.
- **Provenance Links:**
  * **Msg ID 20104** (Conv `6a835f2b-eda8-83ea-9d16-19b6c43eaa5d` | `user/user` -> `direct_user_assertion` | Time: `2026-08-17T19:36:55Z` | Span: `[105..179]`):
    > *"how Jess and I run our vape shop and how we have taken in a lot of strays."*

#### Candidate 2: `claim:candidate:person:dustin:uses_finance_tracker:253ba567db86c80b`
- **Proposition:** uses Rocket Money to categorize and track personal finances
- **Subject Entity:** `person:dustin`
- **Predicate:** `uses_finance_tracker`
- **Category:** `profile`
- **Durability:** `current_state`
- **Confidence:** `0.95` (Direct user statement in historical conversation (primary evidence))
- **Evidence Class:** `RETRIEVED`
- **Valid From:** `2026-05-18T17:15:05Z`
- **Advisory Recommendation:** **`APPROVE`**
- **Advisory Rationale:** Direct user assertion of software tooling used for budgeting and financial categorizations.
- **Relationship to Existing Memory:** New procedural/tooling context.
- **Provenance Links:**
  * **Msg ID 16190** (Conv `6a0b350d-7aac-83ea-aeda-f317c1ea25ed` | `user/user` -> `direct_user_assertion` | Time: `2026-05-18T17:15:05Z` | Span: `[0..97]`):
    > *"So I have Rocket Money, and it goes through and categorizes and tracks a lot of this stuff for me"*

#### Candidate 3: `claim:candidate:person:dustin:has_monthly_mortgage:030243e889b7fefd`
- **Proposition:** has a remaining home mortgage payment of approximately $1,500 per month
- **Subject Entity:** `person:dustin`
- **Predicate:** `has_monthly_mortgage`
- **Category:** `profile`
- **Durability:** `current_state`
- **Confidence:** `0.9` (Direct user statement in historical conversation (primary evidence))
- **Evidence Class:** `RETRIEVED`
- **Valid From:** `2026-05-18T17:59:35Z`
- **Advisory Recommendation:** **`REVIEW`**
- **Advisory Rationale:** Point-in-time financial liability ($1,500/mo mortgage). Useful baseline financial context, but should be marked current_state and verified periodically.
- **Relationship to Existing Memory:** New point-in-time financial profile fact.
- **Provenance Links:**
  * **Msg ID 16201** (Conv `6a0b350d-7aac-83ea-aeda-f317c1ea25ed` | `user/user` -> `direct_user_assertion` | Time: `2026-05-18T17:59:35Z` | Span: `[105..194]`):
    > *"the mortgage on the house that we have left, which is hitting us at about $1,500 a month."*

### Preferences & Strategic Directives

#### Candidate 4: `claim:candidate:person:dustin:prefers_maximizing_access_without_burning_limits:9eaa5ee271293d27`
- **Proposition:** want to give Josie as much access to you and Gemini, Bernie as possible without burning up my limits
- **Subject Entity:** `person:dustin`
- **Predicate:** `prefers_maximizing_access_without_burning_limits`
- **Category:** `preference`
- **Durability:** `preference`
- **Confidence:** `1.0` (Direct user statement in historical conversation (primary evidence))
- **Evidence Class:** `RETRIEVED`
- **Valid From:** `2026-08-25T16:16:47Z`
- **Advisory Recommendation:** **`APPROVE`**
- **Advisory Rationale:** Core operating goal: give Josie maximum intelligence and multi-model access without exhausting subscription rate limits.
- **Relationship to Existing Memory:** Corroborates candidate claim 'prefers_model_access_without_subscription_burn:5ffaa93fd9cba477'.
- **Provenance Links:**
  * **Msg ID 21070** (Conv `6a8d9741-259c-83ea-a623-2bae1e59417c` | `user/user` -> `direct_user_assertion` | Time: `2026-08-25T16:16:47Z` | Span: `[11..110]`):
    > *"I want to give it as much access to you and Gemini, Bernie as possible without burning up my limits"*

#### Candidate 5: `claim:candidate:person:dustin:has_preference:ebb6aa113a63653c`
- **Proposition:** Josie to be as intelligent as possible
- **Subject Entity:** `person:dustin`
- **Predicate:** `has_preference`
- **Category:** `preference`
- **Durability:** `preference`
- **Confidence:** `0.9` (Direct user statement in historical conversation (primary evidence))
- **Evidence Class:** `RETRIEVED`
- **Valid From:** `2026-08-25T16:31:57Z`
- **Advisory Recommendation:** **`APPROVE`**
- **Advisory Rationale:** High-level goal for Josie intelligence. Direct user statement.
- **Relationship to Existing Memory:** New general preference.
- **Provenance Links:**
  * **Msg ID 21087** (Conv `6a8d9741-259c-83ea-a623-2bae1e59417c` | `user/user` -> `direct_user_assertion` | Time: `2026-08-25T16:31:57Z` | Span: `[81..126]`):
    > *"I want this to be as intelligent as possible."*

#### Candidate 6: `claim:candidate:person:dustin:prefers:800c808f1200a4bd`
- **Proposition:** paying $250 with buyer protection for GPU purchase
- **Subject Entity:** `person:dustin`
- **Predicate:** `prefers`
- **Category:** `preference`
- **Durability:** `preference`
- **Confidence:** `0.9` (Direct user statement in historical conversation (primary evidence))
- **Evidence Class:** `RETRIEVED`
- **Valid From:** `2026-08-20T12:50:50Z`
- **Advisory Recommendation:** **`APPROVE`**
- **Advisory Rationale:** Direct user purchasing rule: willing to pay $250 for GPU if buyer protection is included.
- **Relationship to Existing Memory:** Refines candidate claim 'seeks GPU with at least 8GB VRAM under $300 budget'.
- **Provenance Links:**
  * **Msg ID 20033** (Conv `6a7e741c-57cc-83ea-8c14-0d7553c4ec30` | `user/user` -> `direct_user_assertion` | Time: `2026-08-20T12:50:50Z` | Span: `[0..87]`):
    > *"Or just pay 250 and be done..... buyer protection is nice, fb does it on shipped items."*

#### Candidate 7: `claim:candidate:person:dustin:seeks_profit_work_tier_with_minimal_regular_involvement:d8c141212d959159`
- **Proposition:** prefers work models requiring less ongoing personal/sales involvement
- **Subject Entity:** `person:dustin`
- **Predicate:** `seeks_profit_work_tier_with_minimal_regular_involvement`
- **Category:** `preference`
- **Durability:** `preference`
- **Confidence:** `0.9` (Direct user statement in historical conversation (primary evidence))
- **Evidence Class:** `RETRIEVED`
- **Valid From:** `2026-08-24T20:51:34Z`
- **Advisory Recommendation:** **`APPROVE`**
- **Advisory Rationale:** Direct user strategic goal: preference for autonomous/passive profit tiers requiring minimal ongoing sales involvement.
- **Relationship to Existing Memory:** New project/work preference.
- **Provenance Links:**
  * **Msg ID 20983** (Conv `6a8ae364-7694-83ea-8813-540635f2cc66` | `user/user` -> `direct_user_assertion` | Time: `2026-08-24T20:51:34Z` | Span: `[0..223]`):
    > *"Is there a better, more reliable profit work tier that we could figure out that still involves as little involvement from me as possible? Or as little regular involvement from me, or sales, or, you know, that sort of thing."*

#### Candidate 8: `claim:candidate:person:dustin:reduced_green_sky_payment_to_minimum:2850e9f4bc9d82d7`
- **Proposition:** from $350 to minimum
- **Subject Entity:** `person:dustin`
- **Predicate:** `reduced_green_sky_payment_to_minimum`
- **Category:** `preference`
- **Durability:** `current_state`
- **Confidence:** `0.9` (Direct user statement in historical conversation (primary evidence))
- **Evidence Class:** `RETRIEVED`
- **Valid From:** `2026-05-18T17:42:28Z`
- **Advisory Recommendation:** **`REVIEW`**
- **Advisory Rationale:** Point-in-time debt servicing adjustment (reduced GreenSky from $350 to minimum). Current state.
- **Relationship to Existing Memory:** New financial current state.
- **Provenance Links:**
  * **Msg ID 16191** (Conv `6a0b350d-7aac-83ea-aeda-f317c1ea25ed` | `user/user` -> `direct_user_assertion` | Time: `2026-05-18T17:42:28Z` | Span: `[0..43]`):
    > *"Also i dumped this down from 350 to minimum"*

#### Candidate 9: `claim:candidate:person:dustin:considers_repaying_401k_loan:3affb4a9bd802384`
- **Proposition:** to reach $170,000 mortgage payoff
- **Subject Entity:** `person:dustin`
- **Predicate:** `considers_repaying_401k_loan`
- **Category:** `preference`
- **Durability:** `current_state`
- **Confidence:** `0.85` (Direct user statement in historical conversation (primary evidence))
- **Evidence Class:** `RETRIEVED`
- **Valid From:** `2026-05-18T17:59:35Z`
- **Advisory Recommendation:** **`REVIEW`**
- **Advisory Rationale:** Deliberative consideration regarding $41,000 401(k) loan repayment toward $170k mortgage balance. Not a completed decision.
- **Relationship to Existing Memory:** New financial consideration.
- **Provenance Links:**
  * **Msg ID 16201** (Conv `6a0b350d-7aac-83ea-aeda-f317c1ea25ed` | `user/user` -> `direct_user_assertion` | Time: `2026-05-18T17:59:35Z` | Span: `[195..326]`):
    > *"I think we're at like $170,000. If I repay the $41,000 that I still have outstanding, that'd put me right around that exact number."*

#### Candidate 10: `claim:candidate:person:dustin:retained_subscriptions:6743b8bfe15b5c03`
- **Proposition:** cancelled non-essential recurring subscriptions while keeping Hulu, Netflix, Disney, Google, YouTube, and ChatGPT
- **Subject Entity:** `person:dustin`
- **Predicate:** `retained_subscriptions`
- **Category:** `preference`
- **Durability:** `current_state`
- **Confidence:** `0.95` (Direct user statement in historical conversation (primary evidence))
- **Evidence Class:** `RETRIEVED`
- **Valid From:** `2026-05-18T17:45:50Z`
- **Advisory Recommendation:** **`APPROVE`**
- **Advisory Rationale:** Direct user assertion of active recurring subscriptions (Hulu, Netflix, Disney, Google, YouTube, ChatGPT) and explicit policy to cancel other non-essential subscriptions.
- **Relationship to Existing Memory:** New financial preference and spend constraint.
- **Provenance Links:**
  * **Msg ID 16193** (Conv `6a0b350d-7aac-83ea-aeda-f317c1ea25ed` | `user/user` -> `direct_user_assertion` | Time: `2026-05-18T17:45:50Z` | Span: `[56..156]`):
    > *"The subscriptions, I canceled everything except for Hulu, Netflix, Disney, Google, YouTube, ChatGPT."*

#### Candidate 11: `claim:candidate:person:dustin:prefers_pc_resale_strategy:33787280b1dab592`
- **Proposition:** prefers selling PC builds as a whole unit rather than parting out individual components
- **Subject Entity:** `person:dustin`
- **Predicate:** `prefers_pc_resale_strategy`
- **Category:** `preference`
- **Durability:** `preference`
- **Confidence:** `0.95` (Direct user statement in historical conversation (primary evidence))
- **Evidence Class:** `RETRIEVED`
- **Valid From:** `2026-08-14T01:51:08Z`
- **Advisory Recommendation:** **`APPROVE`**
- **Advisory Rationale:** Clear user hardware build strategy preference (selling completed systems as a whole unit rather than parted out).
- **Relationship to Existing Memory:** New hardware project preference.
- **Provenance Links:**
  * **Msg ID 19977** (Conv `6a7e741c-57cc-83ea-8c14-0d7553c4ec30` | `user/user` -> `direct_user_assertion` | Time: `2026-08-14T01:51:08Z` | Span: `[0..26]`):
    > *"Sell as a whole preferably"*

#### Candidate 12: `claim:candidate:person:dustin:prefers_local_model_memory:186e9ce707620502`
- **Proposition:** prefers running a local AI model with larger memory and VRAM capacity
- **Subject Entity:** `person:dustin`
- **Predicate:** `prefers_local_model_memory`
- **Category:** `preference`
- **Durability:** `preference`
- **Confidence:** `0.95` (Direct user statement in historical conversation (primary evidence))
- **Evidence Class:** `RETRIEVED`
- **Valid From:** `2026-08-25T15:15:00Z`
- **Advisory Recommendation:** **`APPROVE`**
- **Advisory Rationale:** Direct user preference for local models with larger memory/VRAM to maintain state and avoid cloud card transitions. Aligns directly with Josie local-first architecture.
- **Relationship to Existing Memory:** Corroborates candidate claim 'prefers_local_first_desktop_ai_setup:7cd4ba7ee9db062d'.
- **Provenance Links:**
  * **Msg ID 21046** (Conv `6a8d9741-259c-83ea-a623-2bae1e59417c` | `user/user` -> `direct_user_assertion` | Time: `2026-08-25T15:15:00Z` | Span: `[0..147]`):
    > *"Yeah again this is another reason I want a local model with more memory because we already asked him that and he said he had moved on to a new card"*

### Hardware Inventory & Build Specifications

#### Candidate 13: `claim:candidate:system:josie:has_current_state:a8016cdbb5482ea6`
- **Proposition:** local model is an i7
- **Subject Entity:** `system:josie`
- **Predicate:** `has_current_state`
- **Category:** `hardware`
- **Durability:** `current_state`
- **Confidence:** `0.9` (Direct user statement in historical conversation (primary evidence))
- **Evidence Class:** `RETRIEVED`
- **Valid From:** `2026-08-25T17:07:11Z`
- **Advisory Recommendation:** **`APPROVE`**
- **Advisory Rationale:** Direct user statement confirming host processor baseline is an Intel Core i7.
- **Relationship to Existing Memory:** Corroborates candidate claim 'owns i7-7700 CPU and 32GB RAM' (Msg 4548).
- **Provenance Links:**
  * **Msg ID 21107** (Conv `6a8d9741-259c-83ea-a623-2bae1e59417c` | `user/user` -> `direct_user_assertion` | Time: `2026-08-25T17:07:11Z` | Span: `[257..295]`):
    > *"local model is nothing more than an i7"*

#### Candidate 14: `claim:candidate:person:dustin:budget_rewards_balance:8fdefd93f96d849b`
- **Proposition:** allocated $80 from Upside and $50 Amazon from Zen rewards toward PC build components
- **Subject Entity:** `person:dustin`
- **Predicate:** `budget_rewards_balance`
- **Category:** `hardware`
- **Durability:** `transient`
- **Confidence:** `0.95` (Direct user statement in historical conversation (primary evidence))
- **Evidence Class:** `RETRIEVED`
- **Valid From:** `2026-08-17T18:05:48Z`
- **Advisory Recommendation:** **`REVIEW`**
- **Advisory Rationale:** Transient allocation ($80 Upside + $50 Amazon Zen rewards earmarked for PC case/PSU). Accurately classified as durability='transient'.
- **Relationship to Existing Memory:** New transient hardware budget allocation.
- **Provenance Links:**
  * **Msg ID 19994** (Conv `6a7e741c-57cc-83ea-8c14-0d7553c4ec30` | `user/user` -> `direct_user_assertion` | Time: `2026-08-17T18:05:48Z` | Span: `[0..107]`):
    > *"Okay, so I have $80 from my Upside collection and $50 Amazon from my Zen rewards. 130 bucks on Amazon then."*

### Relational & Ministry Context

#### Candidate 15: `claim:candidate:person:dustin:ministry_co_leader:df3a909ad2b90e6e`
- **Proposition:** co-leads the Everyday Discipleship Study assisted by Kevin Slack
- **Subject Entity:** `person:dustin`
- **Predicate:** `ministry_co_leader`
- **Category:** `relationship_context`
- **Durability:** `current_state`
- **Confidence:** `0.9` (Direct user statement in historical conversation (primary evidence))
- **Evidence Class:** `RETRIEVED`
- **Valid From:** `2026-08-17T20:05:39Z`
- **Advisory Recommendation:** **`APPROVE`**
- **Advisory Rationale:** Direct personal relationship and ministry context. Identifies Kevin Slack as co-leader for the Everyday Discipleship Study.
- **Relationship to Existing Memory:** New relational/ministry context.
- **Provenance Links:**
  * **Msg ID 20112** (Conv `6a835f2b-eda8-83ea-9d16-19b6c43eaa5d` | `user/user` -> `direct_user_assertion` | Time: `2026-08-17T20:05:39Z` | Span: `[6..115]`):
    > *"Kevin Slack is assisting me. He asked if he could co-lead, I guess mostly because Mark's gonna be in and out."*

### Architecture & Model Proposals

#### Candidate 16: `claim:candidate:assistant:chatgpt:proposes:7a1e8715c70af2dc`
- **Proposition:** Josie should not be built around fixed roles or rigid architecture. She should be built around disciplined discernment, earned trust, simple solutions, and the ability to seek wise counsel when she recognizes a blind spot.
- **Subject Entity:** `assistant:chatgpt`
- **Predicate:** `proposes`
- **Category:** `architecture`
- **Durability:** `durable`
- **Confidence:** `0.6` (Quoted or pasted external content in historical conversation (secondary evidence; unconfirmed by user))
- **Evidence Class:** `INFERRED`
- **Valid From:** `2026-08-25T17:45:58Z`
- **Advisory Recommendation:** **`REJECT`**
- **Advisory Rationale:** Assistant-generated philosophical recommendation quoted from ChatGPT. While insightful, it lacks Dustin's explicit affirmation as an invariant and is classified as INFERRED (confidence 0.60).
- **Relationship to Existing Memory:** New assistant proposal; non-authoritative.
- **Provenance Links:**
  * **Msg ID 21123** (Conv `6a8d9741-259c-83ea-a623-2bae1e59417c` | `assistant/ChatGPT` -> `quoted_or_pasted_content` | Time: `2026-08-25T17:45:58Z` | Span: `[153..375]`):
    > *"Josie should not be built around fixed roles or rigid architecture. She should be built around disciplined discernment, earned trust, simple solutions, and the ability to seek wise counsel when she recognizes a blind spot."*

---

## 5. Corroboration & Memory Delta Analysis

### Corroborating Claims:
1. **Local Host Processor:** Candidate `system:josie:has_current_state:a8016cdbb5482ea6` ('local model is an i7') directly corroborates existing candidate `person:dustin:current_state:9c9c9d886c9d694d` ('owns i7-7700 CPU and 32GB RAM').
2. **Subscription Conservation:** Candidate `person:dustin:prefers_maximizing_access_without_burning_limits:9eaa5ee271293d27` directly corroborates existing candidate `person:dustin:prefers_model_access_without_subscription_burn:5ffaa93fd9cba477` ('to maintain existing subscription limits').
3. **Local First AI:** Candidate `person:dustin:prefers_local_model_memory:186e9ce707620502` reinforces `person:dustin:prefers_local_first_desktop_ai_setup:7cd4ba7ee9db062d`.

### Refining Claims:
1. **GPU Budget Rule:** Candidate `person:dustin:prefers:800c808f1200a4bd` ('paying $250 with buyer protection for GPU purchase') refines `person:dustin:preference:44afa9f306f344bf` ('under $300 budget').
2. **Hardware Sourcing:** Extends eBay-only buying preference to Facebook Marketplace when buyer protection applies.

### Net New Claims (High Value):
1. **Vape Shop Ownership:** Dustin and wife Jess operate a vape shop (`person:dustin:operates_business:666e11a5c4ee1d97`). Foundational profile context.
2. **Financial Management:** Uses Rocket Money (`uses_finance_tracker:253ba567db86c80b`), retains Hulu/Netflix/Disney/Google/YouTube/ChatGPT while cancelling other recurring subscriptions (`retained_subscriptions:6743b8bfe15b5c03`).
3. **Ministry Partnership:** Co-leads Everyday Discipleship Study assisted by Kevin Slack (`ministry_co_leader:df3a909ad2b90e6e`).

---

## 6. Adjudication Instructions

All 16 claims staged in this batch currently reside in `memory_claims` with `canonical_effect = 0`, `status = 'candidate'`, `approved_by = NULL`, and `reviewed_at = NULL`.
Per the Josie Constitution and Epistemic Architecture, an AI model may propose claims, but **ONLY Dustin** may approve or promote claims to canonical knowledge (`canonical_effect = 1`).

To adjudicate any of these claims via CLI:
```bash
python -m josie.candidate_claims approve <claim_id> --reviewer "Dustin" --confirmation "EXPLICIT HUMAN APPROVAL" --reason "<reason>"
python -m josie.candidate_claims reject <claim_id> --reviewer "Dustin" --reason "<reason>"
```

STOP

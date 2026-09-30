# First Canonical Memory Recall 001 — Retrieval Category Review & Closure

**Document Version:** 1.0.0  
**Phase:** Memory Vault — Retrieval Category Closure  
**Date:** 2026-09-30  
**Subject:** `person:dustin`  
**Predicate:** `has_durable_credential`  
**Repository:** `D:\Josie`  
**Branch:** `reconcile/live-work-20260917`  
**Target Claim:** `claim:candidate:person:dustin:has_durable_credential:4a70966b5994bdac`  

---

## 1. Executive Summary

During the First Real Canonical Memory Recall Loop (Pilot 001), exactly one historical claim was approved by Dustin:
> *"Dustin is A+ certified with years of experience with commercial servers."*

The claim was promoted with `authority_scope = "canonical:decision"` and was successfully recalled using a priming manifest specifying the category `"decision"`.

While the recall loop passed, this classification was semantically incorrect:
- A technical credential and professional server experience fact is an immutable **profile / background** fact.
- It is NOT an architectural or project **decision**.
- Treating `authority_scope` as both the security/governing authority level and the semantic retrieval category conflated two independent architectural dimensions.

This review documents:
1. The exact root cause of why this claim became `candidate:decision` and then `canonical:decision`.
2. The schema and code repair separating governing authority (`authority_scope`) from semantic retrieval category (`claim_category`).
3. The metadata correction for the approved credential claim in `data/josie.db`.
4. Verification of category filtering (retrieves under `profile`, excluded under `decision`).
5. Investigation of ordinary front-door automatic category selection (`BLOCKED`).

---

## 2. Root Cause Analysis: Why "canonical:decision" Occurred

A trace of the entire extraction, staging, adjudication, and knowledge-loading pipeline identified the compound root cause:

1. **Extraction Prompt Omission:**
   In `CandidateClaimExtractor._extract_batch` (`josie/candidate_claims.py`), explicit instructions were provided for `durability`, `subject_entity_id`, and `evidence_references` attribution, but zero classification rules were given for selecting among the 13 allowed categories in `ALLOWED_CLAIM_CATEGORIES`. The local model (`qwen3:14b`) picked `"decision"` for lack of explicit guidance.

2. **No Predicate-to-Category Normalization:**
   `CandidateClaimProposal.from_dict` and `validate_proposal` checked whether `claim_category` belonged to `ALLOWED_CLAIM_CATEGORIES`, but lacked semantic normalization mapping credentials, certifications, and experience (e.g., `has_durable_credential`) to `"profile"`.

3. **Schema Conflation in `memory_claims`:**
   The `memory_claims` SQLite table lacked an independent `claim_category` column. During staging (`stage_candidate_claims`), the system concatenated the status and proposed category into `authority_scope = f"candidate:{data['claim_category']}"`.

4. **Adjudication Authority Overwrite:**
   In `adjudicate_candidate_claim`, promotion logic replaced `"candidate:"` with `"canonical:"`:
   ```python
   new_auth = (
       f"canonical:{old_auth.split(':', 1)[1]}"
       if old_auth.startswith("candidate:")
       else (old_auth or "canonical:general")
   )
   ```
   This cemented `authority_scope = "canonical:decision"`.

5. **Knowledge Loading Interpretation:**
   In `josie/knowledge.py` (`load_knowledge_from_store`), `KnowledgeRecord.category` was extracted by splitting `authority_scope` on `:`:
   ```python
   if ":" in auth_scope:
       category = auth_scope.split(":", 1)[1]
   ```
   Consequently, priming manifests had to specify `"decision"` to retrieve the record.

---

## 3. Structural Architectural Repair

We cleanly separated governing authority from semantic retrieval category:

| Dimension | Field | Semantics | Allowed / Typical Values |
|---|---|---|---|
| **Governing Authority** | `authority_scope` | Security and governance level | `'canonical'`, `'candidate'`, `'constitution'`, `'canonical_seed'` |
| **Retrieval Category** | `claim_category` | Semantic topic for priming/retrieval | `'profile'`, `'hardware'`, `'preference'`, `'architecture'`, `'procedure'`, `'decision'`, `'identity'` |

### Implementation Changes

1. **Schema Migration (`josie/storage.py`):**
   - Added `claim_category TEXT` column to `memory_claims`.
   - Migration in `LocalStore._migrate_sqlite` adds the column non-destructively and backfills existing rows from `candidate_extractions` or `authority_scope`.

2. **Category Inference & Normalization (`josie/candidate_claims.py`):**
   - Added `infer_claim_category(predicate, value_text, subject_entity_id, proposed_category)` to deterministically map certifications, qualifications, and background to `"profile"`.
   - Updated `CandidateClaimProposal.__post_init__` and `from_dict` to normalize categories automatically.
   - Updated extractor prompt in `_extract_batch` with explicit category guidance.

3. **Staging & Adjudication (`josie/candidate_claims.py`):**
   - In `stage_candidate_claims`: `authority_scope` is set to `"candidate"`, and `claim_category` is populated directly.
   - In `adjudicate_candidate_claim`: `authority_scope` is updated to `"canonical"`, and `claim_category` is preserved as `"profile"`.

4. **Knowledge Store Integration (`josie/knowledge.py`):**
   - `load_knowledge_from_store` selects `claim_category` directly from `memory_claims`, falling back to `auth_scope` split only for legacy backwards-compatibility.
   - Preserves both `claim_category` and `authority_scope` in `KnowledgeRecord.metadata`.

---

## 4. Metadata Correction for Approved Credential Claim

Under Dustin's authorization, the metadata for the single approved claim was corrected in `data/josie.db`:

- **Claim ID:** `claim:candidate:person:dustin:has_durable_credential:4a70966b5994bdac`
- **Claim Text:** `A+ certified with years of experience with commercial servers` (UNTOUCHED)
- **Subject:** `person:dustin` (UNTOUCHED)
- **Predicate:** `has_durable_credential` (UNTOUCHED)
- **Durability:** `durable` (UNTOUCHED)
- **Status:** `active` (UNTOUCHED)
- **Canonical Effect:** `1` (UNTOUCHED)
- **Evidence References:** Msg 485, Takeout span [15..85], `direct_user_assertion` (UNTOUCHED)
- **Corrected Claim Category:** `profile` (was `decision`)
- **Corrected Authority Scope:** `canonical` (was `canonical:decision`)
- **Corrected Memory Layer:** `identity` (was `semantic`)
- **Audit ID:** `4379` (`event: claim_category_corrected`)

All other 4 candidate claims in `data/josie.db` remained unapproved candidates (`canonical_effect=0`).

---

## 5. Priming Verification Results

Priming tests executed directly against `data/josie.db` with `josie.knowledge.assemble_priming_from_knowledge`:

| Test Query | Manifest Categories | Retrieved Items | Credential Included? | Status |
|---|---|---|---|---|
| **Test A: Profile Priming** | `('profile',)` | 1 item (`claim:candidate:person:dustin:has_durable_credential:4a70966b5994bdac`) | **YES** | PASS |
| **Test B: Decision Priming** | `('decision',)` | 0 items | **NO** | PASS |
| **Test C: Bootstrap Priming** | `('architecture', 'procedure', 'identity')` | 4 items (supervisor separation, identity above models, dustin authority, destructive gate) | **NO** | PASS |
| **Test D: Candidate Exclusion** | All categories | 5 active canonical records | **Candidates Excluded** | PASS |

---

## 6. Front-Door Recall Boundary Investigation

### Fresh User Request Tested
> *"What technical certification or server experience do I have that's relevant to working on Josie?"*

### Evaluation
Sent through Josie's ordinary front-door execution paths without manual category hints:
1. `josie.context_builder.retrieval_trigger`:
   - Returns: `{'triggered': False, 'reason': 'none', 'domain': 'ordinary'}`
   - Barrier: The regex trigger only fires on naming/origins (`_CANONICAL_PATTERN`) or historical entity keywords (`_HISTORY_PATTERNS`).
2. `supervisor.remote_adapter.resolve_task_categories`:
   - Returns: `()` (empty tuple)
   - Barrier: Line 69 explicitly codifies the architecture rule:
     > *"Arbitrary conversational wording in `task` alone does NOT trigger categories."*
   - Categories are only triggered if the caller provides structured metadata (`priming_categories`, `task_class`) or touches specific code prefixes (`ARCH_PATH_PREFIXES`, `AUTHORITY_PATH_PREFIXES`).
   - Consequently, the supervisor generates an empty `PrimingBundle` (`items=0`).

### Outcome: BLOCKED
```
BLOCKED: automatic task-to-memory selection is not yet implemented
```

**Exact Boundary / API Barrier:**
`supervisor.remote_adapter.resolve_task_categories` (lines 54–118) and `josie.context_builder.retrieval_trigger` (lines 73–93).
Josie currently possesses deterministic category filtering once categories are known, but does not yet possess natural-language intent-to-category semantic classification from conversational prompts. This defines the next bounded engineering task.

---

## 7. Regression Verification Summary

- **Candidate Claims Suite:** 66/66 passing (`tests.test_candidate_claims`)
- **Full Repository Suite:** 423/423 passing (`unittest discover -s tests`)
- **Whitespace / Diff Check:** `git diff --check` clean (0 errors)

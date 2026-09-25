# Build Receipt: Memory Vault Phase 3B v1

**Milestone:** Phase 3B: Candidate Claim Extraction + Adjudication Pipeline
**Repository:** `daboggess/josie-core`
**Branch:** `reconcile/live-work-20260917`
**Base HEAD:** `9dd215ca3863dfc6c85db15149450a3d9b308a94`
**Date:** 2026-09-25
**Role:** Implementation Engineer for Josie Core
**Reviewer Authority:** Dustin (Sole Human Authority)

---

## 1. Executive Summary

Phase 3B v1 formalizes the boundary between unverified historical evidence and Josie's canonical beliefs. The system prevents unvetted historical claims or automated extraction outputs from automatically entering worker prompts or supervisor routing.

All historical messages remain immutable in `history_messages`. When claims are proposed by extractors or rule heuristics, they are staged into `memory_claims` with `status='candidate'`, `canonical_effect=0`, `approved_by=NULL`, and zero priming authority. Only explicit human adjudication (`reviewer='Dustin'` with `APPROVAL_CONFIRMATION='EXPLICIT HUMAN APPROVAL'`) can promote a candidate claim to canonical knowledge (`status='active'`, `canonical_effect=1`, `evidence_class='CANONICAL'`).

## 2. Core Epistemic Invariants Verified

1. **Extraction Boundary:**
   - Raw Evidence != Candidate Claim != Canonical Knowledge != Primed Worker Context.
   - Models/extractors may propose claims; models/extractors may **never** approve claims.
2. **Deterministic Stable Deduplication:**
   - Propositions are identified by `claim:candidate:{subject_entity_id}:{predicate}:{normalized_value_hash}`.
   - Re-discovery across distinct historical messages appends provenance links to `claim_evidence` without duplicate claim rows.
   - Contradictory statements form separate candidate claims and are never silently merged.
3. **Role-Weighted Confidence:**
   - Direct user statements (`role='user'`, `speaker='Dustin'`) receive primary weighting (0.85 - 1.0 confidence).
   - Assistant assertions (`role='assistant'`) are capped at <= 0.60 confidence with explicit secondary basis notation.
4. **Strict Priming Isolation (Section J):**
   - Pending candidates (`status='candidate'`, `canonical_effect=0`): **ZERO** priming authority.
   - Rejected candidates (`status='rejected'`, `canonical_effect=0`): **ZERO** priming authority.
   - Needs-review / disputed candidates (`status='disputed'`, `canonical_effect=0`): **ZERO** priming authority.
   - Superseded claims (`status='superseded'`, `canonical_effect=0`): **ZERO** priming authority.
   - Only active approved claims (`status='active'`, `canonical_effect=1`, `approved_by='Dustin'`) enter `assemble_priming_from_knowledge` or worker prompt manifests.
5. **Temporal Supersession & Provenance Retention:**
   - When a claim is superseded by an updated policy, its status becomes `superseded` and `canonical_effect` becomes `0`.
   - Historical evidence links and audit history remain permanently intact; historical evidence is never deleted.
6. **Bounded Evidence Processing:**
   - Enforces `DEFAULT_MAX_BUNDLE_MESSAGES=50`, `DEFAULT_MAX_BUNDLE_CHARS=25000`, and `DEFAULT_MAX_MESSAGE_CHARS=2500`.
   - Large message streams are chunked via `split_evidence_bundle`.
7. **Adjudication Atomicity & Rollback:**
   - Database operations execute within transactions; any failure during adjudication immediately triggers rollback, leaving the candidate unmutated.
8. **Strict Human Approval Gate:**
   - `adjudicate_candidate_claim()` and CLI `approve` fail closed unless explicit human confirmation token (`EXPLICIT HUMAN APPROVAL`) is provided.
   - A caller passing `reviewer='Dustin'` alone without confirmation fails with `PermissionError`.
   - CLI approval command requires `--reviewer` and `--confirmation` with no default bypasses.
   - Models/workers (`opencode`, `goose`, `assistant`, `model`, etc.) are prohibited from approving, rejecting, or disputing claims.
9. **Separate Extraction & Live Staging Modes:**
   - `extract --dry-run` performs inspection/proposals validation with zero database writes.
   - `extract --stage` persists validated non-canonical review candidates (`status='candidate'`, `canonical_effect=0`, `approved_by=NULL`) with zero priming authority.
   - Re-running live staging is idempotent.
10. **Centralized Schema Architecture:**
   - `candidate_extractions` table is initialized centrally in `LocalStore._initialize` in `josie/storage.py`, ensuring deterministic schema generation on fresh stores.

## 3. Section K Synthetic History Reference Fixture

The full lifecycle and temporal evolution is verified in `tests/test_candidate_claims.py::test_24_synthetic_history_fixture_full_lifecycle_and_temporal_evolution`:
- **Message 1** (`2026-08-01`): *"For coding tasks, use OpenCode as the primary coding worker."*
- **Message 2** (`2026-08-15`): *"Update policy: Goose is primary; OpenCode is fallback."*
- **Message 3** (`2026-08-20`): *"Remember our test policy: Do not let NOT_RUN win a result gate."*

### Lifecycle Steps Verified:
1. **Raw Evidence Seeding:** Messages inserted into `history_messages`.
2. **Extraction:** Rule-based extraction produces 3 valid candidate claim proposals.
3. **Staging:** Candidates staged with `status='candidate'`, `canonical_effect=0`.
4. **Zero Authority Check:** Manifest queries for `architecture` and `procedure` return 0 items.
5. **Adjudication 1:** Dustin approves OpenCode policy -> promoted to active canonical; primes into architecture tasks.
6. **Adjudication 2 (Supersession):** Dustin approves Goose primary policy with `supersedes_claim_id=claim_1`:
   - Goose claim promoted to active canonical (`canonical_effect=1`).
   - OpenCode claim transitions to superseded (`canonical_effect=0`).
   - OpenCode historical evidence remains 100% intact in `claim_evidence`.
   - Architecture priming delivers Goose policy and strictly excludes OpenCode policy.
7. **Adjudication 3:** Dustin approves NOT_RUN gate policy -> promoted to active canonical; primes into procedure tasks.
8. **Provenance Verification:** All claims retain complete chain-of-custody to source `history_messages`.

## 4. Test Verification Evidence

### Candidate Claims Test Suite (`tests/test_candidate_claims.py`):
- **Command:** `python -m unittest tests/test_candidate_claims.py`
- **Result:** **33 tests passed** in **17.61s** (0 failures, 0 errors).
  - `test_01` - `test_03`: Proposal structure, model self-approval rejection, stable proposition ID hashing.
  - `test_04` - `test_06`: Staging defaults, evidence aggregation, opposing values yield distinct claims.
  - `test_07` - `test_08`: User vs assistant weighting, extraction window bounds.
  - `test_09` - `test_12`: Human approval gate, model reviewer rejection, confirmation token, evidence requirement.
  - `test_13` - `test_15`: Rejection preserves provenance, needs_review marks disputed, supersession retains prior record.
  - `test_16` - `test_20`: Strict priming isolation, priming assembly, audit log immutability.
  - `test_21` - `test_23`: Inspection queue, dry-run extraction, live database protection.
  - `test_24`: Section K synthetic history fixture (full lifecycle & temporal supersession).
  - `test_25`: Bounded evidence bundle limit enforcement.
  - `test_26`: Adjudication transactional rollback on failure.
  - `test_27`: Lifecycle needs_review action and inspection queue.
  - `test_28`: Claim taxonomy validation (all 13 categories).
  - `test_29`: CLI commands (list, inspect, approve, reject, show-provenance, verify-canonical).
  - `test_30`: Section J 5-condition strict priming isolation.
  - `test_31`: Strict human confirmation requirement (Dustin alone fails, bad token fails, models fail, correct approval succeeds, non-approval actions gated).
  - `test_32`: Real live staging vs dry-run CLI/pipeline (zero writes on dry-run, non-canonical staging, zero priming, idempotency, fail-closed out-of-window).
  - `test_33`: Centralized `candidate_extractions` schema initialization on fresh `LocalStore`.

### Full Repository Regression Suite:
- **Command:** `python -m unittest discover -s tests -p "test_*.py"`
- **Result:** **390 tests passed** in **93.82s** (0 failures, 0 errors).
  - `tests/test_candidate_claims.py`: 33 passed.
  - `tests/test_evidence_ingestion.py`: 22 passed.
  - `tests/test_knowledge.py`: 17 passed.
  - `tests/test_frontdoor_priming.py` & `test_supervisor_remote_bridge.py`: 21 passed.
  - `tests/test_josie.py`: 116 passed.
  - All other subsystem test suites: 100% passing.

### Database Safety Confirmation:
- The production database at `D:\Josie\data\josie.db` was guarded and verified untouched across all test executions.

## 5. Artifacts and Files Created / Modified

- `josie/storage.py`: Centralized `candidate_extractions` table creation in `LocalStore._initialize`.
- `josie/candidate_claims.py`: Core Phase 3B module (extraction interface, bounded bundles, staging, taxonomy, strict human approval gate, live staging CLI).
- `tests/test_candidate_claims.py`: 33 automated test cases verifying all Phase 3B specifications.
- `docs/memory/CANDIDATE_CLAIMS.md`: Architectural design, CLI guide, taxonomy reference, and Section K documentation.
- `docs/memory/PHASE_3B_RECEIPT.md`: Formal build receipt.

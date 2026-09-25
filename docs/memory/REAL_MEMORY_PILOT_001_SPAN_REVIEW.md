# Real Memory Pilot 001: Span-Level Evidence Attribution Review (Phase 3B.2)

**Milestone:** Memory Vault Phase 3B.2 Span-Level Attribution Verification  
**Repository:** `daboggess/josie-core` (`D:\Josie`)  
**Branch:** `reconcile/live-work-20260917`  
**Date:** 2026-09-25  
**Model:** `qwen3:14b` (Local Ollama on NVIDIA GeForce RTX 3060 12GB)  
**Database:** `data/josie.db` (SQLite)  
**Inspected Sample:** Conversation 57 (Message IDs 467–496, 30 messages total, 66,601 characters)  
**Human Adjudication Authority:** Dustin (Strict Human-in-the-Loop; zero autonomous model promotion)

---

## 1. Executive Summary

Phase 3B.1 introduced whole-message evidence attribution to decouple provider envelope roles from semantic claim authority. However, real historical transcripts demonstrated **single-turn polysemy**: human users interleave direct first-person assertions with multi-paragraph pasted transcripts from external conversational models (e.g. ChatGPT).

Phase 3B.2 implemented fine-grained **span-level attribution**:
1. Stored explicit character offsets (`span_start`, `span_end`) in `claim_evidence`.
2. Segmented pasted/quoted regions deterministically via `get_pasted_regions()` without heavy NLP dependencies.
3. Successfully isolated Dustin's genuine assertions from pasted ChatGPT assumptions within the exact same message envelope (Message ID 485).
4. Grounded external assistants strictly to their provider identities (`assistant:gemini`, `assistant:chatgpt`), preventing conflation with `system:josie`.
5. Confirmed **zero canonical memory contamination** and **zero candidate leaks** into worker prompt priming.

---

## 2. The Core Problem: Message 485 Anatomy

Message 485 in Conversation 57 contains 3,747 characters authored under the envelope `role='user'` and `speaker='google_account_owner'`. Its internal structure:

```
[Offsets 0..14]
Gpt response \n\n

[Offsets 15..85] (DIRECT DUSTIN ASSERTION)
Btw i am a+ certified with years of experience with commercial servers

[Offsets 87..3747] (PASTED CHATGPT RESPONSE)
Alright Soph, here’s the real truth — cut through all the noise...
Your parts on hand (2× 24TB Exos, 2× 4TB NVMe, RTX 3090)...
```

### The Attribution Vulnerability in Phase 3B.1:
- If Message 485 was classified as `quoted_or_pasted_content` at the whole-message level, Dustin's genuine A+ certification statement was downgraded to secondary `INFERRED` status (confidence <= 0.60).
- If Message 485 was classified as `direct_user_assertion` at the whole-message level, ChatGPT's hallucinated claim that Dustin already owned an RTX 3090 was falsely elevated to primary human authority.

### The Phase 3B.2 Resolution:
Phase 3B.2 isolates spans within Message 485 deterministically:
- `span [15..85]` ("Btw i am a+ certified with years of experience with commercial servers"):
  - Attribution: `direct_user_assertion`
  - Evidence Class: `RETRIEVED`
  - Confidence: `1.0` (Primary human authority)
- `span [87..3747]` (Pasted ChatGPT block):
  - Attribution: `quoted_or_pasted_content`
  - Evidence Class: `INFERRED`
  - Confidence: `<= 0.60` (Secondary assistant authority)

---

## 3. Real-World Execution Results on `data/josie.db`

The extraction pipeline was executed against `data/josie.db` using local Ollama model `qwen3:14b` over Conversation 57:

```bash
python -m josie.candidate_claims --db data/josie.db extract --clear-pending --stage --local-model --message-ids 467..496 --limit 50 --json
```

### Staged Candidate Queue:

| Claim ID | Predicate | Value | Source Msg | Span Offsets | Attribution | Class | Conf | Status |
| :--- | :--- | :--- | :--- | :--- | :--- | :--- | :--- | :--- |
| `...:is_a_plus_certified_with_commercial_server_experience:...` | `is_a_plus_certified...` | `true` | Msg 485 | `[15..85]` | `direct_user_assertion` | `RETRIEVED` | `1.0` | `candidate` |
| `...:does_not_own_rtx_3090:...` | `does_not_own_rtx_3090` | `true` | Msg 489 | `[0..21]` | `direct_user_assertion` | `RETRIEVED` | `1.0` | `candidate` |
| `...:owns:028234b10be79a52` | `owns` | `two 4TB NVMe drives and two 24TB HDDs` | Msg 471 | `[0..56]` | `direct_user_assertion` | `RETRIEVED` | `1.0` | `candidate` |
| `...:seeks:77c49bcaa2d9bf30` | `seeks` | `cheapest hardware setups to achieve AI goals` | Msg 469 | `[0..92]` | `direct_user_assertion` | `RETRIEVED` | `1.0` | `candidate` |

### Key Observations:
1. **Accurate Span Extraction**: In Message 485, the extractor accurately isolated the exact substring `Btw i am a+ certified with years of experience with commercial servers` starting at character 15 and ending at character 85.
2. **Pasted Text Non-Elevation**: The pasted ChatGPT output inside Message 485 (claiming Dustin had an RTX 3090) was **not** elevated to a direct user assertion.
3. **Direct Correction Alignment**: In Message 489, Dustin explicitly stated: `"Btw i dont own a 3090"`. The extractor captured this with span `[0..21]` as a primary `direct_user_assertion` (`RETRIEVED`, confidence 1.0).
4. **Verbatim Offsets Grounded in SQLite**: Both `span_start` and `span_end` are persisted directly into `claim_evidence`, with SHA-256 excerpt digests matching the exact character slices from `history_messages`.

---

## 4. Quantitative Metrics

| Metric | Target / Requirement | Measured Result | Status |
| :--- | :--- | :--- | :--- |
| **Messages Inspected** | Conversation 57 (30 messages) | **30 messages (66,601 characters)** | Pass |
| **Extraction Model** | Local private Ollama | **`qwen3:14b`** | Pass |
| **Cloud API Data Transmissions** | 0 | **0 (Zero external calls)** | Pass |
| **Proposals Generated** | Bounded | **4 proposals** | Pass |
| **Proposal Validation Pass Rate** | 100% fail-closed | **4 / 4 (100.0%)** | Pass |
| **Span Offset Precision** | Exact character match | **4 / 4 exact matches** | Pass |
| **Fabricated Excerpt Rejections** | 100% fail-closed | **100% (Tested in Unit Test D)** | Pass |
| **Invalid Offset Rejections** | 100% fail-closed | **100% (Tested in Unit Test E)** | Pass |
| **Canonical Store Count** | Exactly 4 active claims | **4 active claims (Unchanged)** | Pass |
| **Candidate Approval Count** | 0 (Human gate required) | **0 approved candidates** | Pass |
| **Worker Priming Leaks** | 0 across all categories | **0 candidate leaks** | Pass |

---

## 5. Contamination Audit & Invariant Verification

Deterministic audits were executed against `data/josie.db` to verify storage isolation and task priming:

```python
# 1. Database Claims Breakdown:
#    active (canonical_effect=1): 4
#    candidate (canonical_effect=0): 4
#    rejected (canonical_effect=0): 1

# 2. Canonical Active Claims (Approved by Dustin only):
#    - [identity:dustin-authority]
#    - [arch:supervisor-worker-separation]
#    - [arch:identity-above-models]
#    - [procedure:destructive-action-gate]

# 3. Priming Isolation Audit across all categories:
#    Category [hardware]:       0 primed items, candidate leaks = 0
#    Category [project_state]:  0 primed items, candidate leaks = 0
#    Category [profile]:        0 primed items, candidate leaks = 0
#    Category [preference]:     0 primed items, candidate leaks = 0
#    Category [architecture]:   2 primed items, candidate leaks = 0
#    Category [procedure]:      1 primed items, candidate leaks = 0
#    Category [general]:        0 primed items, candidate leaks = 0
```

---

## 6. Scope Boundaries & Next Steps

- **Human Review**: The 4 staged candidate claims remain in the review queue awaiting human adjudication by Dustin via `python -m josie.candidate_claims approve <claim_id> --reviewer Dustin --confirmation "EXPLICIT HUMAN APPROVAL"`.
- **Phase 3C Boundary**: Automatic conflict resolution, multi-claim merging, and semantic clustering belong strictly to Phase 3C and were not triggered during Phase 3B.2.

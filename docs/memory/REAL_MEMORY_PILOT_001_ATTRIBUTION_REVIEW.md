# Real Memory Pilot 001: Evidence Attribution & Identity Review (Phase 3B.1)

## Executive Summary

During the initial run of Real Memory Pilot 001 on historical Conversation 57 (messages 467–496, dated November 27, 2025), two critical epistemic risks were discovered in the candidate extraction pipeline:

1. **Provider Envelope Conflation**: Because message 485 had provider envelope `role: "user"` and `speaker: "google_account_owner"`, the extractor treated third-party AI content pasted by Dustin (a ChatGPT response claiming Dustin owned an RTX 3090) as a direct Dustin assertion with `confidence = 1.0` and `evidence_class = "RETRIEVED"`.
2. **Assistant Identity Conflation**: Advice and hardware opinions offered by Google's Gemini Apps cloud assistant in November 2025 were erroneously normalized to `subject_entity_id = "system:josie"`, treating external cloud model output as Josie architectural facts.

Phase 3B.1 successfully decoupled provider envelope roles from semantic speaker authority, introduced a strict 4-class evidence attribution model, enforced external assistant identity isolation, and verified that zero candidate claims contaminate canonical memory or worker priming.

---

## Epistemic Architecture & Attribution Model

### The 4-Class Attribution Taxonomy

Provider envelope roles (`role="user"`, `role="assistant"`) represent transport-level metadata, NOT semantic authority. Phase 3B.1 formalizes:

```python
ALLOWED_ATTRIBUTIONS = frozenset({
    "direct_user_assertion",      # Dustin speaking directly
    "assistant_assertion",        # Conversational assistant (Gemini, Claude, etc.)
    "quoted_or_pasted_content",   # Pasted AI or external text inside a turn
    "ambiguous_source",           # Mixed, unverified, or unclear origin
})
```

### Authority & Evidentiary Weight Hierarchy

| Attribution | Evidence Class | Base Confidence | Priming Eligibility | Description |
|---|---|---|---|---|
| `direct_user_assertion` | `RETRIEVED` | 0.85 – 1.0 | Requires Human Approval | Spoken directly by Dustin. Primary evidence. |
| `assistant_assertion` | `INFERRED` | <= 0.60 | Requires Human Approval | Direct statement by external AI. Secondary evidence. |
| `quoted_or_pasted_content` | `INFERRED` | <= 0.60 | Requires Human Approval | Quoted/pasted external AI. Secondary evidence. |
| `ambiguous_source` | `INFERRED` | <= 0.50 | Requires Human Approval | Contextual/unverified source. Lowest weight. |

### Deterministic Classifiers & Boundary Enforcement

1. **Pasted Marker Detection**: User messages beginning with or containing pasted AI indicators (e.g. `gpt response`, `chatgpt response`, `chapgpt response`, `chatgpt:`, `from gpt`, blockquote markers `> `) are deterministically classified as `quoted_or_pasted_content`.
2. **Assistant Identity Normalization**:
   - `Gemini Apps` -> `assistant:gemini`
   - `ChatGPT` -> `assistant:chatgpt`
   - System architecture specifications -> `system:josie` ONLY when describing Josie's actual software architecture.
3. **Weighting Gate (`evaluate_evidence_weight`)**: Envelope `role == 'user'` alone does NOT grant primary authority. Only claims supported by `direct_user_assertion` receive `RETRIEVED` and high confidence.

---

## Detailed Case Analysis: Message 485 vs Message 489

### The Ground Truth

In Message 485, Dustin pasted a ChatGPT response:
```text
Gpt response 

Btw i am a+ certified with years of experience with commercial servers

Alright Soph, here’s the real truth – cut through all the noise...
Your parts on hand (2× 24TB Exos, 2× 4TB NVMe, RTX 3090)
```
ChatGPT falsely hallucinated that Dustin owned an RTX 3090. In Message 489, Dustin directly corrected the record:
```text
Btw i dont own a 3090
```

### Before Phase 3B.1 vs After Phase 3B.1

| Metric / Dimension | Pilot 001 (Initial) | Pilot 001 (Phase 3B.1 Attribution) |
|---|---|---|
| **Msg 485 Attribution** | Direct Dustin Assertion (`role: user`) | `quoted_or_pasted_content` |
| **Msg 485 Confidence** | `1.0` (`RETRIEVED`) | `0.60` (`INFERRED`) |
| **Msg 485 Basis** | "Direct user statement" | "Quoted or pasted external content" |
| **Msg 489 Extraction** | `does_not_own_hardware` (Dustin) | `does_not_own_hardware` (Dustin) |
| **Msg 489 Attribution** | Direct User Assertion | `direct_user_assertion` |
| **Msg 489 Confidence** | `0.95` (`RETRIEVED`) | `0.95` (`RETRIEVED`) |
| **Gemini Subject ID** | `system:josie` (Conflated) | `assistant:gemini` (Isolated) |
| **Gemini Attribution** | Unclassified / Secondary | `assistant_assertion` |
| **Canonical Effect** | `0` (Zero contamination) | `0` (Zero contamination) |

---

## Current Review Queue in `data/josie.db`

Re-running the extraction pipeline on Conversation 57 (messages 467–496) staged 6 non-canonical candidate records in `data/josie.db`:

```
Candidate Claims (6 records, status=candidate):
 1. [PENDING] claim:candidate:person:dustin:does_not_own_hardware:58256dc9b4be1c96
    Value: does not own an RTX 3090
    Confidence: 0.95 (Direct user statement in historical conversation (primary evidence))
    Attribution: direct_user_assertion | Speaker: google_account_owner/user | Msg: 489

 2. [PENDING] claim:candidate:person:dustin:has_professional_certification:4a70966b5994bdac
    Value: A+ certified with years of experience with commercial servers
    Confidence: 0.60 (Quoted or pasted external content in historical conversation (secondary evidence; unconfirmed by user))
    Attribution: quoted_or_pasted_content | Speaker: google_account_owner/user | Msg: 485

 3. [PENDING] claim:candidate:assistant:gemini:asserts_hardware_compatibility_issue:884d7e462c64439f
    Value: RTX 3090 + 24TB Exos in proprietary server (TD350) creates physical nightmare
    Confidence: 0.60 (Assistant assertion in historical conversation (secondary evidence; unconfirmed by user))
    Attribution: assistant_assertion | Speaker: Gemini Apps/assistant | Msg: 484

 4. [PENDING] claim:candidate:assistant:gemini:asserts_hardware_cost_comparison:f3b86434e6693efe
    Value: RTX 3090 costs ~$750 used vs Tesla P40 at ~$175 used
    Confidence: 0.60 (Assistant assertion in historical conversation (secondary evidence; unconfirmed by user))
    Attribution: assistant_assertion | Speaker: Gemini Apps/assistant | Msg: 490

 5. [PENDING] claim:candidate:assistant:gemini:asserts_hardware_price_range:ffe4d49977b4f7e6
    Value: working RTX 3090 trades for $600–$700 on eBay
    Confidence: 0.60 (Assistant assertion in historical conversation (secondary evidence; unconfirmed by user))
    Attribution: assistant_assertion | Speaker: Gemini Apps/assistant | Msg: 494

 6. [PENDING] claim:candidate:person:dustin:requests_information_on_components_for_option_1:a755f58b8a701cf0
    Value: psu, fans, coolers ect
    Confidence: 1.0 (Direct user statement in historical conversation (primary evidence))
    Attribution: direct_user_assertion | Speaker: google_account_owner/user | Msg: 481
```

---

## Canonical Knowledge Contamination Verification

A database audit of `data/josie.db` confirms zero contamination of canonical memory:

- `canonical_effect = 1` claims: **Exactly 4**
  - `identity:dustin-authority` (`person:dustin`)
  - `arch:supervisor-worker-separation` (`system:josie`)
  - `arch:identity-above-models` (`system:josie`)
  - `procedure:destructive-action-gate` (`system:josie`)
- `canonical_effect = 0` candidate claims: **6** (all pending human adjudication, none approved)
- `canonical_effect = 0` rejected claims: **1** (`witness:genesis-clm-012-bernie-values`)
- **Priming leakage**: **0 items**. Running `assemble_priming_from_knowledge()` returns strictly active canonical claims, with 0 candidate items primed.

---

## Summary of Completed Acceptance Criteria

1. **Envelope Decoupling**: Implemented `classify_evidence_attribution()` and updated `evaluate_evidence_weight()`.
2. **Schema Migration**: Added `attribution` column to `claim_evidence` and `EvidenceReference`.
3. **Identity Isolation**: Ensured Gemini Apps maps to `assistant:gemini` and ChatGPT to `assistant:chatgpt`, preventing `system:josie` identity pollution.
4. **Test Fixtures (A–G)**: Added unit test suite `TestEvidenceAttribution` in `tests/test_candidate_claims.py` verifying direct, pasted, assistant, and ambiguous attribution, hierarchy ordering, adjudication gates, and priming isolation (41/41 passing).
5. **Real Pilot Re-Run**: Safely re-staged review queue on Conversation 57 with local model `qwen3:14b`.
6. **Zero Memory Contamination**: Durably verified in `data/josie.db`.

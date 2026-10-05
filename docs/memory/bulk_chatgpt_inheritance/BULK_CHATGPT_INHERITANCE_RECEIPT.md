# Production Build Receipt: Bulk ChatGPT Historical Corpus Inheritance

**Milestone:** Production Bulk Candidate Claim Extraction & Inheritance  
**Repository:** `daboggess/josie-core` (`D:\Josie`)  
**Branch:** `reconcile/live-work-20260917`  
**Date:** 2026-10-04  
**Extractor Engine:** `LocalModelClaimExtractor(qwen3:14b)` on local Ollama (`http://127.0.0.1:11434`)  
**Database:** `data/josie.db`  
**Master Manifest SHA-256:** `manifests/master_bulk_manifest.json`  
**Canonical Invariant Status:** Strictly 10 before -> strictly 10 after (`canonical_effect=1`)  
**Candidate Approvals Created:** Exactly 0 (`approved_by=NULL`, `reviewed_at=NULL`)  
**Zero Cloud Inference:** 100% local GPU execution  
**Final Verdict:** **PASS**  

---

## 1. Corpus Reconciliation Audit

- **Total Imported ChatGPT Conversations in Database:** 702
- **Batch 001 Processed Conversations:** 5
- **Batch 002 Processed Conversations:** 9
- **Batch 003 Processed Conversations:** 15
- **Bulk Units Processed:** 32 / 32 units
- **Bulk Conversations Processed:** 673
- **Reconciliation Arithmetic:** 29 (prior batches) + 673 (bulk units) = 702 / 702
- **Unaccounted Conversations:** **0** (Exact 100% corpus reconciliation: PASS)

## 2. 18-Point Extraction Funnel Cumulative Totals

01. **source_conversations_processed:** 673
02. **textual_messages_processed:** 11871
03. **user_messages_processed:** 5562
04. **raw_model_proposals:** 575
05. **assistant_authority_rejections:** 19
06. **entailment_rejections:** 2
07. **hypothetical_fictional_rejections:** 39
08. **event_preference_rejections:** 0
09. **transient_noise_suppression:** 70
10. **historical_only_routing:** 68
11. **duplicate_corroborating_evidence:** 0
12. **personal_memory_candidates:** 234
13. **project_architecture_candidates:** 4
14. **hardware_state_candidates:** 116
15. **runbook_procedural_candidates:** 5
16. **sensitive_review_candidates:** 5
17. **extraction_errors:** 2
18. **malformed_source_problems:** 34

## 3. Destination Routing Breakdown

- **context_archive:** 0
- **hardware_state:** 116
- **historical_only:** 68
- **personal_canonical:** 234
- **project_architecture:** 4
- **runbook_procedure:** 5
- **sensitive_review:** 5
- **transient_noise:** 49

## 4. Canonical & Safety Invariant Audit

- **Canonical Claims Count Before Bulk Extraction:** 10
- **Canonical Claims Count After Bulk Extraction:** **10** (Invariant Strictly Preserved: PASS)
- **Total Candidate Claims in Database:** 559
- **Total Provenance Evidence Links:** 594
- **Candidates with `approved_by` set:** **0** (Human-only authority preserved: PASS)
- **Candidates with `canonical_effect = 1`:** **0** (Zero automatic promotion: PASS)
- **Quarantined Sensitive Items:** **6** (Quarantined in `sensitive_review`: PASS)
- **Replay Idempotency Verification:** **PASS** (Zero duplicate records on re-staging across all units)

## 5. Review Artifacts Generated

- Summary: `docs/memory/bulk_chatgpt_inheritance/BULK_CHATGPT_INHERITANCE_SUMMARY.md`
- Priority A (Personal Canonical): `docs/memory/bulk_chatgpt_inheritance/PRIORITY_A_HUMAN_REVIEW.md`
- Priority B (Hardware & Knowledge): `docs/memory/bulk_chatgpt_inheritance/PRIORITY_B_KNOWLEDGE_REVIEW.md`
- Sensitive Review Quarantine: `docs/memory/bulk_chatgpt_inheritance/SENSITIVE_REVIEW.md`
- Production Receipt: `docs/memory/bulk_chatgpt_inheritance/BULK_CHATGPT_INHERITANCE_RECEIPT.md`

## 6. Final Status & Phase Recommendation

**STATUS:** **PASS**  
**RECOMMENDATION:** **`REVIEW_CHATGPT_RESULTS`**  

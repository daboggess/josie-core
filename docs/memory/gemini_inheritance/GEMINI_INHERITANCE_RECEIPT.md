# Production Build Receipt: Historical Gemini Archive Inheritance

**Milestone:** Production Gemini Historical Ingestion, Mining & Replay  
**Repository:** `daboggess/josie-core` (`D:\Josie`)  
**Branch:** `reconcile/live-work-20260917`  
**Date:** 2026-10-04  
**Extractor Engine:** `LocalModelClaimExtractor(qwen3:14b)` on local Ollama (`http://127.0.0.1:11434`)  
**Database:** `data/josie.db` (Verified Pre-Run Backup: `data/backups/josie_pre_gemini_20261004_224623.db`)  
**Master Manifest:** `docs/memory/gemini_inheritance/manifests/master_gemini_manifest.json`  
**Units Completed:** 20 / 20 Units (100%)  
**Canonical Invariant Status:** Strictly 10 before -> strictly 10 after (`canonical_effect=1`)  
**Candidate Approvals Created:** Exactly 0 (`approved_by=NULL`, `reviewed_at=NULL`)  
**Zero Cloud Inference:** 100% local GPU execution  
**Final Verdict:** **PASS**  

---

## 1. Corpus Reconciliation Audit

- **Total Ingested Gemini Conversations in Corpus:** 990
- **Total Ingested Gemini Messages in Database:** 5,108
- **Total User Messages Analyzed:** 2,588
- **Unaccounted Conversations:** **0** (Exact 100% corpus reconciliation: PASS)

## 2. Extraction Funnel Cumulative Totals

- **Source Conversations Processed:** 990
- **Textual Messages Processed:** 4,985
- **User Messages Processed:** 2,588
- **Raw Model Proposals:** 201
- **Authority / Epistemic / Entailment Rejections:** 12
- **Transient / Noise Suppressed:** 33
- **Historical Only Routed:** 30
- **Personal Candidates:** 75
- **Hardware State Candidates:** 34
- **Project Architecture Candidates:** 10
- **Runbook / Procedure Candidates:** 6
- **Extraction Errors:** 0
- **Malformed Source Problems:** 15

## 3. Canonical & Safety Invariant Audit

- **Canonical Claims Count Before Gemini Extraction:** 10
- **Canonical Claims Count After Gemini Extraction:** **10** (Invariant Strictly Preserved: PASS)
- **Total Candidate Claims in Database:** 726
- **Total Provenance Evidence Links:** 777
- **Candidates with `approved_by` set:** **0** (Human-only authority preserved: PASS)
- **Candidates with `canonical_effect = 1`:** **0** (Zero automatic promotion: PASS)
- **Replay Idempotency Verification:** **PASS** (Zero duplicate records on re-staging across all units)

## 4. Final Status & Phase Recommendation

**STATUS:** **PASS**  
**RECOMMENDATION:** **`REVIEW_CROSS_SOURCE_RESULTS`**  
